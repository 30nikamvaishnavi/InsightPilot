FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
RUN mkdir -p /app/data/uploads /app/traces && chown -R appuser:appuser /app/data/uploads /app/traces
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/health', timeout=2)" || exit 1
CMD ["sh", "-c", "exec uvicorn insightpilot.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
