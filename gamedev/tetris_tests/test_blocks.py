"""Block styles: the glyph a piece is drawn with, independent of its colour."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import pty_lib
from pty_lib import VT, drain, spawn, stop
import tetris as T

H, W = 30, 90
pty_lib.H, pty_lib.W = H, W
LAY = T.Layout(*T.SCALES["small"])
OX, OY = (W - LAY.w) // 2, (H - LAY.h) // 2
GAME = os.path.join(HERE, "..", "tetris.py")

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

print("[1] every style tiles at every cell size")
for style in T.BLOCK_STYLES:
    for cw, ch in T.SCALES.values():
        g = T.Glyphs(True, cw, ch, style)
        check("%s at %dx%d fills the cell exactly" % (style, cw, ch),
              len(g.solid) == ch and all(len(r) == cw for r in g.solid),
              [len(r) for r in g.solid])
        check("%s at %dx%d has a matching ghost" % (style, cw, ch),
              len(g.ghost) == ch and all(len(r) == cw for r in g.ghost))
        check("%s at %dx%d has a matching empty cell" % (style, cw, ch),
              len(g.empty) == ch and all(len(r) == cw for r in g.empty))

print("\n[2] the styles are actually different")
sigs = dict((st, tuple(T.Glyphs(True, 2, 1, st).solid)) for st in T.BLOCK_STYLES)
check("no two styles draw the same block", len(set(sigs.values())) == len(sigs),
      sigs)
check("a ghost is never the same as its block",
      all(T.Glyphs(True, cw, ch, st).ghost != T.Glyphs(True, cw, ch, st).solid
          for st in T.BLOCK_STYLES for cw, ch in T.SCALES.values()))
ghosts = dict((st, T.Glyphs(True, 2, 1, st).ghost[0]) for st in T.BLOCK_STYLES)
check("the ghost follows the style rather than sitting at one glyph",
      len(set(ghosts.values())) >= 4, ghosts)
check("a round block has a hollow round ghost", ghosts["round"] == "\u25cb\u25cb",
      ghosts["round"])
check("a braille block has a sparser braille ghost",
      ghosts["dots"] == "\u2836\u2836", ghosts["dots"])
check("a dark-shade block has a light-shade ghost",
      ghosts["shade"] == "\u2591\u2591", ghosts["shade"])
check("every ghost is lighter-looking than its block",
      all(ghosts[st] != T.Glyphs(True, 2, 1, st).solid[0] for st in T.BLOCK_STYLES))
check("the clear flash is solid whatever the style",
      all(T.Glyphs(True, 2, 1, st).full == ["██"] for st in T.BLOCK_STYLES))

print("\n[3] unicode styles degrade on an ascii terminal")
for style in T.BLOCK_STYLES:
    g = T.Glyphs(False, 2, 1, style)
    check("%s stays printable without unicode" % style,
          all(all(ord(c) < 128 for c in row) for row in g.solid + g.ghost + g.empty),
          g.solid)
check("inset falls back to brackets", T.Glyphs(False, 2, 1, "inset").solid == ["[]"])
check("shade falls back to hashes", T.Glyphs(False, 2, 1, "shade").solid == ["##"])

print("\n[4] the flags")
out = subprocess.run([sys.executable, GAME, "--help"], capture_output=True, text=True).stdout
check("every style is offered", all(st in out for st in T.BLOCK_STYLES),
      [st for st in T.BLOCK_STYLES if st not in out])
check("--no-margins is kept as a shorthand", "--no-margins" in out)

def render(extra):
    pid, fd = spawn([GAME, "--scale", "small", "--no-shake", "--quiet",
                     "--seed", "7"] + extra)
    vt = VT(H, W)
    vt.feed(drain(fd, .9).decode("utf-8", "replace"))
    os.write(fd, b" "); vt.feed(drain(fd, .5).decode("utf-8", "replace"))
    d = vt.dump()
    os.write(fd, b"q"); drain(fd, .2); stop(pid, fd)
    return d

print("\n[5] they reach the screen")
seen = {}
for style in T.BLOCK_STYLES:
    d = render(["--blocks", style])
    glyph = T.Glyphs(True, 2, 1, style).solid[0][0]
    seen[style] = d
    check("%s is drawn in the well" % style, glyph in d, repr(glyph))
check("--no-margins still means solid",
      T.Glyphs(True, 2, 1, "solid").solid[0] in render(["--no-margins"]))
check("--ascii overrides a unicode style",
      "[]" in render(["--ascii", "--blocks", "shade"]) or
      "##" in render(["--ascii", "--blocks", "shade"]))

print("\n[5b] the ghost on screen changes with the style")
def ghost_on_screen(dump):
    marks = set()
    for st in T.BLOCK_STYLES:
        g = T.Glyphs(True, 2, 1, st).ghost[0][0]
        if g in dump:
            marks.add(g)
    return marks

for style in ("inset", "shade", "dots", "round"):
    d = render(["--blocks", style])
    want = T.Glyphs(True, 2, 1, style).ghost[0][0]
    check("%s shows its own ghost in the well" % style, want in d, repr(want))

pid, fd = spawn([GAME, "--scale", "small", "--no-shake", "--quiet", "--seed", "7"])
vt = VT(H, W); vt.feed(drain(fd, .9).decode("utf-8", "replace"))
first = ghost_on_screen(vt.dump())
seen_ghosts = set(first)
for _ in range(len(T.BLOCK_STYLES)):
    os.write(fd, b"m"); vt.feed(drain(fd, .35).decode("utf-8", "replace"))
    seen_ghosts |= ghost_on_screen(vt.dump())
os.write(fd, b"q"); drain(fd, .2); stop(pid, fd)
check("pressing m repaints the ghost too", len(seen_ghosts) >= 4,
      sorted(seen_ghosts))
print("       ghosts seen while cycling: %s" % " ".join(sorted(seen_ghosts)))

print("\n[6] m cycles them in game")
pid, fd = spawn([GAME, "--scale", "small", "--no-shake", "--quiet", "--seed", "7"])
vt = VT(H, W); vt.feed(drain(fd, .9).decode("utf-8", "replace"))
names = []
for _ in range(len(T.BLOCK_STYLES)):
    os.write(fd, b"m"); vt.feed(drain(fd, .3).decode("utf-8", "replace"))
    hit = [n for n in T.BLOCK_STYLES if n.upper() in vt.dump()]
    if hit:
        names.append(hit[0])
os.write(fd, b"q"); drain(fd, .2); stop(pid, fd)
check("it walks the whole list", len(set(names)) == len(T.BLOCK_STYLES),
      names)
check("and names each one", names[0] == T.BLOCK_STYLES[1], names[:3])
print("       " + " -> ".join(names))

print("\n" + ("BLOCKS OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
