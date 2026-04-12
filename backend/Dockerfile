
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends     ffmpeg     fonts-dejavu-core     libnss3     libatk1.0-0     libatk-bridge2.0-0     libcups2     libdrm2     libxkbcommon0     libxcomposite1     libxdamage1     libxfixes3     libxrandr2     libgbm1     libasound2     libpango-1.0-0     libcairo2     libx11-xcb1     libxshmfence1     && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade "pip<26" "setuptools<81" "wheel<0.46" \
    && python -c "import pkg_resources; print('pkg_resources ok')" \
    && pip install --no-cache-dir --no-build-isolation -r /app/requirements.txt \
    && playwright install chromium

COPY app /app/app
COPY static /app/static

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
