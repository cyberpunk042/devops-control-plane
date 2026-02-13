"""
Library knowledge base — curated catalog of popular packages.

Maps library names → category, type, and ecosystem so the audit engine
can automatically classify dependencies without needing external APIs.

Categories:
    framework    — web/app frameworks (Flask, Express, Django, …)
    orm          — object-relational / object-document mappers
    client       — external service clients (Redis, Kafka, AWS, …)
    database     — database drivers / connectors
    testing      — test frameworks and utilities
    typing       — type checkers, stubs
    logging      — logging / observability
    security     — auth, crypto, scanning
    serialization— JSON, protobuf, msgpack, …
    http         — HTTP clients and utilities
    cli          — command-line frameworks
    utility      — general purpose libraries
    build        — build tools, bundlers, compilers
    devtool      — linters, formatters, dev utilities
"""

from __future__ import annotations

from typing import TypedDict


class LibraryInfo(TypedDict, total=False):
    category: str               # framework | orm | client | …
    type: str                   # web | relational | cache | …
    ecosystem: str              # python | node | go | rust | …
    description: str            # short human-readable label
    service: str                # logical service identity (Redis, PostgreSQL, AWS, …)


# ── Service inference ───────────────────────────────────────────
#
# Rather than hand-editing 300+ entries, we infer the `service`
# field from `type` + `description` at lookup time.  Manual
# overrides below take precedence.

_SERVICE_BY_TYPE: dict[str, str] = {
    "cache/store": "Redis",
    "message-broker": "Kafka",          # default, overridden per-lib below
    "task-queue": "Redis",              # most task queues are backed by Redis
    "cloud-aws": "AWS",
    "cloud-gcp": "Google Cloud",
    "cloud-azure": "Azure",
    "search": "Elasticsearch",
    "object-storage": "S3",
    "payment": "Stripe",
    "rpc": "gRPC",
    "realtime": "WebSocket",
    "error-tracking": "Sentry",
    "metrics": "Prometheus",
    "tracing": "OpenTelemetry",
}

# Per-library overrides where the type alone isn't enough
_SERVICE_OVERRIDE: dict[str, str] = {
    # Database drivers → actual database
    "psycopg2": "PostgreSQL",
    "psycopg2-binary": "PostgreSQL",
    "psycopg": "PostgreSQL",
    "asyncpg": "PostgreSQL",
    "pg": "PostgreSQL",
    "github.com/lib/pq": "PostgreSQL",
    "github.com/jackc/pgx": "PostgreSQL",
    "mysqlclient": "MySQL",
    "pymysql": "MySQL",
    "mysql2": "MySQL",
    "pymongo": "MongoDB",
    "motor": "MongoDB",
    "mongoengine": "MongoDB",
    "beanie": "MongoDB",
    "mongoose": "MongoDB",
    "go.mongodb.org/mongo-driver": "MongoDB",
    "sqlite3": "SQLite",
    "better-sqlite3": "SQLite",
    "sqlx": "SQL",
    # ORMs map to "SQL" (generic) since they're multi-DB
    "sqlalchemy": "SQL",
    "django-orm": "SQL",
    "tortoise-orm": "SQL",
    "peewee": "SQL",
    "sqlmodel": "SQL",
    "prisma": "SQL",
    "@prisma/client": "SQL",
    "typeorm": "SQL",
    "sequelize": "SQL",
    "knex": "SQL",
    "drizzle-orm": "SQL",
    "gorm.io/gorm": "SQL",
    "diesel": "SQL",
    "sea-orm": "SQL",
    "alembic": "SQL",
    # Message broker specifics
    "pika": "RabbitMQ",
    "aio-pika": "RabbitMQ",
    "kombu": "RabbitMQ",
    "amqplib": "RabbitMQ",
    "github.com/rabbitmq/amqp091-go": "RabbitMQ",
    "kafka-python": "Kafka",
    "confluent-kafka": "Kafka",
    "kafkajs": "Kafka",
    "github.com/segmentio/kafka-go": "Kafka",
    "rdkafka": "Kafka",
    # Communication
    "twilio": "Twilio",
    "sendgrid": "SendGrid",
    "slack-sdk": "Slack",
    # Specific AWS packages
    "@aws-sdk/client-s3": "AWS S3",
}


