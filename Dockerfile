FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
RUN useradd -r -u 10001 botuser && mkdir /data && chown botuser /data
USER botuser
ENV DB_PATH=/data/bot.sqlite3
VOLUME /data
CMD ["python", "-m", "bot.main"]
