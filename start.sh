#!/bin/bash
cd /app/rag-service
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
cd /app/server
node src/index.js &
# if either process dies, stop the container so the host restarts it
wait -n
exit 1
