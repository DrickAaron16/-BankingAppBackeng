from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models import Compte, Transaction, Notification

accounts_bp = Blueprint("accounts", __name__)

@accounts_bp.route("/", methods=["GET"])
@jwt_required()
def get_accounts():
    user_id = int(get_jwt_identity())
    comptes = Compte.query.filter_by(utilisateur_id=user_id).all()
    return jsonify([c.to_dict() for c in comptes]), 200

@accounts_bp.route("/<int:compte_id>/transactions", methods=["GET"])
@jwt_required()
def get_transactions(compte_id):
    user_id = int(get_jwt_identity())
    compte = Compte.query.filter_by(id=compte_id, utilisateur_id=user_id).first_or_404()
    transactions = Transaction.query.filter(
        (Transaction.compte_source_id == compte.id) |
        (Transaction.compte_dest_id == compte.id)
    ).order_by(Transaction.created_at.desc()).limit(50).all()
    return jsonify([t.to_dict() for t in transactions]), 200

@accounts_bp.route("/notifications", methods=["GET"])
@jwt_required()
def get_notifications():
    user_id = int(get_jwt_identity())
    notifs = Notification.query.filter_by(utilisateur_id=user_id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    return jsonify([n.to_dict() for n in notifs]), 200

@accounts_bp.route("/notifications/mark-read", methods=["POST"])
@jwt_required()
def mark_notifications_read():
    user_id = int(get_jwt_identity())
    Notification.query.filter_by(utilisateur_id=user_id, lu=False).update({"lu": True})
    db.session.commit()
    return jsonify({"message": "OK"}), 200

@accounts_bp.route("/poll", methods=["GET"])
@jwt_required()
def poll():
    user_id = int(get_jwt_identity())
    comptes = Compte.query.filter_by(utilisateur_id=user_id).all()
    notifs_non_lues = Notification.query.filter_by(utilisateur_id=user_id, lu=False).count()
    derniere_notif = Notification.query.filter_by(utilisateur_id=user_id).order_by(
        Notification.created_at.desc()
    ).first()
    return jsonify({
        "comptes": [c.to_dict() for c in comptes],
        "notifs_non_lues": notifs_non_lues,
        "derniere_notif": derniere_notif.to_dict() if derniere_notif else None,
    }), 200
