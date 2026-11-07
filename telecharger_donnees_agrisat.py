"""
AGRISAT, telechargement des donnees ouvertes (version 2) (a lancer sur votre ordinateur, avec internet).

1. Installer Python 3.10 ou plus (python.org, cocher "Add Python to PATH" sous Windows)
2. Dans un terminal :   pip install requests
   Facultatif :         pip install kaggle      (catalogue Kaggle, voir plus bas)
3. Lancer :             python telecharger_donnees_agrisat.py
4. Renvoyer a Claude le fichier produit :  agrisat_donnees.zip

Le script ne modifie rien sur votre machine en dehors du dossier "agrisat_donnees" et de
l'archive "agrisat_donnees.zip", crees a cote du script. Chaque source est independante :
si l'une echoue, les autres continuent, et le rapport final indique ce qui manque.

Kaggle (facultatif) : sur kaggle.com, Settings, API, "Create New Token". Placer le fichier
kaggle.json telecharge dans C:\\Users\\VOUS\\.kaggle\\ (Windows) ou ~/.kaggle/ (Mac, Linux).
"""
import json
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Installez d'abord requests :  pip install requests")

HERE = Path(__file__).resolve().parent
OUT = HERE / "agrisat_donnees"
UA = {"User-Agent": "AGRISAT-telechargement/1.0 (projet academique)"}
REPORT = []

# 27 communes du Nord Benin : identifiant, nom, latitude et longitude du centroide (geoBoundaries)
COMMUNES = {
    1: ("Banikoara", 11.3453, 2.4047), 2: ("Gogounou", 10.7694, 2.6984), 3: ("Kandi", 11.2104, 2.9665),
    4: ("Karimama", 11.9497, 2.7493), 5: ("Malanville", 11.6587, 3.2633), 6: ("Segbana", 10.9355, 3.4676),
    7: ("Bembereke", 10.2714, 2.7494), 8: ("Kalale", 10.3657, 3.3926), 9: ("N'Dali", 9.7247, 2.4669),
    10: ("Nikki", 9.9493, 3.19), 11: ("Parakou", 9.3469, 2.6032), 12: ("Perere", 9.5916, 2.9858),
    13: ("Sinende", 10.247, 2.3464), 14: ("Tchaourou", 9.1617, 2.4946), 15: ("Boukoumbe", 10.2503, 1.1337),
    16: ("Cobly", 10.4724, 0.9052), 17: ("Kerou", 10.9357, 2.0055), 18: ("Kouande", 10.4261, 1.7211),
    19: ("Materi", 10.7916, 1.0281), 20: ("Natitingou", 10.2421, 1.4068), 21: ("Pehunco", 10.2562, 2.0318),
    22: ("Tanguieta", 11.0302, 1.4378), 23: ("Toucountouna", 10.5253, 1.4642), 24: ("Bassila", 8.9652, 1.8606),
    25: ("Copargo", 9.8728, 1.5435), 26: ("Djougou", 9.6735, 1.853), 27: ("Ouake", 9.59, 1.4388),
}


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def get(url, timeout=180, tries=3, **kw):
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except Exception as e:
            log(f"   tentative {i + 1} echouee : {e}")
            time.sleep(4 * (i + 1))
    raise RuntimeError(f"echec apres {tries} tentatives : {url}")


def step(name):
    def deco(fn):
        def run():
            log(f"== {name}")
            t0 = time.time()
            try:
                detail = fn() or ""
                REPORT.append({"source": name, "statut": "ok", "detail": detail, "duree_s": round(time.time() - t0)})
                log(f"   ok {detail}")
            except Exception as e:
                REPORT.append({"source": name, "statut": "echec", "detail": str(e)[:300]})
                log(f"   ECHEC : {e}")
        return run
    return deco


# ------------------------------------------------------------------ 1. NASA POWER, climat journalier
END = (datetime.now() - __import__("datetime").timedelta(days=7)).strftime("%Y%m%d")


@step("NASA POWER, climat journalier des 27 communes (1981 a aujourd'hui)")
def nasa_power():
    d = OUT / "nasa_power"
    d.mkdir(parents=True, exist_ok=True)
    params = "PRECTOTCORR,T2M_MAX,T2M_MIN,TOA_SW_DWN,ALLSKY_SFC_SW_DWN,RH2M,WS2M,GWETTOP,GWETROOT"
    ok = 0
    for cid, (name, lat, lon) in COMMUNES.items():
        f = d / f"commune_{cid:02d}.json"
        if f.exists() and f.stat().st_size > 10000 and END[:4] in f.read_text(errors="ignore")[-400:]:
            ok += 1
            continue
        url = ("https://power.larc.nasa.gov/api/temporal/daily/point"
               f"?parameters={params}&community=AG&longitude={lon}&latitude={lat}"
               f"&start=19810101&end={END}&format=JSON")
        try:
            f.write_bytes(get(url, timeout=300).content)
            ok += 1
            log(f"   {cid:02d} {name}")
        except Exception as e:
            log(f"   {cid:02d} {name} : {e}")
        time.sleep(1)
    if ok == 0:
        raise RuntimeError("aucune commune telechargee")
    return f"{ok} communes sur 27"


# ------------------------------------------------------------------ 2. HDX (WFP) : NDVI et pluie CHIRPS par commune
def hdx_package(pid):
    return get(f"https://data.humdata.org/api/3/action/package_show?id={pid}", timeout=60).json()["result"]


