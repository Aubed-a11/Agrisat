"""Parcours complet: souscription, calcul, validation, paiement, rapport, USSD."""
import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

from fastapi.testclient import TestClient  # noqa: E402
from api.main import app  # noqa: E402


def login(c, user):
    t = c.post("/api/auth/login", data={"username": user, "password": "agrisat2026"}).json()
    return {"Authorization": "Bearer " + t["access_token"]}


def test_end_to_end():
    with TestClient(app) as c:
        H = login(c, "assureur")
        assert c.get("/api/health").json()["status"] == "ok"
        season = c.get("/api/season?crop=coton&asof=2025-08-25", headers=H).json()
        assert len(season) == 27
        q = c.post("/api/pricing/quote", headers=H, json={"commune_id": 5, "crop": "coton", "area_ha": 2}).json()
        assert q["premium_farmer"] + q["premium_subsidy"] == q["premium_total"] or abs(
            q["premium_farmer"] + q["premium_subsidy"] - q["premium_total"]) <= 1

        HC = login(c, "coop")
        assert c.post("/api/payouts/compute", headers=HC, json={}).status_code == 403
        bad = c.post("/api/farmers", headers=HC, json={"full_name": "Sans consentement", "phone": "0197000001",
                                                        "commune_id": 1, "consent": False})
        assert bad.status_code == 400

        r = c.post("/api/payouts/compute", headers=H, json={}).json()
        assert r["policies_checked"] > 0
        ids = [p["id"] for p in c.get("/api/payouts", headers=H).json()]
        c.post("/api/payouts/validate", headers=H, json={"ids": ids})
        paid = c.post("/api/payouts/pay", headers=H, json={}).json()
        assert paid["paid"] + paid["failed"] == len(ids)
        for p in c.get("/api/payouts", headers=H).json():
            assert abs(p["to_credit"] + p["to_farmer"] - p["amount"]) < 1 or p["status"] == "echec"

        assert c.get("/api/reports/export.pdf", headers=H).status_code == 200
        assert c.get("/api/reports/export.xlsx", headers=H).status_code == 200
        phone = c.get("/api/farmers", headers=H).json()[0]["phone"]
        menu = c.post("/api/ussd", data={"phoneNumber": phone, "text": ""}).text
        assert menu.startswith("CON")
        assert c.post("/api/ussd", data={"phoneNumber": "0100000000", "text": ""}).text.startswith("END")
