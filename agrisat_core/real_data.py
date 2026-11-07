"""Exploitation des donnees REELLES deja recuperees (data/external).

Sources:
  * Rendements, superficies et productions de mais par commune, 1995 a 2023, Direction de la
    Statistique Agricole (DSA, MAEP), publies dans le depot GitHub steftdg/ZeaMays-Yield-Prediction-Benin.
  * FAOSTAT, mais, Benin, 1961 a 2024 (meme depot).
  * Prix de detail du mais a Cotonou, Natitingou et Parakou, 2013 a 2024 (depot
    GensericAguidissou/Analyse-Price-Maize-Benin, licence MIT, donnees de type WFP VAM).
  * Limites communales geoBoundaries gbOpen BEN ADM2 (CC BY 4.0).

Produit data/processed/real_maize.json: controle qualite, tendance et pertes par commune,
comparaison DSA et FAOSTAT, et un contrat d'assurance RENDEMENT PAR ZONE (area-yield index)
tarife directement sur les rendements communaux observes. Ce contrat ne depend d'aucune
donnee climatique: il est calculable des maintenant sur donnees reelles.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .actuarial.pricing import premium_from_payouts
from .actuarial.basis_risk import LOSS_THRESHOLD

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external"
OUT = ROOT / "data" / "processed"

COVERAGE_LEVELS = [0.70, 0.80, 0.90]
PRODUCER_PRICE_RATIO = 0.85   # prix bord champ estime a 85 pour cent du prix de detail


def _clean(o):
    """Remplace NaN et infinis par None (JSON strict)."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    return o


def available():
    return (EXT / "dsa_mais_communes.csv").exists()


def quality_flags(df):
    """Signale les valeurs aberrantes: hors de [300, 3500] kg/ha ou ecart de plus de 3 ecarts types
    (en log) a la mediane de la commune."""
    df = df.copy()
    df["flag"] = ""
    for cid, g in df.groupby("commune_id"):
        ly = np.log(g.yield_kg_ha.clip(lower=1))
        med, sd = ly.median(), ly.std()
        z = (ly - med) / (sd if sd > 0 else 1)
        bad = (g.yield_kg_ha < 300) | (g.yield_kg_ha > 3500) | (z.abs() > 3)
        df.loc[g.index[bad], "flag"] = "aberrant"
    return df


def _trend(years, y):
    a, b = np.polyfit(years, y, 1)
    return a * years + b, float(a)


def maize_price():
    p = pd.read_csv(EXT / "prix_mais_detail.csv", parse_dates=["date"])
    recent = p[p.date.dt.year >= 2019]
    north = recent[["natitingou", "parakou"]].mean().mean()
    return {"retail_north_mean_2019_2024": round(float(north), 1),
            "producer_price_estimate": round(float(north * PRODUCER_PRICE_RATIO), 0),
            "series": p.assign(date=p.date.dt.strftime("%Y-%m")).to_dict(orient="records")}


def diversification_factor(rel_matrix, weights, coverage, n_sims=10000, seed=0, level=0.995):
    """Reechantillonnage d'annees completes (conserve la correlation spatiale entre communes)."""
    from .actuarial.pricing import var_cvar
    rng = np.random.default_rng(seed)
    C, Y = rel_matrix.shape
    bw = 1.06 * np.nanstd(rel_matrix, axis=1) * Y ** -0.2
    yrs = rng.integers(0, Y, n_sims)
    sims = rel_matrix[:, yrs].T + rng.normal(0, 1, (n_sims, C)) * bw[None, :]
    frac = np.maximum(0, coverage - sims) / coverage
    port = (frac * weights[None, :]).sum(axis=1)
    _, pc = var_cvar(port, level)
    port_cap = max(pc - port.mean(), 0)
    sa = 0.0
    for c in range(C):
        _, cc = var_cvar(frac[:, c], level)
        sa += max(cc - frac[:, c].mean(), 0) * weights[c]
    return min(1.0, port_cap / sa) if sa > 0 else 1.0


def area_yield_contract(rel, coverage, sum_insured, n_sims=10000, seed=0, **pricing):
    """Indemnite = max(0, couverture x tendance moins rendement) / (couverture x tendance) x somme assuree.
    rel: rendements relatifs a la tendance (historique). Simulation par bootstrap lisse (noyau gaussien)."""
    rel = np.asarray(rel, float)
    burn = np.maximum(0, coverage - rel) / coverage
    rng = np.random.default_rng(seed)
    bw = 1.06 * rel.std() * len(rel) ** -0.2
    sims = rng.choice(rel, n_sims) + rng.normal(0, bw, n_sims)
    frac = np.maximum(0, coverage - sims) / coverage
    pr = premium_from_payouts(frac, sum_insured, **pricing)
    pr["burn_rate_historical"] = round(float(burn.mean()), 5)
    pr["years_paid_historical"] = int((burn > 0).sum())
    return pr, burn


