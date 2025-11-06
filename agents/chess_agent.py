# agents/chess_agent.py
import chess
import chess.svg
from uuid import uuid4
from typing import List, Optional
from datetime import datetime
import asyncio
from io import BytesIO
import os
import tempfile
import cairosvg

from models.a2a import (
    A2AMessage, TaskResult, TaskStatus, Artifact,
    MessagePart, MessageConfiguration
)


class ChessAgent:
    def __init__(self, engine_path: str):
        """
        A lightweight chess-playing agent that uses Stockfish
        for AI moves and stores board images locally.
        """
        self.engine_path = engine_path
        self.boards = {}  # Track active boards by context_id

    async def process_messages(
        self,
        messages: List[A2AMessage],
        context_id: Optional[str] = None,
        task_id: Optional[str] = None,
        config: Optional[MessageConfiguration] = None
    ) -> TaskResult:
        """Process incoming messages and generate chess moves"""

        # Generate IDs if not provided
        context_id = context_id or str(uuid4())
        task_id = task_id or str(uuid4())

        # Get or create board for this context
        board = self.boards.get(context_id, chess.Board())

        # Extract last user message
        user_message = messages[-1] if messages else None
        if not user_message:
            raise ValueError("No message provided")

        # Extract move text
        move_text = ""
        for part in user_message.parts:
            if part.kind == "text":
                move_text = part.text.strip()
                break

        # Apply user's move
        try:
            move = board.parse_san(move_text)
            board.push(move)
        except Exception:
            raise ValueError(f"Invalid move: {move_text}")

        # Save updated board state
        self.boards[context_id] = board

        # Generate AI move using Stockfish (fallback: random legal move)
        ai_move = await self._get_stockfish_move(board)
        if ai_move:
            ai_move_san = board.san(ai_move)
            board.push(ai_move)            
        else:
            ai_move_san = "No legal moves available"

        # Generate board visualization and save locally
        board_svg = chess.svg.board(board)
        board_url = await self._save_board_image(board_svg, context_id, task_id)

        # Build response message
        response_text = f"I played {ai_move_san}"
        if board.is_checkmate():
            response_text += " - Checkmate!"
        elif board.is_check():
            response_text += " - Check!"

        response_message = A2AMessage(
            role="agent",
            parts=[MessagePart(kind="text", text=response_text)],
            taskId=task_id
        )

        # Build artifacts (move + board)
        artifacts = [
            Artifact(
                name="move",
                parts=[MessagePart(kind="text", text=ai_move_san)]
            ),
            Artifact(
                name="board",
                parts=[MessagePart(kind="file", file_url=board_url)]
            )
        ]

        # Build history
        history = messages + [response_message]

        # Determine state
        state = "input-required" if not board.is_game_over() else "completed"

        return TaskResult(
            id=task_id,
            contextId=context_id,
            status=TaskStatus(
                state=state,
                message=response_message
            ),
            artifacts=artifacts,
            history=history
        )

    async def _get_stockfish_move(self, board: chess.Board) -> Optional[chess.Move]:
        """Get best move from Stockfish engine"""
        try:
            process = await asyncio.create_subprocess_exec(
                self.engine_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            commands = [
                "uci\n",
                "isready\n",
                f"position fen {board.fen()}\n",
                "go movetime 1000\n"
            ]

            stdout, _ = await process.communicate("".join(commands).encode())
            output = stdout.decode()

            for line in output.split("\n"):
                if line.startswith("bestmove"):
                    move_uci = line.split()[1]
                    return chess.Move.from_uci(move_uci)

            return None
        except FileNotFoundError:
            print("Stockfish binary not found, using random legal move.")
            legal_moves = list(board.legal_moves)
            return legal_moves[0] if legal_moves else None
        except Exception as e:
            print(f"Stockfish error: {e}")
            legal_moves = list(board.legal_moves)
            return legal_moves[0] if legal_moves else None

    async def _save_board_image(
        self,
        svg_content: str,
        context_id: str,
        task_id: str
    ) -> str:
        """Save board image locally and return file:// URL"""
        try:
            png_data = cairosvg.svg2png(bytestring=svg_content.encode())

            # Save to /tmp (Render has ephemeral storage)
            tmp_dir = tempfile.gettempdir()
            file_path = os.path.join(tmp_dir, f"{context_id}-{task_id}.png")

            with open(file_path, "wb") as f:
                f.write(png_data)

            return f"file://{file_path}"
        except Exception as e:
            print(f"Image save error: {e}")
            return ""

    async def cleanup(self):
        """Cleanup resources"""
        self.boards.clear()
