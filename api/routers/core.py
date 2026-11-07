"""Authentification, referentiels, contrats, modeles, portefeuille, suivi de saison, tarification."""
from datetime import date

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agrisat_core.communes import CROP_PARAMS
from agrisat_core.actuarial.contract import payout_fraction
from agrisat_core.actuarial.pricing import premium_from_payouts, simulate_commune_index
from ..auth import create_token, current_user, verify_password
from ..db import get_db
from ..models import User
from ..settings_service import get_settings
from ..store import get_store
from ..services.season import commune_season, commune_series, doy_of

router = APIRouter(prefix="/api")


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(username=form.username).first()
    if not u or not verify_password(form.password, u.password_hash):
        raise HTTPException(401, "Identifiants incorrects")
    return {"access_token": create_token(u), "token_type": "bearer",
            "user": {"username": u.username, "full_name": u.full_name, "role": u.role, "organisation_id": u.organisation_id}}


@router.get("/auth/me")
def me(u: User = Depends(current_user)):
    return {"username": u.username, "full_name": u.full_name, "role": u.role, "organisation_id": u.organisation_id}


@router.get("/health")
def health():
    s = get_store()
    return {"status": "ok", "data_source": s.meta["data_source"], "campaign": s.current_campaign}


@router.get("/meta")
def meta(_: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_store()
    campaigns = sorted({s.current_campaign} | ({s.real["years"][1]} if s.real else set()), reverse=True)
    return {**s.meta, "campaign": s.current_campaign, "campaigns": campaigns, "years_available": s.years,
            "last_yield_year": s.real["years"][1] if s.real else None, "settings": get_settings(db)}


@router.get("/communes")
def communes(_: User = Depends(current_user)):
    return get_store().meta["communes"]


@router.get("/contracts")
def contracts(crop: str | None = None, _: User = Depends(current_user)):
    s = get_store()
    out = []
    for c in s.contracts:
        if crop and c["crop"] != crop:
            continue
        com = s.communes[c["commune_id"]]
        fn = c["basis_risk"]["false_negative_rate"]
        out.append({**c, "commune": com["name"], "department": com["department"],
                    "insurable": c.get("validated", True) and (fn is None or fn <= 0.20)})
    return out


@router.get("/contracts/{commune_id}/{crop}")
def contract_detail(commune_id: int, crop: str, _: User = Depends(current_user)):
    s = get_store()
    c = s.contract(commune_id, crop)
    if not c:
        raise HTTPException(404, "Contrat introuvable")
    h = s.history[(s.history.commune_id == commune_id) & (s.history.crop == crop)].sort_values("year")
    hist = h.replace({np.nan: None}).to_dict(orient="records")
    for r in hist:
        if r["yield_kg_ha"] and r["trend_kg_ha"]:
            r["loss_rel"] = round(max(0.0, 1 - r["yield_kg_ha"] / r["trend_kg_ha"]), 4)
        r["payout_fcfa_ha"] = round(r["payout_frac"] * c["sum_insured_ha"], 0)
    return {**c, "commune": s.communes[commune_id]["name"], "history": hist}


@router.get("/real-data")
def real_data(_: User = Depends(current_user)):
    st = get_store()
    if not st.real:
        raise HTTPException(404, "Données réelles absentes (data/external)")
    import json as _json
    from ..store import PROC
    src = PROC.parent / "external" / "sources.json"
    return {**st.real, "sources": _json.load(open(src, encoding="utf-8")) if src.exists() else st.real["sources"],
            "findings": st.findings}


@router.get("/findings")
def findings(_: User = Depends(current_user)):
    return get_store().findings or {}


@router.get("/geo/communes")
def geo_communes(_: User = Depends(current_user)):
    g = get_store().geo
    if not g:
        raise HTTPException(404, "Limites communales absentes")
    return g


@router.get("/models")
def models(_: User = Depends(current_user)):
    return get_store().ml


@router.get("/portfolio")
def portfolio(_: User = Depends(current_user)):
    return get_store().portfolio


def _asof(year, asof):
    if asof:
        d = date.fromisoformat(asof)
        return doy_of(d)
    return 364


@router.get("/season")
def season(crop: str = "coton", year: int | None = None, asof: str | None = None, _: User = Depends(current_user)):
    s = get_store()
    year = year or s.current_campaign
    if year not in s.years:
        raise HTTPException(400, f"Campagne {year} absente des données")
    a = _asof(year, asof)
    return [commune_season(s, cid, crop, year, a) for cid in s.cids]


@router.get("/season/{commune_id}")
def season_commune(commune_id: int, crop: str = "coton", year: int | None = None, asof: str | None = None,
                   _: User = Depends(current_user)):
    s = get_store()
    year = year or s.current_campaign
    a = _asof(year, asof)
    return {**commune_season(s, commune_id, crop, year, a), "series": commune_series(s, commune_id, year, a)}


class QuoteIn(BaseModel):
    commune_id: int
    crop: str = "coton"
    area_ha: float = Field(gt=0, le=200)
    live: bool = False
    n_sims: int = Field(default=10000, ge=500, le=50000)
    product: str = "indice_pluie"          # indice_pluie ou rendement_zone
    coverage: float | None = None


def area_yield_commune(store, commune_id):
    if not store.real:
        return None
    return next((c for c in store.real["communes"] if c["commune_id"] == int(commune_id)), None)


def area_yield_trend(rc, year):
    """Tendance lineaire des rendements DSA valides, evaluee pour une campagne donnee."""
    import numpy as _np
    ok = [(r["year"], r["yield"]) for r in rc["series"] if not r["flag"]]
    a, b = _np.polyfit([x for x, _ in ok], [y for _, y in ok], 1)
    return float(a * year + b)


def quote_area_yield(q, db, s):
    if q.crop != "mais":
        raise HTTPException(400, "Le contrat rendement par zone n'existe que pour le maïs (rendements DSA)")
    rc = area_yield_commune(s, q.commune_id)
    if not rc:
        raise HTTPException(404, "Rendements communaux absents pour cette commune")
    st = get_settings(db)
    cov = q.coverage or st["area_yield_coverage"]
    key = min(rc["area_yield"], key=lambda k: abs(float(k) - cov))
    pr = rc["area_yield"][key]
    si_ha = float(st["sum_insured_ha"]["mais"])
    ratio = si_ha / s.real["params"]["sum_insured_ha"]
    com = (pr["pure_premium"] * ratio + st["cost_of_capital"] * pr["allocated_capital"] * ratio) / (1 - st["expense_rate"])
    a = q.area_ha
    return {
        "product": "rendement_zone", "coverage": float(key), "commune": s.communes[q.commune_id]["name"], "crop": "mais",
        "area_ha": a, "live_simulation": False, "n_sims": pr.get("n_sims", 10000),
        "sum_insured": round(si_ha * a), "premium_total": round(com * a),
        "premium_subsidy": round(st["subsidy_rate"] * com * a), "premium_farmer": round((1 - st["subsidy_rate"]) * com * a),
        "pure_premium": round(pr["pure_premium"] * ratio * a), "commercial_rate": round(com / si_ha, 5),
        "prob_payout": pr["prob_payout"], "subsidy_rate": st["subsidy_rate"],
        "trend_next": round(area_yield_trend(rc, s.real["years"][1] + 1)), "years_paid_historical": pr["years_paid_historical"],
        "n_years": rc["n_years"] - rc["n_flagged"], "insurable": True, "validated": True,
        "basis_risk": {"correlation": None, "false_negative_rate": None, "false_positive_rate": None},
    }


@router.post("/pricing/quote")
def quote(q: QuoteIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    s = get_store()
    if q.product == "rendement_zone":
        return quote_area_yield(q, db, s)
    c = s.contract(q.commune_id, q.crop)
    if not c:
        raise HTTPException(404, "Contrat introuvable")
    st = get_settings(db)
    si_ha = float(st["sum_insured_ha"].get(q.crop, c["sum_insured_ha"]))
    div = c["pricing"].get("diversification_factor", 1.0)
    if q.live:
        idx = simulate_commune_index(s.generator, s.cidx(q.commune_id), CROP_PARAMS[q.crop], n=q.n_sims, seed=7)
        frac = payout_fraction(idx, c["trigger"], c["exit"], c["weights"])
    else:
        frac = None
    if frac is not None:
        pr = premium_from_payouts(frac, si_ha, st["subsidy_rate"], st["expense_rate"], st["cost_of_capital"], diversification=div)
    else:
        base = c["pricing"]
        ratio = si_ha / c["sum_insured_ha"]
        el = base["pure_premium"] * ratio
        cap = base["allocated_capital"] * ratio
        com =(el + st["cost_of_capital"] * cap) / (1 - st["expense_rate"])
        pr = {**base, "sum_insured": si_ha, "pure_premium": round(el, 1), "commercial_premium": round(com, 1),
              "commercial_rate": round(com / si_ha, 5), "subsidy": round(st["subsidy_rate"] * com, 1),
              "farmer_premium": round((1 - st["subsidy_rate"]) * com, 1)}
    a = q.area_ha
    fn = c["basis_risk"]["false_negative_rate"]
    return {
        "product": "indice_pluie", "commune": s.communes[q.commune_id]["name"], "crop": q.crop, "area_ha": a, "live_simulation": q.live,
        "n_sims": q.n_sims if q.live else c["pricing"]["n_sims"],
        "sum_insured": round(si_ha * a), "premium_total": round(pr["commercial_premium"] * a),
        "premium_subsidy": round(pr["subsidy"] * a), "premium_farmer": round(pr["farmer_premium"] * a),
        "pure_premium": round(pr["pure_premium"] * a), "commercial_rate": pr["commercial_rate"],
        "prob_payout": pr.get("prob_payout"), "subsidy_rate": st["subsidy_rate"],
        "trigger": c["trigger"], "exit": c["exit"], "weights": c["weights"], "phase_names": c["phase_names"],
        "basis_risk": c["basis_risk"], "insurable": c.get("validated", True) and (fn is None or fn <= 0.20),
        "validated": c.get("validated", True), "area_yield_available": q.crop == "mais" and area_yield_commune(s, q.commune_id) is not None,
    }
