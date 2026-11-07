"""Telechargement des donnees ouvertes sur VOTRE machine (acces internet requis).

    pip install requests pandas openpyxl kaggle faostat
    python -m agrisat_core.sources.fetch_open_data all            # tout
    python -m agrisat_core.sources.fetch_open_data nasa-power     # climat journalier reel des 27 communes
    python -m agrisat_core.sources.fetch_open_data hdx            # NDVI et pluie CHIRPS par commune (WFP)
    python -m agrisat_core.sources.fetch_open_data faostat        # mais et coton au niveau national
    python -m agrisat_core.sources.fetch_open_data kaggle         # catalogue Kaggle + jeu FAO international
    python -m agrisat_core.sources.fetch_open_data github         # limites communales et rendements DSA

Puis:  python -m agrisat_core.pipeline --source real
Le pipeline tourne alors sur le climat reel NASA POWER et les rendements reels du mais (DSA).
Le coton reste sans rendements communaux ouverts: son contrat est conçu sur le seul climat
tant que les donnees DSA ou de l'interprofession ne sont pas fournies.

Kaggle: creer un jeton sur kaggle.com, rubrique Settings, API, Create New Token, puis placer
kaggle.json dans ~/.kaggle/ (ou definir KAGGLE_USERNAME et KAGGLE_KEY).
"""
import io
import json
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
EXT = ROOT / "data" / "external"
sys.path.insert(0, str(ROOT))
from agrisat_core.communes import COMMUNES  # noqa: E402

HDX_API = "https://data.humdata.org/api/3/action/package_show?id="
POWER = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR,T2M_MAX,T2M_MIN,"
         "TOA_SW_DWN,GWETTOP&community=AG&longitude={lon}&latitude={lat}&start={start}0101&end={end}1231&format=JSON")
UA = {"User-Agent": "AGRISAT-data-fetch/1.0"}


def _requests():
    import requests
    return requests


