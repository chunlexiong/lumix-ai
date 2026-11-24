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

Wagtail document uploads allow the configured file extensions, including MP4 videos and WebVTT caption files. Set `DOCKER_WAGTAILDOCS_MAX_UPLOAD_SIZE` in `.env.docker` or `.env.prod` to set the per-file limit in bytes; the Compose default is 104857600 (100 MB).

Student project preview screenshots are generated when the Student life page is published and cached in the media volume. The web image includes Playwright and Chromium for this task. If a screenshot cannot be generated, the project URL remains available through its Explore link.

For Student life videos, admins can upload a poster image or leave the poster field empty. When the page is published, the web container uses FFmpeg to extract and cache a frame from videos without a supplied poster. Generated posters are stored in the media volume.

Do not commit `.env.docker` or `.env.prod`; their local values are ignored by Git.

## Enable enquiry emails

Set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` to the values issued by your SMTP provider. Use a sender address the provider has authorised. The visitor's email is set as Reply-To. The destination and the address shown on the Contact page both use `CONTACT_EMAIL`, which defaults to `chenjingsay@gmail.com`.

The Docker configuration defaults to STARTTLS on port 587. For a provider using implicit TLS, set `EMAIL_USE_SSL=true`, `EMAIL_USE_TLS=false`, and the provider's port. Store the SMTP settings in the local `.env.docker` or the production `.env.prod` and recreate the web container to apply them. When running directly with Python, export the same variables before starting Django.

## Family enrolment

Run the database migrations, then use **Enrol** in the site header or **Enrol in this class** on a course card. The family account stores reusable student names and enrolments. Checkout uses the full published class fee in AUD.

Local development offers an explicitly labelled checkout preview without collecting card details or confirming a booking. To use Stripe-hosted Checkout, configure `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and `STRIPE_CHECKOUT_ORIGIN` in the web environment. Register `/enrol/stripe/webhook/` on that origin for Stripe's `checkout.session.completed` event. A test key produces a test receipt only. A live key requires a non-debug site and an HTTPS origin. Recreate the web container after changing these values. Confirm the sale availability and session times in the course catalogue before enabling live payments.
