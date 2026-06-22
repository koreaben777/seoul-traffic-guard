FROM python:3.13-slim

ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY server.py ./

EXPOSE 8000
CMD ["python", "server.py"]
