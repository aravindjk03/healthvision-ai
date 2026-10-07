# HealthVision AI — container image (for a private server / edge box; see docs/14 §5).
# V1 is designed as a local, single-device app. If you expose this container on a network,
# put it behind HTTPS and restrict access — see "Deploying" in the README.
FROM node:20-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HEALTHVISION_ROOT=/app
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgles2 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ backend/
RUN pip install --no-cache-dir ./backend
COPY config/ config/
COPY models/registry.yaml models/registry.yaml
COPY tools/ tools/
RUN python tools/fetch_models.py
COPY --from=web /src/frontend/dist frontend/dist
COPY deploy/healthvision.container.yaml config/healthvision.yaml
RUN useradd --create-home hv && mkdir -p /app/data && chown -R hv /app/data
USER hv
VOLUME ["/app/data"]
EXPOSE 8600
# HEALTHVISION_KEK (base64, 32 bytes) must be supplied as a secret — see README.
CMD ["python", "-m", "healthvision.main"]
