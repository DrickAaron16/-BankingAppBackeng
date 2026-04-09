from functools import wraps
from flask import session, redirect, url_for, jsonify

def login_required_web(roles=None):
    """Décorateur pour les routes web (session Flask)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.web_login"))
            if roles and session.get("role") not in roles:
                return redirect(url_for("auth.web_login"))
            return f(*args, **kwargs)
        return decorated
    return decorator
