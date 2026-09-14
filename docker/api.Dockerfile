FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY fraudlatch ./fraudlatch
COPY scripts ./scripts
RUN python -m pip install --no-cache-dir .
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "fraudlatch.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
