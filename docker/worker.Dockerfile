FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY fraudlatch ./fraudlatch
COPY scripts ./scripts
RUN python -m pip install --no-cache-dir .
USER app
CMD ["python", "-m", "fraudlatch.worker"]