def build(sum_insured_ha=100000.0, subsidy_rate=0.8, expense_rate=0.25, cost_of_capital=0.10):
    if not available():
        return None
    dsa = quality_flags(pd.read_csv(EXT / "dsa_mais_communes.csv"))
    fao = pd.read_csv(EXT / "faostat_benin_mais.csv")
    price = maize_price()
    communes = []
    # matrice commune x annee des rendements relatifs, ponderations = superficie recente
    rel_rows, weights = [], []
    for cid, g in dsa.groupby("commune_id"):
        ok = g[g.flag == ""]
        a, b = np.polyfit(ok.year.values, ok.yield_kg_ha.values, 1)
        r = (g.yield_kg_ha / (a * g.year + b)).where(g.flag == "")
        rel_rows.append(r.fillna(r.median()).values)
        weights.append(float(g.sort_values("year").area_ha.iloc[-1]))
    rel_m, wts = np.array(rel_rows), np.array(weights)
    div = {cov: diversification_factor(rel_m, wts, cov) for cov in COVERAGE_LEVELS}
    for cid, g in dsa.groupby("commune_id"):
        g = g.sort_values("year")
        ok = g[g.flag == ""]
        trend_ok, slope = _trend(ok.year.values, ok.yield_kg_ha.values)
        a, b = np.polyfit(ok.year.values, ok.yield_kg_ha.values, 1)
        g = g.assign(trend=a * g.year + b)
        g["rel"] = g.yield_kg_ha / g.trend
        rel_ok = g.loc[g.flag == "", "rel"].values
        contracts = {}
        for cov in COVERAGE_LEVELS:
            pr, burn = area_yield_contract(rel_ok, cov, sum_insured_ha, subsidy_rate=subsidy_rate,
                                           expense_rate=expense_rate, cost_of_capital=cost_of_capital, seed=cid,
                                           diversification=div[cov])
            contracts[str(cov)] = pr
        loss = (1 - g.rel).clip(lower=0)
        communes.append({
            "commune_id": int(cid), "commune": g.commune.iloc[0],
            "n_years": int(len(g)), "n_flagged": int((g.flag != "").sum()),
            "mean_yield": round(float(ok.yield_kg_ha.mean()), 0),
            "trend_kg_ha_per_year": round(slope, 1),
            "cv_detrended": round(float(np.std(rel_ok)), 3),
            "loss_years": int(((1 - rel_ok) > LOSS_THRESHOLD).sum()),
            "worst_years": [int(y) for y in g.loc[g.flag == ""].sort_values("rel").year.head(3)],
            "series": [{"year": int(r.year), "yield": round(float(r.yield_kg_ha), 0), "trend": round(float(r.trend), 0),
                        "area_ha": None if pd.isna(r.area_ha) else round(float(r.area_ha), 0),
                        "rel": round(float(r.rel), 3), "flag": r.flag,
                        "loss_rel": round(float(l), 3)} for r, l in zip(g.itertuples(), loss)],
            "area_yield": contracts,
        })
    # comparaison: rendement moyen pondere des 27 communes du Nord et FAOSTAT national
    w = dsa[dsa.flag == ""].assign(prod=lambda x: x.yield_kg_ha * x.area_ha)
    north = w.groupby("year").agg(prod=("prod", "sum"), area=("area_ha", "sum"))
    north["yield_north"] = north["prod"] / north["area"]
    cmp = north[["yield_north"]].join(fao.set_index("year")["yield_kg_ha"].rename("yield_faostat"), how="left").reset_index()
    corr = cmp.dropna().corr().loc["yield_north", "yield_faostat"]
    out = {
        "sources": json.load(open(EXT / "sources.json", encoding="utf-8")) if (EXT / "sources.json").exists() else [],
        "years": [int(dsa.year.min()), int(dsa.year.max())],
        "n_observations": int(len(dsa)), "n_flagged": int((dsa.flag != "").sum()),
        "flagged": dsa[dsa.flag != ""][["commune", "year", "yield_kg_ha"]].to_dict(orient="records"),
        "communes": communes,
        "north_vs_faostat": [{"year": int(r.year), "north": round(float(r.yield_north), 0),
                              "faostat": None if pd.isna(r.yield_faostat) else round(float(r.yield_faostat), 0)}
                             for r in cmp.itertuples()],
        "north_vs_faostat_corr": round(float(corr), 3),
        "faostat": [{"year": int(r.year), "yield": round(float(r.yield_kg_ha), 0), "area_ha": round(float(r.area_ha), 0)}
                    for r in fao.itertuples() if r.year >= 1990],
        "price": price,
        "diversification": {str(k): round(v, 3) for k, v in div.items()},
        "params": {"sum_insured_ha": sum_insured_ha, "coverage_levels": COVERAGE_LEVELS,
                   "subsidy_rate": subsidy_rate, "expense_rate": expense_rate, "cost_of_capital": cost_of_capital},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(_clean(out), open(OUT / "real_maize.json", "w", encoding="utf-8"), ensure_ascii=False, allow_nan=False)
    return out


def write_yields_for_pipeline():
    """Ecrit data/raw/rendements_communes.csv (mais reel DSA, valeurs aberrantes exclues)."""
    dsa = quality_flags(pd.read_csv(EXT / "dsa_mais_communes.csv"))
    dsa = dsa[dsa.flag == ""][["commune_id", "crop", "year", "yield_kg_ha", "source"]]
    path = ROOT / "data" / "raw" / "rendements_communes.csv"
    dsa.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    r = build()
    print(f"{r['n_observations']} observations, {r['n_flagged']} aberrantes, correlation Nord et FAOSTAT {r['north_vs_faostat_corr']}")
