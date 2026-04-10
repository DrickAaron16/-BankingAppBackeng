from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Compte, Transaction, TypeTransaction, StatutEnum
from app.utils import generate_reference, log_action, notify
from decimal import Decimal

transactions_bp = Blueprint("transactions", __name__)

EMOJIS = {
    "debit":  "📤",
    "credit": "📥",
    "info":   "ℹ️",
}

def _debit(compte, montant, type_tx, description, user_id, dest_id=None):
    if compte.solde < montant:
        return None, "Solde insuffisant"
    compte.solde -= montant
    tx = Transaction(
        reference=generate_reference(),
        type=type_tx,
        montant=montant,
        compte_source_id=compte.id,
        compte_dest_id=dest_id,
        description=description,
        statut=StatutEnum.valide,
    )
    db.session.add(tx)
    db.session.commit()
    # Notifier le propriétaire du compte débité
    notify(user_id,
           f"📤 Débit de {montant:,.0f} {compte.devise} — {description} | Nouveau solde : {float(compte.solde):,.0f} {compte.devise}",
           type="debit")
    log_action(user_id, type_tx.value.upper(), details=f"Ref:{tx.reference}")
    return tx, None


@transactions_bp.route("/transfert", methods=["POST"])
@jwt_required()
def transfert():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    source = Compte.query.filter_by(id=data["compte_source_id"], utilisateur_id=user_id).first_or_404()
    dest = Compte.query.filter_by(numero=data["numero_dest"]).first()
    if not dest:
        return jsonify({"error": "Compte destinataire introuvable"}), 404

    montant = Decimal(str(data["montant"]))
    tx, err = _debit(source, montant, TypeTransaction.transfert,
                     data.get("description", "Transfert bancaire"), user_id, dest.id)
    if err:
        return jsonify({"error": err}), 400

    dest.solde += montant
    db.session.commit()
    notify(dest.utilisateur_id,
           f"📥 Crédit de {montant:,.0f} {source.devise} reçu depuis {source.numero} | Nouveau solde : {float(dest.solde):,.0f} {dest.devise}",
           type="credit")
    return jsonify(tx.to_dict()), 201


@transactions_bp.route("/mobile-money/envoi", methods=["POST"])
@jwt_required()
def mobile_money_envoi():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    source = Compte.query.filter_by(id=data["compte_source_id"], utilisateur_id=user_id).first_or_404()
    montant = Decimal(str(data["montant"]))
    operateur = data.get("operateur", "Mobile Money")
    numero = data.get("numero_mobile", "")

    tx, err = _debit(source, montant, TypeTransaction.mobile_money_envoi,
                     f"Envoi {operateur} → {numero}", user_id)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(tx.to_dict()), 201


@transactions_bp.route("/mobile-money/retrait", methods=["POST"])
@jwt_required()
def mobile_money_retrait():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    source = Compte.query.filter_by(id=data["compte_source_id"], utilisateur_id=user_id).first_or_404()
    montant = Decimal(str(data["montant"]))
    operateur = data.get("operateur", "Mobile Money")
    numero = data.get("numero_mobile", "")

    tx, err = _debit(source, montant, TypeTransaction.mobile_money_retrait,
                     f"Retrait {operateur} depuis {numero}", user_id)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(tx.to_dict()), 201


@transactions_bp.route("/mobile-money/depot", methods=["POST"])
@jwt_required()
def mobile_money_depot():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    compte = Compte.query.filter_by(id=data["compte_dest_id"], utilisateur_id=user_id).first_or_404()
    montant = Decimal(str(data["montant"]))
    operateur = data.get("operateur", "Mobile Money")
    numero = data.get("numero_mobile", "")

    compte.solde += montant
    tx = Transaction(
        reference=generate_reference(),
        type=TypeTransaction.mobile_money_depot,
        montant=montant,
        compte_dest_id=compte.id,
        description=f"Dépôt {operateur} depuis {numero}",
        statut=StatutEnum.valide,
    )
    db.session.add(tx)
    db.session.commit()
    notify(user_id,
           f"📥 Dépôt {operateur} de {montant:,.0f} {compte.devise} crédité | Nouveau solde : {float(compte.solde):,.0f} {compte.devise}",
           type="credit")
    log_action(user_id, "MOBILE_MONEY_DEPOT", details=f"Ref:{tx.reference}")
    return jsonify(tx.to_dict()), 201


@transactions_bp.route("/facture", methods=["POST"])
@jwt_required()
def paiement_facture():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    source = Compte.query.filter_by(id=data["compte_source_id"], utilisateur_id=user_id).first_or_404()
    montant = Decimal(str(data["montant"]))
    fournisseur = data.get("fournisseur", "")
    reference_facture = data.get("reference_facture", "")

    tx, err = _debit(source, montant, TypeTransaction.paiement_facture,
                     f"Facture {fournisseur} — Réf: {reference_facture}", user_id)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(tx.to_dict()), 201


@transactions_bp.route("/credit", methods=["POST"])
@jwt_required()
def paiement_credit():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    source = Compte.query.filter_by(id=data["compte_source_id"], utilisateur_id=user_id).first_or_404()
    montant = Decimal(str(data["montant"]))
    reference_credit = data.get("reference_credit", "")

    tx, err = _debit(source, montant, TypeTransaction.paiement_credit,
                     f"Remboursement crédit — Réf: {reference_credit}", user_id)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(tx.to_dict()), 201


@transactions_bp.route("/abonnement", methods=["POST"])
@jwt_required()
def abonnement():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    source = Compte.query.filter_by(id=data["compte_source_id"], utilisateur_id=user_id).first_or_404()
    montant = Decimal(str(data["montant"]))
    service = data.get("service", "")
    periodicite = data.get("periodicite", "mensuel")

    tx, err = _debit(source, montant, TypeTransaction.abonnement,
                     f"Abonnement {service} ({periodicite})", user_id)
    if err:
        return jsonify({"error": err}), 400
    return jsonify(tx.to_dict()), 201


@transactions_bp.route("/mobile-money", methods=["POST"])
@jwt_required()
def mobile_money_legacy():
    return mobile_money_envoi()
