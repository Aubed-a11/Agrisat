"""Generateur de donnees SYNTHETIQUES realistes pour le Nord Benin.

Objectif: faire tourner toute la chaine hors ligne tant que les vraies donnees
(CHIRPS, MODIS, ERA5 Land via Earth Engine et rendements communaux du MAEP) ne sont
pas branchees. Les sorties suivent exactement le schema des vraies donnees.

Toute donnee produite ici est marquee source="synthetique" et ne doit jamais servir
a une tarification commerciale.

Principe:
  1. pluie "vraie" par chaine de Markov et loi Gamma, saisonnalite unimodale, correlation
     spatiale (facteur regional, departemental, local) et variabilite interannuelle;
  2. pluie "satellite" = pluie vraie + erreur d'estimation (source du risque de base);
  3. temperature, evapotranspiration, humidite du sol (seau), NDVI (verdissement retarde,
     composites 16 jours, trous nuageux en saison);
  4. rendements par bilan hydrique de la culture par phase (type WRSI, coefficients ky FAO 33)
     + choc de pluies extremes en maturation + effets non climatiques (ravageurs, gestion).
"""
import numpy as np
import pandas as pd
from scipy import stats

from .communes import COMMUNES, CROP_PARAMS, annual_rain_normal
from . import phenology as ph

MONTH_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
MONTH_OF_DAY = np.repeat(np.arange(12), MONTH_DAYS)
MONTH_FRAC = np.array([0.0, 0.004, 0.02, 0.05, 0.10, 0.14, 0.17, 0.21, 0.19, 0.08, 0.008, 0.0])
MONTH_FRAC = MONTH_FRAC / MONTH_FRAC.sum()
P_WET = np.array([0.008, 0.015, 0.05, 0.12, 0.25, 0.38, 0.48, 0.56, 0.48, 0.22, 0.03, 0.008])
GAMMA_SHAPE = 0.78
TMAX_CLIM = np.array([34.5, 36.8, 38.2, 37.6, 35.0, 32.4, 30.6, 29.9, 30.8, 33.0, 34.8, 34.0])


def _dates(year):
    d = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    return d[~((d.month == 2) & (d.day == 29))]


def generate_climate(years=range(1981, 2026), seed=42):
    rng = np.random.default_rng(seed)
    years = list(years)
    C, Y = len(COMMUNES), len(years)
    depts = sorted({c[2] for c in COMMUNES})
    dept_idx = np.array([depts.index(c[2]) for c in COMMUNES])
    normals = np.array([annual_rain_normal(c[3], c[4]) for c in COMMUNES])

    # parametres de Markov par commune et par jour
    wet_scale = (normals / 1050.0) ** 0.5
    p = np.clip(P_WET[MONTH_OF_DAY][None, :] * wet_scale[:, None], 0.002, 0.85)  # (C, 365)
    p11 = p + 0.30 * (1 - p)
    p01 = p * (1 - p11) / (1 - p)
    month_total = normals[:, None] * MONTH_FRAC[None, :]                        # (C, 12)
    mean_wet = month_total[:, MONTH_OF_DAY] / (MONTH_DAYS[MONTH_OF_DAY][None, :] * p)
    scale = np.maximum(np.nan_to_num(mean_wet / GAMMA_SHAPE), 0.5)

    rain_true = np.zeros((C, Y, 365), np.float32)
    for yi in range(Y):
        # variabilite interannuelle: regionale + departementale + locale
        yr_reg = rng.normal(0, 0.14)
        yr_dep = rng.normal(0, 0.07, len(depts))[dept_idx]
        yr_loc = rng.normal(0, 0.05, C)
        amount_factor = np.exp(yr_reg + yr_dep + yr_loc)
        onset_shift = rng.normal(1.0, 0.28)          # installation precoce ou tardive (mai, juin)
        occ_factor = np.ones((C, 365))
        occ_factor[:, 120:181] *= np.clip(onset_shift + rng.normal(0, 0.08, (C, 1)), 0.5, 1.6)
        occ_factor[:, 181:260] *= 1.12
        # poche seche aleatoire en juillet-septembre (certaines annees)
        if rng.random() < 0.35:
            start = rng.integers(195, 255)
            length = rng.integers(10, 22)
            occ_factor[:, start:start + length] *= rng.uniform(0.15, 0.5)
        wet = np.zeros(C, bool)
        for d in range(365):
            g = rng.normal()
            dep = rng.normal(size=len(depts))[dept_idx]
            z = np.sqrt(0.30) * g + np.sqrt(0.25) * dep + np.sqrt(0.45) * rng.normal(size=C)
            u = stats.norm.cdf(z)
            prob = np.where(wet, p11[:, d], p01[:, d]) * occ_factor[:, d]
            wet = u < np.clip(prob, 0, 0.95)
            g2 = np.sqrt(0.35) * rng.normal() + np.sqrt(0.65) * rng.normal(size=C)
            u2 = np.clip(stats.norm.cdf(g2), 1e-6, 1 - 1e-6)
            amt = stats.gamma.ppf(u2, GAMMA_SHAPE, scale=scale[:, d]) * amount_factor
            rain_true[:, yi, d] = np.where(wet, np.minimum(amt, 220.0), 0.0)

    # pluie "satellite": erreur multiplicative + pluies legeres manquees + petites fausses pluies
    err = rng.lognormal(0, 0.35, rain_true.shape).astype(np.float32)
    rain_sat = rain_true * err
    rain_sat[(rain_true < 4) & (rng.random(rain_true.shape) < 0.35)] = 0.0
    false_rain = (rain_true == 0) & (rng.random(rain_true.shape) < 0.015)
    rain_sat[false_rain] = rng.exponential(3.0, false_rain.sum())
    rain_sat = np.round(rain_sat, 1)

    # temperature maximale et evapotranspiration de reference
    tmax = (TMAX_CLIM[MONTH_OF_DAY][None, None, :]
            + (np.array([c[3] for c in COMMUNES])[:, None, None] - 10.0) * 0.6
            + rng.normal(0, 1.2, rain_true.shape)
            - 2.2 * (rain_true > 5)).astype(np.float32)
    et0 = np.clip(2.6 + 0.30 * (tmax - 29.0), 2.5, 7.5).astype(np.float32)

    # humidite du sol (seau de 120 mm) et NDVI
    wmax = 120.0
    sm = np.zeros_like(rain_true)
    ndvi_daily = np.zeros_like(rain_true)
    w = np.full((C, Y), 15.0)
    gr = np.full((C, Y), 0.05)
    for d in range(365):
        aet = et0[:, :, d] * 0.75 * (w / wmax)
        w = np.clip(w + rain_true[:, :, d] - aet, 0, wmax)
        sm[:, :, d] = 0.05 + 0.33 * w / wmax
        target = np.clip(1.25 * w / wmax, 0, 1)
        gr = gr + np.where(target > gr, 0.045, 0.025) * (target - gr)
        ndvi_daily[:, :, d] = 0.20 + 0.52 * gr
    ndvi_daily += rng.normal(0, 0.015, ndvi_daily.shape).astype(np.float32)

    return dict(years=years, rain_true=rain_true, rain=rain_sat, tmax=tmax, et0=et0,
                sm=sm.astype(np.float32), ndvi_daily=ndvi_daily.astype(np.float32), rng=rng)


