"""Pipeline complet AGRISAT.

    python -m agrisat_core.pipeline                # donnees synthetiques (defaut si data/raw vide)
    python -m agrisat_core.pipeline --source real  # donnees reelles exportees par gee/extract_gee.py
    python -m agrisat_core.pipeline --sims 2000    # tarification plus rapide (demo)

Sorties dans data/processed/.
"""
import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .communes import COMMUNES, CROP_PARAMS, PRICING_DEFAULTS, commune_list
from . import synthetic, features as ft, ml
from .actuarial.weather_generator import RainGenerator
from .actuarial.contract import payout_fraction, phase_payouts
from .actuarial.pricing import premium_from_payouts, simulate_commune_index
from .actuarial.optimize import design_contract
from .actuarial.portfolio import simulate_portfolio, portfolio_metrics
from . import real_data

ROOT = Path(__file__).resolve().parents[1]
MIN_CORRELATION = 0.30   # correlation minimale indemnites et pertes pour commercialiser un indice
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
CIDS = [c[0] for c in COMMUNES]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _to_cube(df, col, years):
    df = df.copy()
    d = pd.to_datetime(df["date"])
    df = df[~((d.dt.month == 2) & (d.dt.day == 29))]
    d = pd.to_datetime(df["date"])
    df["year"], df["doy"] = d.dt.year, d.dt.dayofyear - 1
    df.loc[d.dt.is_leap_year & (d.dt.month > 2), "doy"] -= 1
    cube = np.full((len(CIDS), len(years), 365), np.nan, np.float32)
    ci = df["commune_id"].map({c: i for i, c in enumerate(CIDS)}).values
    yi = df["year"].map({y: i for i, y in enumerate(years)}).values
    ok = ~pd.isna(ci) & ~pd.isna(yi)
    cube[ci[ok].astype(int), yi[ok].astype(int), df["doy"].values[ok]] = df[col].values[ok]
    return cube


def load_data(source):
    OUT.mkdir(parents=True, exist_ok=True)
    if source == "real":
        clim = pd.read_csv(RAW / "climate_daily.csv")
        ndvi = pd.read_csv(RAW / "ndvi.csv") if (RAW / "ndvi.csv").exists() else pd.DataFrame(columns=["commune_id", "date", "ndvi"])
        if not (RAW / "rendements_communes.csv").exists() and real_data.available():
            real_data.write_yields_for_pipeline()
        yields = pd.read_csv(RAW / "rendements_communes.csv")
        exposure = pd.read_csv(RAW / "exposition.csv") if (RAW / "exposition.csv").exists() else synthetic.generate_exposure()
        years = sorted(pd.to_datetime(clim["date"]).dt.year.unique().tolist())
        cube = {k: _to_cube(clim, k, years) for k in ("rain", "tmax", "et0", "sm")}
        for k in cube:
            cube[k] = np.nan_to_num(cube[k], nan=0.0 if k == "rain" else float(np.nanmean(cube[k])))
        data_source = "reel"
    else:
        log("Generation des donnees synthetiques (1981 a 2025)")
        c = synthetic.generate_climate()
        years = c["years"]
        cube = {"rain": c["rain"], "tmax": c["tmax"], "et0": c["et0"], "sm": c["sm"]}
        ndvi = synthetic.ndvi_composites(c["ndvi_daily"], years)
        yields = synthetic.generate_yields(c)
        exposure = synthetic.generate_exposure()
        synthetic.climate_to_frame(c).to_csv(OUT / "climate_daily.csv.gz", index=False, compression="gzip")
        data_source = "synthetique"
    ndvi.to_csv(OUT / "ndvi.csv", index=False)
    yields.to_csv(OUT / "yields.csv", index=False)
    exposure.to_csv(OUT / "exposure.csv", index=False)
    ndvi_daily = ft.ndvi_daily_from_composites(ndvi, CIDS, years)
    return years, cube, ndvi_daily, yields, exposure, data_source


