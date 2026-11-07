"""Donnees de demonstration FICTIVES (aucune donnee personnelle reelle)."""
import random

from .auth import hash_password
from .models import User, Organisation, Farmer, Policy
from .routers.operations import create_policy_internal, PolicyIn
from .store import get_store

FIRST = ["Bio", "Sabi", "Gounou", "Orou", "Yarou", "Bake", "Chabi", "Worou", "Soumaila", "Issifou", "Adamou", "Moussa",
         "Kora", "Sanni", "Zakari", "Bawa", "Tamou", "Doko", "Kpatchiti", "N'Tcha", "Yaya", "Saka", "Mama", "Gado"]
LAST = ["Guera", "Sounon", "Bani", "Seko", "Kpéra", "Gani", "Sika", "Boni", "Dramane", "Tchabi", "Nassourou",
        "Gnanhoui", "Yerima", "Tokpanou", "Sambieni", "N'Dah", "Kassa", "Yacoubou"]
LANG = {"Alibori": ["bariba", "dendi", "fr"], "Borgou": ["bariba", "fr"], "Atacora": ["ditammari", "fr"], "Donga": ["fr", "bariba"]}


def seed(db):
    if db.query(User).count():
        return
    rnd = random.Random(2026)
    s = get_store()
    orgs = [Organisation(name="Union communale des producteurs de Banikoara", kind="cooperative", commune_id=1),
            Organisation(name="Union communale des producteurs de Kandi", kind="cooperative", commune_id=3),
            Organisation(name="Coopérative des producteurs de Djougou", kind="cooperative", commune_id=26),
            Organisation(name="Coopérative agricole de Natitingou", kind="cooperative", commune_id=20),
            Organisation(name="Caisse de microfinance rurale du Nord (fictive)", kind="imf", commune_id=11)]
    db.add_all(orgs)
    db.flush()
    users = [("admin", "Administrateur AGRISAT", "admin", None), ("assureur", "Service actuariat de l'assureur", "assureur", None),
             ("coop", "Agent, Union de Banikoara", "cooperative", orgs[0].id), ("imf", "Agent de crédit, caisse du Nord", "imf", orgs[4].id),
             ("partenaire", "Suivi FNDA et MAEP", "partenaire", None)]
    for u, n, r, o in users:
        db.add(User(username=u, full_name=n, role=r, password_hash=hash_password("agrisat2026"), organisation_id=o))
    db.flush()
    admin = db.query(User).filter_by(username="assureur").first()
    coop_by_commune = {o.commune_id: o.id for o in orgs if o.kind == "cooperative"}
    campaign = s.current_campaign
    k = 0
    for cid, com in s.communes.items():
        for _ in range(rnd.randint(3, 6)):
            k += 1
            f = Farmer(full_name=f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", phone=f"01{rnd.choice('596')}{rnd.randint(1000000, 9999999)}",
                       operator=rnd.choice(["mtn", "mtn", "moov", "celtiis"]), language=rnd.choice(LANG[com["department"]]),
                       commune_id=cid, village=f"Village {rnd.randint(1, 12)}", cooperative_id=coop_by_commune.get(cid),
                       consent=True, is_test_data=True)
            if k % 23 == 0:
                f.phone = f.phone[:6] + "0000"  # compte inactif simule, pour tester les echecs de paiement
            db.add(f)
            db.flush()
            for crop in ("coton", "mais"):
                if crop == "coton" and com["department"] in ("Donga",) and rnd.random() < 0.5:
                    continue
                if rnd.random() < 0.25 and crop == "mais":
                    continue
                c = s.contract(cid, crop)
                fn = c["basis_risk"]["false_negative_rate"]
                index_ok = c.get("validated", True) and (fn is None or fn <= 0.20)
                if crop == "mais" and s.real and (not index_ok or rnd.random() < 0.5):
                    product = "rendement_zone"
                    # campagnes : derniere annee avec statistiques DSA (indemnites calculables) et campagne en cours
                    camp = s.real["years"][1] if rnd.random() < 0.5 else campaign
                elif index_ok:
                    product, camp = "indice_pluie", campaign
                else:
                    continue
                credit = rnd.random() < 0.5
                si_ha = c["sum_insured_ha"]
                body = PolicyIn(farmer_id=f.id, crop=crop, area_ha=round(rnd.uniform(0.75, 4.0), 2), campaign=camp,
                                product=product,
                                premium_payment_mode="retenue_credit" if credit else "mobile_money",
                                credit_amount=round(si_ha * rnd.uniform(0.8, 3.0), -3) if credit else None,
                                institution_id=orgs[4].id if credit else None)
                p = create_policy_internal(db, body, admin, send_sms=False)
                if not p.premium_paid and rnd.random() < 0.85:
                    p.premium_paid, p.status = True, "active"
    db.commit()
