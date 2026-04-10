"""
API pour le chef de caisse : récapitulatif journée, clôture, signature.
"""
from flask import Blueprint, request, jsonify, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models import (ClotureCaisse, Cheque, Remise, Transaction,
                         Utilisateur, RoleEnum, StatutEnum)
from app.utils import save_file, log_action
from datetime import date, datetime
import os

chef_caisse_bp = Blueprint("chef_caisse", __name__)


def _roles_autorises():
    return [RoleEnum.chef_caisse.value, RoleEnum.gestionnaire.value]


@chef_caisse_bp.route("/journee", methods=["GET"])
@jwt_required()
def recap_journee():
    """Récapitulatif automatique de la journée en cours."""
    role = get_jwt().get("role")
    if role not in _roles_autorises():
        return jsonify({"error": "Accès refusé"}), 403

    date_str = request.args.get("date", date.today().isoformat())
    try:
        jour = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Date invalide"}), 400

    debut = datetime.combine(jour, datetime.min.time())
    fin = datetime.combine(jour, datetime.max.time())

    cheques = Cheque.query.filter(Cheque.created_at.between(debut, fin)).all()
    remises = Remise.query.filter(Remise.created_at.between(debut, fin)).all()
    transactions = Transaction.query.filter(Transaction.created_at.between(debut, fin)).all()

    total_enc = sum(float(c.montant) for c in cheques if c.statut == StatutEnum.valide)
    total_enc += sum(float(r.details[0].montant if r.details else 0) for r in remises if r.statut == StatutEnum.valide)
    total_dec = sum(float(t.montant) for t in transactions if t.statut == StatutEnum.valide)

    # Détail par caissier
    caissiers = {}
    for c in cheques:
        if c.caissier_id:
            caissiers.setdefault(c.caissier_id, {"nb_cheques": 0, "nb_remises": 0, "nb_transactions": 0})
            caissiers[c.caissier_id]["nb_cheques"] += 1

    return jsonify({
        "date": date_str,
        "nb_cheques": len(cheques),
        "nb_cheques_valides": sum(1 for c in cheques if c.statut == StatutEnum.valide),
        "nb_cheques_refuses": sum(1 for c in cheques if c.statut == StatutEnum.refuse),
        "nb_remises": len(remises),
        "nb_remises_validees": sum(1 for r in remises if r.statut == StatutEnum.valide),
        "nb_transactions": len(transactions),
        "total_encaissements": total_enc,
        "total_decaissements": total_dec,
        "solde_journee": total_enc - total_dec,
        "cheques": [c.to_dict() for c in cheques],
        "remises": [r.to_dict() for r in remises],
        "transactions": [t.to_dict() for t in transactions],
        "par_caissier": caissiers,
    }), 200


@chef_caisse_bp.route("/cloture", methods=["POST"])
@jwt_required()
def cloturer_journee():
    """Chef de caisse clôture la journée."""
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role not in _roles_autorises():
        return jsonify({"error": "Accès refusé"}), 403

    data = request.get_json()
    date_journee = date.fromisoformat(data.get("date", date.today().isoformat()))

    existing = ClotureCaisse.query.filter_by(date_journee=date_journee).first()
    if existing and existing.signe:
        return jsonify({"error": "Cette journée est déjà clôturée et signée"}), 409

    debut = datetime.combine(date_journee, datetime.min.time())
    fin = datetime.combine(date_journee, datetime.max.time())

    cheques = Cheque.query.filter(Cheque.created_at.between(debut, fin)).all()
    remises = Remise.query.filter(Remise.created_at.between(debut, fin)).all()
    transactions = Transaction.query.filter(Transaction.created_at.between(debut, fin)).all()

    total_enc = sum(float(c.montant) for c in cheques if c.statut == StatutEnum.valide)
    total_dec = sum(float(t.montant) for t in transactions if t.statut == StatutEnum.valide)

    cloture = existing or ClotureCaisse(date_journee=date_journee)
    cloture.chef_caisse_id = user_id
    cloture.nb_cheques = len(cheques)
    cloture.nb_remises = len(remises)
    cloture.nb_transactions = len(transactions)
    cloture.total_encaissements = total_enc
    cloture.total_decaissements = total_dec
    cloture.solde_journee = total_enc - total_dec
    cloture.observations = data.get("observations", "")

    if not existing:
        db.session.add(cloture)
    db.session.commit()

    log_action(user_id, "CLOTURE_JOURNEE", details=f"Date:{date_journee}")
    return jsonify(cloture.to_dict()), 201


@chef_caisse_bp.route("/cloture/<int:cloture_id>/signer", methods=["POST"])
@jwt_required()
def signer_cloture(cloture_id):
    """Chef de caisse signe la clôture (upload image signature)."""
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role not in _roles_autorises():
        return jsonify({"error": "Accès refusé"}), 403

    cloture = ClotureCaisse.query.get_or_404(cloture_id)
    if cloture.signe:
        return jsonify({"error": "Déjà signé"}), 409

    if "signature" not in request.files:
        return jsonify({"error": "Signature requise"}), 400

    sig_path = save_file(request.files["signature"], "signatures")
    cloture.signature_path = sig_path
    cloture.signe = True
    db.session.commit()

    log_action(user_id, "CLOTURE_SIGNEE", details=f"Cloture#{cloture_id}")
    return jsonify({"message": "Clôture signée", "cloture": cloture.to_dict()}), 200


@chef_caisse_bp.route("/clotures", methods=["GET"])
@jwt_required()
def list_clotures():
    role = get_jwt().get("role")
    if role not in _roles_autorises():
        return jsonify({"error": "Accès refusé"}), 403
    clotures = ClotureCaisse.query.order_by(ClotureCaisse.date_journee.desc()).limit(30).all()
    return jsonify([c.to_dict() for c in clotures]), 200
