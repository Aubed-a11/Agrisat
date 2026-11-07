"""Generateur stochastique de pluie journaliere multi-sites.

Occurrence: chaine de Markov d'ordre 1 par commune et par mois, correlation spatiale par
copule gaussienne (Cholesky de la matrice de correlation des scores normaux observes).
Hauteur: loi Gamma par commune et par mois (methode des moments sur les jours pluvieux).
Variabilite interannuelle: facteur multiplicatif lognormal (regional + local) calibre pour
reproduire l'ecart type observe des cumuls saisonniers.
"""
import numpy as np
from scipy import stats

from ..synthetic import MONTH_OF_DAY

WET = 1.0


class RainGenerator:
    def __init__(self):
        self.fitted = False

    def fit(self, rain):
        """rain: (C, Y, 365) pluie observee (satellite)."""
        rain = np.asarray(rain, np.float64)
        C, Y, D = rain.shape
        self.C = C
        self.p01 = np.zeros((C, 12))
        self.p11 = np.zeros((C, 12))
        self.shape = np.ones((C, 12))
        self.scale = np.ones((C, 12))
        wet = rain >= WET
        for m in range(12):
            days = np.where(MONTH_OF_DAY == m)[0]
            for c in range(C):
                w = wet[c][:, days]
                prev, cur = w[:, :-1].ravel(), w[:, 1:].ravel()
                n0, n1 = (~prev).sum(), prev.sum()
                self.p01[c, m] = (cur & ~prev).sum() / n0 if n0 else 0.0
                self.p11[c, m] = (cur & prev).sum() / n1 if n1 else 0.0
                amt = rain[c][:, days][w[:, :]] - WET
                if len(amt) > 10:
                    mu, var = amt.mean(), amt.var()
                    k = np.clip(mu ** 2 / max(var, 1e-6), 0.3, 3.0)
                    self.shape[c, m], self.scale[c, m] = k, mu / k
                else:
                    self.shape[c, m], self.scale[c, m] = 0.8, 5.0
        # correlation spatiale de l'occurrence (juin a septembre)
        jjas = np.where((MONTH_OF_DAY >= 5) & (MONTH_OF_DAY <= 8))[0]
        x = rain[:, :, jjas].reshape(C, -1)
        ranks = stats.rankdata(x, axis=1) / (x.shape[1] + 1)
        z = stats.norm.ppf(ranks)
        corr = np.corrcoef(z) if C > 1 else np.ones((1, 1))
        corr = (corr + corr.T) / 2 + np.eye(C) * 1e-6
        self.corr = corr
        self.chol = np.linalg.cholesky(corr)
        # calibrage de la variabilite interannuelle sur les cumuls de mai a octobre
        season = np.where((MONTH_OF_DAY >= 4) & (MONTH_OF_DAY <= 9))[0]
        obs_sd = np.log(rain[:, :, season].sum(axis=2) + 1).std(axis=1)
        self.sigma_year = np.zeros(C)
        self.fitted = True
        pilot = self.simulate(400, seed=123, batch=400).__next__()
        sim_sd = np.log(pilot[:, :, season].sum(axis=2) + 1).std(axis=0)
        self.sigma_year = np.sqrt(np.maximum(obs_sd ** 2 - sim_sd ** 2, 1e-4))
        return self

    def simulate(self, n, communes=None, seed=0, batch=1000):
        """Generateur de lots (b, len(communes), 365) de saisons simulees."""
        assert self.fitted
        idx = np.arange(self.C) if communes is None else np.asarray(communes)
        L = np.linalg.cholesky(self.corr[np.ix_(idx, idx)] + np.eye(len(idx)) * 1e-9)
        rng = np.random.default_rng(seed)
        p01 = self.p01[idx][:, MONTH_OF_DAY]
        p11 = self.p11[idx][:, MONTH_OF_DAY]
        k = self.shape[idx][:, MONTH_OF_DAY]
        th = self.scale[idx][:, MONTH_OF_DAY]
        sig = self.sigma_year[idx]
        done = 0
        while done < n:
            b = min(batch, n - done)
            c = len(idx)
            reg = rng.normal(size=(b, 1))
            loc = rng.normal(size=(b, c))
            yf = np.exp(sig[None, :] * (np.sqrt(0.9) * reg + np.sqrt(0.1) * loc) - sig[None, :] ** 2 / 2)
            out = np.zeros((b, c, 365), np.float32)
            wet = np.zeros((b, c), bool)
            for d in range(365):
                z = rng.normal(size=(b, c)) @ L.T
                u = stats.norm.cdf(z)
                prob = np.where(wet, p11[:, d], p01[:, d])
                wet = u < prob
                amt = WET + rng.gamma(k[:, d], th[:, d], size=(b, c)) * yf
                out[:, :, d] = np.where(wet, amt, 0.0)
            done += b
            yield out
