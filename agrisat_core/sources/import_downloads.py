"""Import de l'archive produite par telecharger_donnees_agrisat.py (agrisat_donnees.zip).

    python -m agrisat_core.sources.import_downloads chemin/vers/agrisat_donnees.zip

Produit :
  data/raw/climate_daily.csv   pluie journaliere, temperature maximale, ET0, humidite du sol
  data/raw/ndvi.csv            NDVI decadaire par commune (WFP, MODIS)
  data/external/chirps_dekadal_communes.csv, faostat_benin.csv, banque_mondiale_benin.csv,
  kaggle_catalogue.csv, data_validation.json

Choix methodologique pour la pluie : l'indice contractuel doit reposer sur CHIRPS (cahier des
charges, section 6). HDX fournit CHIRPS par commune au pas DECADAIRE ; NASA POWER fournit une pluie
JOURNALIERE (MERRA-2, 0,5 degre) moins precise mais qui donne la chronologie des jours de pluie.
La pluie journaliere retenue est donc NASA POWER RECALEE sur CHIRPS : dans chaque decade, les pluies
journalieres NASA sont multipliees pour que leur somme egale le cumul CHIRPS. Si NASA ne voit aucune
pluie alors que CHIRPS en mesure, le cumul est reparti sur les jours de la decade a parts egales.
Les totaux decadaires, mensuels et saisonniers sont ainsi exactement ceux de CHIRPS.
"""
import io
import json
import sys
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
EXT = ROOT / "data" / "external"
sys.path.insert(0, str(ROOT))
from agrisat_core.communes import COMMUNES  # noqa: E402

ALIASES = {"boukoumbe": {"boukombe"}, "cobly": {"kobli"}, "pehunco": {"pehounco"}}


