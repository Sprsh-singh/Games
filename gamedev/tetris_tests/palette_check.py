"""Colour-vision maths for the Tetris palettes.

Seven falling pieces have to be told apart at a glance, including by players
with colour vision deficiency. Eyeballing a palette does not establish that,
so this measures it: simulate dichromatic vision (Vienot, Brettel & Mollon
1999) and report the closest pair in CIE Lab.
"""

# ---- xterm-256 index -> sRGB -----------------------------------------------

_BASE16 = [
    (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
    (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
    (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
]
_CUBE = (0, 95, 135, 175, 215, 255)


def xterm_rgb(i):
    if i < 16:
        return _BASE16[i]
    if i < 232:
        i -= 16
        return (_CUBE[i // 36], _CUBE[(i // 6) % 6], _CUBE[i % 6])
    v = 8 + (i - 232) * 10
    return (v, v, v)


def nearest_xterm(hex_str):
    r = int(hex_str[0:2], 16); g = int(hex_str[2:4], 16); b = int(hex_str[4:6], 16)
    best, bestd = 0, 1e9
    for i in range(16, 256):
        rr, gg, bb = xterm_rgb(i)
        d = (rr - r) ** 2 + (gg - g) ** 2 + (bb - b) ** 2
        if d < bestd:
            best, bestd = i, d
    return best


# ---- colour space ----------------------------------------------------------

def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _unlin(c):
    c = max(0.0, min(1.0, c))
    return 255.0 * (12.92 * c if c <= 0.0031308
                    else 1.055 * (c ** (1 / 2.4)) - 0.055)


def _mul(m, v):
    return tuple(sum(m[r][c] * v[c] for c in range(3)) for r in range(3))


RGB2LMS = ((17.8824, 43.5161, 4.11935),
           (3.45565, 27.1554, 3.86714),
           (0.0299566, 0.184309, 1.46709))
LMS2RGB = ((0.0809444479, -0.130504409, 0.116721066),
           (-0.0102485335, 0.0540193266, -0.113614708),
           (-0.000365296938, -0.00412161469, 0.693511405))
SIMS = {
    "normal":      ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "protanopia":  ((0, 2.02344, -2.52581), (0, 1, 0), (0, 0, 1)),
    "deuteranopia": ((1, 0, 0), (0.494207, 0, 1.24827), (0, 0, 1)),
    "tritanopia":  ((1, 0, 0), (0, 1, 0), (-0.395913, 0.801109, 0)),
}


def simulate(rgb, mode):
    lin = tuple(_lin(c) * 255.0 for c in rgb)
    lms = _mul(RGB2LMS, lin)
    lms = _mul(SIMS[mode], lms)
    out = _mul(LMS2RGB, lms)
    return tuple(_unlin(c / 255.0) for c in out)


def to_lab(rgb):
    r, g, b = (_lin(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.00000
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1.0 / 3) if t > 0.008856 else (7.787 * t + 16.0 / 116)
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a, b):
    la, lb = to_lab(a), to_lab(b)
    return sum((x - y) ** 2 for x, y in zip(la, lb)) ** 0.5


def worst_pair(indices, mode):
    """Closest two colours under one kind of vision: (deltaE, i, j)."""
    cols = [(i, simulate(xterm_rgb(i), mode)) for i in indices]
    worst = (1e9, None, None)
    for a in range(len(cols)):
        for b in range(a + 1, len(cols)):
            d = delta_e(cols[a][1], cols[b][1])
            if d < worst[0]:
                worst = (d, cols[a][0], cols[b][0])
    return worst


def audit(indices):
    return dict((m, worst_pair(indices, m)) for m in SIMS)
