FROM python:3.12-slim

WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python API (sans GUI Tkinter)
COPY requirements.api.txt .
RUN pip install --no-cache-dir -r requirements.api.txt

# Code source
COPY core/ ./core/
COPY run_api.py .
COPY config.example.yaml ./config.yaml

# Dossiers persistants
RUN mkdir -p data/attachments logs

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')"

CMD ["python", "run_api.py"]
