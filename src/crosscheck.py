"""Cross-check with reference building maps and the census: pure functions, no Earth Engine needed.

References are roof fractions (0-100 % of each 10 m pixel covered by buildings) on the
same grid as our map. Our map shows built-up *pixels* (roofs, yards, streets between
houses), so its area is larger than a roof area by definition: the checks below measure
where the two agree, not whether the areas are equal.
"""
import re
import unicodedata

import numpy as np
from scipy import ndimage


def roof_share_inside(roof: np.ndarray, ours: np.ndarray, inside: np.ndarray) -> float:
    """Share of the reference roof area of the zone that falls in our built-up pixels.

    Close to 1: we miss few of the buildings of the reference (low omission).
    """
    total = roof[inside].sum(dtype=np.float64)
    return float(roof[ours & inside].sum(dtype=np.float64) / total) if total > 0 else float("nan")


def confirmed(roof: np.ndarray, window_px: int, min_roof_pct: float) -> np.ndarray:
    """Pixels with reference roofs nearby: mean roof fraction of the window >= ``min_roof_pct``.

    The window absorbs small misregistrations between the two maps (a few metres).
    """
    return ndimage.uniform_filter(roof.astype(np.float32), size=window_px, mode="nearest") >= min_roof_pct


def confirmation_rates(confirmed_mask: np.ndarray, groups: dict) -> dict:
    """Share (%) of the pixels of each group that are confirmed (NaN for an empty group)."""
    return {name: float(confirmed_mask[mask].mean() * 100) if mask.any() else float("nan")
            for name, mask in groups.items()}


def block_mean(a: np.ndarray, k: int) -> np.ndarray:
    """Mean over k x k blocks (the last rows and columns that do not fill a block are dropped)."""
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    return a[:h, :w].astype(np.float64).reshape(h // k, k, w // k, k).mean(axis=(1, 3))


def cell_correlation(ours: np.ndarray, roof: np.ndarray, inside: np.ndarray, k: int) -> float:
    """Pearson correlation between our built-up share and the roof share, over k x k cells.

    Only cells entirely inside the zone are used.
    """
    full = block_mean(inside, k) == 1
    x, y = block_mean(ours, k)[full], block_mean(roof, k)[full]
    if x.size < 2 or x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def growth_pct(start: float, end: float) -> float:
    """Growth from ``start`` to ``end`` in %."""
    return (end / start - 1) * 100 if start > 0 else float("nan")


def annual_growth_pct(start: float, end: float, years: float) -> float:
    """Compound annual growth rate in % (to compare periods of different lengths)."""
    return ((end / start) ** (1 / years) - 1) * 100 if start > 0 and years > 0 else float("nan")


def name_key(name: str) -> str:
    """Comparable commune name: 'Mermoz-Sacré-Cœur' and 'MERMOZ SACRE COEUR' give the same key."""
    s = str(name).replace("œ", "oe").replace("Œ", "OE")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"['’`]", "", s)            # M'bour -> MBOUR
    s = re.sub(r"[-_./]", " ", s)
    return re.sub(r"\s+", " ", s).strip()