def hdx_download(pid, keep):
    d = OUT / "hdx"
    d.mkdir(parents=True, exist_ok=True)
    pkg = hdx_package(pid)
    (d / f"{pid}_metadonnees.json").write_text(json.dumps(pkg, ensure_ascii=False, indent=1), encoding="utf-8")
    got = []
    for r in pkg["resources"]:
        name = (r.get("name") or r["url"].split("/")[-1]).replace("/", "_")
        if keep(name.lower(), r["url"].lower()):
            (d / name).write_bytes(get(r["url"], timeout=600).content)
            got.append(name)
    if not got:
        raise RuntimeError(f"aucune ressource retenue, disponibles : {[r.get('name') for r in pkg['resources']]}")
    return ", ".join(got)


@step("HDX, NDVI par commune (WFP, MODIS)")
def hdx_ndvi():
    return hdx_download("ben-ndvi-subnational", lambda n, u: n.endswith(".csv") and "full" in n)


@step("HDX, pluie CHIRPS par commune (WFP)")
def hdx_rain():
    return hdx_download("ben-rainfall-subnational", lambda n, u: n.endswith(".csv") and "full" in n)


@step("HDX, codes administratifs du Benin (COD-AB)")
def hdx_cod():
    return hdx_download("cod-ab-ben", lambda n, u: n.endswith((".xlsx", ".xls", ".csv")))


# ------------------------------------------------------------------ 3. FAOSTAT : mais et coton, Benin
@step("FAOSTAT, mais et coton graine au Benin")
def faostat():
    d = OUT / "faostat"
    d.mkdir(parents=True, exist_ok=True)
    if (d / "faostat_afrique_production.zip").exists() or (d / "faostat_benin_mais_coton.csv").exists():
        return "deja telecharge"
    # 1. paquet python faostat (pip install faostat)
    try:
        import faostat as fs
        df = fs.get_data_df("QCL", pars={"area": "53", "item": ["56", "328"], "element": ["5312", "5412", "5510"]})
        df.to_csv(d / "faostat_benin_mais_coton.csv", index=False)
        return "paquet faostat"
    except Exception as e:
        log(f"   paquet faostat indisponible ({e}), essai du telechargement groupe")
    # 2. telechargement groupe public de la FAO (production agricole, Afrique)
    for url in ["https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_Africa.zip",
                "https://fenixservices.fao.org/faostat/static/bulkdownloads/Production_Crops_Livestock_E_Africa.zip"]:
        try:
            r = get(url, timeout=900, tries=2)
            (d / "faostat_afrique_production.zip").write_bytes(r.content)
            return f"telechargement groupe Afrique ({len(r.content) / 1e6:.1f} Mo)"
        except Exception as e:
            log(f"   {url} : {e}")
    raise RuntimeError("FAOSTAT indisponible, voir les instructions manuelles")


# ------------------------------------------------------------------ 4. Banque mondiale : indicateurs agricoles
@step("Banque mondiale, indicateurs agricoles du Benin")
def world_bank():
    d = OUT / "banque_mondiale"
    d.mkdir(parents=True, exist_ok=True)
    ind = {"AG.LND.AGRI.ZS": "terres_agricoles_pct", "NV.AGR.TOTL.ZS": "agriculture_pct_pib",
           "SL.AGR.EMPL.ZS": "emploi_agricole_pct", "AG.CON.FERT.ZS": "engrais_kg_ha",
           "AG.LND.PRCP.MM": "pluie_moyenne_mm", "FP.CPI.TOTL.ZG": "inflation_pct"}
    for code, name in ind.items():
        r = get(f"https://api.worldbank.org/v2/country/BEN/indicator/{code}?format=json&per_page=200", timeout=60)
        (d / f"{name}.json").write_bytes(r.content)
    return f"{len(ind)} indicateurs"


# ------------------------------------------------------------------ 5. Kaggle (facultatif)
@step("Kaggle, catalogue et jeu FAO international (facultatif)")
def kaggle():
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError:
        raise RuntimeError("paquet kaggle absent (pip install kaggle), etape ignoree")
    d = OUT / "kaggle"
    if (d / "catalogue_kaggle.json").exists():
        return "deja telecharge"
    api = KaggleApi()
    api.authenticate()
    d.mkdir(parents=True, exist_ok=True)
    seen = {}
    for q in ["benin", "west africa agriculture", "cotton yield", "maize yield africa", "chirps", "crop insurance",
              "sahel rainfall", "ndvi africa"]:
        for ds in api.dataset_list(search=q):
            seen[ds.ref] = {"ref": ds.ref, "titre": ds.title, "requete": q,
                            "url": f"https://www.kaggle.com/datasets/{ds.ref}"}
    (d / "catalogue_kaggle.json").write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    api.dataset_download_files("patelris/crop-yield-prediction-dataset", path=str(d / "crop_yield"), unzip=True)
    return f"{len(seen)} jeux catalogues"


# ------------------------------------------------------------------ archive
def pack():
    (OUT / "rapport_telechargement.json").write_text(json.dumps(
        {"date": datetime.now().isoformat(timespec="seconds"), "python": sys.version.split()[0], "etapes": REPORT},
        ensure_ascii=False, indent=1), encoding="utf-8")
    z = HERE / "agrisat_donnees.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in OUT.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(OUT.parent))
    return z


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for fn in (nasa_power, hdx_ndvi, hdx_rain, hdx_cod, faostat, world_bank, kaggle):
        fn()
    z = pack()
    print("\n================ RESUME ================")
    for r in REPORT:
        print(f"{'OK    ' if r['statut'] == 'ok' else 'ECHEC '} {r['source']} : {r['detail']}")
    print(f"\nArchive a renvoyer a Claude : {z}  ({z.stat().st_size / 1e6:.1f} Mo)")
    if shutil.which("explorer") and sys.platform.startswith("win"):
        import subprocess
        subprocess.run(["explorer", "/select,", str(z)])
