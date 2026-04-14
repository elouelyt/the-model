# Tennis AI Prediction API — Cloud Run container
#
# Build:  docker build -t tennis-ai-api .
# Run:    docker run --env-file .env -e TENNIS_API_KEY=yourkey -p 8080:8080 tennis-ai-api

FROM python:3.12-slim

# Keeps Python from buffering stdout/stderr so logs appear in Cloud Logging immediately
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first — separate layer so it's cached on rebuilds
# when only source code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the code the API needs — nothing else enters the image
COPY api/      api/
COPY src/      src/
COPY config.yaml .

# Cloud Run injects $PORT (always 8080 in practice); honour it explicitly
# so the container also works in other environments
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
