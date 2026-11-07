"""Calcul des indices par phase et des variables explicatives du modele de rendement."""
import numpy as np
import pandas as pd

from . import phenology as ph

DAILY_CAP_MM = 50.0     # plafond journalier de l'indice contractuel
HEAVY_MM = 45.0


def contract_index(rain, crop_params, return_sowing=False):
    """Indice contractuel: pluie cumulee plafonnee par phase. rain (N, 365) -> (N, 4)."""
    rain = np.asarray(rain, dtype=np.float32)
    onset = ph.detect_onset(rain)
    sow = ph.sowing_dates(onset, crop_params)
    bounds = ph.phase_bounds(sow, crop_params)
    idx = ph.window_sum(np.minimum(rain, DAILY_CAP_MM), bounds)
    if return_sowing:
        return idx, onset, sow
    return idx


def _max_dry_spell(rain_row, s, e):
    best = cur = 0
    for v in rain_row[s:e]:
        cur = cur + 1 if v < ph.WET_DAY_MM else 0
        best = max(best, cur)
    return best


def phase_features(rain, tmax, et0, ndvi, crop_params):
    """Variables par phase. Tous les tableaux sont (N, 365); ndvi peut contenir des NaN.

    Retourne un DataFrame de N lignes.
    """
    rain = np.asarray(rain, np.float32)
    onset = ph.detect_onset(rain)
    sow = ph.sowing_dates(onset, crop_params)
    b = ph.phase_bounds(sow, crop_params)
    out = {"onset_doy": onset, "sowing_doy": sow}
    capped = ph.window_sum(np.minimum(rain, DAILY_CAP_MM), b)
    total = ph.window_sum(rain, b)
    heavy = ph.window_sum((rain >= HEAVY_MM).astype(np.float32), b)
    kc = np.array(crop_params["kc"], np.float32)
    n = rain.shape[0]
    for k in range(4):
        out[f"rain_cap_p{k+1}"] = capped[:, k]
        out[f"rain_p{k+1}"] = total[:, k]
        out[f"heavy_p{k+1}"] = heavy[:, k]
        dry, tm, deficit, nd_mean, nd_max = [], [], [], [], []
        for i in range(n):
            s, e = b[i, k]
            dry.append(_max_dry_spell(rain[i], s, e))
            tm.append(float(np.mean(tmax[i, s:e])))
            deficit.append(float(np.sum(rain[i, s:e] - kc[k] * et0[i, s:e])))
            if ndvi is not None:
                seg = ndvi[i, s:e]
                nd_mean.append(float(np.nanmean(seg)) if np.isfinite(seg).any() else np.nan)
                nd_max.append(float(np.nanmax(seg)) if np.isfinite(seg).any() else np.nan)
        out[f"dry_p{k+1}"] = dry
        out[f"tmax_p{k+1}"] = tm
        out[f"deficit_p{k+1}"] = deficit
        if ndvi is not None:
            out[f"ndvi_mean_p{k+1}"] = nd_mean
            out[f"ndvi_max_p{k+1}"] = nd_max
    return pd.DataFrame(out)


def ndvi_daily_from_composites(ndvi_df, commune_ids, years):
    """Interpole les composites 16 jours en serie journaliere (C, Y, 365), NaN avant 2000."""
    arr = np.full((len(commune_ids), len(years)), np.nan, dtype=object)
    out = np.full((len(commune_ids), len(years), 365), np.nan, np.float32)
    df = ndvi_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df.date.dt.year
    df["doy"] = df.date.dt.dayofyear - 1
    days = np.arange(365)
    for (cid, yr), g in df.groupby(["commune_id", "year"]):
        if cid not in commune_ids or yr not in years:
            continue
        g = g.dropna(subset=["ndvi"])
        if len(g) < 4:
            continue
        step = np.median(np.diff(np.sort(g["doy"].values))) if len(g) > 2 else 16
        x = g["doy"].values + (5 if step <= 11 else 8)  # centre de la decade ou du composite 16 jours
        out[commune_ids.index(cid), years.index(yr)] = np.interp(days, x, g["ndvi"].values)
    del arr
    return out
