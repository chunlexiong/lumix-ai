FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=lumix_ai.settings.production \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libjpeg62-turbo libwebp7 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app \
    && adduser --system --ingroup app app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=app:app . .
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app/staticfiles /app/media

USER app

# Build the immutable, hashed static assets without requiring the runtime secrets.
RUN DJANGO_SECRET_KEY=build-only-secret \
    DJANGO_ALLOWED_HOSTS=localhost \
    POSTGRES_DB=build \
    POSTGRES_USER=build \
    POSTGRES_PASSWORD=build \
    POSTGRES_HOST=localhost \
    POSTGRES_PORT=5432 \
    python manage.py collectstatic --noinput --clear

EXPOSE 8000

CMD ["gunicorn", "lumix_ai.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
