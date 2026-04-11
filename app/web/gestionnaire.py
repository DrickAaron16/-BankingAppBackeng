from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app import db
from app.models import Cheque, ChequeEmis, Remise, Utilisateur, Compte, StatutEnum, Notification, RoleEnum
from app.decorators import login_required_web
from app.utils import log_action, notify
import random, string

gestionnaire_bp = Blueprint("gestionnaire", __name__)

@gestionnaire_bp.route("/")
@login_required_web(roles=["gestionnaire"])
def dashboard():
    uid = session["user_id"]
    stats = {
        "cheques_en_attente": Cheque.query.filter_by(statut=StatutEnum.en_attente).count(),
        "cheques_valides": Cheque.query.filter_by(statut=StatutEnum.valide).count(),
        "cheques_refuses": Cheque.query.filter_by(statut=StatutEnum.refuse).count(),
        "remises_en_attente": Remise.query.filter_by(statut=StatutEnum.en_attente).count(),
        "remises_validees": Remise.query.filter_by(statut=StatutEnum.valide).count(),
        "total_clients": Utilisateur.query.filter_by(role="client").count(),
    }
    notifs = (Notification.query.filter_by(utilisateur_id=uid, lu=False)
              .order_by(Notification.created_at.desc()).limit(10).all())
    derniers_cheques = Cheque.query.order_by(Cheque.created_at.desc()).limit(6).all()
    return render_template("gestionnaire/dashboard.html",
                           stats=stats, notifs=notifs, derniers_cheques=derniers_cheques)


# ─── Notifications ────────────────────────────────────────────────────────────

@gestionnaire_bp.route("/notifications")
@login_required_web(roles=["gestionnaire"])
def notifications():
    uid = session["user_id"]
    # Marquer toutes comme lues
    Notification.query.filter_by(utilisateur_id=uid, lu=False).update({"lu": True})
    db.session.commit()
    notifs = (Notification.query.filter_by(utilisateur_id=uid)
              .order_by(Notification.created_at.desc()).limit(50).all())
    return render_template("gestionnaire/notifications.html", notifs=notifs)


# ─── Chèques ──────────────────────────────────────────────────────────────────

@gestionnaire_bp.route("/cheques")
@login_required_web(roles=["gestionnaire"])
def cheques():
    statut = request.args.get("statut", "en_attente")
    q = Cheque.query
    if statut != "tous":
        q = q.filter_by(statut=StatutEnum[statut])
    liste = q.order_by(Cheque.created_at.desc()).all()
    counts = {
        "en_attente": Cheque.query.filter_by(statut=StatutEnum.en_attente).count(),
        "valide": Cheque.query.filter_by(statut=StatutEnum.valide).count(),
        "refuse": Cheque.query.filter_by(statut=StatutEnum.refuse).count(),
        "retour": Cheque.query.filter_by(statut=StatutEnum.retour).count(),
    }
    cheques_emis = ChequeEmis.query.order_by(ChequeEmis.created_at.desc()).all()
    cheques_emis_data = []
    for ce in cheques_emis:
        cheque_lie = Cheque.query.filter_by(cheque_emis_id=ce.id).first()
        cheques_emis_data.append({"cheque_emis": ce, "est_saisi": cheque_lie is not None})
    return render_template("gestionnaire/cheques.html",
                           cheques=liste, statut_filtre=statut, counts=counts,
                           cheques_emis=cheques_emis_data)


@gestionnaire_bp.route("/cheques-emis/<int:cheque_emis_id>")
@login_required_web(roles=["gestionnaire"])
def detail_cheque_emis(cheque_emis_id):
    cheque_emis = ChequeEmis.query.get_or_404(cheque_emis_id)
    cheque_saisi = Cheque.query.filter_by(cheque_emis_id=cheque_emis_id).first()
    est_saisi = cheque_saisi is not None
    divergence = None
    if est_saisi:
        diff = abs(float(cheque_saisi.montant) - float(cheque_emis.montant))
        if diff > 1:
            divergence = diff
    return render_template(
        "gestionnaire/detail_cheque_emis.html",
        cheque_emis=cheque_emis,
        cheque_saisi=cheque_saisi,
        est_saisi=est_saisi,
        divergence=divergence,
    )


