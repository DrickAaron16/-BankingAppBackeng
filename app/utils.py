import uuid
import segno
import os
from flask import current_app
from app import db
from app.models import Log, Notification

def generate_reference():
    """Génère une référence unique."""
    return str(uuid.uuid4()).replace("-", "").upper()[:16]

def generate_qr_code(data: str, filename: str) -> str:
    """Génère un QR code SVG et retourne le chemin du fichier."""
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    qr_folder = os.path.join(upload_folder, "qrcodes")
    os.makedirs(qr_folder, exist_ok=True)

    qr = segno.make(data, error='h')
    path = os.path.join(qr_folder, f"{filename}.svg")
    qr.save(path, scale=8)
    return f"qrcodes/{filename}.svg"

def save_file(file, subfolder="cheques") -> str:
    """Sauvegarde un fichier uploadé et retourne le chemin relatif."""
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    dest_folder = os.path.join(upload_folder, subfolder)
    os.makedirs(dest_folder, exist_ok=True)

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    filename = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(dest_folder, filename)
    file.save(path)
    return f"{subfolder}/{filename}"

def log_action(utilisateur_id, action, details=None, ip=None):
    """Enregistre une action dans les logs."""
    log = Log(utilisateur_id=utilisateur_id, action=action, details=details, ip=ip)
    db.session.add(log)
    db.session.commit()

def notify(utilisateur_id, message, type="info"):
    """Crée une notification pour un utilisateur."""
    notif = Notification(utilisateur_id=utilisateur_id, message=message, type=type)
    db.session.add(notif)
    db.session.commit()
