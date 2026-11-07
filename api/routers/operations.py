"""Souscription, indemnites, paiements, reclamations, alertes et USSD."""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agrisat_core.actuarial.contract import phase_payouts
from ..auth import current_user, require, audit
from ..db import get_db
from ..models import Farmer, Organisation, Credit, Policy, Payout, Payment, Claim, SmsMessage, User
from ..settings_service import get_settings
from ..store import get_store
from ..services.payments import get_provider, normalize_phone
from ..services.sms import render, Gateway, LANGUAGES
from ..services.season import commune_season, doy_of
from .core import quote, QuoteIn

router = APIRouter(prefix="/api")
CROP_LABEL = {"coton": "coton", "mais": "maïs"}


def _fmt(x):
    return f"{int(round(x)):,}".replace(",", " ")


def _farmer_scope(q, u: User, db):
    if u.role == "cooperative":
        return q.filter(Farmer.cooperative_id == u.organisation_id)
    if u.role == "imf":
        ids = [c.farmer_id for c in db.query(Credit).filter_by(institution_id=u.organisation_id)]
        return q.filter(Farmer.id.in_(ids or [-1]))
    return q


def _send(db, farmer, category, **kw):
    body, note = render(category, farmer.language, **kw)
    gw = Gateway()
    st = gw.send(farmer.phone, body)
    db.add(SmsMessage(farmer_id=farmer.id, phone=farmer.phone, language=farmer.language, category=category,
                      body=body + (f" [{note}]" if note else ""), status=st, provider=gw.provider))


