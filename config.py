import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(os.path.dirname(__file__), "banking.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1 heure
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
    PROPAGATE_EXCEPTIONS = True

    # Twilio SMS (OTP)
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE = os.getenv("TWILIO_PHONE", "")
