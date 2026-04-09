from flask import send_from_directory
from app import create_app, db

app = create_app()

# Servir les fichiers uploadés (images chèques, QR codes)
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

def init_db():
    """Crée les tables et insère les données de test si la DB est vide."""
    from app.models import Utilisateur, Compte, Transaction, TypeTransaction, StatutEnum, RoleEnum
    import random, string
    from decimal import Decimal

    db.create_all()

    if Utilisateur.query.first():
        return  # DB déjà initialisée

    print("🔧 Initialisation de la base de données...")

    def make_numero():
        return "BK" + "".join(random.choices(string.digits, k=10))

    def make_ref():
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=16))

    # ── Utilisateurs ──────────────────────────────────────────────────────────
    users_data = [
        {"nom": "Dupont",  "prenom": "Alice",  "email": "client@bank.com",        "tel": "+22500000001", "role": RoleEnum.client,       "password": "client123"},
        {"nom": "Koné",    "prenom": "Koffi",  "email": "koffi@bank.com",         "tel": "+22500000004", "role": RoleEnum.client,       "password": "client123"},
        {"nom": "Traoré",  "prenom": "Marie",  "email": "marie@bank.com",         "tel": "+22500000005", "role": RoleEnum.client,       "password": "client123"},
        {"nom": "Martin",  "prenom": "Bob",    "email": "caissier@bank.com",      "tel": "+22500000002", "role": RoleEnum.caissier,     "password": "caissier123"},
        {"nom": "Diallo",  "prenom": "Fatou",  "email": "gestionnaire@bank.com",  "tel": "+22500000003", "role": RoleEnum.gestionnaire, "password": "gestionnaire123"},
    ]

    created = {}
    for u in users_data:
        user = Utilisateur(nom=u["nom"], prenom=u["prenom"], email=u["email"], telephone=u["tel"], role=u["role"])
        user.set_password(u["password"])
        db.session.add(user)
        db.session.flush()
        created[u["email"]] = user

        # Créer un compte pour chaque client
        if u["role"] == RoleEnum.client:
            solde = random.choice([250000, 500000, 750000, 1200000])
            compte = Compte(
                numero=make_numero(),
                type="courant",
                solde=solde,
                utilisateur_id=user.id
            )
            db.session.add(compte)
            db.session.flush()

            # Compte épargne pour Alice uniquement
            if u["email"] == "client@bank.com":
                epargne = Compte(
                    numero=make_numero(),
                    type="epargne",
                    solde=2500000,
                    utilisateur_id=user.id
                )
                db.session.add(epargne)
                db.session.flush()

            # Simuler des transactions sur le compte courant
            types = [TypeTransaction.transfert, TypeTransaction.mobile_money, TypeTransaction.paiement, TypeTransaction.depot]
            descriptions = ["Loyer", "Facture CIE", "Achat Orange Money", "Virement reçu", "Paiement SIB", "Recharge MTN", "Dépôt espèces"]
            for _ in range(random.randint(5, 10)):
                tx = Transaction(
                    reference=make_ref(),
                    type=random.choice(types),
                    montant=Decimal(str(random.choice([5000, 10000, 25000, 50000, 75000, 100000]))),
                    compte_source_id=compte.id,
                    description=random.choice(descriptions),
                    statut=StatutEnum.valide,
                )
                db.session.add(tx)

    db.session.commit()
    print("✅ Base de données prête !")
    print("   client@bank.com       / client123")
    print("   koffi@bank.com        / client123")
    print("   marie@bank.com        / client123")
    print("   caissier@bank.com     / caissier123")
    print("   gestionnaire@bank.com / gestionnaire123")

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
