# Stage 1: build the React client
FROM node:22-slim AS web
WORKDIR /build/client
COPY client/package*.json ./
RUN npm ci
COPY client ./
RUN npm run build

# Stage 2: install the Express server's dependencies
FROM node:22-slim AS api
WORKDIR /build/server
COPY server/package*.json ./
RUN npm ci --omit=dev
COPY server ./

# Final image: Python + the Node binary, one container, one public port
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=api /usr/local/bin/node /usr/local/bin/node

ENV PYTHONUNBUFFERED=1 \
    ANONYMIZED_TELEMETRY=False \
    MALLOC_ARENA_MAX=2 \
    MALLOC_TRIM_THRESHOLD_=65536 \
    OMP_NUM_THREADS=1 \
    EMBEDDER=gemini \
    RERANKER=jina \
    NODE_ENV=production

WORKDIR /app/rag-service
COPY rag-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY rag-service/app ./app

COPY --from=api /build/server /app/server
COPY --from=web /build/client/dist /app/client/dist
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 10000
CMD ["/app/start.sh"]
