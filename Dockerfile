FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# 루트 requirements.txt는 실험용 torch·transformers까지 깔아서 서버엔 backend 것만 쓴다
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY ai ai
COPY data_pipeline data_pipeline
COPY data/layouts.json data/layouts.json

ENV CARDSYNC_DB_PATH=/data/cardsync.db
EXPOSE 8000
# 작업을 프로세스 안에서 돌리고 SQLite에 저장하므로 워커는 1개만 둔다
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
