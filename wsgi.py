from flask import send_from_directory
from app import create_app, db
import os

app = create_app()

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

def init_db():
    from app.models import Utilisateur, Compte, Transaction, TypeTransaction, StatutEnum, RoleEnum
    import random, string
    from decimal import Decimal

    db.create_all()

    # ── Migration automatique des colonnes manquantes ──
    with db.engine.connect() as conn:
        migrations = [
            ("utilisateurs", "signature_path", "VARCHAR(255)"),
            ("cheques", "cheque_emis_id", "INTEGER"),
            ("cheques", "recu_signe", "BOOLEAN DEFAULT 0"),
            ("cheques", "recu_path", "VARCHAR(255)"),
            ("remises", "bordereau_path", "VARCHAR(255)"),
            ("remises", "signature_gestionnaire", "VARCHAR(255)"),
            ("transactions", "caissier_id", "INTEGER"),
            ("transactions", "recu_signe", "BOOLEAN DEFAULT 0"),
            ("transactions", "recu_path", "VARCHAR(255)"),
        ]
        for table, col, col_type in migrations:
            try:
                conn.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
            except Exception:
                pass  # colonne déjà existante
        conn.commit()

    if Utilisateur.query.first():
        return

    print("Initialisation de la base de données...")

    def make_numero():
        return "BK" + "".join(random.choices(string.digits, k=10))

    def make_ref():
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=16))

    users_data = [
        {"nom": "Dupont",  "prenom": "Alice",  "email": "client@bank.com",        "tel": "+22500000001", "role": RoleEnum.client,       "password": "client123"},
        {"nom": "Koné",    "prenom": "Koffi",  "email": "koffi@bank.com",         "tel": "+22500000004", "role": RoleEnum.client,       "password": "client123"},
        {"nom": "Martin",  "prenom": "Bob",    "email": "caissier@bank.com",      "tel": "+22500000002", "role": RoleEnum.caissier,     "password": "caissier123"},
        {"nom": "Diallo",  "prenom": "Fatou",  "email": "gestionnaire@bank.com",  "tel": "+22500000003", "role": RoleEnum.gestionnaire, "password": "gestionnaire123"},
        {"nom": "Kouassi", "prenom": "Jean",   "email": "chef@bank.com",          "tel": "+22500000005", "role": RoleEnum.chef_caisse,  "password": "chef123"},
    ]

    for u in users_data:
        user = Utilisateur(nom=u["nom"], prenom=u["prenom"], email=u["email"], telephone=u["tel"], role=u["role"])
        user.set_password(u["password"])
        db.session.add(user)
        db.session.flush()

        if u["role"] == RoleEnum.client:
            solde = random.choice([250000, 500000, 750000, 1200000])
            compte = Compte(numero=make_numero(), type="courant", solde=solde, utilisateur_id=user.id)
            db.session.add(compte)
            db.session.flush()

            if u["email"] == "client@bank.com":
                epargne = Compte(numero=make_numero(), type="epargne", solde=2500000, utilisateur_id=user.id)
                db.session.add(epargne)

            types = [TypeTransaction.transfert, TypeTransaction.mobile_money_envoi, TypeTransaction.paiement_facture]
            descriptions = ["Loyer", "Facture CIE", "Virement reçu", "Paiement SIB", "Dépôt espèces"]
            for _ in range(random.randint(4, 8)):
                tx = Transaction(
                    reference=make_ref(),
                    type=random.choice(types),
                    montant=Decimal(str(random.choice([5000, 10000, 25000, 50000, 100000]))),
                    compte_source_id=compte.id,
                    description=random.choice(descriptions),
                    statut=StatutEnum.valide,
                )
                db.session.add(tx)

    db.session.commit()
    print("Base de données initialisée.")

with app.app_context():
    init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
