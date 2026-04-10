"""
API pour les chèques déclarés par les clients émetteurs via l'app mobile.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models import ChequeEmis, Utilisateur, RoleEnum, StatutEnum
from app.utils import save_file, log_action, notify

cheques_emis_bp = Blueprint("cheques_emis", __name__)


@cheques_emis_bp.route("/", methods=["POST"])
@jwt_required()
def declarer_cheque():
    """Client déclare un chèque qu'il émet."""
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role != RoleEnum.client.value:
        return jsonify({"error": "Accès refusé"}), 403

    image_path = None
    if "image" in request.files and request.files["image"].filename:
        image_path = save_file(request.files["image"], "cheques_emis")

    cheque = ChequeEmis(
        numero=request.form.get("numero"),
        montant=request.form.get("montant"),
        banque=request.form.get("banque"),
        beneficiaire=request.form.get("beneficiaire"),
        compte_beneficiaire=request.form.get("compte_beneficiaire"),
        compte_emetteur_id=request.form.get("compte_emetteur_id"),
        image_path=image_path,
        emetteur_id=user_id,
    )
    db.session.add(cheque)
    db.session.flush()

    # Notifier tous les gestionnaires
    gestionnaires = Utilisateur.query.filter_by(role=RoleEnum.gestionnaire, actif=True).all()
    for g in gestionnaires:
        cheque.gestionnaire_id = g.id  # assigner le premier gestionnaire
        notify(g.id, f"Nouveau chèque déclaré N°{cheque.numero} — {cheque.montant} XOF — Bénéficiaire : {cheque.beneficiaire}", type="alerte")

    db.session.commit()
    log_action(user_id, "CHEQUE_EMIS_DECLARE", details=f"N°{cheque.numero}")
    return jsonify(cheque.to_dict()), 201


@cheques_emis_bp.route("/", methods=["GET"])
@jwt_required()
def list_cheques_emis():
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role == RoleEnum.client.value:
        cheques = ChequeEmis.query.filter_by(emetteur_id=user_id).order_by(ChequeEmis.created_at.desc()).all()
    elif role in [RoleEnum.gestionnaire.value, RoleEnum.caissier.value, RoleEnum.chef_caisse.value]:
        cheques = ChequeEmis.query.order_by(ChequeEmis.created_at.desc()).all()
    else:
        return jsonify({"error": "Accès refusé"}), 403
    return jsonify([c.to_dict() for c in cheques]), 200


@cheques_emis_bp.route("/verifier/<numero>", methods=["GET"])
@jwt_required()
def verifier_cheque(numero):
    """Caissier vérifie si un chèque a été pré-déclaré par l'émetteur."""
    role = get_jwt().get("role")
    if role not in [RoleEnum.caissier.value, RoleEnum.gestionnaire.value, RoleEnum.chef_caisse.value]:
        return jsonify({"error": "Accès refusé"}), 403

    cheque = ChequeEmis.query.filter_by(numero=numero).order_by(ChequeEmis.created_at.desc()).first()
    if not cheque:
        return jsonify({"pre_declare": False, "message": "Chèque non déclaré par l'émetteur"}), 200

    return jsonify({
        "pre_declare": True,
        "cheque": cheque.to_dict(),
        "message": f"✔ Chèque pré-déclaré par {cheque.emetteur.prenom} {cheque.emetteur.nom}",
    }), 200
