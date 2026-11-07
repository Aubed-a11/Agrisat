"""Chargement en memoire des resultats du pipeline (data/processed)."""
import json
import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"


class Store:
    def __init__(self):
        self.reload()

    def reload(self):
        if not (PROC / "meta.json").exists():
            raise RuntimeError("Donnees absentes. Lancer d'abord: npm run setup (ou python -m agrisat_core.pipeline)")
        self.meta = json.load(open(PROC / "meta.json", encoding="utf-8"))
        self.contracts = json.load(open(PROC / "contracts.json", encoding="utf-8"))
        self.ml = json.load(open(PROC / "ml_results.json"))
        self.portfolio = json.load(open(PROC / "portfolio.json"))
        self.climatology = json.load(open(PROC / "climatology.json"))
        self.history = pd.read_csv(PROC / "historical_payouts.csv")
        self.exposure = pd.read_csv(PROC / "exposure.csv")
        cube = np.load(PROC / "climate_cube.npz")
        self.years = [int(y) for y in cube["years"]]
        self.rain, self.tmax, self.et0, self.ndvi = cube["rain"], cube["tmax"], cube["et0"], cube["ndvi"]
        self.generator = pickle.load(open(PROC / "rain_generator.pkl", "rb"))
        self.communes = {c["id"]: c for c in self.meta["communes"]}
        self.cids = [c["id"] for c in self.meta["communes"]]
        self.real = json.load(open(PROC / "real_maize.json", encoding="utf-8")) if (PROC / "real_maize.json").exists() else None
        self.findings = json.load(open(PROC / "findings.json", encoding="utf-8")) if (PROC / "findings.json").exists() else None
        geo = PROC.parent / "external" / "communes_nord.geojson"
        self.geo = json.load(open(geo, encoding="utf-8")) if geo.exists() else None
        self._contract_map = {(c["commune_id"], c["crop"]): c for c in self.contracts}

    def contract(self, commune_id, crop):
        return self._contract_map.get((int(commune_id), crop))

    def cidx(self, commune_id):
        return self.cids.index(int(commune_id))

    @property
    def current_campaign(self):
        return self.years[-1]


@lru_cache
def get_store() -> Store:
    return Store()
