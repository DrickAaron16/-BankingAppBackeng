from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app import db
from app.models import (ClotureCaisse, Cheque, Remise, Transaction,
                         Utilisateur, StatutEnum, RoleEnum)
from app.decorators import login_required_web
from app.utils import save_file, log_action
from datetime import date, datetime

chef_caisse_bp = Blueprint("chef_caisse_web", __name__)


@chef_caisse_bp.route("/")
@login_required_web(roles=["chef_caisse", "gestionnaire"])
def dashboard():
    aujourd_hui = date.today()
    debut = datetime.combine(aujourd_hui, datetime.min.time())
    fin = datetime.combine(aujourd_hui, datetime.max.time())

    stats = {
        "nb_cheques": Cheque.query.filter(Cheque.created_at.between(debut, fin)).count(),
        "nb_cheques_valides": Cheque.query.filter(Cheque.created_at.between(debut, fin), Cheque.statut == StatutEnum.valide).count(),
        "nb_remises": Remise.query.filter(Remise.created_at.between(debut, fin)).count(),
        "nb_transactions": Transaction.query.filter(Transaction.created_at.between(debut, fin)).count(),
    }
    cloture_du_jour = ClotureCaisse.query.filter_by(date_journee=aujourd_hui).first()
    dernieres_clotures = ClotureCaisse.query.order_by(ClotureCaisse.date_journee.desc()).limit(7).all()

    return render_template("chef_caisse/dashboard.html",
                           stats=stats,
                           aujourd_hui=aujourd_hui,
                           cloture_du_jour=cloture_du_jour,
                           dernieres_clotures=dernieres_clotures)


@chef_caisse_bp.route("/journee")
@login_required_web(roles=["chef_caisse", "gestionnaire"])
def journee():
    date_str = request.args.get("date", date.today().isoformat())
    try:
        jour = date.fromisoformat(date_str)
    except ValueError:
        jour = date.today()

    debut = datetime.combine(jour, datetime.min.time())
    fin = datetime.combine(jour, datetime.max.time())

    cheques = Cheque.query.filter(Cheque.created_at.between(debut, fin)).order_by(Cheque.created_at).all()
    remises = Remise.query.filter(Remise.created_at.between(debut, fin)).order_by(Remise.created_at).all()
    transactions = Transaction.query.filter(Transaction.created_at.between(debut, fin)).order_by(Transaction.created_at).all()

    total_enc = sum(float(c.montant) for c in cheques if c.statut == StatutEnum.valide)
    total_dec = sum(float(t.montant) for t in transactions if t.statut == StatutEnum.valide)

    cloture = ClotureCaisse.query.filter_by(date_journee=jour).first()

    return render_template("chef_caisse/journee.html",
                           jour=jour,
                           cheques=cheques,
                           remises=remises,
                           transactions=transactions,
                           total_enc=total_enc,
                           total_dec=total_dec,
                           solde=total_enc - total_dec,
                           cloture=cloture)


@chef_caisse_bp.route("/cloture", methods=["POST"])
@login_required_web(roles=["chef_caisse", "gestionnaire"])
def cloturer():
    date_str = request.form.get("date", date.today().isoformat())
    observations = request.form.get("observations", "")
    jour = date.fromisoformat(date_str)

    existing = ClotureCaisse.query.filter_by(date_journee=jour).first()
    if existing and existing.signe:
        flash("Cette journée est déjà clôturée et signée", "warning")
        return redirect(url_for("chef_caisse_web.journee", date=date_str))

    debut = datetime.combine(jour, datetime.min.time())
    fin = datetime.combine(jour, datetime.max.time())

    cheques = Cheque.query.filter(Cheque.created_at.between(debut, fin)).all()
    remises = Remise.query.filter(Remise.created_at.between(debut, fin)).all()
    transactions = Transaction.query.filter(Transaction.created_at.between(debut, fin)).all()

    total_enc = sum(float(c.montant) for c in cheques if c.statut == StatutEnum.valide)
    total_dec = sum(float(t.montant) for t in transactions if t.statut == StatutEnum.valide)

    cloture = existing or ClotureCaisse(date_journee=jour)
    cloture.chef_caisse_id = session["user_id"]
    cloture.nb_cheques = len(cheques)
    cloture.nb_remises = len(remises)
    cloture.nb_transactions = len(transactions)
    cloture.total_encaissements = total_enc
    cloture.total_decaissements = total_dec
    cloture.solde_journee = total_enc - total_dec
    cloture.observations = observations

    if not existing:
        db.session.add(cloture)
    db.session.commit()

    log_action(session["user_id"], "CLOTURE_JOURNEE", details=f"Date:{jour}")
    flash(f"Journée du {jour.strftime('%d/%m/%Y')} clôturée", "success")
    return redirect(url_for("chef_caisse_web.signer_form", cloture_id=cloture.id))


@chef_caisse_bp.route("/cloture/<int:cloture_id>/signer", methods=["GET", "POST"])
@login_required_web(roles=["chef_caisse", "gestionnaire"])
def signer_form(cloture_id):
    cloture = ClotureCaisse.query.get_or_404(cloture_id)

    if request.method == "POST":
        if "signature" not in request.files or not request.files["signature"].filename:
            flash("Veuillez fournir une signature", "danger")
            return render_template("chef_caisse/signer.html", cloture=cloture)

        sig_path = save_file(request.files["signature"], "signatures")
        cloture.signature_path = sig_path
        cloture.signe = True
        db.session.commit()
        log_action(session["user_id"], "CLOTURE_SIGNEE", details=f"Cloture#{cloture_id}")
        flash("Clôture signée avec succès", "success")
        return redirect(url_for("chef_caisse_web.dashboard"))

    return render_template("chef_caisse/signer.html", cloture=cloture)
