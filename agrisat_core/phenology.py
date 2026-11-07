"""Phenologie: demarrage de saison (critere de type AGRHYMET) et fenetres de phases.

Toutes les fonctions travaillent sur des tableaux (N, 365) de pluie journaliere en mm,
un calendrier de 365 jours (le 29 fevrier est ignore). Les jours sont indexes de 0 a 364.
"""
import numpy as np

ONSET_SEARCH_START = 104   # 15 avril (index 0 = 1er janvier)
ONSET_SEARCH_END = 212     # 31 juillet
WET_DAY_MM = 1.0


def _dry_run_lengths(rain):
    """Longueur de la sequence seche qui se termine a chaque jour. rain: (N, D)."""
    n, d = rain.shape
    dry = rain < WET_DAY_MM
    run = np.zeros((n, d), dtype=np.int16)
    cur = np.zeros(n, dtype=np.int16)
    for t in range(d):
        cur = np.where(dry[:, t], cur + 1, 0)
        run[:, t] = cur
    return run


def detect_onset(rain, start=ONSET_SEARCH_START, end=ONSET_SEARCH_END,
                 threshold=20.0, window3=3, dry_spell=7, horizon=30):
    """Date de demarrage de la saison par serie.

    Premier jour d tel que la pluie cumulee sur d..d+2 atteint `threshold` mm et qu'aucune
    sequence seche de `dry_spell` jours n'apparait dans les `horizon` jours suivants.
    Retourne un tableau (N,) d'index de jour; `end` si aucun demarrage n'est trouve.
    """
    rain = np.asarray(rain, dtype=np.float32)
    n, d = rain.shape
    cs = np.concatenate([np.zeros((n, 1), np.float32), np.cumsum(rain, axis=1)], axis=1)
    run = _dry_run_lengths(rain)
    onset = np.full(n, end, dtype=np.int32)
    found = np.zeros(n, dtype=bool)
    for day in range(start, end):
        s3 = cs[:, day + window3] - cs[:, day]
        hi = min(d, day + window3 + horizon)
        max_run = run[:, day + window3:hi].max(axis=1)
        ok = (s3 >= threshold) & (max_run < dry_spell) & (~found)
        onset[ok] = day
        found |= ok
        if found.all():
            break
    return onset


def false_start(rain, onset, dry_spell=10, horizon=20):
    """Vrai si une sequence seche d'au moins `dry_spell` jours suit le demarrage."""
    run = _dry_run_lengths(rain)
    res = np.zeros(len(onset), dtype=bool)
    for i, o in enumerate(onset):
        res[i] = run[i, o + 1:o + 1 + horizon].max(initial=0) >= dry_spell
    return res


def sowing_dates(onset, crop_params):
    lo, hi = crop_params["sowing_window"]
    return np.clip(onset, lo, hi).astype(np.int32)


def phase_bounds(sowing, crop_params):
    """Bornes [debut, fin) des 4 phases. Retourne (N, 4, 2)."""
    lengths = np.array(crop_params["phase_lengths"], dtype=np.int32)
    starts = sowing[:, None] + np.concatenate([[0], np.cumsum(lengths)[:-1]])[None, :]
    ends = starts + lengths[None, :]
    ends = np.minimum(ends, 365)
    return np.stack([starts, ends], axis=2)


def window_sum(arr, bounds):
    """Somme de arr (N, D) sur des fenetres (N, P, 2) via sommes cumulees."""
    n = arr.shape[0]
    cs = np.concatenate([np.zeros((n, 1), arr.dtype), np.cumsum(arr, axis=1)], axis=1)
    rows = np.arange(n)[:, None]
    return cs[rows, bounds[:, :, 1]] - cs[rows, bounds[:, :, 0]]
