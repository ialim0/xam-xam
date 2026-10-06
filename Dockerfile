# Image du bot WhatsApp Xam-Xam (FastAPI + ffmpeg).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    XAMXAM_CACHE_DIR=/cache

# ffmpeg : conversion des notes vocales (OGG Opus) et découpage des audios longs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# Extra « bedrock » : SDK AWS pour le provider LLM Bedrock (déploiement principal).
RUN pip install ".[bedrock]"
# Lexique et données, lus depuis le répertoire de travail.
COPY data ./data

# Utilisateur sans privilèges ; /cache reçoit le bucket Cloud Storage en production.
RUN useradd --create-home --uid 10001 xamxam \
    && mkdir -p /cache && chown xamxam:xamxam /cache
USER xamxam

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn --factory xamxam.whatsapp.app:create_app --host 0.0.0.0 --port ${PORT}"]
