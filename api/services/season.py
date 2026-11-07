"""Suivi de saison en temps reel (decade par decade) a partir des donnees disponibles a une date."""
from datetime import date

import numpy as np

from agrisat_core import phenology as ph
from agrisat_core.communes import CROP_PARAMS
from agrisat_core.features import DAILY_CAP_MM
from agrisat_core.actuarial.contract import phase_payouts

VIGILANCE_MARGIN = 1.15


def doy_of(d: date) -> int:
    doy = d.timetuple().tm_yday - 1
    if d.year % 4 == 0 and d.month > 2:
        doy -= 1
    return min(max(doy, 0), 364)


def commune_season(store, commune_id, crop, year, asof_doy):
    ci, yi = store.cidx(commune_id), store.years.index(year)
    cp = CROP_PARAMS[crop]
    ct = store.contract(commune_id, crop)
    obs = store.rain[ci, yi].astype(np.float32)
    clim_daily = store.rain[ci].mean(axis=0)
    clim_capped = np.minimum(store.rain[ci], DAILY_CAP_MM).mean(axis=0)
    known = obs.copy()
    known[asof_doy + 1:] = clim_daily[asof_doy + 1:]   # futur inconnu: esperance climatologique
    onset = int(ph.detect_onset(known[None, :])[0])
    onset_confirmed = onset + 33 <= asof_doy
    sow = int(ph.sowing_dates(np.array([onset]), cp)[0])
    bounds = ph.phase_bounds(np.array([sow]), cp)[0]
    phases, status = [], "normal"
    if asof_doy < sow:
        status = "hors_saison"
    for k in range(4):
        s, e = int(bounds[k, 0]), int(bounds[k, 1])
        T, E, w = ct["trigger"][k], ct["exit"][k], ct["weights"][k]
        upto = min(e, asof_doy + 1)
        partial = float(np.minimum(obs[s:upto], DAILY_CAP_MM).sum()) if upto > s else 0.0
        if asof_doy + 1 >= e:
            st, projected = "terminee", partial
        elif asof_doy >= s:
            st, projected = "en_cours", partial + float(clim_capped[upto:e].sum())
        else:
            st, projected = "a_venir", float(clim_capped[s:e].sum())
        frac = float(phase_payouts(np.array([[projected if i == k else 1e9 for i in range(4)]]),
                                   ct["trigger"], ct["exit"], ct["weights"])[0, k])
        if w > 0 and st == "terminee" and frac > 0:
            status = "declenche"
        elif w > 0 and st == "en_cours" and projected < T * VIGILANCE_MARGIN and status != "declenche":
            status = "vigilance"
        phases.append({"phase": k + 1, "name": cp["phase_names"][k], "start_doy": s, "end_doy": e,
                       "status": st, "index_observed": round(partial, 1), "index_projected": round(projected, 1),
                       "trigger": T, "exit": E, "weight": w, "payout_fraction": round(frac, 4) if st == "terminee" else None,
                       "payout_fraction_projected": round(frac, 4)})
    total_frac = min(1.0, sum(p["payout_fraction"] or 0 for p in phases))
    return {"commune_id": commune_id, "commune": store.communes[commune_id]["name"],
            "department": store.communes[commune_id]["department"], "crop": crop, "year": year,
            "asof_doy": asof_doy, "onset_doy": onset, "onset_confirmed": onset_confirmed, "sowing_doy": sow,
            "status": status, "phases": phases, "payout_fraction_to_date": round(total_frac, 4),
            "lat": store.communes[commune_id]["lat"], "lon": store.communes[commune_id]["lon"],
            "rain_to_date": round(float(obs[:asof_doy + 1].sum()), 1),
            "rain_normal_to_date": round(float(clim_daily[:asof_doy + 1].sum()), 1)}


def commune_series(store, commune_id, year, asof_doy):
    ci, yi = store.cidx(commune_id), store.years.index(year)
    cum = np.cumsum(store.rain[ci, yi])
    mean_cum = store.climatology["mean_cum"][ci]
    p20 = store.climatology["p20_cum"][ci]
    nd = store.ndvi[ci, yi]
    nd_mean = np.nanmean(store.ndvi[ci], axis=0)
    out = []
    for d in range(0, 365, 5):
        out.append({"doy": d, "rain_cum": round(float(cum[d]), 1) if d <= asof_doy else None,
                    "normal_cum": mean_cum[d], "dry_year_cum": p20[d],
                    "ndvi": round(float(nd[d]), 3) if d <= asof_doy and np.isfinite(nd[d]) else None,
                    "ndvi_normal": round(float(nd_mean[d]), 3) if np.isfinite(nd_mean[d]) else None})
    return out
