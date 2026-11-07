"""Rapports partenaires, exports, parametres, journal d'audit, utilisateurs."""
import io
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import current_user, require, audit, hash_password
from ..db import get_db
from ..models import Policy, Payout, Payment, Claim, AuditLog, User, Farmer
from ..settings_service import get_settings, set_setting, DEFAULTS
from ..store import get_store

router = APIRouter(prefix="/api")


def summary_data(db, campaign):
    s = get_store()
    pols = db.query(Policy).filter_by(campaign=campaign).all()
    pays = db.query(Payout).filter_by(campaign=campaign).all()
    by_c = defaultdict(lambda: {"policies": 0, "farmers": set(), "area_ha": 0.0, "sum_insured": 0.0, "premium_total": 0.0,
                                "premium_farmer": 0.0, "premium_subsidy": 0.0, "payouts": 0.0, "payouts_paid": 0.0})
    for p in pols:
        r = by_c[(p.commune_id, p.crop)]
        r["policies"] += 1
        r["farmers"].add(p.farmer_id)
        r["area_ha"] += p.area_ha
        r["sum_insured"] += p.sum_insured
        r["premium_total"] += p.premium_total
        r["premium_farmer"] += p.premium_farmer
        r["premium_subsidy"] += p.premium_subsidy
    for o in pays:
        if o.status == "rejete":
            continue
        r = by_c[(o.policy.commune_id, o.policy.crop)]
        r["payouts"] += o.amount
        if o.status == "paye":
            r["payouts_paid"] += o.amount
    rows = []
    for (cid, crop), r in sorted(by_c.items()):
        rows.append({"commune": s.communes[cid]["name"], "department": s.communes[cid]["department"], "crop": crop,
                     "policies": r["policies"], "farmers": len(r["farmers"]), "area_ha": round(r["area_ha"], 1),
                     "sum_insured": round(r["sum_insured"]), "premium_total": round(r["premium_total"]),
                     "premium_farmer": round(r["premium_farmer"]), "premium_subsidy": round(r["premium_subsidy"]),
                     "payouts": round(r["payouts"]), "payouts_paid": round(r["payouts_paid"]),
                     "loss_ratio": round(r["payouts"] / r["premium_total"], 3) if r["premium_total"] else None})
    tot = {k: sum(r[k] for r in rows) for k in ("policies", "farmers", "area_ha", "sum_insured", "premium_total",
                                                "premium_farmer", "premium_subsidy", "payouts", "payouts_paid")}
    tot["loss_ratio"] = round(tot["payouts"] / tot["premium_total"], 3) if tot["premium_total"] else None
    tot["claims"] = db.query(Claim).filter_by(campaign=campaign).count()
    tot["claims_in_audit"] = db.query(Claim).filter_by(campaign=campaign, status="audit").count()
    tot["payments_failed"] = db.query(Payment).filter_by(kind="indemnite", status="echec").count()
    tot["premium_unpaid"] = db.query(Policy).filter_by(campaign=campaign, premium_paid=False).count()
    return {"campaign": campaign, "totals": tot, "by_commune": rows, "data_source": s.meta["data_source"]}