def _norm(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").lower()
    return s.replace("'", "").replace("-", "").replace(" ", "")


def _lookup():
    out = {}
    for cid, name, *_ in COMMUNES:
        k = _norm(name)
        for key in {k} | ALIASES.get(k, set()):
            out[key] = cid
    return out


class Archive:
    def __init__(self, path):
        p = Path(path)
        self.zip = zipfile.ZipFile(p) if p.suffix == ".zip" else None
        self.dir = None if self.zip else p
        self.names = self.zip.namelist() if self.zip else [str(f.relative_to(p)) for f in p.rglob("*") if f.is_file()]

    def find(self, suffix):
        return [n for n in self.names if n.replace("\\", "/").endswith(suffix)]

    def read(self, name):
        return self.zip.read(name) if self.zip else (self.dir / name).read_bytes()


# ------------------------------------------------------------------ NASA POWER
def nasa_power(ar):
    frames = []
    for cid, name, *_ in COMMUNES:
        f = ar.find(f"nasa_power/commune_{cid:02d}.json")
        if not f:
            print(f"  NASA POWER absent pour {name}")
            continue
        j = json.loads(ar.read(f[0]))
        p = j["properties"]["parameter"]
        df = pd.DataFrame({k: pd.Series(v) for k, v in p.items()}).replace(-999.0, np.nan)
        df.index = pd.to_datetime(df.index, format="%Y%m%d")
        df["commune_id"] = cid
        frames.append(df)
    d = pd.concat(frames)
    d.index.name = "date"
    return d.reset_index()


# ------------------------------------------------------------------ HDX
def hdx(ar):
    adm = pd.read_excel(io.BytesIO(ar.read(ar.find("ben_admin_boundaries.xlsx")[0])), sheet_name="ben_admin2")
    lk = _lookup()
    pcode = {r.adm2_pcode: lk.get(_norm(r.adm2_name)) for r in adm.itertuples()}
    missing = [n for cid, n, *_ in COMMUNES if cid not in pcode.values()]
    if missing:
        raise RuntimeError(f"Communes sans code administratif: {missing}")
    rain = pd.read_csv(io.BytesIO(ar.read(ar.find("ben-rainfall-subnat-full.csv")[0])), low_memory=False)
    rain = rain[rain.adm_level == 2].assign(commune_id=lambda x: x.PCODE.map(pcode)).dropna(subset=["commune_id"])
    rain["commune_id"] = rain.commune_id.astype(int)
    rain["date"] = pd.to_datetime(rain["date"])
    ndvi = pd.read_csv(io.BytesIO(ar.read(ar.find("ben-ndvi-subnat-full.csv")[0])))
    ndvi = ndvi[ndvi.adm_level == 2].assign(commune_id=lambda x: x.PCODE.map(pcode)).dropna(subset=["commune_id"])
    ndvi["commune_id"] = ndvi.commune_id.astype(int)
    return rain, ndvi, {v: k for k, v in pcode.items() if v}


def dekad_start(d):
    day = np.where(d.dt.day <= 10, 1, np.where(d.dt.day <= 20, 11, 21))
    return pd.to_datetime(dict(year=d.dt.year, month=d.dt.month, day=day))


def recalibrate(nasa, chirps):
    """Pluie journaliere NASA recalee sur les cumuls decadaires CHIRPS, commune par commune."""
    n = nasa[["commune_id", "date", "PRECTOTCORR"]].copy()
    n["dekad"] = dekad_start(n["date"])
    n["PRECTOTCORR"] = n["PRECTOTCORR"].fillna(0).clip(lower=0)
    tot = n.groupby(["commune_id", "dekad"]).PRECTOTCORR.agg(["sum", "size"]).reset_index()
    c = chirps[["commune_id", "date", "rfh"]].rename(columns={"date": "dekad", "rfh": "chirps"})
    tot = tot.merge(c, on=["commune_id", "dekad"], how="left")
    n = n.merge(tot, on=["commune_id", "dekad"], how="left")
    has_chirps = n["chirps"].notna()
    scale = np.where(n["sum"] > 0.5, n["chirps"] / n["sum"].where(n["sum"] > 0.5, 1), np.nan)
    rain = np.where(~has_chirps, n["PRECTOTCORR"],
                    np.where(n["sum"] > 0.5, n["PRECTOTCORR"] * scale, n["chirps"] / n["size"]))
    n["rain"] = np.round(np.clip(rain, 0, 300), 1)
    n["source_rain"] = np.where(has_chirps, "CHIRPS recale", "NASA POWER")
    return n[["commune_id", "date", "rain", "PRECTOTCORR", "source_rain"]]


def validation(nasa, chirps, rain_daily):
    """Comparaison NASA POWER et CHIRPS (cumuls de mai a octobre)."""
    nasa = nasa.assign(year=nasa.date.dt.year, month=nasa.date.dt.month)
    ch = chirps.assign(year=chirps.date.dt.year, month=chirps.date.dt.month)
    a = nasa[nasa.month.between(5, 10)].groupby(["commune_id", "year"]).PRECTOTCORR.sum().rename("nasa")
    b = ch[ch.month.between(5, 10)].groupby(["commune_id", "year"]).rfh.sum().rename("chirps")
    m = pd.concat([a, b], axis=1).dropna()
    m = m[m.index.get_level_values("year") <= 2025]
    per = m.groupby(level=0).apply(lambda g: pd.Series({"corr": g.nasa.corr(g.chirps), "bias_pct": (g.nasa.sum() / g.chirps.sum() - 1)}))
    r = rain_daily.assign(dekad=dekad_start(rain_daily.date)).groupby(["commune_id", "dekad"]).rain.sum().reset_index()
    chk = r.merge(chirps.rename(columns={"date": "dekad"})[["commune_id", "dekad", "rfh"]], on=["commune_id", "dekad"])
    return {
        "season_corr_nasa_chirps_mean": round(float(per["corr"].mean()), 3),
        "season_bias_nasa_vs_chirps_pct_mean": round(float(per["bias_pct"].mean()) * 100, 1),
        "dekad_max_abs_error_after_recalibration_mm": round(float((chk.rain - chk.rfh).abs().max()), 2),
        "seasonal_totals_chirps_mm_mean": round(float(m.chirps.mean()), 0),
        "per_commune": {int(k): {"corr": round(float(v["corr"]), 3), "bias_pct": round(float(v["bias_pct"]) * 100, 1)}
                        for k, v in per.iterrows()},
    }


# ------------------------------------------------------------------ FAOSTAT, Banque mondiale, Kaggle
def faostat(ar):
    f = ar.find("faostat_afrique_production.zip")
    if not f:
        return None
    z = zipfile.ZipFile(io.BytesIO(ar.read(f[0])))
    name = next(n for n in z.namelist() if n.endswith("Africa_NOFLAG.csv")) if any(
        n.endswith("NOFLAG.csv") for n in z.namelist()) else next(n for n in z.namelist() if n.endswith("Africa.csv"))
    df = pd.read_csv(z.open(name), encoding="latin-1", low_memory=False)
    df = df[(df["Area"] == "Benin") & (df["Item"].isin(["Maize (corn)", "Seed cotton, unginned", "Maize"]))]
    ycols = [c for c in df.columns if c.startswith("Y") and c[1:5].isdigit() and len(c) == 5]
    long = df.melt(id_vars=["Item", "Element", "Unit"], value_vars=ycols, var_name="year", value_name="value")
    long["year"] = long.year.str[1:].astype(int)
    long = long.dropna(subset=["value"])
    wide = long.pivot_table(index=["Item", "year"], columns="Element", values="value").reset_index()
    wide.columns.name = None
    ren = {"Item": "item", "Area harvested": "area_ha", "Production": "production_t", "Yield": "yield_raw"}
    wide = wide.rename(columns=ren)
    unit = long[long.Element == "Yield"].Unit.iloc[0] if (long.Element == "Yield").any() else "kg/ha"
    wide["yield_kg_ha"] = wide["yield_raw"] / 10 if unit.lower().startswith("hg") else wide["yield_raw"]
    wide["crop"] = wide["item"].map(lambda s: "coton" if "cotton" in s.lower() else "mais")
    return wide[["crop", "year", "area_ha", "production_t", "yield_kg_ha"]].sort_values(["crop", "year"])


def world_bank(ar):
    rows = []
    for f in ar.find(".json"):
        if "banque_mondiale/" not in f.replace("\\", "/"):
            continue
        j = json.loads(ar.read(f))
        if len(j) < 2 or not j[1]:
            continue
        name = Path(f).stem
        for r in j[1]:
            if r["value"] is not None:
                rows.append({"indicator": name, "code": r["indicator"]["id"], "label": r["indicator"]["value"],
                             "year": int(r["date"]), "value": r["value"]})
    return pd.DataFrame(rows).sort_values(["indicator", "year"])


def kaggle(ar):
    f = ar.find("kaggle/catalogue_kaggle.json")
    cat = pd.DataFrame(json.loads(ar.read(f[0]))) if f else pd.DataFrame()
    y = ar.find("crop_yield/yield_df.csv")
    bj = None
    if y:
        d = pd.read_csv(io.BytesIO(ar.read(y[0])))
        bj = d[d["Area"].str.lower() == "benin"]
    return cat, bj


def main(path):
    ar = Archive(path)
    RAW.mkdir(parents=True, exist_ok=True)
    EXT.mkdir(parents=True, exist_ok=True)
    print("NASA POWER")
    nasa = nasa_power(ar)
    print("HDX, CHIRPS et NDVI par commune")
    chirps, ndvi, pcodes = hdx(ar)
    rain = recalibrate(nasa, chirps)
    tmean = (nasa.T2M_MAX + nasa.T2M_MIN) / 2
    et0 = 0.0023 * 0.408 * nasa.TOA_SW_DWN * (tmean + 17.8) * np.sqrt((nasa.T2M_MAX - nasa.T2M_MIN).clip(lower=0))
    clim = pd.DataFrame({"commune_id": nasa.commune_id, "date": nasa.date, "tmax": nasa.T2M_MAX.round(1),
                         "et0": et0.round(2), "sm": nasa.GWETTOP.round(3)})
    clim = clim.merge(rain[["commune_id", "date", "rain", "source_rain"]], on=["commune_id", "date"])
    clim["date"] = clim.date.dt.strftime("%Y-%m-%d")
    clim[["commune_id", "date", "rain", "tmax", "et0", "sm", "source_rain"]].to_csv(RAW / "climate_daily.csv", index=False)
    print("  ecrit", RAW / "climate_daily.csv", len(clim))
    ndvi_out = ndvi[["commune_id", "date", "vim"]].rename(columns={"vim": "ndvi"})
    ndvi_out.to_csv(RAW / "ndvi.csv", index=False)
    chirps_out = chirps[["commune_id", "date", "rfh", "rfh_avg", "version"]].copy()
    chirps_out["date"] = chirps_out.date.dt.strftime("%Y-%m-%d")
    chirps_out.to_csv(EXT / "chirps_dekadal_communes.csv", index=False)
    val = validation(nasa, chirps, rain)
    val["chirps_last_dekad"] = str(chirps.date.max().date())
    val["ndvi_last_dekad"] = str(pd.to_datetime(ndvi.date).max().date())
    val["nasa_last_day"] = str(nasa.date.max().date())
    val["pcodes"] = {str(k): v for k, v in pcodes.items()}
    fao = faostat(ar)
    if fao is not None:
        fao.to_csv(EXT / "faostat_benin.csv", index=False)
        val["faostat_years"] = {c: [int(g.year.min()), int(g.year.max())] for c, g in fao.groupby("crop")}
        print("  FAOSTAT", val["faostat_years"])
    wb = world_bank(ar)
    wb.to_csv(EXT / "banque_mondiale_benin.csv", index=False)
    cat, bj = kaggle(ar)
    cat.to_csv(EXT / "kaggle_catalogue.csv", index=False)
    val["kaggle"] = {"datasets": int(len(cat)), "benin_rows_in_crop_yield": None if bj is None else int(len(bj))}
    json.dump(val, open(EXT / "data_validation.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in val.items() if k not in ("per_commune", "pcodes")}, indent=1))
    from agrisat_core.real_data import write_yields_for_pipeline
    print("  rendements mais DSA ->", write_yields_for_pipeline())


if __name__ == "__main__":
    main(sys.argv[1])
