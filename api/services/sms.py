"""Alertes SMS et vocales.

Les modeles sont rediges en francais. Les versions en bariba, dendi, ditammari et fon
doivent etre traduites ET validees par des locuteurs natifs avant tout envoi reel:
tant qu'elles ne le sont pas, le message part en francais et la langue cible est
signalee comme "traduction a valider". Aucune traduction automatique n'est utilisee.
"""
import os

import httpx

TEMPLATES = {
    "vigilance": "AGRISAT: la pluie de la phase {phase} est faible a {commune} ({index} mm sur {trigger} mm attendus). "
                 "Votre assurance {crop} suit la situation.",
    "declenchement": "AGRISAT: l'assurance {crop} est declenchee a {commune} pour la phase {phase}. "
                     "Indemnite prevue: {amount} FCFA, versee par mobile money apres validation.",
    "paiement": "AGRISAT: {amount} FCFA ont ete verses sur votre compte {operator}. Ref {ref}.",
    "paiement_credit": "AGRISAT: {credit} FCFA ont rembourse votre credit intrants et {amount} FCFA vous ont ete verses.",
    "souscription": "AGRISAT: votre police {number} ({crop}, {area} ha) est enregistree. Prime a payer: {premium} FCFA.",
    "prime_payee": "AGRISAT: prime recue. Votre assurance {crop} {campaign} est active.",
}

VALIDATED_TRANSLATIONS = {}  # {(langue, categorie): texte}, a remplir apres validation par des locuteurs natifs
LANGUAGES = {"fr": "Français", "bariba": "Bariba", "dendi": "Dendi", "ditammari": "Ditammari", "fon": "Fon"}


def render(category, language, **kw):
    tpl = VALIDATED_TRANSLATIONS.get((language, category))
    note = None
    if tpl is None:
        tpl = TEMPLATES[category]
        if language != "fr":
            note = f"Traduction {LANGUAGES.get(language, language)} à valider, envoyé en français"
    return tpl.format(**kw), note


class Gateway:
    def __init__(self):
        self.user = os.environ.get("AT_USERNAME")
        self.key = os.environ.get("AT_API_KEY")
        self.provider = "africastalking" if self.user and self.key else "simulation"

    def send(self, phone, body):
        if self.provider == "simulation":
            return "envoye"
        try:  # pragma: no cover
            r = httpx.post("https://api.africastalking.com/version1/messaging",
                           headers={"apiKey": self.key, "Accept": "application/json"},
                           data={"username": self.user, "to": "+229" + phone[-10:], "message": body}, timeout=15)
            return "envoye" if r.status_code < 300 else "echec"
        except Exception:
            return "echec"
