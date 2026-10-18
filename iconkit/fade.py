"""Tooltip bottom fade: a clean curve of the row only (user, 2026-10-14).
Fitted to the central-column median of tooltip/controller alpha over 1,405 vanilla icons
(`python -m iconkit.extract fadefit` re-measures it): RMSE 1.7/255, max 7/255."""
import numpy as np

Y0, Y1, POWER = .253, 1.247, 1.8   # fade starts at 25.3% of the height; smoothstep would end below the icon


def bottom_fade(size):
    """(size, size) alpha multiplier: 1 at the top, easing to ~0 at the bottom edge."""
    t = np.clip(((np.arange(size) + .5) / size - Y0) / (Y1 - Y0), 0, 1)
    col = (1 - t * t * (3 - 2 * t)) ** POWER
    return np.repeat(col[:, None], size, axis=1).astype(np.float32)
