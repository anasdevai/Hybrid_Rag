FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY rag-chatbot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules from parent context
COPY embeddings/ ./embeddings/
COPY retrieval/  ./retrieval/
COPY chain/      ./chain/
COPY rag-chatbot/main.py ./main.py

ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
