"""Script de seed : crée les utilisateurs de test et quelques données."""
from app import create_app, db
from app.models import Utilisateur, Compte, RoleEnum
import random, string

app = create_app()

def random_account_number():
    return 'BK' + ''.join(random.choices(string.digits, k=10))

with app.app_context():
    db.create_all()

    users = [
        {"nom": "Dupont", "prenom": "Alice", "email": "client@bank.com", "tel": "+22500000001", "role": RoleEnum.client, "password": "client123"},
        {"nom": "Martin", "prenom": "Bob", "email": "caissier@bank.com", "tel": "+22500000002", "role": RoleEnum.caissier, "password": "caissier123"},
        {"nom": "Diallo", "prenom": "Fatou", "email": "gestionnaire@bank.com", "tel": "+22500000003", "role": RoleEnum.gestionnaire, "password": "gestionnaire123"},
    ]

    for u in users:
        if not Utilisateur.query.filter_by(email=u["email"]).first():
            user = Utilisateur(nom=u["nom"], prenom=u["prenom"], email=u["email"], telephone=u["tel"], role=u["role"])
            user.set_password(u["password"])
            db.session.add(user)
            db.session.flush()

            if u["role"] == RoleEnum.client:
                compte = Compte(numero=random_account_number(), solde=500000.00, utilisateur_id=user.id)
                db.session.add(compte)

    db.session.commit()
    print("✅ Seed terminé !")
    print("  client@bank.com / client123")
    print("  caissier@bank.com / caissier123")
    print("  gestionnaire@bank.com / gestionnaire123")
