"""Extraction des VRAIES donnees satellitaires par commune via Google Earth Engine.

Prerequis:
    pip install earthengine-api
    earthengine authenticate          # compte Google avec acces Earth Engine (gratuit en usage non commercial)
    export GEE_PROJECT=mon-projet-gcp

Usage:
    python -m agrisat_core.gee.extract_gee --start 1981 --end 2025

Sorties (schema identique aux donnees synthetiques):
    data/raw/climate_daily.csv   commune_id,date,rain,tmax,et0,sm
    data/raw/ndvi.csv            commune_id,date,ndvi

Puis fournir data/raw/rendements_communes.csv (commune_id,crop,year,yield_kg_ha,source)
a partir des annuaires du MAEP (voir data/raw/rendements_communes_MODELE.csv) et lancer:
    python -m agrisat_core.pipeline --source real

Notes sur les donnees:
  * CHIRPS: UCSB-CHG/CHIRPS/DAILY, 0,05 degre, depuis 1981. La version definitive est
    publiee environ 3 semaines apres la fin du mois: ne calculer les indemnites definitives
    qu'avec cette version.
  * MODIS: MODIS/061/MOD13Q1, 250 m, 16 jours, depuis 2000. Les pixels de mauvaise qualite
    (SummaryQA > 1) sont masques. Relais prevu: NOAA/VIIRS/001/VNP13A1.
  * ERA5 Land: ECMWF/ERA5_LAND/DAILY_AGGR, temperature maximale et evaporation potentielle.
  * Humidite du sol: ERA5 Land volumetric_soil_water_layer_1 (ESA CCI disponible hors GEE).
  * Masque cultures: ESA/WorldCover/v200, classe 40 (cropland).
  * Limites: WM/geoLab/geoBoundaries/600/ADM2, filtre shapeGroup == 'BEN'.
"""
import argparse
import os
from pathlib import Path

import pandas as pd

from ..communes import COMMUNES

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"


def _norm(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().replace("'", "").replace("-", " ")


def main(start, end, scale_rain=5566, scale_ndvi=250):
    import ee
    ee.Initialize(project=os.environ.get("GEE_PROJECT"))
    adm2 = ee.FeatureCollection("WM/geoLab/geoBoundaries/600/ADM2").filter(ee.Filter.eq("shapeGroup", "BEN"))
    names = adm2.aggregate_array("shapeName").getInfo()
    lookup = {_norm(n): n for n in names}
    feats = []
    for cid, name, *_ in COMMUNES:
        gname = lookup.get(_norm(name))
        if gname is None:
            raise SystemExit(f"Commune introuvable dans geoBoundaries: {name}. Corriger le nom.")
        feats.append(adm2.filter(ee.Filter.eq("shapeName", gname)).first().set("commune_id", cid))
    communes = ee.FeatureCollection(feats)
    crop_mask = ee.ImageCollection("ESA/WorldCover/v200").first().eq(40)

    def reduce(img, band, scale, masked=True):
        im = img.select(band)
        if masked:
            im = im.updateMask(crop_mask)
        return im.reduceRegions(communes, ee.Reducer.mean(), scale).map(
            lambda f: f.set("date", img.date().format("YYYY-MM-dd")).setGeometry(None))

    RAW.mkdir(parents=True, exist_ok=True)
    clim_rows, ndvi_rows = [], []
    for year in range(start, end + 1):
        a, b = f"{year}-01-01", f"{year + 1}-01-01"
        print("Annee", year)
        chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(a, b)
        era = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filterDate(a, b)
        r = chirps.map(lambda im: reduce(im, "precipitation", scale_rain, masked=False)).flatten().getInfo()
        e = era.map(lambda im: reduce(im.addBands(im.select("temperature_2m_max").subtract(273.15).rename("tmax"))
                                        .addBands(im.select("potential_evaporation_sum").multiply(-1000).rename("et0"))
                                        .addBands(im.select("volumetric_soil_water_layer_1").rename("sm")),
                                        ["tmax", "et0", "sm"], 11132, masked=False)).flatten().getInfo()
        rd = {(f["properties"]["commune_id"], f["properties"]["date"]): f["properties"].get("mean") for f in r["features"]}
        for f in e["features"]:
            p = f["properties"]
            key = (p["commune_id"], p["date"])
            clim_rows.append({"commune_id": key[0], "date": key[1], "rain": rd.get(key),
                              "tmax": p.get("tmax"), "et0": p.get("et0"), "sm": p.get("sm")})
        if year >= 2000:
            mod = ee.ImageCollection("MODIS/061/MOD13Q1").filterDate(a, b).map(
                lambda im: im.select("NDVI").multiply(0.0001).updateMask(im.select("SummaryQA").lte(1))
                .copyProperties(im, ["system:time_start"]))
            n = mod.map(lambda im: reduce(ee.Image(im), "NDVI", scale_ndvi)).flatten().getInfo()
            ndvi_rows += [{"commune_id": f["properties"]["commune_id"], "date": f["properties"]["date"],
                           "ndvi": f["properties"].get("mean")} for f in n["features"]]
    pd.DataFrame(clim_rows).sort_values(["commune_id", "date"]).to_csv(RAW / "climate_daily.csv", index=False)
    pd.DataFrame(ndvi_rows).sort_values(["commune_id", "date"]).to_csv(RAW / "ndvi.csv", index=False)
    print("Ecrit:", RAW / "climate_daily.csv", RAW / "ndvi.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1981)
    ap.add_argument("--end", type=int, default=2025)
    a = ap.parse_args()
    main(a.start, a.end)
