"""Passerelle de paiement mobile money.

SimulatedProvider: aucun appel externe, echec si numero invalide (demo et tests).
FedaPayProvider: environnement sandbox FedaPay (https://sandbox-api.fedapay.com) si
FEDAPAY_SECRET_KEY est defini. KkiaPay peut etre ajoute avec la meme interface.
"""
import os
import re
import uuid

import httpx

MODES = {"mtn": "mtn_open", "moov": "moov", "celtiis": "celtiis_bj"}


def normalize_phone(phone: str) -> str | None:
    """Numeros beninois: 10 chiffres commencant par 01 (format en vigueur depuis fin 2024),
    avec ou sans indicatif +229. Les anciens numeros a 8 chiffres sont convertis en 01XXXXXXXX."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("229"):
        digits = digits[3:]
    if len(digits) == 8:
        digits = "01" + digits
    return digits if len(digits) == 10 and digits.startswith("01") else None


class SimulatedProvider:
    name = "simulation"

    def payout(self, phone, operator, amount, description):
        p = normalize_phone(phone)
        ref = "SIM-" + uuid.uuid4().hex[:12].upper()
        if p is None:
            return {"reference": ref, "status": "echec", "message": "Numéro invalide"}
        if p.endswith("0000"):
            return {"reference": ref, "status": "echec", "message": "Compte mobile money inactif (simulation)"}
        return {"reference": ref, "status": "reussi", "message": f"Versement simulé vers {operator.upper()} {p}"}

    def collect(self, phone, operator, amount, description):
        return self.payout(phone, operator, amount, description)


class FedaPayProvider:
    name = "fedapay"

    def __init__(self, secret, base="https://sandbox-api.fedapay.com/v1"):
        self.base, self.h = base, {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}

    def _customer(self, phone):
        return {"firstname": "Assure", "lastname": "AGRISAT", "phone_number": {"number": "+229" + phone, "country": "bj"}}

    def payout(self, phone, operator, amount, description):
        p = normalize_phone(phone)
        if p is None:
            return {"reference": "", "status": "echec", "message": "Numéro invalide"}
        try:
            with httpx.Client(timeout=20) as c:
                r = c.post(f"{self.base}/payouts", headers=self.h, json={
                    "amount": int(round(amount)), "currency": {"iso": "XOF"}, "mode": MODES.get(operator, "mtn_open"),
                    "customer": self._customer(p), "description": description})
                r.raise_for_status()
                po = r.json().get("v1/payout", r.json())
                c.put(f"{self.base}/payouts/start", headers=self.h, json={"payouts": [{"id": po["id"]}]})
            return {"reference": str(po.get("reference", po["id"])), "status": "en_cours", "message": "Soumis à FedaPay"}
        except Exception as e:  # pragma: no cover
            return {"reference": "", "status": "echec", "message": f"FedaPay: {e}"[:250]}

    def collect(self, phone, operator, amount, description):
        p = normalize_phone(phone)
        try:
            with httpx.Client(timeout=20) as c:
                r = c.post(f"{self.base}/transactions", headers=self.h, json={
                    "amount": int(round(amount)), "currency": {"iso": "XOF"}, "description": description,
                    "customer": self._customer(p)})
                r.raise_for_status()
                tx = r.json().get("v1/transaction", r.json())
            return {"reference": str(tx.get("reference", tx["id"])), "status": "en_cours", "message": "Demande de paiement envoyée"}
        except Exception as e:  # pragma: no cover
            return {"reference": "", "status": "echec", "message": f"FedaPay: {e}"[:250]}


def get_provider():
    key = os.environ.get("FEDAPAY_SECRET_KEY")
    return FedaPayProvider(key) if key else SimulatedProvider()