@router.get("/reports/summary")
def report_summary(campaign: int | None = None, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return summary_data(db, campaign or get_store().current_campaign)


HEAD = ["Commune", "Département", "Culture", "Polices", "Producteurs", "Superficie (ha)", "Somme assurée",
        "Prime totale", "Part producteur", "Subvention", "Indemnités", "Indemnités payées", "S/P"]
KEYS = ["commune", "department", "crop", "policies", "farmers", "area_ha", "sum_insured", "premium_total",
        "premium_farmer", "premium_subsidy", "payouts", "payouts_paid", "loss_ratio"]


@router.get("/reports/export.xlsx")
def export_xlsx(campaign: int | None = None, _: User = Depends(current_user), db: Session = Depends(get_db)):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    d = summary_data(db, campaign or get_store().current_campaign)
    wb = Workbook()
    ws = wb.active
    ws.title = f"Campagne {d['campaign']}"
    ws.append([f"AGRISAT, rapport de campagne {d['campaign']} (données {d['data_source']})"])
    ws.append([])
    ws.append(HEAD)
    for c in ws[3]:
        c.font = Font(bold=True)
    for r in d["by_commune"]:
        ws.append([r[k] for k in KEYS])
    t = d["totals"]
    ws.append(["Total", "", "", t["policies"], t["farmers"], t["area_ha"], t["sum_insured"], t["premium_total"],
               t["premium_farmer"], t["premium_subsidy"], t["payouts"], t["payouts_paid"], t["loss_ratio"]])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for col in "ABCDEFGHIJKLM":
        ws.column_dimensions[col].width = 16
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=agrisat_campagne_{d['campaign']}.xlsx"})


@router.get("/reports/export.pdf")
def export_pdf(campaign: int | None = None, _: User = Depends(current_user), db: Session = Depends(get_db)):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    d = summary_data(db, campaign or get_store().current_campaign)
    t = d["totals"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=f"Rapport AGRISAT {d['campaign']}")
    h = ParagraphStyle("h", fontName="Times-Bold", fontSize=16, leading=20)
    b = ParagraphStyle("b", fontName="Times-Roman", fontSize=11, leading=15, alignment=TA_JUSTIFY)
    fmt = lambda x: f"{int(round(x)):,}".replace(",", " ")
    story = [Paragraph(f"Rapport de campagne {d['campaign']}, assurance agricole indicielle AGRISAT", h), Spacer(1, 8),
             Paragraph(f"La campagne compte {t['policies']} polices pour {t['farmers']} producteurs et "
                       f"{t['area_ha']:.1f} hectares assurés. Les primes s'élèvent à {fmt(t['premium_total'])} FCFA, "
                       f"dont {fmt(t['premium_subsidy'])} FCFA de subvention publique et {fmt(t['premium_farmer'])} FCFA "
                       f"à la charge des producteurs. Les indemnités calculées atteignent {fmt(t['payouts'])} FCFA, "
                       f"dont {fmt(t['payouts_paid'])} FCFA déjà payées. Le ratio sinistres sur primes est de "
                       f"{(t['loss_ratio'] or 0) * 100:.1f} pour cent. Source des données climatiques, {d['data_source']}.", b),
             Spacer(1, 10)]
    rows = [HEAD] + [[str(r[k]) if not isinstance(r[k], (int, float)) or k == "loss_ratio" else fmt(r[k]) for k in KEYS]
                     for r in d["by_commune"]]
    tb = Table(rows, repeatRows=1)
    tb.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Times-Roman", 8.5), ("FONT", (0, 0), (-1, 0), "Times-Bold", 8.5),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("ALIGN", (3, 1), (-1, -1), "RIGHT")]))
    story.append(tb)
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename=agrisat_campagne_{d['campaign']}.pdf"})


@router.get("/settings")
def read_settings(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return get_settings(db)


@router.put("/settings")
def write_settings(body: dict, u: User = Depends(require("admin")), db: Session = Depends(get_db)):
    before = get_settings(db)
    for k, v in body.items():
        if k not in DEFAULTS:
            raise HTTPException(400, f"Paramètre inconnu: {k}")
        if k in ("subsidy_rate", "expense_rate", "cost_of_capital", "claims_audit_threshold") and not (0 <= float(v) < 1):
            raise HTTPException(400, f"{k} doit être compris entre 0 et 1")
        set_setting(db, k, v)
    audit(db, u, "modification_parametres", "settings", before=before, after=body)
    db.commit()
    return get_settings(db)


@router.get("/audit")
def audit_log(_: User = Depends(require("assureur")), db: Session = Depends(get_db)):
    return [{"id": a.id, "username": a.username, "action": a.action, "target": a.target, "after": a.after,
             "created_at": a.created_at.isoformat()} for a in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(500)]


class UserIn(BaseModel):
    username: str
    full_name: str
    role: str
    password: str
    organisation_id: int | None = None


@router.get("/users")
def users(_: User = Depends(require("admin")), db: Session = Depends(get_db)):
    return [{"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
             "organisation_id": u.organisation_id} for u in db.query(User)]


@router.post("/users")
def create_user(body: UserIn, u: User = Depends(require("admin")), db: Session = Depends(get_db)):
    if body.role not in ("admin", "assureur", "cooperative", "imf", "partenaire"):
        raise HTTPException(400, "Rôle inconnu")
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(400, "Identifiant déjà utilisé")
    nu = User(username=body.username, full_name=body.full_name, role=body.role,
              password_hash=hash_password(body.password), organisation_id=body.organisation_id)
    db.add(nu)
    audit(db, u, "creation_utilisateur", body.username, after={"role": body.role})
    db.commit()
    return {"id": nu.id}
