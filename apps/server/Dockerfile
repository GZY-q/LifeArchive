FROM python:3.12.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv

ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
WORKDIR /app

COPY apps/server/pyproject.toml apps/server/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY apps/server/src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12.14-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

RUN groupadd --gid 10001 life_archive \
    && useradd --uid 10001 --gid life_archive --no-create-home life_archive

COPY --from=builder /app/.venv ./.venv
COPY apps/server/alembic.ini ./alembic.ini
COPY apps/server/alembic ./alembic

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "life_archive.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