def _infer_service(key: str, info: LibraryInfo) -> str | None:
    """Infer the logical service identity for a library entry."""
    # Manual override first
    svc = _SERVICE_OVERRIDE.get(key)
    if svc:
        return svc
    # Auto-infer from type
    lib_type = info.get("type", "")
    svc = _SERVICE_BY_TYPE.get(lib_type)
    if svc:
        return svc
    # Clients with type "email" → service from description
    if info.get("category") in ("client", "database"):
        return info.get("description", "").split(" ")[0]  # e.g., "Redis client" → "Redis"
    return None


# ── The catalog ─────────────────────────────────────────────────
#
# Keys are normalized (lowercase, underscores → hyphens).
# Lookup should normalize the query the same way.

CATALOG: dict[str, LibraryInfo] = {
    # ═══════════════════════════════════════════════════════════
    #  Python — Frameworks
    # ═══════════════════════════════════════════════════════════
    "flask": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Micro web framework"},
    "django": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Full-stack web framework"},
    "fastapi": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Modern async API framework"},
    "starlette": {"category": "framework", "type": "web", "ecosystem": "python", "description": "ASGI framework/toolkit"},
    "tornado": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Async web framework"},
    "sanic": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Async web framework"},
    "bottle": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Micro web framework"},
    "falcon": {"category": "framework", "type": "web", "ecosystem": "python", "description": "REST API framework"},
    "pyramid": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Web framework"},
    "aiohttp": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Async HTTP client/server"},
    "quart": {"category": "framework", "type": "web", "ecosystem": "python", "description": "Async Flask-like framework"},
    "litestar": {"category": "framework", "type": "web", "ecosystem": "python", "description": "High-performance API framework"},
    "streamlit": {"category": "framework", "type": "dashboard", "ecosystem": "python", "description": "Data app framework"},
    "gradio": {"category": "framework", "type": "dashboard", "ecosystem": "python", "description": "ML demo app framework"},
    "dash": {"category": "framework", "type": "dashboard", "ecosystem": "python", "description": "Plotly dashboard framework"},
    "nicegui": {"category": "framework", "type": "dashboard", "ecosystem": "python", "description": "Python UI framework"},
    "textual": {"category": "framework", "type": "tui", "ecosystem": "python", "description": "Terminal UI framework"},
    "rich": {"category": "framework", "type": "tui", "ecosystem": "python", "description": "Rich terminal output"},

    # ═══════════════════════════════════════════════════════════
    #  Python — ORMs & Database
    # ═══════════════════════════════════════════════════════════
    "sqlalchemy": {"category": "orm", "type": "relational", "ecosystem": "python", "description": "SQL toolkit and ORM"},
    "django-orm": {"category": "orm", "type": "relational", "ecosystem": "python", "description": "Django built-in ORM"},
    "tortoise-orm": {"category": "orm", "type": "relational", "ecosystem": "python", "description": "Async ORM"},
    "peewee": {"category": "orm", "type": "relational", "ecosystem": "python", "description": "Lightweight ORM"},
    "sqlmodel": {"category": "orm", "type": "relational", "ecosystem": "python", "description": "SQLAlchemy + Pydantic"},
    "mongoengine": {"category": "orm", "type": "document", "ecosystem": "python", "description": "MongoDB ODM"},
    "motor": {"category": "orm", "type": "document", "ecosystem": "python", "description": "Async MongoDB driver"},
    "beanie": {"category": "orm", "type": "document", "ecosystem": "python", "description": "Async MongoDB ODM"},
    "alembic": {"category": "database", "type": "migration", "ecosystem": "python", "description": "SQLAlchemy migrations"},
    "psycopg2": {"category": "database", "type": "driver", "ecosystem": "python", "description": "PostgreSQL adapter"},
    "psycopg2-binary": {"category": "database", "type": "driver", "ecosystem": "python", "description": "PostgreSQL adapter (binary)"},
    "psycopg": {"category": "database", "type": "driver", "ecosystem": "python", "description": "PostgreSQL adapter v3"},
    "asyncpg": {"category": "database", "type": "driver", "ecosystem": "python", "description": "Async PostgreSQL driver"},
    "mysqlclient": {"category": "database", "type": "driver", "ecosystem": "python", "description": "MySQL adapter"},
    "pymysql": {"category": "database", "type": "driver", "ecosystem": "python", "description": "MySQL adapter (pure Python)"},
    "pymongo": {"category": "database", "type": "driver", "ecosystem": "python", "description": "MongoDB driver"},
    "sqlite3": {"category": "database", "type": "driver", "ecosystem": "python", "description": "SQLite (stdlib)"},

    # ═══════════════════════════════════════════════════════════
    #  Python — Clients (external services)
    # ═══════════════════════════════════════════════════════════
    "redis": {"category": "client", "type": "cache/store", "ecosystem": "python", "description": "Redis client"},
    "celery": {"category": "client", "type": "task-queue", "ecosystem": "python", "description": "Distributed task queue"},
    "rq": {"category": "client", "type": "task-queue", "ecosystem": "python", "description": "Simple task queue (Redis)"},
    "dramatiq": {"category": "client", "type": "task-queue", "ecosystem": "python", "description": "Task processing library"},
    "kafka-python": {"category": "client", "type": "message-broker", "ecosystem": "python", "description": "Apache Kafka client"},
    "confluent-kafka": {"category": "client", "type": "message-broker", "ecosystem": "python", "description": "Confluent Kafka client"},
    "pika": {"category": "client", "type": "message-broker", "ecosystem": "python", "description": "RabbitMQ client"},
    "aio-pika": {"category": "client", "type": "message-broker", "ecosystem": "python", "description": "Async RabbitMQ client"},
    "kombu": {"category": "client", "type": "message-broker", "ecosystem": "python", "description": "Messaging library"},
    "boto3": {"category": "client", "type": "cloud-aws", "ecosystem": "python", "description": "AWS SDK"},
    "botocore": {"category": "client", "type": "cloud-aws", "ecosystem": "python", "description": "AWS SDK core"},
    "google-cloud-storage": {"category": "client", "type": "cloud-gcp", "ecosystem": "python", "description": "GCS client"},
    "google-cloud-pubsub": {"category": "client", "type": "cloud-gcp", "ecosystem": "python", "description": "Pub/Sub client"},
    "google-auth": {"category": "client", "type": "cloud-gcp", "ecosystem": "python", "description": "Google auth library"},
    "azure-storage-blob": {"category": "client", "type": "cloud-azure", "ecosystem": "python", "description": "Azure Blob Storage"},
    "azure-identity": {"category": "client", "type": "cloud-azure", "ecosystem": "python", "description": "Azure auth"},
    "elasticsearch": {"category": "client", "type": "search", "ecosystem": "python", "description": "Elasticsearch client"},
    "opensearch-py": {"category": "client", "type": "search", "ecosystem": "python", "description": "OpenSearch client"},
    "minio": {"category": "client", "type": "object-storage", "ecosystem": "python", "description": "MinIO / S3 client"},
    "stripe": {"category": "client", "type": "payment", "ecosystem": "python", "description": "Stripe API client"},
    "twilio": {"category": "client", "type": "communication", "ecosystem": "python", "description": "Twilio API client"},
    "sendgrid": {"category": "client", "type": "email", "ecosystem": "python", "description": "SendGrid email client"},
    "slack-sdk": {"category": "client", "type": "communication", "ecosystem": "python", "description": "Slack API client"},
    "grpcio": {"category": "client", "type": "rpc", "ecosystem": "python", "description": "gRPC framework"},
    "grpcio-tools": {"category": "client", "type": "rpc", "ecosystem": "python", "description": "gRPC code generator"},
    "httpx": {"category": "http", "type": "client", "ecosystem": "python", "description": "Modern HTTP client"},
    "requests": {"category": "http", "type": "client", "ecosystem": "python", "description": "HTTP library"},
    "urllib3": {"category": "http", "type": "client", "ecosystem": "python", "description": "HTTP client (low-level)"},

    # ═══════════════════════════════════════════════════════════
    #  Python — Testing
    # ═══════════════════════════════════════════════════════════
    "pytest": {"category": "testing", "type": "framework", "ecosystem": "python", "description": "Test framework"},
    "pytest-cov": {"category": "testing", "type": "coverage", "ecosystem": "python", "description": "Coverage plugin"},
    "pytest-asyncio": {"category": "testing", "type": "plugin", "ecosystem": "python", "description": "Async test support"},
    "pytest-mock": {"category": "testing", "type": "plugin", "ecosystem": "python", "description": "Mock integration"},
    "coverage": {"category": "testing", "type": "coverage", "ecosystem": "python", "description": "Code coverage"},
    "tox": {"category": "testing", "type": "runner", "ecosystem": "python", "description": "Test automation"},
    "nox": {"category": "testing", "type": "runner", "ecosystem": "python", "description": "Test automation"},
    "hypothesis": {"category": "testing", "type": "property", "ecosystem": "python", "description": "Property-based testing"},
    "faker": {"category": "testing", "type": "data", "ecosystem": "python", "description": "Fake data generator"},
    "factory-boy": {"category": "testing", "type": "data", "ecosystem": "python", "description": "Test fixture factory"},
    "unittest": {"category": "testing", "type": "framework", "ecosystem": "python", "description": "Stdlib test framework"},

    # ═══════════════════════════════════════════════════════════
    #  Python — DevTools
    # ═══════════════════════════════════════════════════════════
    "ruff": {"category": "devtool", "type": "linter", "ecosystem": "python", "description": "Fast linter + formatter"},
    "mypy": {"category": "typing", "type": "checker", "ecosystem": "python", "description": "Static type checker"},
    "pyright": {"category": "typing", "type": "checker", "ecosystem": "python", "description": "Static type checker"},
    "black": {"category": "devtool", "type": "formatter", "ecosystem": "python", "description": "Code formatter"},
    "isort": {"category": "devtool", "type": "formatter", "ecosystem": "python", "description": "Import sorter"},
    "flake8": {"category": "devtool", "type": "linter", "ecosystem": "python", "description": "Style checker"},
    "pylint": {"category": "devtool", "type": "linter", "ecosystem": "python", "description": "Code analyzer"},
    "bandit": {"category": "security", "type": "scanner", "ecosystem": "python", "description": "Security linter"},
    "safety": {"category": "security", "type": "scanner", "ecosystem": "python", "description": "Dependency checker"},
    "pip-audit": {"category": "security", "type": "scanner", "ecosystem": "python", "description": "Vulnerability scanner"},
    "pre-commit": {"category": "devtool", "type": "hooks", "ecosystem": "python", "description": "Git hook manager"},

    # ═══════════════════════════════════════════════════════════
    #  Python — Serialization / Config
    # ═══════════════════════════════════════════════════════════
    "pydantic": {"category": "serialization", "type": "validation", "ecosystem": "python", "description": "Data validation"},
    "pydantic-settings": {"category": "serialization", "type": "config", "ecosystem": "python", "description": "Settings management"},
    "marshmallow": {"category": "serialization", "type": "validation", "ecosystem": "python", "description": "Object serialization"},
    "attrs": {"category": "serialization", "type": "dataclass", "ecosystem": "python", "description": "Class helpers"},
    "msgpack": {"category": "serialization", "type": "binary", "ecosystem": "python", "description": "MessagePack codec"},
    "protobuf": {"category": "serialization", "type": "binary", "ecosystem": "python", "description": "Protocol Buffers"},
    "orjson": {"category": "serialization", "type": "json", "ecosystem": "python", "description": "Fast JSON library"},
    "ujson": {"category": "serialization", "type": "json", "ecosystem": "python", "description": "Ultra JSON"},
    "pyyaml": {"category": "serialization", "type": "yaml", "ecosystem": "python", "description": "YAML parser"},
    "toml": {"category": "serialization", "type": "config", "ecosystem": "python", "description": "TOML parser"},
    "tomli": {"category": "serialization", "type": "config", "ecosystem": "python", "description": "TOML parser"},
    "python-dotenv": {"category": "serialization", "type": "config", "ecosystem": "python", "description": "Dotenv loader"},
    "dynaconf": {"category": "serialization", "type": "config", "ecosystem": "python", "description": "Settings management"},

    # ═══════════════════════════════════════════════════════════
    #  Python — CLI
    # ═══════════════════════════════════════════════════════════
    "click": {"category": "cli", "type": "framework", "ecosystem": "python", "description": "CLI framework"},
    "typer": {"category": "cli", "type": "framework", "ecosystem": "python", "description": "CLI framework (Click+)"},
    "argparse": {"category": "cli", "type": "framework", "ecosystem": "python", "description": "Stdlib CLI parser"},
    "fire": {"category": "cli", "type": "framework", "ecosystem": "python", "description": "Auto CLI generator"},

    # ═══════════════════════════════════════════════════════════
    #  Python — Security / Auth
    # ═══════════════════════════════════════════════════════════
    "cryptography": {"category": "security", "type": "crypto", "ecosystem": "python", "description": "Cryptographic primitives"},
    "pyjwt": {"category": "security", "type": "auth", "ecosystem": "python", "description": "JWT tokens"},
    "python-jose": {"category": "security", "type": "auth", "ecosystem": "python", "description": "JOSE/JWT"},
    "passlib": {"category": "security", "type": "auth", "ecosystem": "python", "description": "Password hashing"},
    "bcrypt": {"category": "security", "type": "auth", "ecosystem": "python", "description": "Bcrypt hashing"},
    "authlib": {"category": "security", "type": "auth", "ecosystem": "python", "description": "OAuth/OIDC library"},
    "oauthlib": {"category": "security", "type": "auth", "ecosystem": "python", "description": "OAuth library"},

    # ═══════════════════════════════════════════════════════════
    #  Python — Logging / Observability
    # ═══════════════════════════════════════════════════════════
    "structlog": {"category": "logging", "type": "structured", "ecosystem": "python", "description": "Structured logging"},
    "loguru": {"category": "logging", "type": "logger", "ecosystem": "python", "description": "Simplified logging"},
    "sentry-sdk": {"category": "logging", "type": "error-tracking", "ecosystem": "python", "description": "Sentry integration"},
    "prometheus-client": {"category": "logging", "type": "metrics", "ecosystem": "python", "description": "Prometheus exporter"},
    "opentelemetry-api": {"category": "logging", "type": "tracing", "ecosystem": "python", "description": "OpenTelemetry API"},
    "opentelemetry-sdk": {"category": "logging", "type": "tracing", "ecosystem": "python", "description": "OpenTelemetry SDK"},

    # ═══════════════════════════════════════════════════════════
    #  Python — Utility
    # ═══════════════════════════════════════════════════════════
    "pillow": {"category": "utility", "type": "image", "ecosystem": "python", "description": "Image processing"},
    "numpy": {"category": "utility", "type": "scientific", "ecosystem": "python", "description": "Numerical computing"},
    "pandas": {"category": "utility", "type": "data", "ecosystem": "python", "description": "Data analysis"},
    "scipy": {"category": "utility", "type": "scientific", "ecosystem": "python", "description": "Scientific computing"},
    "scikit-learn": {"category": "utility", "type": "ml", "ecosystem": "python", "description": "Machine learning"},
    "torch": {"category": "utility", "type": "ml", "ecosystem": "python", "description": "PyTorch deep learning"},
    "tensorflow": {"category": "utility", "type": "ml", "ecosystem": "python", "description": "TensorFlow"},
    "transformers": {"category": "utility", "type": "ml", "ecosystem": "python", "description": "HuggingFace models"},
    "spacy": {"category": "utility", "type": "nlp", "ecosystem": "python", "description": "NLP library"},
    "jinja2": {"category": "utility", "type": "templating", "ecosystem": "python", "description": "Template engine"},
    "mako": {"category": "utility", "type": "templating", "ecosystem": "python", "description": "Template engine"},
    "celery-beat": {"category": "utility", "type": "scheduling", "ecosystem": "python", "description": "Periodic tasks"},
    "apscheduler": {"category": "utility", "type": "scheduling", "ecosystem": "python", "description": "Task scheduler"},
    "watchdog": {"category": "utility", "type": "filesystem", "ecosystem": "python", "description": "File system events"},
    "pathlib": {"category": "utility", "type": "filesystem", "ecosystem": "python", "description": "Path manipulation"},

    # ═══════════════════════════════════════════════════════════
    #  Node — Frameworks
    # ═══════════════════════════════════════════════════════════
    "express": {"category": "framework", "type": "web", "ecosystem": "node", "description": "Minimal web framework"},
    "next": {"category": "framework", "type": "web-ssr", "ecosystem": "node", "description": "React SSR framework"},
    "nuxt": {"category": "framework", "type": "web-ssr", "ecosystem": "node", "description": "Vue SSR framework"},
    "nestjs": {"category": "framework", "type": "web", "ecosystem": "node", "description": "Enterprise framework"},
    "@nestjs/core": {"category": "framework", "type": "web", "ecosystem": "node", "description": "NestJS core"},
    "koa": {"category": "framework", "type": "web", "ecosystem": "node", "description": "Next-gen web framework"},
    "fastify": {"category": "framework", "type": "web", "ecosystem": "node", "description": "Fast web framework"},
    "hapi": {"category": "framework", "type": "web", "ecosystem": "node", "description": "Server framework"},
    "@hapi/hapi": {"category": "framework", "type": "web", "ecosystem": "node", "description": "Server framework"},
    "react": {"category": "framework", "type": "ui", "ecosystem": "node", "description": "UI library"},
    "react-dom": {"category": "framework", "type": "ui", "ecosystem": "node", "description": "React DOM renderer"},
    "vue": {"category": "framework", "type": "ui", "ecosystem": "node", "description": "Progressive UI framework"},
    "svelte": {"category": "framework", "type": "ui", "ecosystem": "node", "description": "Compiled UI framework"},
    "angular": {"category": "framework", "type": "ui", "ecosystem": "node", "description": "Full UI framework"},
    "@angular/core": {"category": "framework", "type": "ui", "ecosystem": "node", "description": "Angular core"},
    "solid-js": {"category": "framework", "type": "ui", "ecosystem": "node", "description": "Reactive UI library"},
    "astro": {"category": "framework", "type": "ssg", "ecosystem": "node", "description": "Content-first framework"},
    "gatsby": {"category": "framework", "type": "ssg", "ecosystem": "node", "description": "React SSG"},
    "remix": {"category": "framework", "type": "web-ssr", "ecosystem": "node", "description": "Full-stack React framework"},
    "electron": {"category": "framework", "type": "desktop", "ecosystem": "node", "description": "Desktop app framework"},
    "tauri": {"category": "framework", "type": "desktop", "ecosystem": "node", "description": "Desktop app framework"},

    # ═══════════════════════════════════════════════════════════
    #  Node — ORMs & Database
    # ═══════════════════════════════════════════════════════════
    "prisma": {"category": "orm", "type": "relational", "ecosystem": "node", "description": "Modern ORM"},
    "@prisma/client": {"category": "orm", "type": "relational", "ecosystem": "node", "description": "Prisma client"},
    "typeorm": {"category": "orm", "type": "relational", "ecosystem": "node", "description": "TypeScript ORM"},
    "sequelize": {"category": "orm", "type": "relational", "ecosystem": "node", "description": "SQL ORM"},
    "knex": {"category": "database", "type": "query-builder", "ecosystem": "node", "description": "SQL query builder"},
    "drizzle-orm": {"category": "orm", "type": "relational", "ecosystem": "node", "description": "TypeScript ORM"},
    "mongoose": {"category": "orm", "type": "document", "ecosystem": "node", "description": "MongoDB ODM"},
    "pg": {"category": "database", "type": "driver", "ecosystem": "node", "description": "PostgreSQL driver"},
    "mysql2": {"category": "database", "type": "driver", "ecosystem": "node", "description": "MySQL driver"},
    "better-sqlite3": {"category": "database", "type": "driver", "ecosystem": "node", "description": "SQLite driver"},

    # ═══════════════════════════════════════════════════════════
    #  Node — Clients
    # ═══════════════════════════════════════════════════════════
    "ioredis": {"category": "client", "type": "cache/store", "ecosystem": "node", "description": "Redis client"},
    "redis": {"category": "client", "type": "cache/store", "ecosystem": "node", "description": "Redis client"},
    "kafkajs": {"category": "client", "type": "message-broker", "ecosystem": "node", "description": "Kafka client"},
    "amqplib": {"category": "client", "type": "message-broker", "ecosystem": "node", "description": "RabbitMQ client"},
    "bullmq": {"category": "client", "type": "task-queue", "ecosystem": "node", "description": "Job queue (Redis)"},
    "bull": {"category": "client", "type": "task-queue", "ecosystem": "node", "description": "Job queue (Redis)"},
    "@aws-sdk/client-s3": {"category": "client", "type": "cloud-aws", "ecosystem": "node", "description": "AWS S3 client"},
    "aws-sdk": {"category": "client", "type": "cloud-aws", "ecosystem": "node", "description": "AWS SDK"},
    "@google-cloud/storage": {"category": "client", "type": "cloud-gcp", "ecosystem": "node", "description": "GCS client"},
    "@elastic/elasticsearch": {"category": "client", "type": "search", "ecosystem": "node", "description": "Elasticsearch"},
    "stripe": {"category": "client", "type": "payment", "ecosystem": "node", "description": "Stripe API"},
    "@grpc/grpc-js": {"category": "client", "type": "rpc", "ecosystem": "node", "description": "gRPC framework"},
    "socket.io": {"category": "client", "type": "realtime", "ecosystem": "node", "description": "WebSocket library"},
    "axios": {"category": "http", "type": "client", "ecosystem": "node", "description": "HTTP client"},
    "node-fetch": {"category": "http", "type": "client", "ecosystem": "node", "description": "Fetch polyfill"},
    "got": {"category": "http", "type": "client", "ecosystem": "node", "description": "HTTP client"},

    # ═══════════════════════════════════════════════════════════
    #  Node — Testing
    # ═══════════════════════════════════════════════════════════
    "jest": {"category": "testing", "type": "framework", "ecosystem": "node", "description": "Test framework"},
    "vitest": {"category": "testing", "type": "framework", "ecosystem": "node", "description": "Vite-native testing"},
    "mocha": {"category": "testing", "type": "framework", "ecosystem": "node", "description": "Test framework"},
    "chai": {"category": "testing", "type": "assertion", "ecosystem": "node", "description": "Assertion library"},
    "cypress": {"category": "testing", "type": "e2e", "ecosystem": "node", "description": "E2E testing"},
    "playwright": {"category": "testing", "type": "e2e", "ecosystem": "node", "description": "Browser testing"},
    "@playwright/test": {"category": "testing", "type": "e2e", "ecosystem": "node", "description": "Playwright test runner"},
    "supertest": {"category": "testing", "type": "http", "ecosystem": "node", "description": "HTTP assertions"},
    "storybook": {"category": "testing", "type": "ui", "ecosystem": "node", "description": "UI component testing"},

    # ═══════════════════════════════════════════════════════════
    #  Node — DevTools
    # ═══════════════════════════════════════════════════════════
    "eslint": {"category": "devtool", "type": "linter", "ecosystem": "node", "description": "JS linter"},
    "prettier": {"category": "devtool", "type": "formatter", "ecosystem": "node", "description": "Code formatter"},
    "typescript": {"category": "typing", "type": "language", "ecosystem": "node", "description": "TypeScript compiler"},
    "webpack": {"category": "build", "type": "bundler", "ecosystem": "node", "description": "Module bundler"},
    "vite": {"category": "build", "type": "bundler", "ecosystem": "node", "description": "Fast build tool"},
    "esbuild": {"category": "build", "type": "bundler", "ecosystem": "node", "description": "Fast JS bundler"},
    "rollup": {"category": "build", "type": "bundler", "ecosystem": "node", "description": "Module bundler"},
    "turbo": {"category": "build", "type": "monorepo", "ecosystem": "node", "description": "Monorepo build system"},
    "nx": {"category": "build", "type": "monorepo", "ecosystem": "node", "description": "Monorepo toolkit"},
    "lerna": {"category": "build", "type": "monorepo", "ecosystem": "node", "description": "Monorepo manager"},
    "tailwindcss": {"category": "build", "type": "css", "ecosystem": "node", "description": "Utility CSS framework"},
    "postcss": {"category": "build", "type": "css", "ecosystem": "node", "description": "CSS processor"},
    "sass": {"category": "build", "type": "css", "ecosystem": "node", "description": "CSS preprocessor"},

    # ═══════════════════════════════════════════════════════════
    #  Node — Utility / Serialization
    # ═══════════════════════════════════════════════════════════
    "zod": {"category": "serialization", "type": "validation", "ecosystem": "node", "description": "Schema validation"},
    "joi": {"category": "serialization", "type": "validation", "ecosystem": "node", "description": "Schema validation"},
    "class-validator": {"category": "serialization", "type": "validation", "ecosystem": "node", "description": "Decorator validation"},
    "jsonwebtoken": {"category": "security", "type": "auth", "ecosystem": "node", "description": "JWT tokens"},
    "passport": {"category": "security", "type": "auth", "ecosystem": "node", "description": "Auth middleware"},
    "bcryptjs": {"category": "security", "type": "auth", "ecosystem": "node", "description": "Bcrypt hashing"},
    "helmet": {"category": "security", "type": "middleware", "ecosystem": "node", "description": "Security headers"},
    "cors": {"category": "security", "type": "middleware", "ecosystem": "node", "description": "CORS middleware"},
    "winston": {"category": "logging", "type": "logger", "ecosystem": "node", "description": "Logging library"},
    "pino": {"category": "logging", "type": "logger", "ecosystem": "node", "description": "Fast logger"},
    "dotenv": {"category": "serialization", "type": "config", "ecosystem": "node", "description": "Dotenv loader"},
    "lodash": {"category": "utility", "type": "general", "ecosystem": "node", "description": "Utility library"},
    "dayjs": {"category": "utility", "type": "date", "ecosystem": "node", "description": "Date library"},
    "moment": {"category": "utility", "type": "date", "ecosystem": "node", "description": "Date library (legacy)"},
    "uuid": {"category": "utility", "type": "general", "ecosystem": "node", "description": "UUID generator"},
    "sharp": {"category": "utility", "type": "image", "ecosystem": "node", "description": "Image processing"},

    # ═══════════════════════════════════════════════════════════
    #  Go — Key packages
    # ═══════════════════════════════════════════════════════════
    "github.com/gin-gonic/gin": {"category": "framework", "type": "web", "ecosystem": "go", "description": "Web framework"},
    "github.com/gofiber/fiber": {"category": "framework", "type": "web", "ecosystem": "go", "description": "Express-like framework"},
    "github.com/labstack/echo": {"category": "framework", "type": "web", "ecosystem": "go", "description": "Web framework"},
    "github.com/gorilla/mux": {"category": "framework", "type": "web", "ecosystem": "go", "description": "HTTP router"},
    "gorm.io/gorm": {"category": "orm", "type": "relational", "ecosystem": "go", "description": "ORM"},
    "github.com/go-redis/redis": {"category": "client", "type": "cache/store", "ecosystem": "go", "description": "Redis client"},
    "github.com/segmentio/kafka-go": {"category": "client", "type": "message-broker", "ecosystem": "go", "description": "Kafka client"},
    "github.com/rabbitmq/amqp091-go": {"category": "client", "type": "message-broker", "ecosystem": "go", "description": "RabbitMQ client"},
    "github.com/aws/aws-sdk-go-v2": {"category": "client", "type": "cloud-aws", "ecosystem": "go", "description": "AWS SDK"},
    "google.golang.org/grpc": {"category": "client", "type": "rpc", "ecosystem": "go", "description": "gRPC framework"},
    "github.com/lib/pq": {"category": "database", "type": "driver", "ecosystem": "go", "description": "PostgreSQL driver"},
    "github.com/jackc/pgx": {"category": "database", "type": "driver", "ecosystem": "go", "description": "PostgreSQL driver"},
    "go.mongodb.org/mongo-driver": {"category": "database", "type": "driver", "ecosystem": "go", "description": "MongoDB driver"},

    # ═══════════════════════════════════════════════════════════
    #  Rust — Key crates
    # ═══════════════════════════════════════════════════════════
    "actix-web": {"category": "framework", "type": "web", "ecosystem": "rust", "description": "Web framework"},
    "axum": {"category": "framework", "type": "web", "ecosystem": "rust", "description": "Web framework"},
    "rocket": {"category": "framework", "type": "web", "ecosystem": "rust", "description": "Web framework"},
    "warp": {"category": "framework", "type": "web", "ecosystem": "rust", "description": "Web framework"},
    "diesel": {"category": "orm", "type": "relational", "ecosystem": "rust", "description": "ORM + query builder"},
    "sea-orm": {"category": "orm", "type": "relational", "ecosystem": "rust", "description": "Async ORM"},
    "sqlx": {"category": "database", "type": "driver", "ecosystem": "rust", "description": "Async SQL driver"},
    "tokio": {"category": "utility", "type": "runtime", "ecosystem": "rust", "description": "Async runtime"},
    "serde": {"category": "serialization", "type": "framework", "ecosystem": "rust", "description": "Serialization framework"},
    "serde_json": {"category": "serialization", "type": "json", "ecosystem": "rust", "description": "JSON serialization"},
    "reqwest": {"category": "http", "type": "client", "ecosystem": "rust", "description": "HTTP client"},
    "redis": {"category": "client", "type": "cache/store", "ecosystem": "rust", "description": "Redis client"},
    "rdkafka": {"category": "client", "type": "message-broker", "ecosystem": "rust", "description": "Kafka client"},
    "clap": {"category": "cli", "type": "framework", "ecosystem": "rust", "description": "CLI parser"},
    "tracing": {"category": "logging", "type": "tracing", "ecosystem": "rust", "description": "App instrumentation"},
}


def lookup(name: str) -> LibraryInfo | None:
    """Look up a library by name (case-insensitive, underscore-tolerant).

    Returns a copy with the ``service`` field injected (inferred from
    type/description or the override table).
    """
    key = name.lower().replace("_", "-")
    info = CATALOG.get(key)
    if info is None:
        return None
    # Inject service identity
    enriched: LibraryInfo = {**info}
    svc = _infer_service(key, info)
    if svc:
        enriched["service"] = svc
    return enriched


def classify_batch(names: list[str]) -> dict[str, LibraryInfo | None]:
    """Classify a batch of library names."""
    return {name: lookup(name) for name in names}


def categories_summary(classified: dict[str, LibraryInfo | None]) -> dict[str, int]:
    """Count libraries per category."""
    counts: dict[str, int] = {}
    for info in classified.values():
        if info:
            cat = info["category"]
            counts[cat] = counts.get(cat, 0) + 1
    return counts
