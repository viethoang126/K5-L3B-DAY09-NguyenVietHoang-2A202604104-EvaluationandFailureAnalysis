"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _norm(xs: Sequence[str]) -> list[str]:
    return [str(x).strip().upper() for x in xs]


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    h, j = _norm(human), _norm(judge)
    if len(h) != len(j):
        raise ValueError(f"length mismatch: {len(h)} human vs {len(j)} judge labels")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for hv, jv in zip(h, j):
        if jv == POS:
            cm["tp" if hv == POS else "fp"] += 1
        else:
            cm["fn" if hv == POS else "tn"] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    p_den, r_den = cm["tp"] + cm["fp"], cm["tp"] + cm["fn"]
    precision = cm["tp"] / p_den if p_den else 0.0
    recall = cm["tp"] / r_den if r_den else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = sum(cm.values())
    if n == 0:
        raise ValueError("kappa undefined on an empty sample")
    p_o = (cm["tp"] + cm["tn"]) / n
    h_fail, j_fail = (cm["tp"] + cm["fn"]) / n, (cm["tp"] + cm["fp"]) / n
    p_e = h_fail * j_fail + (1 - h_fail) * (1 - j_fail)
    if math.isclose(p_e, 1.0):
        raise ValueError("kappa undefined: expected agreement is 1 (constant labels)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1].
    Undefined (nan) when sens + spec <= 1: such a judge is no better than chance."""
    den = sensitivity + specificity - 1
    if den <= 0:
        return float("nan")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / den))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy import stats as sps

    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.shape != y.shape:
        raise ValueError(f"paired bootstrap needs equal-length samples ({x.size} vs {y.size})")
    if x.size == 0:
        raise ValueError("paired bootstrap on an empty sample")
    if np.array_equal(x, y):
        return 0.0, 0.0, 0.0
    d = float(x.mean() - y.mean())
    diff = x - y
    if np.all(diff == diff[0]):          # zero variance: every resample gives the same Δ
        return d, d, d

    def stat(u, v, axis=-1):
        return np.mean(u, axis=axis) - np.mean(v, axis=axis)

    res = sps.bootstrap((x, y), stat, paired=True, vectorized=True, n_resamples=n_resamples,
                        confidence_level=confidence, method="percentile",
                        rng=np.random.default_rng(rng))
    return d, float(res.confidence_interval.low), float(res.confidence_interval.high)


def _check_nck(n: int, c: int, k: int) -> None:
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (n, c, k)):
        raise ValueError(f"n, c, k must be integers, got {(n, c, k)!r}")
    if n < 1 or k < 1:
        raise ValueError(f"need n >= 1 and k >= 1, got n={n}, k={k}")
    if not 0 <= c <= n:
        raise ValueError(f"need 0 <= c <= n, got c={c}, n={n}")
    if k > n:
        raise ValueError(f"k={k} > n={n}: cannot draw k trials from n")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_nck(n, c, k)
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    return math.comb(c, k) / math.comb(n, k)
