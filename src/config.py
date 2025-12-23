import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
DEBUG = ENVIRONMENT == "development"

# Server settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))

# Static and template directories
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "info" if not DEBUG else "debug")
