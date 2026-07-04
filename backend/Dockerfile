FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the faster-whisper model so the first transcription job doesn't
# have to fetch it at runtime. Adjust the model name if YTF_WHISPER_MODEL changes.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', compute_type='int8')"

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
