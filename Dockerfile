FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/ /app/
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home app && mkdir -p /data/storage && chown app:app /data/storage
# The slim image has no system time zone data; fail the build if the tzdata package is missing.
RUN python -c "from zoneinfo import ZoneInfo; ZoneInfo('UTC'); ZoneInfo('Asia/Seoul')"
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
