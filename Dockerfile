FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    ORBIT_DATABASE=/app/instance/orbit.db \
    ORBIT_MODEL_DIR=/app/artifacts/models \
    ORBIT_DEMO_DATA=/app/data/demo/synthetic_orbit_users.csv

WORKDIR /app

RUN addgroup --system orbit && adduser --system --ingroup orbit orbit

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/instance && chown -R orbit:orbit /app/instance

USER orbit
EXPOSE 5000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 4 --timeout 60 run:app"]
