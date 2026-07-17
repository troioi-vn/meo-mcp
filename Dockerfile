FROM python:3.12-slim AS builder
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS final
RUN useradd --system --uid 10001 mcp
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini
USER mcp
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
EXPOSE 8020
CMD ["uvicorn", "meo_mcp.main:app", "--host", "0.0.0.0", "--port", "8020", "--proxy-headers", "--no-access-log"]
