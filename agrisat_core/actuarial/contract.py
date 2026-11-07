"""Contrat indiciel par phase: indemnite lineaire entre seuil de declenchement et seuil de sortie."""
from dataclasses import dataclass, asdict, field
import numpy as np


@dataclass
class PhaseContract:
    commune_id: int
    crop: str
    trigger: list            # T par phase (mm de pluie plafonnee)
    exit: list               # E par phase
    weights: list            # part de la somme assuree par phase
    sum_insured_ha: float    # FCFA par hectare
    meta: dict = field(default_factory=dict)

    def payout_fraction(self, index):
        return payout_fraction(index, self.trigger, self.exit, self.weights)

    def to_dict(self):
        return asdict(self)


def payout_fraction(index, trigger, exit_, weights):
    """index (N, 4) -> fraction de la somme assuree versee (N,), plafonnee a 1."""
    index = np.atleast_2d(np.asarray(index, dtype=np.float64))
    T = np.asarray(trigger, dtype=np.float64)[None, :]
    E = np.asarray(exit_, dtype=np.float64)[None, :]
    w = np.asarray(weights, dtype=np.float64)[None, :]
    span = np.maximum(T - E, 1e-9)
    frac = np.clip((T - index) / span, 0.0, 1.0)
    return np.minimum((w * frac).sum(axis=1), 1.0)


def phase_payouts(index, trigger, exit_, weights):
    """Detail par phase (N, 4) de la fraction versee."""
    index = np.atleast_2d(np.asarray(index, dtype=np.float64))
    T = np.asarray(trigger)[None, :]
    E = np.asarray(exit_)[None, :]
    return np.asarray(weights)[None, :] * np.clip((T - index) / np.maximum(T - E, 1e-9), 0, 1)
