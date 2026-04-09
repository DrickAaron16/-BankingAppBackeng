from app import db, bcrypt
from datetime import datetime
import enum

class RoleEnum(str, enum.Enum):
    client = "client"
    caissier = "caissier"
    gestionnaire = "gestionnaire"

class StatutEnum(str, enum.Enum):
    en_attente = "en_attente"
    valide = "valide"
    refuse = "refuse"
    retour = "retour"

# ─── Utilisateur ────────────────────────────────────────────────────────────────
class Utilisateur(db.Model):
    __tablename__ = "utilisateurs"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    telephone = db.Column(db.String(20), unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(RoleEnum), default=RoleEnum.client, nullable=False)
    otp_secret = db.Column(db.String(32))
    actif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comptes = db.relationship("Compte", backref="proprietaire", lazy=True)
    logs = db.relationship("Log", backref="utilisateur", lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "prenom": self.prenom,
            "email": self.email,
            "telephone": self.telephone,
            "role": self.role.value,
        }

class TypeCompte(str, enum.Enum):
    courant = "courant"
    epargne = "epargne"

# ─── Compte ─────────────────────────────────────────────────────────────────────
class Compte(db.Model):
    __tablename__ = "comptes"
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False)
    type = db.Column(db.Enum(TypeCompte), default=TypeCompte.courant, nullable=False)
    solde = db.Column(db.Numeric(15, 2), default=0.00)
    devise = db.Column(db.String(5), default="XOF")
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions_emises = db.relationship("Transaction", foreign_keys="Transaction.compte_source_id", backref="compte_source", lazy=True)
    transactions_recues = db.relationship("Transaction", foreign_keys="Transaction.compte_dest_id", backref="compte_dest", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "numero": self.numero,
            "type": self.type.value,
            "solde": float(self.solde),
            "devise": self.devise,
        }

# ─── Transaction ────────────────────────────────────────────────────────────────
class TypeTransaction(str, enum.Enum):
    transfert = "transfert"
    mobile_money_envoi = "mobile_money_envoi"
    mobile_money_retrait = "mobile_money_retrait"
    mobile_money_depot = "mobile_money_depot"
    paiement_facture = "paiement_facture"
    paiement_credit = "paiement_credit"
    abonnement = "abonnement"
    depot = "depot"
    retrait = "retrait"

class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.Enum(TypeTransaction), nullable=False)
    montant = db.Column(db.Numeric(15, 2), nullable=False)
    compte_source_id = db.Column(db.Integer, db.ForeignKey("comptes.id"))
    compte_dest_id = db.Column(db.Integer, db.ForeignKey("comptes.id"))
    description = db.Column(db.String(255))
    statut = db.Column(db.Enum(StatutEnum), default=StatutEnum.en_attente)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "reference": self.reference,
            "type": self.type.value,
            "montant": float(self.montant),
            "description": self.description,
            "statut": self.statut.value,
            "date": self.created_at.isoformat(),
        }

# ─── Chèque ─────────────────────────────────────────────────────────────────────
class Cheque(db.Model):
    __tablename__ = "cheques"
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    montant = db.Column(db.Numeric(15, 2), nullable=False)
    banque = db.Column(db.String(100))
    beneficiaire = db.Column(db.String(150))
    compte_emetteur_id = db.Column(db.Integer, db.ForeignKey("comptes.id"))
    image_path = db.Column(db.String(255))
    statut = db.Column(db.Enum(StatutEnum), default=StatutEnum.en_attente)
    caissier_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"))
    gestionnaire_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"))
    commentaire = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "numero": self.numero,
            "montant": float(self.montant),
            "banque": self.banque,
            "beneficiaire": self.beneficiaire,
            "statut": self.statut.value,
            "image_path": self.image_path,
            "commentaire": self.commentaire,
            "caissier_id": self.caissier_id,
            "date": self.created_at.isoformat(),
        }

# ─── Remise ──────────────────────────────────────────────────────────────────────
class Remise(db.Model):
    __tablename__ = "remises"
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    compte_id = db.Column(db.Integer, db.ForeignKey("comptes.id"))  # compte à créditer
    qr_code_path = db.Column(db.String(255))
    statut = db.Column(db.Enum(StatutEnum), default=StatutEnum.en_attente)
    caissier_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"))
    gestionnaire_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"))
    commentaire = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    details = db.relationship("DetailRemise", backref="remise", lazy=True, cascade="all, delete-orphan")
    client = db.relationship("Utilisateur", foreign_keys=[client_id])
    compte = db.relationship("Compte", foreign_keys=[compte_id])

    def to_dict(self):
        return {
            "id": self.id,
            "reference": self.reference,
            "statut": self.statut.value,
            "qr_code_path": self.qr_code_path,
            "compte_id": self.compte_id,
            "compte_numero": self.compte.numero if self.compte else None,
            "details": [d.to_dict() for d in self.details],
            "date": self.created_at.isoformat(),
        }

class DetailRemise(db.Model):
    __tablename__ = "details_remises"
    id = db.Column(db.Integer, primary_key=True)
    remise_id = db.Column(db.Integer, db.ForeignKey("remises.id"), nullable=False)
    numero_cheque = db.Column(db.String(50), nullable=False)
    montant = db.Column(db.Numeric(15, 2), nullable=False)
    banque = db.Column(db.String(100))
    beneficiaire = db.Column(db.String(150))
    # Nouveaux champs
    emetteur = db.Column(db.String(150))          # Nom de l'émetteur du chèque
    telephone_emetteur = db.Column(db.String(20)) # Téléphone de l'émetteur
    compte_emetteur = db.Column(db.String(30))    # N° compte bancaire émetteur
    image_path = db.Column(db.String(255))

    def to_dict(self):
        return {
            "id": self.id,
            "numero_cheque": self.numero_cheque,
            "montant": float(self.montant),
            "banque": self.banque,
            "beneficiaire": self.beneficiaire,
            "emetteur": self.emetteur,
            "telephone_emetteur": self.telephone_emetteur,
            "compte_emetteur": self.compte_emetteur,
            "image_path": self.image_path,
        }

# ─── Notification ────────────────────────────────────────────────────────────────
class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    lu = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "message": self.message,
            "lu": self.lu,
            "date": self.created_at.isoformat(),
        }

# ─── Log ─────────────────────────────────────────────────────────────────────────
class Log(db.Model):
    __tablename__ = "logs"
    id = db.Column(db.Integer, primary_key=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"))
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    ip = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
