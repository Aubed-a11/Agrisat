from sqlalchemy.orm import Session

from agrisat_core.communes import CROP_PARAMS, PRICING_DEFAULTS
from .models import Setting

DEFAULTS = {
    "subsidy_rate": PRICING_DEFAULTS["subsidy_rate"],
    "expense_rate": PRICING_DEFAULTS["expense_rate"],
    "cost_of_capital": PRICING_DEFAULTS["cost_of_capital"],
    "sum_insured_ha": {k: v["sum_insured_ha"] for k, v in CROP_PARAMS.items()},
    "claims_audit_threshold": 0.10,     # part des assures d'une commune ayant reclame
    "advance_on_preliminary": True,
    "area_yield_coverage": 0.80,        # contrat rendement par zone (mais): seuil en part de la tendance
}


def get_settings(db: Session) -> dict:
    s = dict(DEFAULTS)
    for row in db.query(Setting).all():
        s[row.key] = row.value["v"]
    return s


def set_setting(db: Session, key, value):
    row = db.get(Setting, key)
    if row:
        row.value = {"v": value}
    else:
        db.add(Setting(key=key, value={"v": value}))
