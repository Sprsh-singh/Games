"""Superpowers: useful when you are buried, worthless for farming points."""
import os, sys, tempfile, time, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import tetris as T
T.SCORE_FILE = os.path.join(tempfile.mkdtemp(), "s.json")

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

def blank(g):
    g.board = [[None] * T.COLS for _ in range(T.ROWS)]
def fill(g, row, gaps=()):
    for c in range(T.COLS):
        g.board[row][c] = None if c in gaps else "I"
def filled_cells(g):
    return sum(1 for r in g.board for c in r if c is not None)

print("[1] one arrives every three levels")
g = T.Game(seed=1)
grants = []
for lvl in range(2, 20):
    g.powers = []
    g.level = lvl - 1
    g.lines = (lvl - 1) * 10
    blank(g); g.board[20][0] = "I"
    fill(g, 39, (9,))
    g.piece = T.Piece("O"); g.piece.x = 8; g.piece.y = 38
    g.lines = lvl * 10 - 1
    g.lock()
    if g.powers:
        grants.append(g.level)
check("granted on every third level", all(l % T.POWER_EVERY == 0 for l in grants), grants)
check("and only then", len(set(grants)) == len(grants) and len(grants) >= 5, grants)
print("       levels that granted one: %s" % sorted(set(grants)))

print("\n[2] you can hold a few, not a hoard")
g = T.Game(seed=2)
for _ in range(10):
    g.grant_power()
check("the queue is capped", len(g.powers) == T.POWER_SLOTS, len(g.powers))
check("every one is a real power", all(p in T.POWERS for p in g.powers), g.powers)

print("\n[3] BOMB takes the bottom row")
g = T.Game(seed=3); blank(g)
fill(g, 39, (3,)); fill(g, 38, (1, 2))
g.piece = T.Piece("O"); g.piece.x = 4; g.piece.y = 20
g.powers = ["BOMB"]
before_score, before_lines = g.score, g.lines
check("it fires", g.use_power() == "BOMB")
check("the bottom row is gone", all(c is None for c in g.board[39][:3]) or
      g.board[39].count(None) == 2, g.board[39])
check("what was above has come down", g.board[39].count(None) == 2, g.board[39])
check("it scored nothing", g.score == before_score and g.lines == before_lines,
      (g.score, g.lines))
check("the power was spent", g.powers == [])
g2 = T.Game(seed=3); blank(g2); g2.powers = ["BOMB"]
check("and it refuses on an empty floor", g2.use_power() is None)
check("keeping the power in hand", g2.powers == ["BOMB"])

print("\n[4] COMPACT closes holes")
g = T.Game(seed=4); blank(g)
g.board[30][0] = "I"; g.board[35][0] = "I"      # column 0 with gaps under it
g.board[20][5] = "I"
g.piece = T.Piece("O"); g.piece.x = 8; g.piece.y = 20
g.powers = ["COMPACT"]
n_before = filled_cells(g)
check("it fires", g.use_power() == "COMPACT")
check("nothing was destroyed", filled_cells(g) == n_before, (n_before, filled_cells(g)))
check("column 0 is packed to the floor",
      g.board[39][0] == "I" and g.board[38][0] == "I" and g.board[37][0] is None,
      [g.board[y][0] for y in range(36, 40)])
check("and so is column 5", g.board[39][5] == "I")

print("\n[5] COMPACT can complete rows, but they pay nothing")
g = T.Game(seed=5); blank(g)
for c in range(T.COLS):
    g.board[20 + c][c] = "I"                    # one block per column, staggered
g.piece = T.Piece("O"); g.piece.x = 4; g.piece.y = 20
g.powers = ["COMPACT"]
s0, l0 = g.score, g.lines
g.use_power()
check("the staggered blocks formed a row and it went", filled_cells(g) == 0,
      filled_cells(g))
check("no score for it", g.score == s0, (s0, g.score))
check("no lines credited", g.lines == l0, (l0, g.lines))
check("no combo either", g.combo == -1, g.combo)

print("\n[6] LINE-I and SKIP")
g = T.Game(seed=6); blank(g)
while g.piece.kind == "I":
    g.spawn()
g.powers = ["LINE-I"]
check("the falling piece becomes an I", g.use_power() == "LINE-I" and g.piece.kind == "I",
      g.piece.kind)
g = T.Game(seed=7); blank(g)
was, nxt = g.piece.kind, g.queue[0]
g.powers = ["SKIP"]
check("skip throws the piece away", g.use_power() == "SKIP")
check("and brings the next one", g.piece.kind == nxt, (was, nxt, g.piece.kind))
check("the board is untouched", filled_cells(g) == 0)

print("\n[7] SLOW slows gravity and wears off")
g = T.Game(seed=8)
normal = g.gravity()
g.powers = ["SLOW"]
g.use_power()
check("gravity eases", g.gravity() > normal * 2, (normal, g.gravity()))
g.slow_until = time.monotonic() - 1
check("and returns to normal", abs(g.gravity() - normal) < 1e-9)

print("\n[8] powers never pay")
for name in T.POWERS:
    g = T.Game(seed=9); blank(g)
    for r in (37, 38, 39):
        fill(g, r, (9,))
    g.piece = T.Piece("O"); g.piece.x = 4; g.piece.y = 20
    g.powers = [name]
    s0, l0, c0 = g.score, g.lines, g.combo
    g.use_power()
    check("%s awards no score" % name, g.score == s0 and g.lines == l0 and g.combo == c0,
          (name, g.score - s0, g.lines - l0))

print("\n[9] undo puts a spent power back")
g = T.Game(seed=10); blank(g)
g.piece = T.Piece("O"); g.piece.x = 4; g.piece.y = 20
g.history = [g.snapshot()]
g.powers = ["BOMB"]
g.history[-1]["powers"] = ["BOMB"]
g.hard_drop()
g.powers = []
check("undo restores it", g.undo() and g.powers == ["BOMB"], g.powers)

print("\n[10] they can be turned off")
g = T.Game(seed=11, powers=False)
g.level = 2; g.lines = 29
blank(g); g.board[20][0] = "I"
fill(g, 39, (9,))
g.piece = T.Piece("O"); g.piece.x = 8; g.piece.y = 38
g.lock()
check("no power at level 3 when disabled", g.powers == [], g.powers)
check("pressing the button does nothing", g.use_power() is None)

print("\n[11] fuzzing with powers on")
bad = None
for seed in range(6):
    g = T.Game(seed=seed)
    rnd = random.Random(seed)
    for _ in range(800):
        if g.state == "over": break
        if rnd.random() < .06:
            g.grant_power()
        a = rnd.random()
        if   a < .20: g.move(-1, 0)
        elif a < .40: g.move(1, 0)
        elif a < .52: g.rotate(1)
        elif a < .62: g.use_power()
        elif a < .70: g.hold_piece()
        else:         g.hard_drop()
        if g.state == "flash":
            g.apply_clear(); g.state = "play"; g.spawn()
        g.update(time.monotonic())
        if g.piece is not None and g.state == "play" and g.collides(g.piece.cells()):
            bad = ("overlap", seed); break
        if len(g.powers) > T.POWER_SLOTS:
            bad = ("hoarding", seed, g.powers); break
        for row in g.board:
            for c in row:
                if c is not None and c not in T.ORDER:
                    bad = ("bad cell", seed); break
    if bad: break
check("no overlap, no corruption, no hoarding", bad is None, bad)

print("\n" + ("POWERS OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
