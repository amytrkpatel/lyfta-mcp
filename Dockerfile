FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt && \
    pip install --no-cache-dir --prefix=/install --no-deps .


FROM python:3.11-slim AS runtime

RUN useradd --system --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local

ENV TRANSPORT=http \
    PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import socket; s=socket.create_connection(('localhost',8000),timeout=5); s.close()"

CMD ["python", "-m", "lyfta_mcp.server"]
