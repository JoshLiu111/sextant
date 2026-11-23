"""Entrypoint for Vercel (``main:app``) and local ``uvicorn main:app``."""

from sextant_compute.app import create_app

app = create_app()
