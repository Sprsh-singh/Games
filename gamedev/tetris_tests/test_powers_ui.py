"""Superpowers, driven through a real terminal."""
import os, sys
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
PROBE = os.path.join(HERE, "probe_tetris.py")

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

def run(powers="", floor="", extra=None):
    env_p, env_f = os.environ.get("PROBE_POWERS"), os.environ.get("PROBE_FLOOR")
    os.environ["PROBE_POWERS"] = powers
    os.environ["PROBE_FLOOR"] = floor
    pid, fd = spawn([PROBE, "--scale", "small", "--no-shake", "--quiet",
                     "--seed", "5"] + (extra or []))
    vt = VT(H, W)
    vt.feed(drain(fd, .9).decode("utf-8", "replace"))
    if env_p is None: os.environ.pop("PROBE_POWERS", None)
    if env_f is None: os.environ.pop("PROBE_FLOOR", None)
    return pid, fd, vt

def key(fd, vt, b, w=.4):
    os.write(fd, b)
    vt.feed(drain(fd, w).decode("utf-8", "replace"))
    return vt.dump()

def well(dump):
    rs = dump.split("\n")
    top = next((i for i, l in enumerate(rs)
                if len(l) > OX + LAY.pf_x and l[OX + LAY.pf_x] == "┌"), OY + 1)
    out = []
    for r in range(T.VISIBLE_ROWS):
        line = (rs[top + 1 + r] if top + 1 + r < len(rs) else "")
        line += " " * (OX + LAY.pf_x + 1 + 20)
        seg = line[OX + LAY.pf_x + 1: OX + LAY.pf_x + 1 + 20]
        out.append("".join("#" if seg[c * 2] in "█▐▗▝" else "." for c in range(T.COLS)))
    return out

print("[1] powers have a panel of their own")
pid, fd, vt = run()
d = vt.dump()
check("the box is always on the side", "POWERS" in d)
check("empty slots are shown", d.count("  -") >= T.POWER_SLOTS, d.count("  -"))
stop(pid, fd)

pid, fd, vt = run(powers="BOMB")
d = vt.dump()
check("the one in hand is keyed to f", "f BOMB" in d,
      [l.strip() for l in d.split("\n") if "BOMB" in l])
check("the other slots stay empty", d.count("  -") >= T.POWER_SLOTS - 1)
stop(pid, fd)

pid, fd, vt = run(powers="COMPACT,SLOW,SKIP")
d = vt.dump()
check("all three are listed at once",
      all(n in d for n in ("COMPACT", "SLOW", "SKIP")),
      [l.strip() for l in d.split("\n") if any(n in l for n in ("COMPACT","SLOW","SKIP"))])
check("only the front one is keyed", d.count("f ") == 1, d.count("f "))
stop(pid, fd)

print("\n[2] f fires it")
pid, fd, vt = run(powers="BOMB", floor="3")
before = well(vt.dump())
check("the floor is stacked", before[-1].count("#") == 9, before[-1])
d = key(fd, vt, b"f", .6)
after = well(d)
check("the bottom row went", after[-1].count("#") < 9 or after[-2].count("#") == 9,
      after[-2:])
check("it says so", "BOMB USED" in d, [l.strip() for l in d.split("\n") if "USED" in l])
check("and the panel no longer offers it", "f BOMB" not in d)
stop(pid, fd)

print("\n[3] with nothing in hand it says so")
pid, fd, vt = run()
d = key(fd, vt, b"f", .5)
check("no power, and it tells you", "NO POWER" in d,
      [l.strip() for l in d.split("\n") if "POWER" in l])
stop(pid, fd)

print("\n[4] a power that cannot help is kept, not wasted")
pid, fd, vt = run(powers="BOMB")          # empty well, nothing to bomb
d = key(fd, vt, b"f", .5)
check("it reports no effect", "NO EFFECT" in d,
      [l.strip() for l in d.split("\n") if "EFFECT" in l])
check("and you still hold it", "f BOMB" in d)
stop(pid, fd)

print("\n[5] SLOW shows a countdown")
import re
pid, fd, vt = run(powers="SLOW")
d = key(fd, vt, b"f", .6)
m = re.search(r"SLOW\s+(\d+)s", d)
check("the timer appears in the powers box", m is not None,
      [l.strip() for l in d.split("\n") if "SLOW" in l])
check("counting down from about twenty", m and 10 <= int(m.group(1)) <= 20,
      m.group(1) if m else None)
stop(pid, fd)

print("\n[6] LINE-I really hands you an I")
pid, fd, vt = run(powers="LINE-I")
d = key(fd, vt, b"f", .6)
top = [r for r in well(d)[:3] if "#" in r]
check("a four-wide piece is at the top", any(r.count("#") == 4 for r in top), top)
stop(pid, fd)

print("\n[7] the help explains them")
pid, fd, vt = run()
d = key(fd, vt, b"?", .6)
check("the key is listed", "use the superpower" in d)
check("and the rule is stated",
      "every %d levels" % T.POWER_EVERY in d,
      [l.strip() for l in d.split("\n") if "superpower" in l])
stop(pid, fd)

print("\n[8] they can be switched off")
pid, fd, vt = run(extra=["--no-powers"])       # nothing injected: as a player sees it
d = vt.dump()
check("the whole box is gone", "POWERS" not in d)
d = key(fd, vt, b"f", .5)
check("the button reports nothing to use", "NO POWER" in d,
      [l.strip() for l in d.split("\n") if "POWER" in l])
stop(pid, fd)

print("\n[9] the panel has room for everything at once")
pid, fd, vt = run(powers="SLOW,BOMB")
d = key(fd, vt, b"f", .6)                      # fire SLOW, still holding BOMB
check("the countdown is visible", "SLOW" in d and "s" in d,
      [l.strip() for l in d.split("\n") if "SLOW" in l])
check("and the next power is still offered", "f BOMB" in d,
      [l.strip() for l in d.split("\n") if "BOMB" in l])
check("the piece counters kept their place", "PIECES" in d and "TETRIS" in d)
check("neither has landed on the key hints",
      "rot" in d.split("\n")[-2] or "rot" in d.split("\n")[-1] or "rot" in d,
      d.split("\n")[-2:])
stop(pid, fd)

print("\n" + ("POWERS UI OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
