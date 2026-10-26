# Stage 1: Build frontend
FROM node:20-alpine3.19 AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Install Python dependencies
FROM python:3.12-slim-bookworm AS builder
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Stage 3: Production runner
FROM python:3.12-slim-bookworm AS runner
WORKDIR /app

RUN groupadd --system --gid 1001 appgroup && \
    useradd --system --uid 1001 --gid appgroup --no-create-home appuser

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/app ./app
COPY --from=builder /app/run.py ./
COPY --from=builder /app/requirements.txt ./
COPY --from=frontend-builder /frontend/dist ./frontend/dist

RUN mkdir -p /data && chown appuser:appgroup /data

USER appuser
EXPOSE 5000
ENV PORT=5000
ENV HOST=0.0.0.0
ENV DATA_DIR=/data
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "run:app"]
