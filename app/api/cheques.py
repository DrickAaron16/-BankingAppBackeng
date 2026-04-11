from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models import Cheque, Remise, Notification, StatutEnum, RoleEnum, Utilisateur
from app.utils import save_file, log_action, notify, get_solde_info

cheques_bp = Blueprint("cheques", __name__)

@cheques_bp.route("/", methods=["GET"])
@jwt_required()
def list_cheques():
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    statut = request.args.get("statut")

    if role == RoleEnum.caissier.value:
        q = Cheque.query.filter_by(caissier_id=user_id)
    elif role == RoleEnum.gestionnaire.value:
        q = Cheque.query
    else:
        return jsonify({"error": "Accès refusé"}), 403

    if statut:
        q = q.filter_by(statut=StatutEnum[statut])
    return jsonify([c.to_dict() for c in q.order_by(Cheque.created_at.desc()).all()]), 200


@cheques_bp.route("/<int:cheque_id>", methods=["GET"])
@jwt_required()
def get_cheque(cheque_id):
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    cheque = Cheque.query.get_or_404(cheque_id)
    if role == RoleEnum.caissier.value and cheque.caissier_id != user_id:
        return jsonify({"error": "Accès refusé"}), 403
    return jsonify(cheque.to_dict()), 200


@cheques_bp.route("/", methods=["POST"])
@jwt_required()
def create_cheque():
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role not in [RoleEnum.caissier.value, RoleEnum.chef_caisse.value]:
        return jsonify({"error": "Accès refusé"}), 403

    image_path = None
    if "image" in request.files:
        image_path = save_file(request.files["image"], "cheques")

    numero = request.form.get("numero")

    # ── Vérification automatique : chèque pré-déclaré ? ──
    from app.models import ChequeEmis
    cheque_emis = ChequeEmis.query.filter_by(numero=numero).order_by(ChequeEmis.created_at.desc()).first()
    pre_declare = cheque_emis is not None
    alerte = None

    if pre_declare:
        montant_saisi = float(request.form.get("montant", 0))
        montant_declare = float(cheque_emis.montant)
        if abs(montant_saisi - montant_declare) > 1:
            alerte = f"⚠ Montant différent du déclaré ({montant_declare:,.0f} XOF)"

    cheque = Cheque(
        numero=numero,
        montant=request.form.get("montant"),
        banque=request.form.get("banque"),
        beneficiaire=request.form.get("beneficiaire"),
        image_path=image_path,
        caissier_id=user_id,
        cheque_emis_id=cheque_emis.id if cheque_emis else None,
    )
    db.session.add(cheque)
    db.session.commit()

    # Notifier l'émetteur que son chèque a été présenté en caisse
    if pre_declare:
        notify(
            cheque_emis.emetteur_id,
            f"🏦 Votre chèque N°{cheque.numero} ({float(cheque.montant):,.0f} XOF) a été présenté en caisse et est en attente de validation.{get_solde_info(cheque_emis.emetteur_id, cheque_emis.compte_emetteur_id)}",
            type="info",
        )

    # Notifier le gestionnaire si pré-déclaré
    if pre_declare:
        # Construire le message enrichi
        message = (
            f"Chèque saisi en caisse - N°{cheque.numero} | {cheque.montant} XOF | "
            f"Bénéficiaire: {cheque.beneficiaire or 'non renseigné'} | En attente de validation"
        )
        if abs(float(cheque.montant) - float(cheque_emis.montant)) > 1:
            message += (
                f" ⚠️ DIVERGENCE DE MONTANT: déclaré {cheque_emis.montant} XOF, saisi {cheque.montant} XOF"
            )

        if cheque_emis.gestionnaire_id:
            notify(
                cheque_emis.gestionnaire_id,
                message,
                type="validation",
                reference_id=cheque_emis.id,
                reference_type="cheque_emis",
            )
        else:
            # Notifier tous les gestionnaires actifs
            gestionnaires = Utilisateur.query.filter_by(role=RoleEnum.gestionnaire, actif=True).all()
            for g in gestionnaires:
                notify(
                    g.id,
                    message,
                    type="validation",
                    reference_id=cheque_emis.id,
                    reference_type="cheque_emis",
                )

    log_action(user_id, "CHEQUE_CREE", details=f"Cheque#{cheque.id} pre_declare={pre_declare}")
    return jsonify({
        "cheque": cheque.to_dict(),
        "pre_declare": pre_declare,
        "alerte": alerte,
        "cheque_emis": cheque_emis.to_dict() if cheque_emis else None,
    }), 201


@cheques_bp.route("/<int:cheque_id>/decision", methods=["PUT"])
@jwt_required()
def decision_cheque(cheque_id):
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role != RoleEnum.gestionnaire.value:
        return jsonify({"error": "Accès refusé"}), 403

    cheque = Cheque.query.get_or_404(cheque_id)
    data = request.get_json()
    decision = data.get("decision")

    if decision not in ["valide", "refuse", "retour"]:
        return jsonify({"error": "Décision invalide"}), 400

    cheque.statut = StatutEnum[decision]
    cheque.gestionnaire_id = user_id
    cheque.commentaire = data.get("commentaire", "")
    db.session.commit()

    labels = {"valide": "validé ✔", "refuse": "refusé ✘", "retour": "retourné ↩"}
    if cheque.caissier_id:
        notify(cheque.caissier_id,
               f"Chèque N°{cheque.numero} ({float(cheque.montant):,.0f} XOF) {labels[decision]}. {cheque.commentaire}",
               type="validation")

    # Notifier l'émetteur si le chèque était pré-déclaré
    if cheque.cheque_emis_id:
        from app.models import ChequeEmis
        ce = ChequeEmis.query.get(cheque.cheque_emis_id)
        if ce:
            emojis = {"valide": "✅", "refuse": "❌", "retour": "↩️"}
            notify(ce.emetteur_id,
                   f"{emojis[decision]} Votre chèque N°{cheque.numero} ({float(cheque.montant):,.0f} XOF) a été {labels[decision]} par la banque.{' ' + cheque.commentaire if cheque.commentaire else ''}{get_solde_info(ce.emetteur_id, ce.compte_emetteur_id)}",
                   type="validation")

    log_action(user_id, f"CHEQUE_{decision.upper()}", details=f"Cheque#{cheque_id}")
    return jsonify(cheque.to_dict()), 200


@cheques_bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    user_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role != RoleEnum.gestionnaire.value:
        return jsonify({"error": "Accès refusé"}), 403

    notifs_non_lues = Notification.query.filter_by(utilisateur_id=user_id, lu=False).count()
    return jsonify({
        "cheques_en_attente": Cheque.query.filter_by(statut=StatutEnum.en_attente).count(),
        "cheques_valides": Cheque.query.filter_by(statut=StatutEnum.valide).count(),
        "cheques_refuses": Cheque.query.filter_by(statut=StatutEnum.refuse).count(),
        "remises_en_attente": Remise.query.filter_by(statut=StatutEnum.en_attente).count(),
        "remises_validees": Remise.query.filter_by(statut=StatutEnum.valide).count(),
        "total_clients": Utilisateur.query.filter_by(role="client").count(),
        "notifs_non_lues": notifs_non_lues,
    }), 200
