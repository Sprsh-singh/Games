"""Undo, driven through a real terminal."""
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
GAME = os.path.join(HERE, "..", "tetris.py")

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

def field(dump):
    rows = dump.split("\n")
    top = next((i for i, l in enumerate(rows)
                if len(l) > OX + LAY.pf_x and l[OX + LAY.pf_x] == "┌"), OY + 1)
    out = []
    for r in range(T.VISIBLE_ROWS):
        line = (rows[top + 1 + r] if top + 1 + r < len(rows) else "")
        line += " " * (OX + LAY.pf_x + 1 + T.COLS * 2)
        seg = line[OX + LAY.pf_x + 1: OX + LAY.pf_x + 1 + T.COLS * 2]
        out.append("".join("#" if seg[c * 2] in "█▐▗▝" else
                           ":" if seg[c * 2] == "▒" else "." for c in range(T.COLS)))
    return out

def solid(dump):
    return [r.replace(":", ".") for r in field(dump)]

class Run(object):
    def __init__(self, extra=None):
        self.pid, self.fd = spawn([GAME, "--scale", "small", "--no-shake",
                                   "--quiet", "--seed", "9"] + (extra or []))
        self.vt = VT(H, W)
        self.vt.feed(drain(self.fd, 1.0).decode("utf-8", "replace"))
    def k(self, b, w=.35):
        os.write(self.fd, b)
        self.vt.feed(drain(self.fd, w).decode("utf-8", "replace"))
        return self.vt.dump()
    def dump(self): return self.vt.dump()
    def close(self):
        os.write(self.fd, b"q"); drain(self.fd, .2); stop(self.pid, self.fd)

print("[1] the counter is on screen")
r = Run()
d = r.dump()
check("undo count is shown", "UNDO" in d, [l.strip() for l in d.split("\n") if "UNDO" in l])
check("it starts at three", "UNDO     3" in d.replace("  ", " ").replace("  ", " ")
      or "UNDO" in d and "3" in [l for l in d.split("\n") if "UNDO" in l][0],
      [l.strip() for l in d.split("\n") if "UNDO" in l])
r.close()

print("\n[2] u takes the piece back")
r = Run()
empty = solid(r.dump())
r.k(b"\x1bOD" * 4)
d = r.k(b" ", .5)
placed = solid(d)
check("a piece landed", any("#" in row for row in placed[-3:]), placed[-3:])
d = r.k(b"u", .5)
after = solid(d)
check("the well is clear again", not any("#" in row for row in after[-3:]), after[-3:])
check("the counter went down", "2" in [l for l in d.split("\n") if "UNDO" in l][0],
      [l.strip() for l in d.split("\n") if "UNDO" in l])
check("it says so", "UNDO  2" in d,
      [l.strip() for l in d.split("\n") if "UNDO" in l])
r.close()

print("\n[3] it runs out")
r = Run()
for _ in range(3):
    r.k(b" ", .4); r.k(b"u", .4)
d = r.k(b" ", .4)
d = r.k(b"u", .5)
check("the fourth is refused", "NO UNDOS" in d,
      [l.strip() for l in d.split("\n") if "UNDO" in l])
check("and the piece stays put", any("#" in row for row in solid(d)[-3:]))
r.close()

print("\n[4] it can be switched off")
r = Run(["--undo", "0"])
d = r.dump()
check("no counter when disabled", "UNDO" not in d)
r.k(b" ", .4)
d = r.k(b"u", .5)
check("pressing u explains itself", "UNDO OFF" in d,
      [l.strip() for l in d.split("\n") if "UNDO" in l])
r.close()

print("\n[5] and turned up")
r = Run(["--undo", "9"])
check("the limit is configurable", "9" in [l for l in r.dump().split("\n") if "UNDO" in l][0],
      [l.strip() for l in r.dump().split("\n") if "UNDO" in l])
r.close()

print("\n[6] the help mentions it")
r = Run()
d = r.k(b"?", .5)
check("listed in the controls", "undo the last piece" in d)
r.close()

print("\n" + ("UNDO UI OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
