# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY bot ./bot
RUN useradd -r -u 10001 botuser && mkdir -p /data /backups && chown botuser /data /backups
USER botuser
ENV DB_PATH=/data/bot.sqlite3 BACKUP_DIR=/backups WEB_HOST=0.0.0.0 WEB_PORT=8080
VOLUME ["/data", "/backups"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/health', timeout=4)" || exit 1
CMD ["python", "-m", "bot.main"]
