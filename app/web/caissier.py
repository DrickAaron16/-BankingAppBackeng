from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app import db
from app.models import Cheque, Remise, DetailRemise, StatutEnum, Utilisateur
from app.decorators import login_required_web
from app.utils import save_file, log_action, notify, generate_reference, generate_qr_code
import json

caissier_bp = Blueprint("caissier", __name__)

@caissier_bp.route("/")
@login_required_web(roles=["caissier"])
def dashboard():
    uid = session["user_id"]
    stats = {
        "mes_cheques_total": Cheque.query.filter_by(caissier_id=uid).count(),
        "mes_cheques_attente": Cheque.query.filter_by(caissier_id=uid, statut=StatutEnum.en_attente).count(),
        "mes_cheques_valides": Cheque.query.filter_by(caissier_id=uid, statut=StatutEnum.valide).count(),
        "mes_cheques_refuses": Cheque.query.filter_by(caissier_id=uid, statut=StatutEnum.refuse).count(),
        "remises_attente": Remise.query.filter_by(statut=StatutEnum.en_attente).count(),
    }
    derniers_cheques = (Cheque.query.filter_by(caissier_id=uid)
                        .order_by(Cheque.created_at.desc()).limit(8).all())
    return render_template("caissier/dashboard.html", stats=stats, derniers_cheques=derniers_cheques)


# ─── Chèques ──────────────────────────────────────────────────────────────────

@caissier_bp.route("/cheques")
@login_required_web(roles=["caissier"])
def cheques():
    statut = request.args.get("statut", "tous")
    q = Cheque.query.filter_by(caissier_id=session["user_id"])
    if statut != "tous":
        q = q.filter_by(statut=StatutEnum[statut])
    liste = q.order_by(Cheque.created_at.desc()).all()
    return render_template("caissier/cheques.html", cheques=liste, statut_filtre=statut)


@caissier_bp.route("/cheques/nouveau", methods=["GET", "POST"])
@login_required_web(roles=["caissier"])
def nouveau_cheque():
    if request.method == "POST":
        image_path = None
        if "image" in request.files and request.files["image"].filename:
            image_path = save_file(request.files["image"], "cheques")

        cheque = Cheque(
            numero=request.form["numero"],
            montant=request.form["montant"],
            banque=request.form.get("banque"),
            beneficiaire=request.form.get("beneficiaire"),
            image_path=image_path,
            caissier_id=session["user_id"],
        )
        db.session.add(cheque)
        db.session.commit()

        # Notifier tous les gestionnaires
        gestionnaires = Utilisateur.query.filter_by(role="gestionnaire", actif=True).all()
        for g in gestionnaires:
            notify(g.id, f"Nouveau chèque #{cheque.numero} soumis par le caissier — Montant : {cheque.montant} XOF")

        log_action(session["user_id"], "CHEQUE_CREE_WEB", details=f"Cheque#{cheque.id}")
        flash("Chèque soumis pour validation au gestionnaire", "success")
        return redirect(url_for("caissier.cheques"))

    return render_template("caissier/nouveau_cheque.html")


@caissier_bp.route("/cheques/<int:cheque_id>")
@login_required_web(roles=["caissier"])
def detail_cheque(cheque_id):
    cheque = Cheque.query.filter_by(id=cheque_id, caissier_id=session["user_id"]).first_or_404()
    return render_template("caissier/detail_cheque.html", cheque=cheque)


# ─── Remises ──────────────────────────────────────────────────────────────────

@caissier_bp.route("/remises")
@login_required_web(roles=["caissier"])
def remises():
    statut = request.args.get("statut", "en_attente")
    q = Remise.query
    if statut != "tous":
        q = q.filter_by(statut=StatutEnum[statut])
    liste = q.order_by(Remise.created_at.desc()).all()
    return render_template("caissier/remises.html", remises=liste, statut_filtre=statut)


@caissier_bp.route("/remises/<int:remise_id>")
@login_required_web(roles=["caissier"])
def detail_remise(remise_id):
    remise = Remise.query.get_or_404(remise_id)
    return render_template("caissier/detail_remise.html", remise=remise)


@caissier_bp.route("/remises/<int:remise_id>/confirmer", methods=["POST"])
@login_required_web(roles=["caissier"])
def confirmer_remise(remise_id):
    remise = Remise.query.get_or_404(remise_id)
    remise.caissier_id = session["user_id"]
    db.session.commit()

    gestionnaires = Utilisateur.query.filter_by(role="gestionnaire", actif=True).all()
    for g in gestionnaires:
        notify(g.id, f"Remise {remise.reference} confirmée par le caissier — {len(remise.details)} chèque(s)")

    log_action(session["user_id"], "REMISE_CONFIRMEE_WEB", details=f"Remise#{remise_id}")
    flash("Remise confirmée et transmise au gestionnaire", "success")
    return redirect(url_for("caissier.remises"))


# ─── Lookup remise par QR (AJAX) ──────────────────────────────────────────────

@caissier_bp.route("/remises/lookup")
@login_required_web(roles=["caissier"])
def lookup_remise():
    ref = request.args.get("ref", "").strip()
    remise = Remise.query.filter_by(reference=ref).first()
    if not remise:
        return jsonify({"error": "Remise introuvable"}), 404
    return jsonify({
        "id": remise.id,
        "reference": remise.reference,
        "statut": remise.statut.value,
        "nb_cheques": len(remise.details),
        "client": f"{remise.client.prenom} {remise.client.nom}",
        "url": url_for("caissier.detail_remise", remise_id=remise.id),
    })
