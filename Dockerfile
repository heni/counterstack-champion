FROM python:3.12-alpine

WORKDIR /app
COPY src/champion /app/champion

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["python", "-m", "champion"]
