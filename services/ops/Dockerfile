FROM python:3.12-slim
RUN pip install --no-cache-dir uv==0.5.31
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 TZ=Europe/Moscow
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY ops ./ops
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 ops && mkdir -p /app/exports && chown ops /app/exports
USER ops
# Сначала схема ops до последней версии, потом воркер.
CMD ["sh", "-c", "alembic upgrade head && python -m ops.worker"]
