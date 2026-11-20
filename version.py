"""PANDA release version. Bump on each user-visible release; shown bottom-right in the app."""

APP_VERSION = "1.1.0"
RELEASE_DATE = "2026-11-20"


def short_version() -> str:
    major, minor, *_ = APP_VERSION.split(".")
    return f"v{major}.{minor}"
