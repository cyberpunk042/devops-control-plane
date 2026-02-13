# ── Build stage ─────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ── Runtime stage ───────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /app /app

USER app

EXPOSE 8000

CMD ["python", "-m", "src.main"]