@gestionnaire_bp.route("/cheques-emis/<int:cheque_emis_id>/decision", methods=["POST"])
@login_required_web(roles=["gestionnaire"])
def decision_cheque_emis_web(cheque_emis_id):
    cheque_emis = ChequeEmis.query.get_or_404(cheque_emis_id)
    cheque = Cheque.query.filter_by(cheque_emis_id=cheque_emis_id).first()
    if not cheque:
        flash("Ce chèque n'a pas encore été saisi en caisse", "danger")
        return redirect(url_for("gestionnaire.detail_cheque_emis", cheque_emis_id=cheque_emis_id))

    decision = request.form.get("decision")
    commentaire = request.form.get("commentaire", "")

    if decision not in ["valide", "refuse", "retour"]:
        flash("Décision invalide", "danger")
        return redirect(url_for("gestionnaire.detail_cheque_emis", cheque_emis_id=cheque_emis_id))

    cheque.statut = StatutEnum[decision]
    cheque.gestionnaire_id = session["user_id"]
    cheque.commentaire = commentaire
    cheque_emis.statut = StatutEnum[decision]
    db.session.commit()

    labels = {"valide": "validé ✔", "refuse": "refusé ✘", "retour": "retourné ↩"}

    if cheque.caissier_id:
        notify(cheque.caissier_id,
               f"Chèque N°{cheque.numero} ({float(cheque.montant):,.0f} XOF) {labels[decision]}. {commentaire}",
               type="validation", reference_id=cheque_emis_id, reference_type="cheque_emis")

    notify(cheque_emis.emetteur_id,
           f"Votre chèque N°{cheque_emis.numero} a été {labels[decision]} par la banque. {commentaire}",
           type="validation")

    log_action(session["user_id"], f"CHEQUE_EMIS_{decision.upper()}", details=f"ChequeEmis#{cheque_emis_id}")
    flash(f"Chèque {labels[decision]}", "success")
    return redirect(url_for("gestionnaire.cheques"))


@gestionnaire_bp.route("/cheques/<int:cheque_id>")
@login_required_web(roles=["gestionnaire"])
def detail_cheque(cheque_id):
    cheque = Cheque.query.get_or_404(cheque_id)
    return render_template("gestionnaire/detail_cheque.html", cheque=cheque)


@gestionnaire_bp.route("/cheques/<int:cheque_id>/decision", methods=["POST"])
@login_required_web(roles=["gestionnaire"])
def decision_cheque(cheque_id):
    cheque = Cheque.query.get_or_404(cheque_id)
    decision = request.form.get("decision")
    commentaire = request.form.get("commentaire", "")

    if decision not in ["valide", "refuse", "retour"]:
        flash("Décision invalide", "danger")
        return redirect(url_for("gestionnaire.detail_cheque", cheque_id=cheque_id))

    cheque.statut = StatutEnum[decision]
    cheque.gestionnaire_id = session["user_id"]
    cheque.commentaire = commentaire
    db.session.commit()

    labels = {"valide": "validé ✔", "refuse": "refusé ✘", "retour": "retourné ↩"}
    if cheque.caissier_id:
        notify(cheque.caissier_id,
               f"Chèque #{cheque.numero} ({cheque.montant} XOF) {labels[decision]}. {commentaire}")

    log_action(session["user_id"], f"CHEQUE_{decision.upper()}", details=f"Cheque#{cheque_id}")
    flash(f"Chèque {labels[decision]}", "success")
    return redirect(url_for("gestionnaire.cheques"))


# ─── Remises ──────────────────────────────────────────────────────────────────

