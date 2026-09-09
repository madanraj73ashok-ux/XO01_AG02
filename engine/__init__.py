"""EvidenceHire screening engine.

Credentials are read from a git-ignored `.env` at the project root and loaded
here, once, because every backend selector in this package decides what it can
do by looking at the environment. Loading it at import time means a module
imported directly - by a test, a script, or the API - sees the same
configuration the server does, rather than silently falling back to a local
stub because the file happened not to have been read yet.
"""

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover - dotenv is optional
    pass
