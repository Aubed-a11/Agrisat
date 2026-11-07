"""Tarification actuarielle: prime pure Monte Carlo, cout du capital, Wang, subvention."""
import numpy as np
from scipy import stats

from ..features import contract_index


def var_cvar(x, level=0.995):
    x = np.sort(np.asarray(x, float))
    q = np.quantile(x, level)
    tail = x[x >= q]
    return float(q), float(tail.mean() if len(tail) else q)


def wang_premium(losses, lam=0.25):
    """Prime par transformation de Wang g(u) = Phi(Phi^-1(u) + lam) sur la fonction de survie."""
    x = np.sort(np.asarray(losses, float))[::-1]
    n = len(x)
    surv = np.arange(1, n + 1) / n
    g = stats.norm.cdf(stats.norm.ppf(np.clip(surv, 1e-12, 1 - 1e-12)) + lam)
    g_prev = np.concatenate([[0.0], g[:-1]])
    return float(np.sum(x * (g - g_prev)))


def premium_from_payouts(frac, sum_insured, subsidy_rate=0.8, expense_rate=0.25,
                         cost_of_capital=0.10, level=0.995, wang_lambda=0.25,
                         diversification=1.0):
    """frac: fractions simulees de la somme assuree. Retourne les primes par hectare en FCFA."""
    frac = np.asarray(frac, float)
    pay = frac * sum_insured
    el = float(pay.mean())
    var, cvar = var_cvar(pay, level)
    standalone_capital = max(cvar - el, 0.0)
    capital = diversification * standalone_capital
    commercial = (el + cost_of_capital * capital) / (1 - expense_rate)
    wang = wang_premium(pay, wang_lambda) / (1 - expense_rate)
    return {
        "sum_insured": round(sum_insured, 0),
        "expected_payout": round(el, 1),
        "std_payout": round(float(pay.std()), 1),
        "prob_payout": round(float((frac > 0).mean()), 4),
        "var": round(var, 1), "cvar": round(cvar, 1),
        "pure_premium": round(el, 1),
        "standalone_capital": round(standalone_capital, 1),
        "allocated_capital": round(capital, 1),
        "diversification_factor": round(diversification, 4),
        "pure_rate": round(el / sum_insured, 5),
        "commercial_premium": round(commercial, 1),
        "commercial_rate": round(commercial / sum_insured, 5),
        "wang_premium": round(wang, 1),
        "subsidy": round(subsidy_rate * commercial, 1),
        "farmer_premium": round((1 - subsidy_rate) * commercial, 1),
        "params": {"subsidy_rate": subsidy_rate, "expense_rate": expense_rate,
                   "cost_of_capital": cost_of_capital, "level": level, "wang_lambda": wang_lambda,
                   "diversification": diversification},
    }


def simulate_commune_index(generator, commune_idx, crop_params, n=10000, seed=0, batch=2000):
    """Indice contractuel simule (n, 4) pour une commune."""
    out = []
    for sims in generator.simulate(n, communes=[commune_idx], seed=seed, batch=batch):
        out.append(contract_index(sims[:, 0, :], crop_params))
    return np.concatenate(out, axis=0)
