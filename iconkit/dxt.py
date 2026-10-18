"""BC3 (DXT5) encoder in numpy. Pillow's encoder (12.2) shifts line colours and paints red / black blocks on our hotbar
cells (3.2: round trip 11 /255 on cells it re-encodes vanilla BC3 cells at 0.02, so the game's own encoder does far better).
Colour: endpoints along the block's principal axis, then least-squares refits of both endpoints keeping the best after 565
rounding (stb_dxt's method); every error weighted by alpha (a transparent pixel's colour is never seen). Alpha: min / max
endpoints, 8 levels.
    python -m iconkit.dxt   -> self-check (decoded by Pillow)"""
import numpy as np

W = np.array([1, 0, 2 / 3, 1 / 3], np.float32)              # share of colour 0 for each 2-bit colour index
FIT = 4                                                      # least-squares refits


def q565(c):
    """(N,3) float 0..255 -> (N,) uint16 565 and the colour the decoder expands it to"""
    r, g, b = (np.clip(np.rint(c[:, i] * m / 255), 0, m).astype(np.uint16) for i, m in ((0, 31), (1, 63), (2, 31)))
    e = np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], 1).astype(np.float32)
    return (r << 11) | (g << 5) | b, e


def colour(col, wt):
    """(N,16,3) colours, (N,16) weights -> 565 endpoints q0, q1 (q0 >= q1: 4-colour mode) and (N,16) indices"""
    mean = (col * wt[..., None]).sum(1) / wt.sum(1)[:, None]
    d = col - mean[:, None]
    cov = np.einsum("npi,np,npj->nij", d, wt, d)
    v = np.ones_like(mean)
    for _ in range(8):                                       # power iteration -> principal axis
        v = np.einsum("nij,nj->ni", cov, v)
        v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
    t, vis = (d * v[:, None]).sum(2), wt > .01                # the axis' extent over visible pixels (0 in a clear block)
    hi, lo = np.where(vis, t, -np.inf).max(1, keepdims=True), np.where(vis, t, np.inf).min(1, keepdims=True)
    c0, c1 = mean + np.where(vis.any(1, keepdims=True), hi, 0) * v, mean + np.where(vis.any(1, keepdims=True), lo, 0) * v
    best = None
    for it in range(FIT + 1):
        (q0, e0), (q1, e1) = q565(c0), q565(c1)
        pal = W[None, :, None] * e0[:, None] + (1 - W)[None, :, None] * e1[:, None]           # (N,4,3)
        dist = ((col[:, :, None] - pal[:, None]) ** 2).sum(-1)                                 # (N,16,4)
        idx = dist.argmin(2)
        err = (dist.min(2) * wt).sum(1)
        if best is None:
            best = [q0, q1, idx, err]
        else:
            k = err < best[3]
            best = [np.where(k, q0, best[0]), np.where(k, q1, best[1]), np.where(k[:, None], idx, best[2]), np.minimum(err, best[3])]
        w = W[idx] * wt ** .5                                # least squares: minimise sum wt |w c0 + (1-w) c1 - x|^2
        u = (1 - W[idx]) * wt ** .5
        x = col * wt[..., None] ** .5
        A11, A12, A22 = (w * w).sum(1), (w * u).sum(1), (u * u).sum(1)
        b0, b1 = (w[..., None] * x).sum(1), (u[..., None] * x).sum(1)
        det = A11 * A22 - A12 * A12
        ok = (np.abs(det) > 1e-6)[:, None]
        sd = np.where(ok[:, 0], det, 1)[:, None]
        c0 = np.clip(np.where(ok, (A22[:, None] * b0 - A12[:, None] * b1) / sd, c0), 0, 255)
        c1 = np.clip(np.where(ok, (A11[:, None] * b1 - A12[:, None] * b0) / sd, c1), 0, 255)
    q0, q1, idx = best[:3]
    swap = q0 < q1                                           # keep 4-colour mode: colour 0 the larger, indices remapped
    q0, q1 = np.where(swap, q1, q0), np.where(swap, q0, q1)
    idx = np.where(swap[:, None], np.array([1, 0, 3, 2])[idx], idx)
    return q0, q1, np.where((q0 == q1)[:, None], 0, idx)


def alpha(a):
    """(N,16) alpha 0..255 -> a0 >= a1 (8-level mode) and (N,16) 3-bit indices"""
    a0, a1 = a.max(1), a.min(1)
    lv = np.stack([a0, a1] + [((8 - i) * a0 + (i - 1) * a1) / 7 for i in range(2, 8)], 1)        # codes 2..7: 6/7 .. 1/7 of a0
    idx = np.abs(a[:, :, None] - lv[:, None]).argmin(2)
    return a0.astype(np.uint8), a1.astype(np.uint8), np.where((a0 == a1)[:, None], 0, idx)


def encode(rgba):
    """(H,W,4) uint8 straight alpha -> BC3 block data (edges padded to whole 4 x 4 blocks)"""
    h, w = rgba.shape[:2]
    x = np.pad(rgba, ((0, -h % 4), (0, -w % 4), (0, 0)), mode="edge").astype(np.float32)
    b = x.reshape(x.shape[0] // 4, 4, x.shape[1] // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4)
    a0, a1, ai = alpha(b[..., 3])
    q0, q1, ci = colour(b[..., :3], b[..., 3] / 255 + 1e-3)
    out = np.zeros((len(b), 16), np.uint8)
    out[:, 0], out[:, 1] = a0, a1
    abits = (ai.astype(np.uint64) << (3 * np.arange(16, dtype=np.uint64))).sum(1)
    out[:, 2:8] = abits[:, None].view(np.uint8).reshape(-1, 8)[:, :6]
    out[:, 8:12] = np.stack([q0, q1], 1).astype("<u2").view(np.uint8)
    out[:, 12:16] = (ci.astype(np.uint32) << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype("<u4")[:, None].view(np.uint8)
    return out.tobytes()


def check():
    """decoded by Pillow: flat colours and alpha exact, a gradient close, transparent pixels' colour ignored"""
    import io, struct
    from PIL import Image

    def dec(im):
        h, w = im.shape[:2]
        head = struct.pack("<4s7I44x2I4s20x5I", b"DDS ", 124, 0x81007, h, w, len(encode(im)), 0, 0, 32, 4, b"DXT5", 0x1000, 0, 0, 0, 0)
        return np.asarray(Image.open(io.BytesIO(head + encode(im))).convert("RGBA")).astype(float)
    flat = np.zeros((8, 8, 4), np.uint8) + np.array([200, 80, 40, 255], np.uint8)
    assert np.abs(dec(flat) - flat).max() <= 4, "flat colour within 565 rounding"
    g = np.zeros((16, 16, 4), np.uint8)
    g[..., 0] = np.linspace(0, 255, 16)[None]
    g[..., 1], g[..., 3] = 128, np.linspace(255, 0, 16)[:, None]
    e = np.abs(dec(g) - g)
    assert e[..., 3].max() <= 3 and e[..., 0][g[..., 3] > 100].mean() < 3, f"gradient: alpha {e[..., 3].max()}, red {e[..., 0].mean():.1f}"
    two = np.zeros((4, 4, 4), np.uint8)
    two[:2] = [255, 0, 0, 255]
    two[2:] = [0, 255, 0, 0]                                # transparent green: its colour must not pull the red
    assert np.abs(dec(two)[:2, :, :3] - [255, 0, 0]).max() <= 4, "transparent pixels do not shift visible colour"
    print("[3.2] dxt check passed: flat colour, gradient, alpha, transparent pixels ignored")


if __name__ == "__main__":
    check()
