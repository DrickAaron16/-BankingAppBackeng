from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models import Utilisateur, RoleEnum
from app.utils import log_action
import pyotp

auth_bp = Blueprint("auth", __name__)

def _make_token(user):
    """Crée un token JWT avec l'id comme subject (string) et le rôle en claim."""
    return create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role.value}
    )

# ─── API Auth (Mobile Flutter) ──────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    identifiant = data.get("email", "").strip()
    password = data.get("password", "")

    # Chercher par code_client d'abord, puis par email
    user = Utilisateur.query.filter_by(code_client=identifiant.upper(), actif=True).first()
    if not user:
        user = Utilisateur.query.filter_by(email=identifiant.lower(), actif=True).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "Identifiants invalides"}), 401

    if user.otp_secret:
        return jsonify({"otp_required": True, "user_id": user.id}), 200

    token = _make_token(user)
    log_action(user.id, "LOGIN", ip=request.remote_addr)
    return jsonify({"token": token, "user": user.to_dict()}), 200


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    user_id = data.get("user_id")
    otp_code = data.get("otp_code", "")

    user = Utilisateur.query.get_or_404(user_id)
    totp = pyotp.TOTP(user.otp_secret)

    if not totp.verify(otp_code):
        return jsonify({"error": "Code OTP invalide"}), 401

    token = _make_token(user)
    log_action(user.id, "LOGIN_OTP", ip=request.remote_addr)
    return jsonify({"token": token, "user": user.to_dict()}), 200


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if Utilisateur.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email déjà utilisé"}), 409

    # Générer un code client unique : CLI + 6 chiffres
    import random
    while True:
        code = f"CLI{random.randint(100000, 999999)}"
        if not Utilisateur.query.filter_by(code_client=code).first():
            break

    user = Utilisateur(
        code_client=code,
        nom=data["nom"],
        prenom=data["prenom"],
        email=data["email"].strip().lower(),
        telephone=data.get("telephone"),
        role=RoleEnum.client,
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return jsonify({
        "message": f"Compte créé. Votre code client est : {code}",
        "code_client": code,
        "user": user.to_dict()
    }), 201


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    user = Utilisateur.query.get_or_404(user_id)
    return jsonify(user.to_dict()), 200


# ─── Web Auth (Caissier / Gestionnaire) ─────────────────────────────────────────

@auth_bp.route("/web/login", methods=["GET", "POST"])
def web_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = Utilisateur.query.filter_by(email=email, actif=True).first()

        if not user or not user.check_password(password):
            return render_template("login.html", error="Identifiants invalides")

        if user.role not in [RoleEnum.caissier, RoleEnum.gestionnaire, RoleEnum.chef_caisse]:
            return render_template("login.html", error="Accès non autorisé")

        session["user_id"] = user.id
        session["role"] = user.role.value
        session["user_nom"] = f"{user.prenom} {user.nom}"
        log_action(user.id, "WEB_LOGIN", ip=request.remote_addr)

        if user.role == RoleEnum.caissier:
            return redirect(url_for("caissier.dashboard"))
        if user.role == RoleEnum.chef_caisse:
            return redirect(url_for("chef_caisse_web.dashboard"))
        return redirect(url_for("gestionnaire.dashboard"))

    return render_template("login.html")


@auth_bp.route("/web/logout")
def web_logout():
    session.clear()
    return redirect(url_for("auth.web_login"))
