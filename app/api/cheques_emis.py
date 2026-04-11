"""
API pour les chèques déclarés par les clients émetteurs via l'app mobile.
"""
from flask import Blueprint, request, jsonify, current_app
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

    # Récupérer l'émetteur pour le message de notification
    emetteur = Utilisateur.query.get(user_id)
    prenom = emetteur.prenom if emetteur else ""
    nom = emetteur.nom if emetteur else ""
    beneficiaire_label = cheque.beneficiaire if cheque.beneficiaire else "bénéficiaire non renseigné"
    message = (
        f"Nouveau chèque déclaré - N°{cheque.numero} | {cheque.montant} XOF | "
        f"Bénéficiaire: {beneficiaire_label} | Émetteur: {prenom} {nom}"
    )

    # Notifier tous les gestionnaires actifs
    gestionnaires = Utilisateur.query.filter_by(role=RoleEnum.gestionnaire, actif=True).all()
    if not gestionnaires:
        current_app.logger.warning(f"WARN_NO_GESTIONNAIRE: aucun gestionnaire actif lors de la déclaration du chèque N°{cheque.numero}")
    else:
        first = True
        for g in gestionnaires:
            if first:
                cheque.gestionnaire_id = g.id  # assigner le premier gestionnaire
                first = False
            notify(g.id, message, type="alerte", reference_id=cheque.id, reference_type="cheque_emis")

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
        return jsonify([c.to_dict() for c in cheques]), 200
    elif role in [RoleEnum.gestionnaire.value, RoleEnum.caissier.value, RoleEnum.chef_caisse.value]:
        cheques = ChequeEmis.query.order_by(ChequeEmis.created_at.desc()).all()
        base_url = request.host_url
        return jsonify([c.to_dict(include_cheque_saisi=True, base_url=base_url) for c in cheques]), 200
    else:
        return jsonify({"error": "Accès refusé"}), 403


@cheques_emis_bp.route("/<int:cheque_emis_id>", methods=["GET"])
@jwt_required()
def get_cheque_emis(cheque_emis_id):
    """Détail d'un chèque déclaré, accessible aux gestionnaires, caissiers et chefs de caisse."""
    role = get_jwt().get("role")
    if role not in [RoleEnum.gestionnaire.value, RoleEnum.caissier.value, RoleEnum.chef_caisse.value]:
        return jsonify({"error": "Accès refusé"}), 403

    cheque = ChequeEmis.query.get(cheque_emis_id)
    if not cheque:
        return jsonify({"error": "ChequeEmis introuvable"}), 404

    base_url = request.host_url
    return jsonify(cheque.to_dict(include_cheque_saisi=True, base_url=base_url)), 200


@cheques_emis_bp.route("/<int:cheque_emis_id>/decision", methods=["PUT"])
@jwt_required()
def decision_cheque_emis(cheque_emis_id):
    """Gestionnaire valide ou refuse un chèque déclaré (après saisie caissier)."""
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role != RoleEnum.gestionnaire.value:
        return jsonify({"error": "Accès refusé"}), 403

    cheque_emis = ChequeEmis.query.get(cheque_emis_id)
    if not cheque_emis:
        return jsonify({"error": "ChequeEmis introuvable"}), 404

    from app.models import Cheque as ChequeModel
    cheque = ChequeModel.query.filter_by(cheque_emis_id=cheque_emis_id).first()
    if not cheque:
        return jsonify({"error": "Ce chèque n'a pas encore été saisi en caisse"}), 400

    data = request.get_json()
    decision = data.get("decision")
    commentaire = data.get("commentaire", "")

    if decision not in ["valide", "refuse", "retour"]:
        return jsonify({"error": "Décision invalide"}), 400

    from app.models import StatutEnum as SE
    cheque.statut = SE[decision]
    cheque.gestionnaire_id = user_id
    cheque.commentaire = commentaire
    cheque_emis.statut = SE[decision]
    db.session.commit()

    labels = {"valide": "validé ✔", "refuse": "refusé ✘", "retour": "retourné ↩"}

    # Notifier le caissier
    if cheque.caissier_id:
        notify(
            cheque.caissier_id,
            f"Chèque N°{cheque.numero} ({float(cheque.montant):,.0f} XOF) {labels[decision]}. {commentaire}",
            type="validation",
            reference_id=cheque_emis_id,
            reference_type="cheque_emis",
        )

    # Notifier l'émetteur
    notify(
        cheque_emis.emetteur_id,
        f"Votre chèque N°{cheque_emis.numero} a été {labels[decision]} par la banque. {commentaire}",
        type="validation",
    )

    log_action(user_id, f"CHEQUE_EMIS_{decision.upper()}", details=f"ChequeEmis#{cheque_emis_id}")
    return jsonify({"message": f"Chèque {labels[decision]}", "cheque": cheque.to_dict()}), 200


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
