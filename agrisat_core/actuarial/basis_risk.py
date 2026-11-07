"""Mesures du risque de base entre indemnites indicielles et pertes reelles."""
import numpy as np

LOSS_THRESHOLD = 0.30     # perte significative: plus de 30 pour cent du rendement de tendance
NO_LOSS = 0.10


def basis_risk_metrics(payout_frac, loss_rel):
    """payout_frac: fraction de la somme assuree versee; loss_rel: perte relative au rendement de tendance."""
    p = np.asarray(payout_frac, float)
    l = np.asarray(loss_rel, float)
    big = l > LOSS_THRESHOLD
    paid = p > 0
    corr = float(np.corrcoef(p, l)[0, 1]) if p.std() > 0 and l.std() > 0 else 0.0
    return {
        "correlation": round(corr, 3),
        "false_negative_rate": round(float((big & ~paid).sum() / big.sum()), 3) if big.sum() else None,
        "false_positive_rate": round(float((paid & (l < NO_LOSS)).sum() / paid.sum()), 3) if paid.sum() else None,
        "n_loss_years": int(big.sum()),
        "n_paid_years": int(paid.sum()),
        "n_years": int(len(p)),
    }
