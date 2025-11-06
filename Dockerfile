# Dockerfile
FROM python:3.11-slim

# Install Stockfish and dependencies
RUN apt-get update && apt-get install -y stockfish libcairo2 libpango-1.0-0 libpangocairo-1.0-0 && apt-get clean

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

ENV PORT=5000
ENV CHESS_ENGINE_PATH=/usr/games/stockfish

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
