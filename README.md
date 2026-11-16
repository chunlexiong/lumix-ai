# Lumix AI

The Lumix AI marketing site, built with Django and Wagtail. The homepage introduces the learning approach, gives families an overview of course paths, and includes a parent-focused section. The hero copy and introduction are editable in Wagtail.

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ for the site. To edit the homepage in Wagtail, create an admin account with `python manage.py createsuperuser`, then visit `/admin/`.

## Deployment notes

Vercel supports Django applications. Before deploying an editable Wagtail site, configure a persistent PostgreSQL database and durable media storage; Vercel Functions have a read-only filesystem apart from temporary `/tmp` storage. The generated Dockerfile is included as a starting point for a later VPS deployment.
