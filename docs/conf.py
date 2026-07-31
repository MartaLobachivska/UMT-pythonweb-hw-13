"""Sphinx configuration for the Contacts API documentation."""
import os
import sys
from pathlib import Path

# Make the project root (containing main.py, crud.py, ...) importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# config.py validates required settings (DATABASE_URL, JWT_SECRET, ...) at
# import time. Provide harmless dummy values so `sphinx-apidoc`/`autodoc`
# can import every module without needing a real .env file.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "docs-build-placeholder")
os.environ.setdefault("MAIL_USERNAME", "docs")
os.environ.setdefault("MAIL_PASSWORD", "docs")
os.environ.setdefault("MAIL_FROM", "docs@example.com")
os.environ.setdefault("MAIL_SERVER", "smtp.example.com")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "docs")
os.environ.setdefault("CLOUDINARY_API_KEY", "docs")
os.environ.setdefault("CLOUDINARY_API_SECRET", "docs")

project = "Contacts API"
copyright = "2026, UMT Python Web HW-13"
author = "UMT Python Web HW-13"
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]