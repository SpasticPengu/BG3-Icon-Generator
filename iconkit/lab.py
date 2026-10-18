"""scikit-image's colour formulas and disk, copied (skimage 0.26 color/colorconv.py, morphology/footprints.py) so the app's
runtime path (glyph.split, grammar.tint, hotbar.compose, variants) runs without scikit-image (D46). Fitting and review code
still gets deltaE_ciede2000 / skeletonize from scikit-image, imported on first use. `check()` compares with skimage."""
import numpy as np

XYZ_FROM_RGB = np.array([[0.412453, 0.357580, 0.180423], [0.212671, 0.715160, 0.072169], [0.019334, 0.119193, 0.950227]])
RGB_FROM_XYZ = np.linalg.inv(XYZ_FROM_RGB)
WHITE = np.array([0.95047, 1.0, 1.08883])                  # D65, 2 degree observer


def _float(x):
    x = np.asarray(x)
    if x.dtype.kind in "ui":
        return x.astype(np.float64) / np.iinfo(x.dtype).max
    return x.astype(np.float32 if x.dtype == np.float32 else np.float64, copy=True)


def rgb2lab(rgb):
    arr = _float(rgb)
    m = arr > 0.04045
    arr[m] = np.power((arr[m] + 0.055) / 1.055, 2.4)
    arr[~m] /= 12.92
    arr = arr @ XYZ_FROM_RGB.T.astype(arr.dtype) / WHITE.astype(arr.dtype)
    m = arr > 0.008856
    arr[m] = np.cbrt(arr[m])
    arr[~m] = 7.787 * arr[~m] + 16.0 / 116.0
    x, y, z = arr[..., 0], arr[..., 1], arr[..., 2]
    return np.stack([116.0 * y - 16.0, 500.0 * (x - y), 200.0 * (y - z)], -1)


def lab2rgb(lab):
    arr = _float(lab)
    y = (arr[..., 0] + 16.0) / 116.0
    out = np.stack([arr[..., 1] / 500.0 + y, y, np.maximum(y - arr[..., 2] / 200.0, 0)], -1)
    m = out > 0.2068966
    out[m] = np.power(out[m], 3.0)
    out[~m] = (out[~m] - 16.0 / 116.0) / 7.787
    arr = (out * WHITE.astype(out.dtype)) @ RGB_FROM_XYZ.T.astype(out.dtype)
    m = arr > 0.0031308
    arr[m] = 1.055 * np.power(arr[m], 1 / 2.4) - 0.055
    arr[~m] *= 12.92
    return np.clip(arr, 0, 1)


def disk(radius, dtype=np.uint8):
    L = np.arange(-radius, radius + 1)
    X, Y = np.meshgrid(L, L)
    return np.array((X ** 2 + Y ** 2) <= radius ** 2, dtype=dtype)


def deltaE_ciede2000(*a, **k):
    from skimage.color import deltaE_ciede2000 as f
    return f(*a, **k)


def skeletonize(*a, **k):
    from skimage.morphology import skeletonize as f
    return f(*a, **k)


def check():
    from skimage import color, morphology
    rng = np.random.default_rng(0)
    for dt in (np.float64, np.float32):
        x = rng.random((64, 64, 3)).astype(dt)
        lab = color.rgb2lab(x)
        assert np.abs(rgb2lab(x) - lab).max() < 1e-4 and rgb2lab(x).dtype == lab.dtype, dt
        y = np.stack([rng.uniform(0, 100, (64, 64)), rng.uniform(-90, 90, (64, 64)), rng.uniform(-90, 90, (64, 64))], -1).astype(dt)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert np.abs(lab2rgb(y) - color.lab2rgb(y)).max() < 1e-5, dt
    assert all((disk(r) == morphology.disk(r)).all() for r in (1, 6, 12, 20))
    print("[lab] check passed: rgb2lab / lab2rgb / disk match scikit-image")


if __name__ == "__main__":
    check()
