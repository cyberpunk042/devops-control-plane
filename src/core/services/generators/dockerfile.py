"""
Dockerfile generator — produce a Dockerfile from detected stack info.

Uses stack name and project structure to generate an appropriate
multi-stage Dockerfile with best-practice defaults.
"""

from __future__ import annotations

from pathlib import Path

from src.core.models.template import GeneratedFile


# ── Stack → Dockerfile mappings ─────────────────────────────────


_PYTHON_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies first for layer caching
COPY pyproject.toml requirements*.txt ./
RUN pip install --no-cache-dir --upgrade pip \\
    && pip install --no-cache-dir -r requirements.txt 2>/dev/null \\
    || pip install --no-cache-dir .

COPY . .

# ── Runtime stage ───────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 app \\
    && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

USER app

EXPOSE 8000

CMD ["python", "-m", "src.main"]
"""

_NODE_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first for layer caching
COPY package*.json ./
RUN npm ci --production=false

COPY . .
RUN npm run build 2>/dev/null || true

# ── Runtime stage ───────────────────────────────────────────────
FROM node:20-alpine

WORKDIR /app

# Create non-root user
RUN addgroup -g 1000 app && adduser -u 1000 -G app -s /bin/sh -D app

COPY --from=builder /app /app

USER app

EXPOSE 3000

CMD ["node", "index.js"]
"""

_GO_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Download dependencies first for layer caching
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/server ./...

# ── Runtime stage ───────────────────────────────────────────────
FROM alpine:3.19

WORKDIR /app

# Create non-root user
RUN addgroup -g 1000 app && adduser -u 1000 -G app -s /bin/sh -D app

COPY --from=builder /app/server /app/server

USER app

EXPOSE 8080

CMD ["/app/server"]
"""

_RUST_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM rust:1.77-slim AS builder

WORKDIR /app

# Cache dependencies by building a dummy project first
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs \\
    && cargo build --release \\
    && rm -rf src

COPY . .
RUN cargo build --release

# ── Runtime stage ───────────────────────────────────────────────
FROM debian:bookworm-slim

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 app \\
    && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /app/target/release/app /app/app

USER app

EXPOSE 8080

CMD ["/app/app"]
"""

_TYPESCRIPT_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json tsconfig*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Runtime stage ───────────────────────────────────────────────
FROM node:20-alpine

WORKDIR /app

RUN addgroup -g 1000 app && adduser -u 1000 -G app -s /bin/sh -D app

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

USER app

EXPOSE 3000

CMD ["node", "dist/index.js"]
"""

_JAVA_MAVEN_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /app

COPY pom.xml .
RUN mvn dependency:resolve -q

COPY . .
RUN mvn package -DskipTests -q

# ── Runtime stage ───────────────────────────────────────────────
FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

RUN addgroup -g 1000 app && adduser -u 1000 -G app -s /bin/sh -D app

COPY --from=builder /app/target/*.jar /app/app.jar

USER app

EXPOSE 8080

CMD ["java", "-jar", "/app/app.jar"]
"""

_JAVA_GRADLE_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM gradle:8-jdk21 AS builder

WORKDIR /app

COPY build.gradle* settings.gradle* gradle* ./
RUN gradle dependencies --no-daemon -q 2>/dev/null || true

COPY . .
RUN gradle build -x test --no-daemon -q

# ── Runtime stage ───────────────────────────────────────────────
FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

RUN addgroup -g 1000 app && adduser -u 1000 -G app -s /bin/sh -D app

COPY --from=builder /app/build/libs/*.jar /app/app.jar

USER app

EXPOSE 8080

CMD ["java", "-jar", "/app/app.jar"]
"""

_DOTNET_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS builder

WORKDIR /app

COPY *.csproj *.sln ./
RUN dotnet restore

COPY . .
RUN dotnet publish -c Release -o /app/publish

# ── Runtime stage ───────────────────────────────────────────────
FROM mcr.microsoft.com/dotnet/aspnet:8.0

WORKDIR /app

RUN groupadd --gid 1000 app \\
    && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /app/publish .

USER app

EXPOSE 8080

CMD ["dotnet", "App.dll"]
"""

_ELIXIR_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM elixir:1.16-alpine AS builder

ENV MIX_ENV=prod

WORKDIR /app

RUN mix local.hex --force && mix local.rebar --force

COPY mix.exs mix.lock ./
RUN mix deps.get --only prod && mix deps.compile

COPY . .
RUN mix release

# ── Runtime stage ───────────────────────────────────────────────
FROM alpine:3.19

WORKDIR /app

RUN addgroup -g 1000 app && adduser -u 1000 -G app -s /bin/sh -D app \\
    && apk add --no-cache libstdc++ openssl ncurses-libs

COPY --from=builder /app/_build/prod/rel/app ./

USER app

EXPOSE 4000

CMD ["bin/app", "start"]
"""

_RUBY_DOCKERFILE = """\
# ── Build stage ─────────────────────────────────────────────────
FROM ruby:3.3-slim AS builder

WORKDIR /app

COPY Gemfile Gemfile.lock ./
RUN bundle install --deployment --without development test

COPY . .

# ── Runtime stage ───────────────────────────────────────────────
FROM ruby:3.3-slim

WORKDIR /app

RUN groupadd --gid 1000 app \\
    && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /app /app

USER app

EXPOSE 3000

CMD ["bundle", "exec", "ruby", "app.rb"]
"""

# Map stack names (and prefixes) to Dockerfile templates
_STACK_TEMPLATES: dict[str, str] = {
    "python": _PYTHON_DOCKERFILE,
    "node": _NODE_DOCKERFILE,
    "typescript": _TYPESCRIPT_DOCKERFILE,
    "go": _GO_DOCKERFILE,
    "rust": _RUST_DOCKERFILE,
    "java-maven": _JAVA_MAVEN_DOCKERFILE,
    "java-gradle": _JAVA_GRADLE_DOCKERFILE,
    "dotnet": _DOTNET_DOCKERFILE,
    "elixir": _ELIXIR_DOCKERFILE,
    "ruby": _RUBY_DOCKERFILE,
}


def _resolve_template(stack_name: str) -> str | None:
    """Match a stack name to a Dockerfile template.

    Tries exact match first, then longest prefix match
    (e.g. ``python-flask`` matches ``python``).
    """
    if stack_name in _STACK_TEMPLATES:
        return _STACK_TEMPLATES[stack_name]

    best: str | None = None
    best_len = 0
    for prefix, tmpl in _STACK_TEMPLATES.items():
        if stack_name.startswith(prefix + "-") and len(prefix) > best_len:
            best = tmpl
            best_len = len(prefix)
    return best


# ── Public API ──────────────────────────────────────────────────


def generate_dockerfile(
    project_root: Path,
    stack_name: str,
    *,
    output_path: str = "Dockerfile",
) -> GeneratedFile | None:
    """Generate a Dockerfile for the given stack.

    Args:
        project_root: Project root (used for existence checks).
        stack_name: Detected or declared stack name.
        output_path: Relative path for the Dockerfile.

    Returns:
        GeneratedFile or None if no template matches the stack.
    """
    template = _resolve_template(stack_name)
    if template is None:
        return None

    return GeneratedFile(
        path=output_path,
        content=template,
        overwrite=False,
        reason=f"Generated Dockerfile for {stack_name} stack",
    )


def supported_stacks() -> list[str]:
    """Return stack names with Dockerfile templates available."""
    return sorted(_STACK_TEMPLATES.keys())