def _norm(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").lower()
    return s.replace("'", "").replace("-", "").replace(" ", "")


ALIASES = {"boukoumbe": {"boukombe"}, "cobly": {"kobli"}, "pehunco": {"pehounco"}}


def _commune_lookup():
    out = {}
    for cid, name, *_ in COMMUNES:
        k = _norm(name)
        for key in {k} | ALIASES.get(k, set()):
            out[key] = cid
    return out


def _centroids():
    f = EXT / "centroids.json"
    if f.exists():
        c = json.load(open(f))
        return {int(k): tuple(v) for k, v in c.items()}
    return {cid: (lat, lon) for cid, _, _, lat, lon in COMMUNES}


# ------------------------------------------------------------------ NASA POWER
def nasa_power(start=1981, end=2025):
    """Climat journalier au centroide de chaque commune. ET0 par Hargreaves Samani."""
    rq = _requests()
    rows = []
    for cid, (lat, lon) in _centroids().items():
        name = next(c[1] for c in COMMUNES if c[0] == cid)
        for attempt in range(3):
            try:
                r = rq.get(POWER.format(lat=lat, lon=lon, start=start, end=end), headers=UA, timeout=180)
                r.raise_for_status()
                p = r.json()["properties"]["parameter"]
                break
            except Exception as e:
                print(f"  {name}: tentative {attempt + 1} echouee ({e})")
                time.sleep(5)
        else:
            continue
        df = pd.DataFrame({k: pd.Series(v) for k, v in p.items()}).replace(-999, np.nan)
        df.index = pd.to_datetime(df.index, format="%Y%m%d")
        tmean = (df.T2M_MAX + df.T2M_MIN) / 2
        et0 = 0.0023 * 0.408 * df.TOA_SW_DWN * (tmean + 17.8) * np.sqrt((df.T2M_MAX - df.T2M_MIN).clip(lower=0))
        rows.append(pd.DataFrame({"commune_id": cid, "date": df.index.strftime("%Y-%m-%d"),
                                  "rain": df.PRECTOTCORR.round(1), "tmax": df.T2M_MAX.round(1),
                                  "et0": et0.round(2), "sm": df.GWETTOP.round(3)}))
        print(f"  {name}: {len(df)} jours")
        time.sleep(1)
    out = pd.concat(rows, ignore_index=True)
    RAW.mkdir(parents=True, exist_ok=True)
    out.to_csv(RAW / "climate_daily.csv", index=False)
    print("Ecrit", RAW / "climate_daily.csv", len(out), "lignes")


# ------------------------------------------------------------------ HDX (WFP)
def _hdx_resource(package, contains):
    rq = _requests()
    res = rq.get(HDX_API + package, headers=UA, timeout=60).json()["result"]["resources"]
    for r in res:
        if contains in r["name"].lower() or contains in r["url"].lower():
            return r["url"]
    raise RuntimeError(f"Ressource '{contains}' introuvable dans {package}: {[r['name'] for r in res]}")


def _read_wfp_csv(url):
    rq = _requests()
    txt = rq.get(url, headers=UA, timeout=300).text
    df = pd.read_csv(io.StringIO(txt), low_memory=False)
    if str(df.iloc[0, 0]).startswith("#"):
        df = df.iloc[1:]      # ligne de balises HXL
    return df


def _pcode_names():
    """Correspondance code administratif et nom de commune, depuis les limites COD-AB du Benin sur HDX."""
    rq = _requests()
    url = None
    for r in rq.get(HDX_API + "cod-ab-ben", headers=UA, timeout=60).json()["result"]["resources"]:
        if r["url"].lower().endswith((".xlsx", ".xls")):
            url = r["url"]
            break
    if not url:
        raise RuntimeError("Tableau des codes administratifs introuvable (cod-ab-ben)")
    book = pd.read_excel(io.BytesIO(rq.get(url, headers=UA, timeout=120).content), sheet_name=None)
    sheet = next(v for k, v in book.items() if "adm2" in k.lower())
    pcol = next(c for c in sheet.columns if c.upper() == "ADM2_PCODE")
    ncol = next(c for c in sheet.columns if c.upper().startswith("ADM2_") and c.upper() not in ("ADM2_PCODE",)
                and sheet[c].dtype == object)
    return dict(zip(sheet[pcol], sheet[ncol]))


def hdx():
    lookup = _commune_lookup()
    try:
        names = _pcode_names()
    except Exception as e:
        names = {}
        print("Codes administratifs indisponibles:", e)

    def attach(df):
        code_col = next((c for c in df.columns if c.upper() in ("PCODE", "ADM2_PCODE", "ADM_PCODE")), None)
        name_col = next((c for c in df.columns if "name" in c.lower()), None)
        if name_col:
            df["commune_id"] = df[name_col].map(lambda n: lookup.get(_norm(n)))
        elif code_col and names:
            df["commune_id"] = df[code_col].map(lambda c: lookup.get(_norm(names.get(c, ""))))
        else:
            df["commune_id"] = None
        return df

    RAW.mkdir(parents=True, exist_ok=True)
    nd = attach(_read_wfp_csv(_hdx_resource("ben-ndvi-subnational", "adm2-full")))
    nd.to_csv(RAW / "hdx_ndvi_adm2_brut.csv", index=False)
    ok = nd.dropna(subset=["commune_id"])
    if len(ok):
        out = pd.DataFrame({"commune_id": ok.commune_id.astype(int), "date": ok["date"],
                            "ndvi": pd.to_numeric(ok["vim"], errors="coerce")})
        out.to_csv(RAW / "ndvi.csv", index=False)
        print("Ecrit", RAW / "ndvi.csv", len(out), "lignes,", out.commune_id.nunique(), "communes")
    else:
        print("NDVI telecharge mais communes non reconnues: voir hdx_ndvi_adm2_brut.csv")
    rf = attach(_read_wfp_csv(_hdx_resource("ben-rainfall-subnational", "adm2-full")))
    rf.to_csv(RAW / "hdx_rainfall_adm2.csv", index=False)
    print("Ecrit", RAW / "hdx_rainfall_adm2.csv", len(rf), "lignes")


# ------------------------------------------------------------------ FAOSTAT
def faostat():
    try:
        import faostat as fs
    except ImportError:
        print("pip install faostat"); return
    df = fs.get_data_df("QCL", pars={"area": "53", "item": ["56", "328"], "element": ["5312", "5412", "5510"]},
                        strval=False)
    df.to_csv(EXT / "faostat_benin_mais_coton.csv", index=False)
    print("Ecrit", EXT / "faostat_benin_mais_coton.csv", len(df), "lignes (mais et coton graine)")


# ------------------------------------------------------------------ Kaggle
KAGGLE_QUERIES = ["benin", "west africa agriculture", "cotton yield", "maize yield africa", "chirps rainfall",
                  "crop insurance", "ndvi africa"]


def kaggle():
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError:
        print("pip install kaggle"); return
    api = KaggleApi()
    api.authenticate()
    out = RAW / "kaggle"
    out.mkdir(parents=True, exist_ok=True)
    seen = {}
    for q in KAGGLE_QUERIES:
        for d in api.dataset_list(search=q):
            seen[d.ref] = {"ref": d.ref, "title": d.title, "size": getattr(d, "totalBytes", None),
                           "updated": str(getattr(d, "lastUpdated", "")), "query": q,
                           "url": f"https://www.kaggle.com/datasets/{d.ref}"}
    pd.DataFrame(seen.values()).to_csv(out / "catalogue_kaggle.csv", index=False)
    print("Catalogue Kaggle:", len(seen), "jeux ->", out / "catalogue_kaggle.csv")
    api.dataset_download_files("patelris/crop-yield-prediction-dataset", path=out / "crop_yield", unzip=True)
    f = out / "crop_yield" / "yield_df.csv"
    if f.exists():
        y = pd.read_csv(f)
        bj = y[y["Area"].str.lower() == "benin"]
        bj.to_csv(out / "crop_yield_benin.csv", index=False)
        print("Lignes Benin dans le jeu FAO de Kaggle:", len(bj))


# ------------------------------------------------------------------ GitHub
def github():
    rq = _requests()
    EXT.mkdir(parents=True, exist_ok=True)
    g = rq.get("https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/main/releaseData/gbOpen/BEN/ADM2/"
               "geoBoundaries-BEN-ADM2_simplified.geojson", headers=UA, timeout=120)
    (EXT / "geoBoundaries-BEN-ADM2.geojson").write_bytes(g.content)
    x = rq.get("https://raw.githubusercontent.com/steftdg/ZeaMays-Yield-Prediction-Benin/main/data/raw/"
               "rendement_communale.xlsx", headers=UA, timeout=120)
    (EXT / "rendement_communale_DSA.xlsx").write_bytes(x.content)
    print("Limites et rendements DSA telecharges dans", EXT)


def build_yields():
    from agrisat_core.real_data import write_yields_for_pipeline
    print("Ecrit", write_yields_for_pipeline())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"nasa-power": nasa_power, "hdx": hdx, "faostat": faostat, "kaggle": kaggle, "github": github,
             "yields": build_yields}
    for name, fn in steps.items():
        if cmd in ("all", name):
            print(f"== {name}")
            try:
                fn()
            except Exception as e:
                print(f"   echec: {e}")