def build_findings(contracts, ml_out, data_source):
    """Ce que disent les donnees: validite de l'indice pluie par culture, verification nationale du coton."""
    out = {"data_source": data_source, "min_correlation": MIN_CORRELATION, "crops": {}}
    for crop in CROP_PARAMS:
        cs = [c for c in contracts if c["crop"] == crop]
        corr = [c["basis_risk"]["correlation"] for c in cs if c["basis_risk"]["correlation"] is not None]
        m = ml_out.get(crop, {})
        best = None if m.get("skipped") else m["metrics"][m["best_model"]]["r2"]
        out["crops"][crop] = {"n_communes": len(cs), "n_validated": sum(bool(c.get("validated")) for c in cs),
                              "mean_correlation": round(float(np.mean(corr)), 3) if corr else None,
                              "best_r2": best, "ml_skipped": m.get("skipped")}
    fao = ROOT / "data" / "external" / "faostat_benin.csv"
    if fao.exists():
        f = pd.read_csv(fao)
        co = f[(f.crop == "coton") & f.year.between(1981, 2025)].set_index("year")
        if len(co) > 10:
            a, b = np.polyfit(co.index, co.yield_kg_ha, 1)
            loss = (1 - co.yield_kg_ha / (a * co.index + b)).clip(lower=0)
            h = pd.read_csv(OUT / "historical_payouts.csv")
            idx = h[h.crop == "coton"].groupby("year").payout_frac.mean()
            j = pd.concat([idx.rename("pay"), loss.rename("loss")], axis=1).dropna()
            out["cotton_national_check"] = {"correlation": round(float(j.pay.corr(j.loss)), 3), "n_years": int(len(j)),
                                            "worst_years_faostat": [int(y) for y in loss.sort_values(ascending=False).index[:4]]}
    val = ROOT / "data" / "external" / "data_validation.json"
    if val.exists():
        v = json.load(open(val))
        out["rain_validation"] = {k: v[k] for k in ("season_corr_nasa_chirps_mean", "season_bias_nasa_vs_chirps_pct_mean",
                                                    "dekad_max_abs_error_after_recalibration_mm", "chirps_last_dekad",
                                                    "ndvi_last_dekad", "nasa_last_day") if k in v}
    return out


