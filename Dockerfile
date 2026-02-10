FROM python:3.12-slim AS base

LABEL maintainer="cyberpunk042"
LABEL description="DevOps Control Plane — project automation engine"

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python package
COPY pyproject.toml README.md ./
COPY src/ src/
COPY stacks/ stacks/

RUN pip install --no-cache-dir -e .

# Copy manage.sh
COPY manage.sh ./
RUN chmod +x manage.sh

# Default: run the web dashboard
ENV FLASK_PORT=5000
EXPOSE 5000

ENTRYPOINT ["python", "-m", "src.main"]
CMD ["web", "--host", "0.0.0.0", "--mock"]
