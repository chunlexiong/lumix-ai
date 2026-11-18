# Lumix AI

The Lumix AI marketing site, built with Django and Wagtail. The homepage is a Wagtail page with editable hero fields; most other marketing content is currently written in Django templates.

## Run locally with Python

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ for the site. To edit the homepage in Wagtail, create an admin account with `python manage.py createsuperuser`, then visit `/admin/`.

## Run with Docker

For local development, copy `.env.docker.example` to `.env.docker`, replace the example secret and database password, then run:

```sh
docker compose --env-file .env.docker run --build --rm web python manage.py migrate
docker compose --env-file .env.docker up --build
```

The site is available at http://127.0.0.1:8000/. Create a Wagtail admin user with:

```sh
docker compose --env-file .env.docker exec web python manage.py createsuperuser
```

For a VPS, copy `.env.prod.example` to `.env.prod`, set a generated secret, strong database password, real domain, and ACME email, then build and migrate before starting the stack:

```sh
docker compose --env-file .env.prod -f docker-compose.prod.yml build
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm web python manage.py migrate
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

Caddy terminates HTTPS, proxies requests to Django, and serves Wagtail media from its persistent volume. Point the configured DNS records at the VPS and allow inbound ports 80 and 443. PostgreSQL data also uses a persistent Docker volume. Static assets are collected into the image and served by WhiteNoise.

Do not commit `.env.docker` or `.env.prod`; their local values are ignored by Git.
