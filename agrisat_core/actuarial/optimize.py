"""Optimisation des seuils: maximise l'equivalent certain du revenu du producteur (utilite CRRA)."""
import numpy as np

from .contract import payout_fraction
from .basis_risk import basis_risk_metrics


def crra_ce(income, gamma=2.0):
    x = np.maximum(np.asarray(income, float), 1.0)
    if abs(gamma - 1) < 1e-9:
        return float(np.exp(np.mean(np.log(x))))
    u = np.mean(x ** (1 - gamma) / (1 - gamma))
    return float((u * (1 - gamma)) ** (1 / (1 - gamma)))


def design_contract(index_hist, index_eval, yields_eval, trend_eval, crop_params, *,
                    gamma=2.0, subsidy_rate=0.8, expense_rate=0.25, capital_load=1.15,
                    max_gross_rate=0.10, q_grid=None, e_grid=None):
    """Choisit (quantile de declenchement, ratio de sortie) communs aux 4 phases.

    index_hist: (Yh, 4) indice historique long (1981 a aujourd'hui) pour le prix de reference.
    index_eval, yields_eval, trend_eval: annees avec rendement observe pour le bien-etre.
    """
    q_grid = np.round(np.arange(0.10, 0.56, 0.05), 2) if q_grid is None else q_grid
    e_grid = np.round(np.arange(0.30, 0.86, 0.05), 2) if e_grid is None else e_grid
    w = np.asarray(crop_params["phase_weights"])
    si = crop_params["sum_insured_ha"]
    price = crop_params["price"]
    wealth0 = si  # richesse de base: equivalent du cout des intrants
    income0 = yields_eval * price - si + wealth0
    ce0 = crra_ce(income0, gamma)
    loss_rel = np.maximum(0.0, 1 - yields_eval / trend_eval)
    best = None
    for q in q_grid:
        T = np.quantile(index_hist, q, axis=0)
        for e in e_grid:
            E = e * T
            burn = payout_fraction(index_hist, T, E, w).mean()
            gross = burn * capital_load / (1 - expense_rate)
            if gross > max_gross_rate or burn <= 0:
                continue
            pay = payout_fraction(index_eval, T, E, w)
            income = income0 + pay * si - (1 - subsidy_rate) * gross * si
            ce = crra_ce(income, gamma)
            corr = np.corrcoef(pay, loss_rel)[0, 1] if pay.std() > 0 else 0.0
            score = (ce - ce0, corr)
            if best is None or score > best["score"]:
                best = {"score": score, "q": float(q), "e": float(e), "T": T, "E": E,
                        "burn_rate": float(burn), "gross_rate_approx": float(gross),
                        "ce_gain": float(ce - ce0), "ce_gain_pct": float((ce - ce0) / ce0)}
    if best is None:  # repli: contrat prudent
        T = np.quantile(index_hist, 0.15, axis=0)
        best = {"q": 0.15, "e": 0.5, "T": T, "E": 0.5 * T, "burn_rate": float(
            payout_fraction(index_hist, T, 0.5 * T, w).mean()), "gross_rate_approx": None,
            "ce_gain": 0.0, "ce_gain_pct": 0.0}
    pay_eval = payout_fraction(index_eval, best["T"], best["E"], w)
    best["basis_risk"] = basis_risk_metrics(pay_eval, loss_rel)
    best.pop("score", None)
    best["T"] = [round(float(v), 1) for v in best["T"]]
    best["E"] = [round(float(v), 1) for v in best["E"]]
    return best
