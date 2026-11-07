"""Referentiel des 27 communes du Nord Benin couvertes par AGRISAT.

Coordonnees approximatives des chefs lieux (pour la carte et le generateur
synthetique). Les limites officielles sont chargees depuis geoBoundaries en
production (voir agrisat_core/gee/extract_gee.py).
"""

COMMUNES = [
    # id, nom, departement, lat, lon
    (1, "Banikoara", "Alibori", 11.298, 2.438),
    (2, "Gogounou", "Alibori", 10.839, 2.836),
    (3, "Kandi", "Alibori", 11.134, 2.938),
    (4, "Karimama", "Alibori", 12.069, 3.185),
    (5, "Malanville", "Alibori", 11.862, 3.386),
    (6, "Ségbana", "Alibori", 10.928, 3.694),
    (7, "Bembèrèkè", "Borgou", 10.228, 2.663),
    (8, "Kalalé", "Borgou", 10.292, 3.381),
    (9, "N'Dali", "Borgou", 9.861, 2.718),
    (10, "Nikki", "Borgou", 9.940, 3.210),
    (11, "Parakou", "Borgou", 9.337, 2.630),
    (12, "Pèrèrè", "Borgou", 9.799, 2.993),
    (13, "Sinendé", "Borgou", 10.346, 2.379),
    (14, "Tchaourou", "Borgou", 8.886, 2.597),
    (15, "Boukoumbé", "Atacora", 10.178, 1.107),
    (16, "Cobly", "Atacora", 10.478, 0.971),
    (17, "Kérou", "Atacora", 10.825, 2.109),
    (18, "Kouandé", "Atacora", 10.332, 1.691),
    (19, "Matéri", "Atacora", 10.698, 1.063),
    (20, "Natitingou", "Atacora", 10.304, 1.380),
    (21, "Péhunco", "Atacora", 10.228, 1.898),
    (22, "Tanguiéta", "Atacora", 10.621, 1.264),
    (23, "Toucountouna", "Atacora", 10.492, 1.377),
    (24, "Bassila", "Donga", 9.008, 1.665),
    (25, "Copargo", "Donga", 9.838, 1.548),
    (26, "Djougou", "Donga", 9.708, 1.666),
    (27, "Ouaké", "Donga", 9.662, 1.385),
]

CROPS = ["coton", "mais"]

# Parametres agronomiques et economiques par defaut (a confirmer avec les partenaires)
CROP_PARAMS = {
    "coton": {
        "label": "Coton",
        "sowing_window": (140, 191),   # jour de l'annee: 20 mai au 10 juillet
        "phase_lengths": [40, 40, 40, 45],
        "phase_names": ["Semis et levée", "Croissance végétative", "Floraison et formation", "Maturation"],
        "phase_weights": [0.20, 0.30, 0.50, 0.0],   # phase 4 (octobre, saison seche): couverte par la garantie exces de pluie
        "ky": [0.25, 0.45, 0.85, 0.35],
        "kc": [0.45, 0.80, 1.15, 0.70],
        "base_yield": 1050.0,          # kg/ha
        "trend": 6.0,                  # kg/ha/an
        "price": 300.0,                # FCFA/kg, prix coton graine
        "sum_insured_ha": 150000.0,    # FCFA/ha, ~ cout des intrants
    },
    "mais": {
        "label": "Maïs",
        "sowing_window": (125, 181),   # 5 mai au 30 juin
        "phase_lengths": [30, 35, 40, 30],
        "phase_names": ["Semis et levée", "Croissance végétative", "Floraison et remplissage", "Maturation"],
        "phase_weights": [0.15, 0.30, 0.45, 0.10],
        "ky": [0.30, 0.45, 1.00, 0.25],
        "kc": [0.40, 0.80, 1.20, 0.60],
        "base_yield": 1350.0,
        "trend": 12.0,
        "price": 180.0,                # FCFA/kg: 85 % du prix de detail moyen Natitingou et Parakou 2019 a 2024
        "sum_insured_ha": 100000.0,
    },
}

PRICING_DEFAULTS = {
    "subsidy_rate": 0.80,
    "expense_rate": 0.25,
    "cost_of_capital": 0.10,
    "cvar_level": 0.995,
    "n_sims": 10000,
    "max_gross_rate": 0.10,     # plafond du taux de prime commerciale lors de l'optimisation
}


def _real_centroids():
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parents[1] / "data" / "external" / "centroids.json"
    return {int(k): v for k, v in json.load(open(f)).items()} if f.exists() else {}


def commune_list():
    """Centroides reels (geoBoundaries) quand ils sont disponibles."""
    rc = _real_centroids()
    return [dict(id=i, name=n, department=d, lat=rc.get(i, (la, lo))[0], lon=rc.get(i, (la, lo))[1])
            for i, n, d, la, lo in COMMUNES]


def annual_rain_normal(lat, lon):
    """Normale annuelle approximative (mm): gradient sud-nord et ouest plus humide (Atacora, Donga)."""
    base = 1160 - (lat - 9.0) * 110
    west = max(0.0, 2.0 - lon) * 35
    return float(max(820.0, base + west))