def run(source="synthetic", n_sims=PRICING_DEFAULTS["n_sims"], seed=2026):
    t0 = time.time()
    if source == "auto":
        source = "real" if (RAW / "climate_daily.csv").exists() and (RAW / "rendements_communes.csv").exists() else "synthetic"
    if real_data.available():
        log("Donnees reelles DSA, FAOSTAT et prix: controle qualite et contrat rendement par zone")
        real_data.build()
    years, cube, ndvi_daily, yields, exposure, data_source = load_data(source)
    C, Y = len(CIDS), len(years)
    rain = cube["rain"]
    np.savez_compressed(OUT / "climate_cube.npz", years=np.array(years), rain=rain, tmax=cube["tmax"],
                        et0=cube["et0"], sm=cube["sm"], ndvi=ndvi_daily)

    # climatologie: cumul moyen journalier par commune (graphe de suivi)
    clim_mean = np.cumsum(rain, axis=2).mean(axis=1)
    clim_p20 = np.percentile(np.cumsum(rain, axis=2), 20, axis=1)
    json.dump({"commune_ids": CIDS, "mean_cum": np.round(clim_mean, 1).tolist(),
               "p20_cum": np.round(clim_p20, 1).tolist()}, open(OUT / "climatology.json", "w"))

    # ---------------- indices, variables et modeles de rendement
    log("Calcul des indices et des variables par phase")
    ydt = ml.detrend(yields)
    ml_out, hist_rows, contracts, pricing = {}, [], [], []
    yr_idx = {y: i for i, y in enumerate(years)}
    feats_by_crop = {}
    for crop, cp in CROP_PARAMS.items():
        flat_rain = rain.reshape(C * Y, 365)
        idx_all, onset_all, sow_all = ft.contract_index(flat_rain, cp, return_sowing=True)
        idx_all = idx_all.reshape(C, Y, 4)
        onset_all, sow_all = onset_all.reshape(C, Y), sow_all.reshape(C, Y)
        np.save(OUT / f"index_{crop}.npy", idx_all)
        sub = ydt[(ydt.crop == crop) & ydt.year.isin(years)]
        if len(sub) < 60:
            log(f"Rendements insuffisants pour {crop} ({len(sub)} observations): contrat concu sur le climat seul")
            ml_out[crop] = {"skipped": f"Rendements communaux absents ou insuffisants ({len(sub)} observations)"}
            for k, cid in enumerate(CIDS):
                T = np.quantile(idx_all[k], 0.15, axis=0)
                E = 0.5 * T
                frac_hist = payout_fraction(idx_all[k], T, E, cp["phase_weights"])
                det = phase_payouts(idx_all[k], T, E, cp["phase_weights"])
                for j, yr in enumerate(years):
                    hist_rows.append({"commune_id": cid, "crop": crop, "year": yr, "onset_doy": int(onset_all[k, j]),
                                      "sowing_doy": int(sow_all[k, j]),
                                      **{f"index_p{p+1}": round(float(idx_all[k, j, p]), 1) for p in range(4)},
                                      **{f"payout_p{p+1}": round(float(det[j, p]), 4) for p in range(4)},
                                      "payout_frac": round(float(frac_hist[j]), 4), "yield_kg_ha": None, "trend_kg_ha": None})
                contracts.append({"commune_id": cid, "crop": crop, "trigger": [round(float(v), 1) for v in T],
                                  "exit": [round(float(v), 1) for v in E], "weights": cp["phase_weights"],
                                  "sum_insured_ha": cp["sum_insured_ha"], "trigger_quantile": 0.15, "exit_ratio": 0.5,
                                  "burn_rate": round(float(frac_hist.mean()), 5), "ce_gain": 0.0, "ce_gain_pct": 0.0,
                                  "basis_risk": {"correlation": None, "false_negative_rate": None, "false_positive_rate": None,
                                                 "n_loss_years": 0, "n_paid_years": int((frac_hist > 0).sum()), "n_years": len(years)},
                                  "validated": False, "phase_names": cp["phase_names"]})
            continue
        rows = []
        for _, r in sub.iterrows():
            rows.append((CIDS.index(r.commune_id), yr_idx.get(int(r.year))))
        ok = [i for i, (a, b) in enumerate(rows) if b is not None]
        sub = sub.iloc[ok].reset_index(drop=True)
        ci = np.array([rows[i][0] for i in ok])
        yi = np.array([rows[i][1] for i in ok])
        F = ft.phase_features(rain[ci, yi], cube["tmax"][ci, yi], cube["et0"][ci, yi], ndvi_daily[ci, yi], cp)
        df = pd.concat([sub, F], axis=1)
        df.to_csv(OUT / f"features_{crop}.csv", index=False)
        feats_by_crop[crop] = df
        log(f"Modeles de rendement ({crop}), validation par annee exclue")
        res, preds = ml.evaluate(df, seed=0)
        res["shap"] = ml.shap_importance(df, seed=0)
        ml_out[crop] = res

        # ---------------- conception des contrats par commune
        log(f"Conception et optimisation des contrats ({crop})")
        for k, cid in enumerate(CIDS):
            d = df[df.commune_id == cid].sort_values("year")
            ev_i = np.array([yr_idx[y] for y in d.year])
            design = design_contract(idx_all[k], idx_all[k, ev_i], d.yield_kg_ha.values,
                                     d.trend_kg_ha.values, cp, subsidy_rate=PRICING_DEFAULTS["subsidy_rate"],
                                     expense_rate=PRICING_DEFAULTS["expense_rate"],
                                     max_gross_rate=PRICING_DEFAULTS["max_gross_rate"])
            frac_hist = payout_fraction(idx_all[k], design["T"], design["E"], cp["phase_weights"])
            det = phase_payouts(idx_all[k], design["T"], design["E"], cp["phase_weights"])
            for j, yr in enumerate(years):
                loss = d[d.year == yr]
                hist_rows.append({
                    "commune_id": cid, "crop": crop, "year": yr,
                    "onset_doy": int(onset_all[k, j]), "sowing_doy": int(sow_all[k, j]),
                    **{f"index_p{p+1}": round(float(idx_all[k, j, p]), 1) for p in range(4)},
                    **{f"payout_p{p+1}": round(float(det[j, p]), 4) for p in range(4)},
                    "payout_frac": round(float(frac_hist[j]), 4),
                    "yield_kg_ha": float(loss.yield_kg_ha.iloc[0]) if len(loss) else None,
                    "trend_kg_ha": round(float(loss.trend_kg_ha.iloc[0]), 1) if len(loss) else None,
                })
            contracts.append({"commune_id": cid, "crop": crop, "trigger": design["T"], "exit": design["E"],
                              "weights": cp["phase_weights"], "sum_insured_ha": cp["sum_insured_ha"],
                              "trigger_quantile": design["q"], "exit_ratio": design["e"],
                              "burn_rate": round(design["burn_rate"], 5), "ce_gain": round(design["ce_gain"], 1),
                              "ce_gain_pct": round(design["ce_gain_pct"], 4), "basis_risk": design["basis_risk"],
                              "validated": bool(design["basis_risk"]["correlation"] is not None
                                                and design["basis_risk"]["correlation"] >= MIN_CORRELATION),
                              "phase_names": cp["phase_names"]})

    json.dump(ml_out, open(OUT / "ml_results.json", "w"), indent=1)
    pd.DataFrame(hist_rows).to_csv(OUT / "historical_payouts.csv", index=False)

    # ---------------- generateur stochastique et tarification Monte Carlo
    log("Calibrage du generateur stochastique de pluie")
    gen = RainGenerator().fit(rain)
    pickle.dump(gen, open(OUT / "rain_generator.pkl", "wb"))
    log(f"Tarification Monte Carlo ({n_sims} saisons par commune et culture)")
    expo = {}
    for _, r in exposure.iterrows():
        expo[(CIDS.index(int(r.commune_id)), r.crop)] = float(r.farmers * r.avg_area_ha)
    hp = pd.DataFrame(hist_rows)
    sims_frac = {}
    for ct in contracts:
        k = CIDS.index(ct["commune_id"])
        sim_idx = simulate_commune_index(gen, k, CROP_PARAMS[ct["crop"]], n=n_sims, seed=seed + k)
        sims_frac[(k, ct["crop"])] = payout_fraction(sim_idx, ct["trigger"], ct["exit"], ct["weights"])
    standalone = {key: premium_from_payouts(f, CROP_PARAMS[key[1]]["sum_insured_ha"]) for key, f in sims_frac.items()}

    log("Simulation conjointe du portefeuille et allocation du capital")
    cmap = {(CIDS.index(c["commune_id"]), c["crop"]): {"T": c["trigger"], "E": c["exit"], "weights": c["weights"],
                                                        "sum_insured_ha": c["sum_insured_ha"]} for c in contracts}
    totals, by_c = simulate_portfolio(gen, cmap, expo, CROP_PARAMS, n=n_sims, seed=seed)
    from .actuarial.pricing import var_cvar
    _, port_cvar = var_cvar(totals, PRICING_DEFAULTS["cvar_level"])
    port_capital = max(port_cvar - totals.mean(), 0.0)
    sum_sa = sum(standalone[key]["standalone_capital"] * expo[key] for key in standalone)
    div = min(1.0, port_capital / sum_sa) if sum_sa > 0 else 1.0
    log(f"Facteur de diversification du capital: {div:.3f}")
    for ct in contracts:
        key = (CIDS.index(ct["commune_id"]), ct["crop"])
        pr = premium_from_payouts(sims_frac[key], ct["sum_insured_ha"], PRICING_DEFAULTS["subsidy_rate"],
                                  PRICING_DEFAULTS["expense_rate"], PRICING_DEFAULTS["cost_of_capital"],
                                  diversification=div)
        hb = hp[(hp.commune_id == ct["commune_id"]) & (hp.crop == ct["crop"])].payout_frac.mean()
        pr["burn_rate_historical"] = round(float(hb), 5)
        pr["n_sims"] = n_sims
        ct["pricing"] = pr
    json.dump(contracts, open(OUT / "contracts.json", "w"), indent=1, ensure_ascii=False)

    premium_income = sum(c["pricing"]["commercial_premium"] * expo[(CIDS.index(c["commune_id"]), c["crop"])] for c in contracts)
    pm = portfolio_metrics(totals, premium_income)
    pm["diversification_factor"] = round(div, 4)
    hp["exposure_ha"] = [expo[(CIDS.index(a), b)] for a, b in zip(hp.commune_id, hp.crop)]
    si = hp.crop.map({k: v["sum_insured_ha"] for k, v in CROP_PARAMS.items()})
    hp["payout_fcfa"] = hp.payout_frac * si * hp.exposure_ha
    by_year = hp.groupby("year").payout_fcfa.sum()
    pm["historical_replay"] = [{"year": int(y), "total_payout": round(float(v), 0),
                                "loss_ratio": round(float(v / premium_income), 3)} for y, v in by_year.items()]
    pm["stress_worst_years"] = sorted(pm["historical_replay"], key=lambda r: -r["total_payout"])[:5]
    pm["expected_payout_by_commune"] = {str(CIDS[k]): round(v, 0) for k, v in by_c.items()}
    pm["total_insured_ha"] = round(sum(expo.values()), 0)
    pm["total_sum_insured"] = round(sum(expo[k] * CROP_PARAMS[k[1]]["sum_insured_ha"] for k in expo), 0)
    pm["n_sims"] = n_sims
    json.dump(pm, open(OUT / "portfolio.json", "w"), indent=1)

    findings = build_findings(contracts, ml_out, data_source)
    json.dump(findings, open(OUT / "findings.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    meta = {"data_source": data_source, "years": [years[0], years[-1]], "n_communes": C,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "n_sims": n_sims,
            "duration_s": round(time.time() - t0, 1), "communes": commune_list(),
            "crops": {k: {kk: v[kk] for kk in ("label", "phase_names", "phase_weights", "price", "sum_insured_ha",
                                                 "phase_lengths", "sowing_window")} for k, v in CROP_PARAMS.items()},
            "pricing_defaults": PRICING_DEFAULTS}
    json.dump(meta, open(OUT / "meta.json", "w"), indent=1, ensure_ascii=False)
    log(f"Termine en {meta['duration_s']} s. Source des donnees: {data_source}")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="auto", choices=["auto", "synthetic", "real"])
    ap.add_argument("--sims", type=int, default=PRICING_DEFAULTS["n_sims"])
    a = ap.parse_args()
    run(a.source, a.sims)
