"""Snake, driven through a real terminal."""
import os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["SNAKE_SAVE"] = os.path.join(tempfile.mkdtemp(), "s.json")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import pty_lib
from pty_lib import VT, drain, spawn, stop
import snake as S

H, W = 30, 100
pty_lib.H, pty_lib.W = H, W
GAME = os.path.join(HERE, "..", "snake.py")

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

class Run(object):
    def __init__(self, extra=None, rows=H, cols=W, start=True):
        pty_lib.H, pty_lib.W = rows, cols
        self.pid, self.fd = spawn([GAME, "--seed", "3"] + (extra or []), rows, cols)
        self.vt = VT(rows, cols)
        self.vt.feed(drain(self.fd, 1.0).decode("utf-8", "replace"))
        self.L = S.Layout(*S.SIZES[self._size(rows, cols, extra)])
        self.ox = max(0, (cols - self.L.w) // 2)
        self.oy = max(0, (rows - self.L.h) // 2)
        if start:
            self.k(b"d", .3)             # the run waits for a direction
    def _size(self, rows, cols, extra):
        if extra and "--size" in extra:
            return extra[extra.index("--size") + 1]
        return S.pick_size(rows, cols)
    def k(self, b, w=.35):
        os.write(self.fd, b)
        self.vt.feed(drain(self.fd, w).decode("utf-8", "replace"))
        return self.vt.dump()
    def dump(self):
        return self.vt.dump()
    def board(self):
        rows = self.dump().split("\n")
        out = []
        for gy in range(self.L.gh):
            line = (rows[self.oy + 2 + gy] if self.oy + 2 + gy < len(rows) else "")
            line += " " * (self.ox + 1 + self.L.gw * 2)
            seg = line[self.ox + 1: self.ox + 1 + self.L.gw * 2]
            out.append("".join(seg[gx * 2] for gx in range(self.L.gw)))
        return out
    def close(self):
        os.write(self.fd, b"q"); drain(self.fd, .2); stop(self.pid, self.fd)

print("[1] it draws")
r = Run(start=False)
check("it waits before setting off", "press a direction" in r.dump(),
      [l.strip() for l in r.dump().split("\n") if "direction" in l])
r.k(b"d", .3)
d = r.dump()
check("the title is there", "S N A K E" in d)
check("a score panel", "SCORE" in d and "BEST" in d)
check("level, length and time", all(w in d for w in ("LEVEL", "LENGTH", "TIME")))
check("key hints", "pause" in d and "quit" in d)
b = r.board()
SNAKE_CHARS = "█▓"
def snake_cells(board):
    return sum(sum(row.count(c) for c in SNAKE_CHARS) for row in board)
check("a snake is on the board", snake_cells(b) >= S.START_LENGTH,
      (snake_cells(b), [row for row in b if any(c in row for c in SNAKE_CHARS)]))
check("it is drawn head, body and tail",
      any("█" in row for row in b) and any("▓" in row for row in b))
check("and an apple", any("◆" in row for row in b), [row for row in b if "◆" in row])
check("nothing spills past the frame",
      all(len(l.rstrip()) <= r.ox + r.L.w for l in d.split("\n")))
r.close()

print("\n[2] it moves on its own")
r = Run()
first = r.board()
r.k(b"", .8)
check("the snake advanced without input", r.board() != first)
r.close()

print("\n[3] steering")
def heading(before, after):
    """Which way the head went between two boards."""
    def head_cells(b):
        return set((x, y) for y, row in enumerate(b)
                   for x, c in enumerate(row) if c == "█")
    a, c = head_cells(before), head_cells(after)
    return c - a

r = Run(["--size", "large"])
r.k(b"w", .5)
up = r.board()
r.k(b"", .5)
after = r.board()
moved = heading(up, after)
check("w sends it upward", moved and min(y for _, y in moved) <= min(
      y for y, row in enumerate(up) for c in row if c == "█"), sorted(moved)[:3])
r.close()

r = Run(["--size", "large"])
before = r.board()
r.k(b"\x1bOB", .5)                     # arrow down, application-cursor form
r.k(b"", .4)
check("the down arrow is understood", r.board() != before)
r.close()

print("\n[4] pause and help")
r = Run()
d = r.k(b"p", .5)
check("pause stops it", "P A U S E D" in d)
frozen = r.board()
r.k(b"", .8)
check("and nothing moves while paused", r.board() == frozen)
d = r.k(b"p", .5)
check("p resumes", "P A U S E D" not in d)
d = r.k(b"?", .6)
check("help explains the keys", "CONTROLS" in d and "pause / resume" in d)
check("and the rules", "golden apple" in d, [l.strip() for l in d.split("\n") if "golden" in l])
d = r.k(b"\r", .5)
check("any key closes it", "CONTROLS" not in d)
r.close()

print("\n[5] themes")
r = Run()
before = r.vt.colours()
d = r.k(b"t", .5)
check("t names the new theme", any(t.upper() in d for t in S.THEME_ORDER[1:]),
      [l.strip() for l in d.split("\n") if any(t.upper() in l for t in S.THEME_ORDER)])
check("and repaints", r.vt.colours() != before)
r.close()

print("\n[6] dying, and starting again")
r = Run(["--size", "small"])
for _ in range(40):                     # drive into the right-hand wall
    r.k(b"d", .12)
d = r.dump()
check("running into the wall ends it", "G A M E   O V E R" in d,
      [l.strip() for l in d.split("\n") if "OVER" in l])
check("it reports the run", "SCORE" in d and "LENGTH" in d)
d = r.k(b"r", .6)
check("r starts a fresh run", "G A M E   O V E R" not in d)
check("with a full-length snake again",
      snake_cells(r.board()) >= S.START_LENGTH, snake_cells(r.board()))
r.close()

print("\n[7] wrap and maze modes")
r = Run(["--wrap", "--size", "small"])
check("wrap is advertised on the frame", "WRAP" in r.dump())
for _ in range(40):
    r.k(b"d", .12)
check("you can circle the board forever", "G A M E   O V E R" not in r.dump())
r.close()

r = Run(["--maze", "12", "--size", "large"])
b = r.board()
check("blocks were laid out", sum(row.count("▒") for row in b) > 5,
      sum(row.count("▒") for row in b))
r.close()

print("\n[8] ascii and small terminals")
r = Run(["--ascii"])
b = r.board()
check("ascii mode draws without unicode",
      any("[" in row for row in b) and not any("█" in row for row in b), b[:3])
r.close()

r = Run(rows=12, cols=40)
check("a small window is refused politely", "Terminal too small" in r.dump(),
      r.dump().split("\n")[0][:60])
r.close()

out = subprocess.run([sys.executable, GAME, "--help"], capture_output=True, text=True).stdout
check("every flag is documented",
      all(f in out for f in ("--size", "--wrap", "--maze", "--theme", "--seed", "--ascii")))

print("\n" + ("SNAKE UI OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