# ------------------------------------------------------------------ organisations et producteurs
@router.get("/organisations")
def organisations(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": o.id, "name": o.name, "kind": o.kind, "commune_id": o.commune_id} for o in db.query(Organisation)]


class FarmerIn(BaseModel):
    full_name: str = Field(min_length=3)
    phone: str
    operator: str = "mtn"
    language: str = "fr"
    commune_id: int
    village: str = ""
    cooperative_id: int | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    consent: bool


def _farmer_dict(f: Farmer, store):
    return {"id": f.id, "full_name": f.full_name, "phone": f.phone, "operator": f.operator, "language": f.language,
            "commune_id": f.commune_id, "commune": store.communes[f.commune_id]["name"], "village": f.village,
            "cooperative_id": f.cooperative_id, "cooperative": f.cooperative.name if f.cooperative else None,
            "consent": f.consent, "is_test_data": f.is_test_data}


@router.get("/farmers")
def list_farmers(commune_id: int | None = None, q: str | None = None, u: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    s = get_store()
    query = _farmer_scope(db.query(Farmer), u, db)
    if commune_id:
        query = query.filter(Farmer.commune_id == commune_id)
    if q:
        query = query.filter(Farmer.full_name.ilike(f"%{q}%") | Farmer.phone.ilike(f"%{q}%"))
    return [_farmer_dict(f, s) for f in query.order_by(Farmer.id.desc()).limit(500)]


@router.post("/farmers")
def create_farmer(body: FarmerIn, u: User = Depends(require("cooperative", "imf", "assureur")), db: Session = Depends(get_db)):
    if not body.consent:
        raise HTTPException(400, "Le consentement du producteur est obligatoire (Code du numérique, APDP)")
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(400, "Numéro invalide: 10 chiffres commençant par 01 attendus")
    if body.commune_id not in get_store().communes:
        raise HTTPException(400, "Commune hors périmètre")
    if body.language not in LANGUAGES:
        raise HTTPException(400, "Langue non prise en charge")
    coop = body.cooperative_id or (u.organisation_id if u.role == "cooperative" else None)
    f = Farmer(**{**body.model_dump(), "phone": phone, "cooperative_id": coop, "consent_date": datetime.utcnow()})
    db.add(f)
    db.flush()
    audit(db, u, "creation_producteur", f"farmer:{f.id}", after={"commune_id": f.commune_id})
    db.commit()
    return _farmer_dict(f, get_store())


@router.post("/farmers/import")
async def import_farmers(file: UploadFile = File(...), cooperative_id: int | None = Form(None),
                         u: User = Depends(require("cooperative", "imf", "assureur")), db: Session = Depends(get_db)):
    """CSV attendu: nom,telephone,operateur,langue,commune,village,consentement (oui/non)"""
    s = get_store()
    by_name = {c["name"].lower(): cid for cid, c in s.communes.items()}
    text = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
    ok, errors = 0, []
    coop = cooperative_id or (u.organisation_id if u.role == "cooperative" else None)
    for i, row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        phone = normalize_phone(row.get("telephone", ""))
        cid = by_name.get(row.get("commune", "").lower())
        consent = row.get("consentement", "").lower() in ("oui", "yes", "1", "true")
        if not row.get("nom"):
            errors.append({"ligne": i, "erreur": "nom manquant"}); continue
        if not phone:
            errors.append({"ligne": i, "erreur": "téléphone invalide"}); continue
        if not cid:
            errors.append({"ligne": i, "erreur": f"commune inconnue: {row.get('commune')}"}); continue
        if not consent:
            errors.append({"ligne": i, "erreur": "consentement absent"}); continue
        db.add(Farmer(full_name=row["nom"], phone=phone, operator=(row.get("operateur") or "mtn").lower(),
                      language=(row.get("langue") or "fr").lower(), commune_id=cid, village=row.get("village", ""),
                      cooperative_id=coop, consent=True, consent_date=datetime.utcnow()))
        ok += 1
    audit(db, u, "import_producteurs", file.filename or "csv", after={"importes": ok, "erreurs": len(errors)})
    db.commit()
    return {"imported": ok, "errors": errors}


# ------------------------------------------------------------------ polices
class PolicyIn(BaseModel):
    farmer_id: int
    crop: str = "coton"
    area_ha: float = Field(gt=0, le=50)
    campaign: int | None = None
    premium_payment_mode: str = "mobile_money"   # mobile_money ou retenue_credit
    credit_amount: float | None = None
    institution_id: int | None = None
    product: str = "indice_pluie"
    coverage: float | None = None


def _policy_dict(p: Policy, store):
    return {"id": p.id, "number": p.number, "farmer_id": p.farmer_id, "farmer": p.farmer.full_name,
            "phone": p.farmer.phone, "commune_id": p.commune_id, "commune": store.communes[p.commune_id]["name"],
            "crop": p.crop, "product": p.product, "coverage": p.coverage, "campaign": p.campaign, "area_ha": p.area_ha, "sum_insured": p.sum_insured,
            "premium_total": p.premium_total, "premium_farmer": p.premium_farmer, "premium_subsidy": p.premium_subsidy,
            "premium_payment_mode": p.premium_payment_mode, "premium_paid": p.premium_paid, "status": p.status,
            "credit": {"id": p.credit.id, "amount": p.credit.amount, "outstanding": p.credit.outstanding,
                       "institution": p.credit.institution.name} if p.credit else None,
            "created_at": p.created_at.isoformat()}


@router.get("/policies")
def list_policies(campaign: int | None = None, commune_id: int | None = None, crop: str | None = None,
                  u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_store()
    q = db.query(Policy).join(Farmer)
    q = _farmer_scope(q, u, db)
    if campaign:
        q = q.filter(Policy.campaign == campaign)
    if commune_id:
        q = q.filter(Policy.commune_id == commune_id)
    if crop:
        q = q.filter(Policy.crop == crop)
    return [_policy_dict(p, s) for p in q.order_by(Policy.id.desc()).limit(1000)]


def create_policy_internal(db, body: PolicyIn, user, send_sms=True):
    s = get_store()
    f = db.get(Farmer, body.farmer_id)
    if not f:
        raise HTTPException(404, "Producteur introuvable")
    c = s.contract(f.commune_id, body.crop)
    q = quote(QuoteIn(commune_id=f.commune_id, crop=body.crop, area_ha=body.area_ha, product=body.product,
                      coverage=body.coverage), db)
    if not q["insurable"]:
        raise HTTPException(400, "Indice pluie non validé dans cette commune : corrélation insuffisante avec les pertes "
                                 "ou trop d'années de perte non indemnisées. Pour le maïs, choisir le contrat rendement par zone.")
    campaign = body.campaign or s.current_campaign
    credit = None
    if body.credit_amount:
        inst = body.institution_id or (user.organisation_id if getattr(user, "role", "") == "imf" else None)
        if not inst:
            raise HTTPException(400, "Institution de microfinance requise pour lier un crédit")
        credit = Credit(farmer_id=f.id, institution_id=inst, amount=body.credit_amount, outstanding=body.credit_amount)
        db.add(credit)
        db.flush()
    if body.premium_payment_mode == "retenue_credit" and not credit:
        raise HTTPException(400, "La retenue sur crédit suppose un crédit lié")
    n = db.query(Policy).count() + 1
    snap = ({"coverage": q["coverage"], "sum_insured_ha": q["sum_insured"] / body.area_ha} if body.product == "rendement_zone"
            else {k: c[k] for k in ("trigger", "exit", "weights", "sum_insured_ha", "phase_names")})
    p = Policy(number=f"AGS-{campaign}-{n:06d}", farmer_id=f.id, commune_id=f.commune_id, crop=body.crop,
               product=body.product, coverage=q.get("coverage"), campaign=campaign, area_ha=body.area_ha, sum_insured=q["sum_insured"], premium_total=q["premium_total"],
               premium_farmer=q["premium_farmer"], premium_subsidy=q["premium_subsidy"],
               premium_payment_mode=body.premium_payment_mode, credit_id=credit.id if credit else None,
               contract_snapshot=snap)
    if body.premium_payment_mode == "retenue_credit":
        p.premium_paid, p.status = True, "active"
        db.add(Payment(kind="prime", reference=f"RET-{n:06d}", policy_id=None, amount=p.premium_farmer,
                       provider="retenue_credit", status="reussi", message="Prime retenue sur le crédit intrants"))
    db.add(p)
    db.flush()
    audit(db, user, "souscription", f"policy:{p.number}", after={"area_ha": p.area_ha, "crop": p.crop})
    if send_sms:
        _send(db, f, "souscription", number=p.number, crop=CROP_LABEL[p.crop], area=p.area_ha, premium=_fmt(p.premium_farmer))
    return p


@router.post("/policies")
def create_policy(body: PolicyIn, u: User = Depends(require("cooperative", "imf", "assureur")), db: Session = Depends(get_db)):
    p = create_policy_internal(db, body, u)
    db.commit()
    return _policy_dict(p, get_store())


@router.post("/policies/{policy_id}/collect-premium")
def collect_premium(policy_id: int, u: User = Depends(require("cooperative", "imf", "assureur")), db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        raise HTTPException(404, "Police introuvable")
    if p.premium_paid:
        return {"status": "deja_payee"}
    res = get_provider().collect(p.farmer.phone, p.farmer.operator, p.premium_farmer, f"Prime AGRISAT {p.number}")
    db.add(Payment(kind="prime", reference=res["reference"], policy_id=p.id, phone=p.farmer.phone, operator=p.farmer.operator,
                   amount=p.premium_farmer, provider=get_provider().name, status=res["status"], message=res["message"]))
    if res["status"] == "reussi":
        p.premium_paid, p.status = True, "active"
        _send(db, p.farmer, "prime_payee", crop=CROP_LABEL[p.crop], campaign=p.campaign)
    audit(db, u, "encaissement_prime", f"policy:{p.number}", after=res)
    db.commit()
    return res


# ------------------------------------------------------------------ indemnites
class ComputeIn(BaseModel):
    campaign: int | None = None
    asof: str | None = None
    data_version: str = "definitive"   # preliminaire (avance) ou definitive


@router.post("/payouts/compute")
def compute_payouts(body: ComputeIn, u: User = Depends(require("assureur")), db: Session = Depends(get_db)):
    s = get_store()
    campaign = body.campaign or s.current_campaign
    asof = doy_of(datetime.fromisoformat(body.asof).date()) if body.asof else 364
    policies = db.query(Policy).filter(Policy.campaign == campaign, Policy.status == "active").all()
    created, total, pending = 0, 0.0, 0
    cache = {}
    from .core import area_yield_commune, area_yield_trend
    for p in [x for x in policies if x.product == "rendement_zone"]:
        rc = area_yield_commune(s, p.commune_id)
        obs = next((r for r in (rc or {}).get("series", []) if r["year"] == campaign and not r["flag"]), None)
        if not obs:
            pending += 1
            continue
        if db.query(Payout).filter_by(policy_id=p.id, phase=0, campaign=campaign).first():
            continue
        trend = area_yield_trend(rc, campaign)
        cov = p.coverage or 0.8
        frac = max(0.0, cov * trend - obs["yield"]) / (cov * trend)
        if frac <= 0:
            continue
        amount = round(frac * p.sum_insured)
        db.add(Payout(policy_id=p.id, campaign=campaign, phase=0, index_value=obs["yield"], trigger=round(cov * trend, 1),
                      exit=0.0, fraction=frac, amount=amount, data_version="DSA"))
        created += 1
        total += amount
        _send(db, p.farmer, "declenchement", crop=CROP_LABEL[p.crop], commune=s.communes[p.commune_id]["name"],
              phase="rendement", amount=_fmt(amount))
    for p in [x for x in policies if x.product != "rendement_zone"]:
        if campaign not in s.years:
            pending += 1
            continue
        key = (p.commune_id, p.crop)
        if key not in cache:
            cache[key] = commune_season(s, p.commune_id, p.crop, campaign, asof)
        season = cache[key]
        snap = p.contract_snapshot
        for ph in season["phases"]:
            if ph["status"] != "terminee" or snap["weights"][ph["phase"] - 1] == 0:
                continue
            k = ph["phase"] - 1
            idx = [[1e9] * 4]
            idx[0][k] = ph["index_observed"]
            frac = float(phase_payouts(idx, snap["trigger"], snap["exit"], snap["weights"])[0, k])
            if frac <= 0:
                continue
            if db.query(Payout).filter_by(policy_id=p.id, phase=ph["phase"], campaign=campaign).first():
                continue
            amount = round(frac * p.sum_insured)
            db.add(Payout(policy_id=p.id, campaign=campaign, phase=ph["phase"], index_value=ph["index_observed"],
                          trigger=snap["trigger"][k], exit=snap["exit"][k], fraction=frac, amount=amount,
                          data_version=body.data_version))
            created += 1
            total += amount
            _send(db, p.farmer, "declenchement", crop=CROP_LABEL[p.crop], commune=s.communes[p.commune_id]["name"],
                  phase=ph["phase"], amount=_fmt(amount))
    audit(db, u, "calcul_indemnites", f"campagne:{campaign}", after={"crees": created, "montant": total})
    db.commit()
    return {"campaign": campaign, "created": created, "total_amount": round(total), "policies_checked": len(policies),
            "pending": pending}


def _payout_dict(o: Payout, s):
    p = o.policy
    return {"id": o.id, "policy_number": p.number, "farmer": p.farmer.full_name, "phone": p.farmer.phone,
            "commune": s.communes[p.commune_id]["name"], "crop": p.crop, "product": p.product, "campaign": o.campaign, "phase": o.phase,
            "index_value": o.index_value, "trigger": o.trigger, "exit": o.exit, "fraction": round(o.fraction, 4),
            "amount": o.amount, "to_credit": o.to_credit, "to_farmer": o.to_farmer, "status": o.status,
            "data_version": o.data_version, "validated_by": o.validated_by,
            "credit_outstanding": p.credit.outstanding if p.credit else None}


@router.get("/payouts")
def list_payouts(campaign: int | None = None, status: str | None = None, u: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    s = get_store()
    q = db.query(Payout).join(Policy).join(Farmer)
    q = _farmer_scope(q, u, db)
    if campaign:
        q = q.filter(Payout.campaign == campaign)
    if status:
        q = q.filter(Payout.status == status)
    return [_payout_dict(o, s) for o in q.order_by(Payout.id.desc()).limit(2000)]


class ValidateIn(BaseModel):
    ids: list[int]
    decision: str = "valide"    # valide ou rejete


@router.post("/payouts/validate")
def validate_payouts(body: ValidateIn, u: User = Depends(require("assureur")), db: Session = Depends(get_db)):
    n = 0
    for o in db.query(Payout).filter(Payout.id.in_(body.ids), Payout.status == "a_valider"):
        o.status, o.validated_by = body.decision, u.username
        audit(db, u, f"indemnite_{body.decision}", f"payout:{o.id}", after={"amount": o.amount})
        n += 1
    db.commit()
    return {"updated": n}


class PayIn(BaseModel):
    ids: list[int] | None = None


@router.post("/payouts/pay")
def pay_payouts(body: PayIn, u: User = Depends(require("assureur")), db: Session = Depends(get_db)):
    prov = get_provider()
    q = db.query(Payout).filter(Payout.status.in_(["valide", "echec"]))
    if body.ids:
        q = q.filter(Payout.id.in_(body.ids))
    done = failed = 0
    for o in q.all():
        p = o.policy
        if o.status == "valide":
            to_credit = min(p.credit.outstanding, o.amount) if p.credit else 0.0
            o.to_credit, o.to_farmer = to_credit, o.amount - to_credit
            if to_credit > 0:
                p.credit.outstanding -= to_credit
                db.add(Payment(kind="remboursement_credit", reference=f"CRD-{o.id}", payout_id=o.id, amount=to_credit,
                               provider="virement_imf", status="reussi",
                               message=f"Remboursement à {p.credit.institution.name}"))
        if o.to_farmer <= 0:
            o.status = "paye"
            done += 1
            continue
        res = prov.payout(p.farmer.phone, p.farmer.operator, o.to_farmer, f"Indemnite AGRISAT {p.number} phase {o.phase}")
        prev = db.query(Payment).filter_by(payout_id=o.id, kind="indemnite").first()
        if prev:
            prev.status, prev.reference, prev.message = res["status"], res["reference"], res["message"]
            prev.attempts += 1
            prev.updated_at = datetime.utcnow()
        else:
            db.add(Payment(kind="indemnite", reference=res["reference"], payout_id=o.id, policy_id=p.id,
                           phone=p.farmer.phone, operator=p.farmer.operator, amount=o.to_farmer, provider=prov.name,
                           status=res["status"], message=res["message"]))
        if res["status"] in ("reussi", "en_cours"):
            o.status = "paye"
            done += 1
            if o.to_credit > 0:
                _send(db, p.farmer, "paiement_credit", credit=_fmt(o.to_credit), amount=_fmt(o.to_farmer))
            else:
                _send(db, p.farmer, "paiement", amount=_fmt(o.to_farmer), operator=p.farmer.operator.upper(), ref=res["reference"])
        else:
            o.status = "echec"
            failed += 1
    audit(db, u, "paiement_indemnites", "lot", after={"payes": done, "echecs": failed, "fournisseur": prov.name})
    db.commit()
    return {"paid": done, "failed": failed, "provider": prov.name}


@router.get("/payments")
def payments(kind: str | None = None, _: User = Depends(require("assureur", "imf", "partenaire")), db: Session = Depends(get_db)):
    q = db.query(Payment)
    if kind:
        q = q.filter(Payment.kind == kind)
    return [{"id": p.id, "kind": p.kind, "reference": p.reference, "phone": p.phone, "operator": p.operator,
             "amount": p.amount, "provider": p.provider, "status": p.status, "attempts": p.attempts,
             "message": p.message, "created_at": p.created_at.isoformat()} for p in q.order_by(Payment.id.desc()).limit(1000)]


@router.post("/payments/webhook")
def payment_webhook(payload: dict, db: Session = Depends(get_db)):
    """Notification de l'agregateur (FedaPay: transaction.approved, payout.sent, payout.failed)."""
    entity = payload.get("entity", {})
    ref = str(entity.get("reference") or entity.get("id") or "")
    pay = db.query(Payment).filter_by(reference=ref).first()
    if pay:
        ev = payload.get("name", "")
        pay.status = "reussi" if ev.endswith(("approved", "sent")) else ("echec" if "fail" in ev or "declined" in ev else pay.status)
        pay.updated_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ reclamations
class ClaimIn(BaseModel):
    farmer_id: int | None = None
    commune_id: int
    crop: str = "coton"
    campaign: int | None = None
    description: str = Field(min_length=5)
    estimated_loss_pct: float | None = Field(default=None, ge=0, le=100)
    channel: str = "agent"


@router.post("/claims")
def create_claim(body: ClaimIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_store()
    campaign = body.campaign or s.current_campaign
    c = Claim(**{**body.model_dump(), "campaign": campaign})
    db.add(c)
    db.flush()
    insured = db.query(Policy).filter_by(commune_id=body.commune_id, crop=body.crop, campaign=campaign).count() or 1
    n_claims = db.query(Claim).filter_by(commune_id=body.commune_id, crop=body.crop, campaign=campaign).count()
    thr = get_settings(db)["claims_audit_threshold"]
    audit_triggered = n_claims / insured >= thr
    if audit_triggered:
        db.query(Claim).filter_by(commune_id=body.commune_id, crop=body.crop, campaign=campaign, status="ouverte") \
            .update({"status": "audit"})
    audit(db, u, "reclamation", f"claim:{c.id}", after={"audit": audit_triggered})
    db.commit()
    return {"id": c.id, "audit_triggered": audit_triggered, "claims_in_commune": n_claims, "insured_in_commune": insured}


@router.get("/claims")
def list_claims(_: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_store()
    return [{"id": c.id, "commune": s.communes[c.commune_id]["name"], "commune_id": c.commune_id, "crop": c.crop,
             "campaign": c.campaign, "channel": c.channel, "description": c.description,
             "estimated_loss_pct": c.estimated_loss_pct, "status": c.status, "audit_result": c.audit_result,
             "created_at": c.created_at.isoformat()} for c in db.query(Claim).order_by(Claim.id.desc())]


class ClaimDecision(BaseModel):
    status: str
    audit_result: str = ""


@router.post("/claims/{claim_id}/decision")
def decide_claim(claim_id: int, body: ClaimDecision, u: User = Depends(require("assureur")), db: Session = Depends(get_db)):
    c = db.get(Claim, claim_id)
    if not c:
        raise HTTPException(404)
    c.status, c.audit_result = body.status, body.audit_result
    audit(db, u, "decision_reclamation", f"claim:{c.id}", after=body.model_dump())
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ alertes
class AlertIn(BaseModel):
    campaign: int | None = None
    crop: str = "coton"
    asof: str


@router.post("/alerts/run")
def run_alerts(body: AlertIn, u: User = Depends(require("assureur")), db: Session = Depends(get_db)):
    s = get_store()
    campaign = body.campaign or s.current_campaign
    asof = doy_of(datetime.fromisoformat(body.asof).date())
    sent = 0
    for cid in s.cids:
        st = commune_season(s, cid, body.crop, campaign, asof)
        if st["status"] != "vigilance":
            continue
        ph = next((p for p in st["phases"] if p["status"] == "en_cours"), None)
        if not ph:
            continue
        for p in db.query(Policy).filter_by(commune_id=cid, crop=body.crop, campaign=campaign, status="active"):
            _send(db, p.farmer, "vigilance", phase=ph["phase"], commune=st["commune"], index=int(ph["index_observed"]),
                  trigger=int(ph["trigger"]), crop=CROP_LABEL[body.crop])
            sent += 1
    audit(db, u, "alertes", f"campagne:{campaign}", after={"envoyees": sent, "date": body.asof})
    db.commit()
    return {"sent": sent}


@router.get("/sms")
def sms_outbox(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": m.id, "phone": m.phone, "language": m.language, "category": m.category, "body": m.body,
             "status": m.status, "provider": m.provider, "created_at": m.created_at.isoformat()}
            for m in db.query(SmsMessage).order_by(SmsMessage.id.desc()).limit(300)]


# ------------------------------------------------------------------ USSD (format Africa's Talking)
@router.post("/ussd", response_class=PlainTextResponse)
def ussd(sessionId: str = Form(""), serviceCode: str = Form(""), phoneNumber: str = Form(...), text: str = Form(""),
         db: Session = Depends(get_db)):
    s = get_store()
    phone = normalize_phone(phoneNumber)
    f = db.query(Farmer).filter_by(phone=phone).first() if phone else None
    if not f:
        return "END Numéro non enregistré chez AGRISAT. Contactez votre coopérative."
    steps = [t for t in text.split("*") if t] if text else []
    pols = db.query(Policy).filter_by(farmer_id=f.id).order_by(Policy.campaign.desc()).all()
    if not steps:
        return ("CON AGRISAT Assurance\n1. Mes polices\n2. Etat de la pluie dans ma commune\n"
                "3. Mes indemnités\n4. Signaler une perte")
    if steps[0] == "1":
        if not pols:
            return "END Aucune police active."
        lines = [f"{p.number} {CROP_LABEL[p.crop]} {p.area_ha} ha, {'active' if p.premium_paid else 'prime à payer'}" for p in pols[:3]]
        return "END " + "\n".join(lines)
    if steps[0] == "2":
        crop = pols[0].crop if pols else "coton"
        today = datetime.utcnow().date()
        year = s.current_campaign
        asof = doy_of(today.replace(year=year)) if today.year != year else doy_of(today)
        st = commune_season(s, f.commune_id, crop, year, asof)
        ph = next((p for p in st["phases"] if p["status"] == "en_cours"), None)
        etat = {"normal": "normal", "vigilance": "vigilance", "declenche": "assurance déclenchée", "hors_saison": "hors saison"}[st["status"]]
        msg = f"END {st['commune']}: {etat}. Pluie cumulée {int(st['rain_to_date'])} mm, normale {int(st['rain_normal_to_date'])} mm."
        if ph:
            msg += f" Phase {ph['phase']}: {int(ph['index_observed'])} mm, seuil {int(ph['trigger'])} mm."
        return msg
    if steps[0] == "3":
        pays = db.query(Payout).join(Policy).filter(Policy.farmer_id == f.id).all()
        if not pays:
            return "END Aucune indemnité pour le moment."
        return "END " + "\n".join(f"Phase {o.phase} {o.campaign}: {_fmt(o.amount)} FCFA, {o.status.replace('_', ' ')}" for o in pays[:4])
    if steps[0] == "4":
        if len(steps) == 1:
            return "CON Perte estimée sur votre récolte\n1. Moins de 30%\n2. 30 à 60%\n3. Plus de 60%"
        pct = {"1": 20, "2": 45, "3": 75}.get(steps[1], None)
        crop = pols[0].crop if pols else "coton"
        create_claim(ClaimIn(farmer_id=f.id, commune_id=f.commune_id, crop=crop, description="Déclaration USSD",
                             estimated_loss_pct=pct, channel="ussd"), u=User(username=f"ussd:{phone}", role="producteur"), db=db)
        return "END Votre déclaration est enregistrée. Votre coopérative sera informée."
    return "END Choix invalide."