@gestionnaire_bp.route("/remises")
@login_required_web(roles=["gestionnaire"])
def remises():
    statut = request.args.get("statut", "en_attente")
    q = Remise.query
    if statut != "tous":
        q = q.filter_by(statut=StatutEnum[statut])
    liste = q.order_by(Remise.created_at.desc()).all()
    counts = {
        "en_attente": Remise.query.filter_by(statut=StatutEnum.en_attente).count(),
        "valide": Remise.query.filter_by(statut=StatutEnum.valide).count(),
        "refuse": Remise.query.filter_by(statut=StatutEnum.refuse).count(),
    }
    return render_template("gestionnaire/remises.html",
                           remises=liste, statut_filtre=statut, counts=counts)


@gestionnaire_bp.route("/remises/<int:remise_id>")
@login_required_web(roles=["gestionnaire"])
def detail_remise(remise_id):
    remise = Remise.query.get_or_404(remise_id)
    return render_template("gestionnaire/detail_remise.html", remise=remise)


@gestionnaire_bp.route("/remises/<int:remise_id>/decision", methods=["POST"])
@login_required_web(roles=["gestionnaire"])
def decision_remise(remise_id):
    remise = Remise.query.get_or_404(remise_id)
    decision = request.form.get("decision")
    commentaire = request.form.get("commentaire", "")

    if decision not in ["valide", "refuse"]:
        flash("Décision invalide", "danger")
        return redirect(url_for("gestionnaire.detail_remise", remise_id=remise_id))

    remise.statut = StatutEnum[decision]
    remise.gestionnaire_id = session["user_id"]
    remise.commentaire = commentaire
    db.session.commit()

    label = "validée ✔" if decision == "valide" else "refusée ✘"
    notify(remise.client_id, f"Votre remise {remise.reference} a été {label}. {commentaire}")
    if remise.caissier_id:
        notify(remise.caissier_id, f"Remise {remise.reference} {label} par le gestionnaire.")

    log_action(session["user_id"], f"REMISE_{decision.upper()}", details=f"Remise#{remise_id}")
    flash(f"Remise {label}", "success")
    return redirect(url_for("gestionnaire.remises"))


# ─── Gestion des clients & comptes ───────────────────────────────────────────

@gestionnaire_bp.route("/clients")
@login_required_web(roles=["gestionnaire"])
def clients():
    clients = Utilisateur.query.filter_by(role=RoleEnum.client, actif=True).order_by(Utilisateur.created_at.desc()).all()
    return render_template("gestionnaire/clients.html", clients=clients)


@gestionnaire_bp.route("/clients/<int:client_id>")
@login_required_web(roles=["gestionnaire"])
def detail_client(client_id):
    client = Utilisateur.query.get_or_404(client_id)
    comptes = Compte.query.filter_by(utilisateur_id=client_id).all()
    return render_template("gestionnaire/detail_client.html", client=client, comptes=comptes)


@gestionnaire_bp.route("/clients/<int:client_id>/compte/nouveau", methods=["POST"])
@login_required_web(roles=["gestionnaire"])
def creer_compte(client_id):
    client = Utilisateur.query.get_or_404(client_id)
    solde_initial = float(request.form.get("solde_initial", 0))
    devise = request.form.get("devise", "XOF")

    numero = "BK" + "".join(random.choices(string.digits, k=10))
    type_compte = request.form.get("type_compte", "courant")
    compte = Compte(numero=numero, solde=solde_initial, devise=devise,
                    type=type_compte, utilisateur_id=client_id)
    db.session.add(compte)
    db.session.commit()

    notify(client_id, f"Votre compte bancaire N° {numero} a été ouvert. Solde initial : {solde_initial:,.0f} {devise}")
    log_action(session["user_id"], "COMPTE_CREE", details=f"Compte {numero} pour client#{client_id}")
    flash(f"Compte {numero} créé pour {client.prenom} {client.nom}", "success")
    return redirect(url_for("gestionnaire.detail_client", client_id=client_id))
