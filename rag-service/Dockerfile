FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    ANONYMIZED_TELEMETRY=False \
    FASTEMBED_CACHE_PATH=/opt/fastembed

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Download both ONNX models at build time, so a cold start does not re-download them
RUN python -c "from app.onnx_models import OnnxEmbeddings, OnnxReranker; OnnxEmbeddings(); OnnxReranker()"

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]