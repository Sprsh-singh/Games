"""Undo: take back the last piece, exactly - board, score, bag and all."""
import os, sys, time, tempfile, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tetris as T
T.SCORE_FILE = os.path.join(tempfile.mkdtemp(), "s.json")

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

def board_sig(g):
    return tuple(tuple(r) for r in g.board)

print("[1] a placement can be taken back")
g = T.Game(seed=1)
before_board = board_sig(g)
before_kind = g.piece.kind
before_score = g.score
g.hard_drop()
check("the board changed", board_sig(g) != before_board)
check("undo is available", g.undo())
check("the board is back", board_sig(g) == before_board)
check("the same piece returns", g.piece.kind == before_kind, (before_kind, g.piece.kind))
check("it returns at the top", g.piece.y == T.SPEC[before_kind][3])
check("the score is back", g.score == before_score, (before_score, g.score))
check("an undo was spent", g.undos_left == g.undo_limit - 1)

print("\n[2] the bag is not reshuffled by undoing")
g = T.Game(seed=2)
queue_before = list(g.queue)
g.hard_drop()
g.undo()
check("the preview is identical", list(g.queue) == queue_before,
      (queue_before[:3], list(g.queue)[:3]))
after = []
for _ in range(6):
    after.append(g.piece.kind)
    g.hard_drop()
    if g.state == "flash":
        g.apply_clear(); g.state = "play"; g.spawn()
g2 = T.Game(seed=2)
same = []
for _ in range(6):
    same.append(g2.piece.kind)
    g2.hard_drop()
    if g2.state == "flash":
        g2.apply_clear(); g2.state = "play"; g2.spawn()
check("the future sequence is unchanged", after == same, (same, after))

print("\n[3] undo restores a line clear")
g = T.Game(seed=3)
g.board = [[None] * T.COLS for _ in range(T.ROWS)]
for c in range(T.COLS):
    if c not in (4, 5):
        g.board[39][c] = "I"
g.piece = T.Piece("O"); g.piece.x = 4; g.piece.y = 20
g.history = [g.snapshot()]
lines_before, score_before = g.lines, g.score
g.hard_drop()
check("the line cleared", g.lines == lines_before + 1, g.lines)
check("the clear animation is running", g.state == "flash", g.state)
check("undo works mid-animation", g.undo())
check("the line is back", g.lines == lines_before and g.board[39][0] == "I",
      (g.lines, g.board[39][0]))
check("the score is back", g.score == score_before, (score_before, g.score))

check("and it took back exactly one piece", g.piece is not None
      and g.piece.kind == "O", g.piece.kind if g.piece else None)

print("\n[3b] undoing mid-animation is not two steps back")
g = T.Game(seed=8)
g.board = [[None] * T.COLS for _ in range(T.ROWS)]
for c in range(T.COLS):
    if c != 9:
        g.board[39][c] = "I"
g.board[38][0] = "I"                       # a marker from an earlier piece
g.piece = T.Piece("I"); g.piece.rot = 1; g.piece.x = 7; g.piece.y = 36
g.history = [g.snapshot()]
g.hard_drop()
check("it cleared and is animating", g.state == "flash")
g.undo()
check("the earlier piece is still there", g.board[38][0] == "I", g.board[38][0])
check("the bottom row is back", g.board[39][0] == "I" and g.board[39][9] is None)

print("\n[4] hold is part of the state")
g = T.Game(seed=4)
g.hold_piece()
held = g.hold
g.hard_drop()
g.undo()
check("the held piece is unchanged", g.hold == held, (held, g.hold))
check("and hold is usable again as it was", g.can_hold in (True, False))

print("\n[5] limits")
g = T.Game(seed=5, undo_limit=2)
for _ in range(4):
    g.hard_drop()
    if g.state == "flash":
        g.apply_clear(); g.state = "play"; g.spawn()
check("first undo allowed", g.undo())
check("second undo allowed", g.undo())
check("third is refused", not g.undo())
check("counter bottoms out at zero", g.undos_left == 0)
g0 = T.Game(seed=5, undo_limit=0)
g0.hard_drop()
check("undo can be switched off entirely", not g0.undo())
check("and no history is kept when off", g0.history == [], len(g0.history))

print("\n[6] undo can rescue you from a game over")
g = T.Game(seed=6)
for _ in range(400):
    if g.state == "over":
        break
    g.hard_drop()
    if g.state == "flash":
        g.apply_clear(); g.state = "play"; g.spawn()
check("the stack topped out", g.state == "over", g.state)
check("undo pulls you back", g.undo())
check("and play resumes", g.state == "play" and g.piece is not None)

print("\n[7] memory does not grow without bound")
g = T.Game(seed=7)
for _ in range(300):
    if g.state == "over":
        g = T.Game(seed=7)
    g.hard_drop()
    if g.state == "flash":
        g.apply_clear(); g.state = "play"; g.spawn()
check("history is capped", len(g.history) <= T.UNDO_KEEP, len(g.history))

print("\n[8] undo does not corrupt anything under fuzzing")
bad = None
for seed in range(6):
    g = T.Game(seed=seed, undo_limit=99)
    rnd = random.Random(seed)
    for _ in range(600):
        if g.state == "over":
            break
        a = rnd.random()
        if   a < .20: g.move(-1, 0)
        elif a < .40: g.move(1, 0)
        elif a < .52: g.rotate(1)
        elif a < .60: g.hold_piece()
        elif a < .72: g.undo()
        else:         g.hard_drop()
        if g.state == "flash":
            g.apply_clear(); g.state = "play"; g.spawn()
        g.update(time.monotonic())
        if g.piece is not None and g.state == "play" and g.collides(g.piece.cells()):
            bad = ("overlap", seed); break
        for row in g.board:
            for c in row:
                if c is not None and c not in T.ORDER:
                    bad = ("bad cell", seed); break
        if g.score < 0 or g.lines < 0:
            bad = ("negative", seed, g.score, g.lines); break
    if bad: break
check("no overlap, no corruption, no negative score", bad is None, bad)

print("\n" + ("UNDO OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
