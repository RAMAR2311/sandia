"""Punto de entrada para Gunicorn: ``gunicorn "wsgi:app"`` o ``gunicorn "app:create_app()"``."""

from app import create_app

app = create_app()
