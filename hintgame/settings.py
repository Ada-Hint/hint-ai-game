"""Settings are read server-side; local credentials are never committed."""
from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent


def setting(name, default=""):
    if name in os.environ:
        return os.environ[name]
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


def local_password():
    path = ROOT / ".local" / "host-password.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    value = secrets.token_urlsafe(24)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")
    return value


@dataclass(frozen=True)
class Settings:
    backend: str
    host_password: str
    event_code: str
    event_id: str
    public_url: str
    supabase_url: str
    supabase_key: str
    sqlite_path: str


def load_settings():
    backend = setting("STORAGE_BACKEND", "sqlite")
    if os.environ.get("HINT_CLOUD_DEPLOYMENT") == "1" and backend != "supabase":
        raise ValueError("Add the Supabase settings in Streamlit Cloud → App settings → Secrets before sharing this app. Shared surveys require persistent storage.")
    if backend not in {"sqlite", "supabase"}:
        raise ValueError("STORAGE_BACKEND must be sqlite or supabase.")
    password = setting("HOST_PASSWORD")
    code = setting("EVENT_CODE", "HINTAI" if backend == "sqlite" else "")
    if backend == "supabase" and (len(password) < 12 or len(code.strip()) < 4):
        raise ValueError("Set HOST_PASSWORD (at least 12 characters) and EVENT_CODE (at least 4 characters) before hosting.")
    public_url = setting("PUBLIC_BASE_URL", "http://localhost:8501").rstrip("/")
    if os.environ.get("HINT_CLOUD_DEPLOYMENT") == "1" and not public_url.startswith("https://"):
        raise ValueError("Set PUBLIC_BASE_URL to this app’s https:// address in Streamlit secrets so survey links and QR codes work for your team.")
    return Settings(backend, password or local_password(), code.strip(), setting("EVENT_ID", "hint-lunch-and-learn"), public_url, setting("SUPABASE_URL"), setting("SUPABASE_SECRET_KEY") or setting("SUPABASE_SERVICE_ROLE_KEY"), setting("SQLITE_PATH", str(ROOT / ".local" / "hint.db")))
