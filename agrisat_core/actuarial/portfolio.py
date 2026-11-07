"""Risque du portefeuille de l'assureur: simulation conjointe, VaR, CVaR, reassurance stop-loss."""
import numpy as np

from ..features import contract_index
from .contract import payout_fraction
from .pricing import var_cvar


def simulate_portfolio(generator, contracts, exposure, crop_params, n=10000, seed=1, batch=1000):
    """contracts: {(commune_idx, crop): dict(T, E, weights, sum_insured_ha)}
    exposure: {(commune_idx, crop): hectares assures}. Retourne les indemnites totales simulees (n,).
    """
    communes = sorted({k[0] for k in contracts})
    pos = {c: i for i, c in enumerate(communes)}
    totals = []
    by_commune = np.zeros(len(communes))
    for sims in generator.simulate(n, communes=communes, seed=seed, batch=batch):
        tot = np.zeros(sims.shape[0])
        for (ci, crop), ct in contracts.items():
            idx = contract_index(sims[:, pos[ci], :], crop_params[crop])
            pay = payout_fraction(idx, ct["T"], ct["E"], ct["weights"]) * ct["sum_insured_ha"] * exposure[(ci, crop)]
            tot += pay
            by_commune[pos[ci]] += pay.sum()
        totals.append(tot)
    totals = np.concatenate(totals)
    return totals, {c: by_commune[pos[c]] / n for c in communes}


def portfolio_metrics(total_payouts, premium_income, level=0.995, attach_lr=1.2, limit_lr=3.0, reins_loading=1.4):
    x = np.asarray(total_payouts, float)
    el = float(x.mean())
    var, cvar = var_cvar(x, level)
    lr = x / premium_income
    recov = np.clip(x - attach_lr * premium_income, 0, (limit_lr - attach_lr) * premium_income)
    reins_premium = float(recov.mean() * reins_loading)
    net = x - recov
    nvar, ncvar = var_cvar(net, level)
    return {
        "premium_income": round(premium_income, 0),
        "expected_payout": round(el, 0),
        "expected_loss_ratio": round(el / premium_income, 3),
        "std_payout": round(float(x.std()), 0),
        "var": round(var, 0), "cvar": round(cvar, 0),
        "prob_loss_ratio_above_100": round(float((lr > 1).mean()), 4),
        "capital_required": round(max(cvar - premium_income, 0.0), 0),
        "stop_loss": {
            "attachment_loss_ratio": attach_lr, "limit_loss_ratio": limit_lr,
            "reinsurance_premium": round(reins_premium, 0),
            "net_var": round(nvar, 0), "net_cvar": round(ncvar, 0),
            "capital_required_net": round(max(ncvar - premium_income + reins_premium, 0.0), 0),
        },
        "loss_ratio_quantiles": {str(q): round(float(np.quantile(lr, q)), 3) for q in (0.5, 0.75, 0.9, 0.95, 0.99, 0.995)},
        "histogram": _hist(lr),
    }


def _hist(lr, bins=None):
    bins = np.array([0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, np.inf]) if bins is None else bins
    h, _ = np.histogram(lr, bins=bins)
    labels = ["0 à 25 %", "25 à 50 %", "50 à 75 %", "75 à 100 %", "100 à 125 %", "125 à 150 %", "150 à 200 %", "200 à 300 %", "plus de 300 %"]
    return [{"bucket": l, "share": round(float(v / len(lr)), 4)} for l, v in zip(labels, h)]
