import os
import secrets
from pathlib import Path
from werkzeug.utils import secure_filename

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif", "svg"}


def setting(settings, key, default=""):
    return settings.get(key, default)


def save_upload(file, upload_folder, prefix="asset"):
    if not file or not file.filename:
        return ""
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        raise ValueError("Formato inválido. Use png, jpg, jpeg, webp, gif ou svg.")
    name = secure_filename(file.filename)
    unique = f"{prefix}-{secrets.token_hex(6)}-{name}"
    path = Path(upload_folder) / unique
    file.save(path)
    return f"uploads/{unique}"


def make_claim_code():
    return secrets.token_hex(3).upper()
