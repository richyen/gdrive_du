# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code and web assets.
COPY gdrive_du/ ./gdrive_du/
COPY templates/ ./templates/
COPY static/ ./static/

# credentials.json / token.json are secrets: mount them at runtime instead of
# baking them into the image (see docker-compose.yml).
ENV GDRIVE_DU_CREDENTIALS=/app/secrets/credentials.json \
    GDRIVE_DU_TOKEN=/app/secrets/token.json

EXPOSE 5000

CMD ["python", "-m", "gdrive_du.web", "--host", "0.0.0.0", "--port", "5000"]
