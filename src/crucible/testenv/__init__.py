"""Local test environment: a deliberately-vulnerable chatbot served as a real web
app, so Crucible's browser adapter can be exercised end-to-end with no API key."""

from .webapp import serve_background

__all__ = ["serve_background"]
