from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models import Remise, DetailRemise, StatutEnum, RoleEnum
from app.utils import generate_reference, generate_qr_code, save_file, log_action, notify, get_solde_info
import json

remises_bp = Blueprint("remises", __name__)

@remises_bp.route("/", methods=["GET"])
@jwt_required()
def list_remises():
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")

    if role == RoleEnum.client.value:
        remises = Remise.query.filter_by(client_id=user_id).order_by(Remise.created_at.desc()).all()
    elif role in [RoleEnum.caissier.value, RoleEnum.gestionnaire.value]:
        remises = Remise.query.order_by(Remise.created_at.desc()).all()
    else:
        return jsonify({"error": "Accès refusé"}), 403
    return jsonify([r.to_dict() for r in remises]), 200


@remises_bp.route("/", methods=["POST"])
@jwt_required()
def create_remise():
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role != RoleEnum.client.value:
        return jsonify({"error": "Accès refusé"}), 403

    ref = generate_reference()
    compte_id = request.form.get("compte_id")
    remise = Remise(reference=ref, client_id=user_id, compte_id=compte_id)
    db.session.add(remise)
    db.session.flush()

    details_raw = request.form.get("details", "[]")
    details = json.loads(details_raw)
    files = request.files

    for i, d in enumerate(details):
        image_path = None
        file_key = f"image_{i}"
        if file_key in files:
            image_path = save_file(files[file_key], "remises")

        detail = DetailRemise(
            remise_id=remise.id,
            numero_cheque=d["numero_cheque"],
            montant=d["montant"],
            banque=d.get("banque"),
            beneficiaire=d.get("beneficiaire"),
            emetteur=d.get("emetteur"),
            telephone_emetteur=d.get("telephone_emetteur"),
            compte_emetteur=d.get("compte_emetteur"),
            image_path=image_path,
        )
        db.session.add(detail)

    qr_path = generate_qr_code(ref, ref)
    remise.qr_code_path = qr_path
    db.session.commit()

    log_action(user_id, "REMISE_CREEE", details=f"Ref:{ref}")
    return jsonify(remise.to_dict()), 201


@remises_bp.route("/<int:remise_id>/scan", methods=["PUT"])
@jwt_required()
def scan_remise(remise_id):
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role != RoleEnum.caissier.value:
        return jsonify({"error": "Accès refusé"}), 403

    remise = Remise.query.get_or_404(remise_id)
    remise.caissier_id = user_id
    db.session.commit()

    log_action(user_id, "REMISE_SCANNEE", details=f"Remise#{remise_id}")
    return jsonify({"message": "Remise confirmée", "remise": remise.to_dict()}), 200


@remises_bp.route("/<int:remise_id>/decision", methods=["PUT"])
@jwt_required()
def decision_remise(remise_id):
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role != RoleEnum.gestionnaire.value:
        return jsonify({"error": "Accès refusé"}), 403

    remise = Remise.query.get_or_404(remise_id)
    data = request.get_json()
    decision = data.get("decision")

    if decision not in ["valide", "refuse"]:
        return jsonify({"error": "Décision invalide"}), 400

    remise.statut = StatutEnum[decision]
    remise.gestionnaire_id = user_id
    remise.commentaire = data.get("commentaire", "")
    db.session.commit()

    label = "validée ✔" if decision == "valide" else "refusée ✘"
    emoji = "✅" if decision == "valide" else "❌"
    total = sum(float(d.montant) for d in remise.details)
    notify(remise.client_id,
           f"{emoji} Votre remise {remise.reference} ({total:,.0f} XOF) a été {label}.{' ' + data.get('commentaire', '') if data.get('commentaire') else ''}{get_solde_info(remise.client_id, remise.compte_id)}",
           type="validation")
    log_action(user_id, f"REMISE_{decision.upper()}", details=f"Remise#{remise_id}")
    return jsonify(remise.to_dict()), 200