def ndvi_composites(ndvi_daily, years, first_year=2000, seed=7):
    """Composites MOD13Q1 (16 jours, valeur max) avec trous nuageux, a partir de 2000."""
    rng = np.random.default_rng(seed)
    rows = []
    starts = list(range(0, 365, 16))
    for yi, yr in enumerate(years):
        if yr < first_year:
            continue
        dates = _dates(yr)
        for ci, c in enumerate(COMMUNES):
            for s in starts:
                val = float(ndvi_daily[ci, yi, s:s + 16].max())
                cloudy = 180 <= s <= 260 and rng.random() < 0.22
                rows.append((c[0], dates[s].strftime("%Y-%m-%d"), None if cloudy else round(val, 4)))
    return pd.DataFrame(rows, columns=["commune_id", "date", "ndvi"])


def climate_to_frame(clim):
    rows = []
    for yi, yr in enumerate(clim["years"]):
        dates = _dates(yr).strftime("%Y-%m-%d")
        for ci, c in enumerate(COMMUNES):
            rows.append(pd.DataFrame({
                "commune_id": c[0], "date": dates,
                "rain": clim["rain"][ci, yi], "tmax": np.round(clim["tmax"][ci, yi], 1),
                "et0": np.round(clim["et0"][ci, yi], 2), "sm": np.round(clim["sm"][ci, yi], 3)}))
    return pd.concat(rows, ignore_index=True)


def generate_yields(clim, first_year=2000, seed=11):
    """Rendements communaux synthetiques par bilan hydrique de la culture."""
    rng = np.random.default_rng(seed)
    years = clim["years"]
    rows = []
    commune_effect = {c[0]: rng.normal(1.0, 0.08) for c in COMMUNES}
    for crop, cp in CROP_PARAMS.items():
        for yi, yr in enumerate(years):
            if yr < first_year:
                continue
            rain = clim["rain_true"][:, yi, :]
            et0 = clim["et0"][:, yi, :]
            onset = ph.detect_onset(rain)
            sow = ph.sowing_dates(onset, cp)
            bounds = ph.phase_bounds(sow, cp)
            for ci, c in enumerate(COMMUNES):
                w, factor = 30.0, 1.0
                for k in range(4):
                    s, e = bounds[ci, k]
                    req = act = 0.0
                    for d in range(s, e):
                        need = et0[ci, d] * cp["kc"][k]
                        w = min(110.0, w + rain[ci, d])
                        got = min(need, w * 0.55)
                        w -= got
                        req += need
                        act += got
                    wrsi = act / req if req > 0 else 1.0
                    factor *= max(0.0, 1 - cp["ky"][k] * (1 - wrsi))
                s, e = bounds[ci, 3]
                heavy = int((rain[ci, s:e] >= 45).sum())
                factor *= max(0.6, 1 - (0.05 if crop == "coton" else 0.03) * heavy)
                late = max(0, sow[ci] - (cp["sowing_window"][0] + 20))
                factor *= max(0.75, 1 - 0.004 * late)
                trend = cp["base_yield"] + cp["trend"] * (yr - 2000)
                noise = rng.lognormal(0, 0.09)
                pest = rng.uniform(0.6, 0.85) if rng.random() < 0.05 else 1.0
                y = trend * commune_effect[c[0]] * factor / 0.80 * noise * pest
                rows.append((c[0], crop, yr, round(float(np.clip(y, 80, 3500)), 1), "synthetique"))
    return pd.DataFrame(rows, columns=["commune_id", "crop", "year", "yield_kg_ha", "source"])


def generate_exposure(seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for c in COMMUNES:
        cotton = c[2] in ("Alibori", "Borgou")
        rows.append((c[0], "coton", int(rng.integers(1800, 5200) if cotton else rng.integers(500, 1800)),
                     round(float(rng.uniform(1.6, 2.6)), 2)))
        rows.append((c[0], "mais", int(rng.integers(900, 2600)), round(float(rng.uniform(1.0, 1.8)), 2)))
    return pd.DataFrame(rows, columns=["commune_id", "crop", "farmers", "avg_area_ha"])
