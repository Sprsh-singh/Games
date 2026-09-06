"""Underwater Mode: Wave current physics, plunge drop wobble, and Protect the Fish hazard."""
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

print("[1] wave current physics")
g = T.Game(seed=42, underwater=True)
check("underwater mode initialized", g.underwater is True)
blank(g)
g.piece = T.Piece("O")
g.piece.x = 4; g.piece.y = 20
g.next_wave = time.monotonic() - 0.1
now = time.monotonic()
g.update(now)
check("wave surge shifts piece or sets wave direction", g.wave_dir in (-1, 1), g.wave_dir)

# Test wall boundary collision safety for waves
g2 = T.Game(seed=43, underwater=True)
blank(g2)
g2.piece = T.Piece("O")
g2.piece.x = 0; g2.piece.y = 20
g2.wave_dir = -1
g2.next_wave = now - 0.1
g2.update(now)
check("wave does not push piece through left wall", g2.piece.x >= 0, g2.piece.x)

g3 = T.Game(seed=44, underwater=True)
blank(g3)
g3.piece = T.Piece("O")
g3.piece.x = T.COLS - 2; g3.piece.y = 20
g3.wave_dir = 1
g3.next_wave = now - 0.1
g3.update(now)
check("wave does not push piece through right wall", g3.piece.x + 2 <= T.COLS, g3.piece.x)

print("\n[2] hard drop hydrodynamic plunge wobble")
# Test drop in open water with wobble
wobbled = False
for s in range(50):
    g = T.Game(seed=s, underwater=True)
    blank(g)
    g.piece = T.Piece("I")
    g.piece.x = 4; g.piece.y = 20
    orig_x = g.piece.x
    g.hard_drop()
    # In underwater mode, a 19-row drop through open water should experience lateral wobble on some seeds
    if g.fx_lock_cells and any(x != orig_x for x, y in g.fx_lock_cells):
        wobbled = True
        break
check("hard drop plunges with hydrodynamic wobble in open water", wobbled)

# Test drop in narrow channel (must never get stuck)
g_chan = T.Game(seed=10, underwater=True)
blank(g_chan)
for y in range(20, 40):
    for c in range(T.COLS):
        if c != 3:  # narrow 1-wide column at x=3
            g_chan.board[y][c] = "I"
g_chan.piece = T.Piece("I")  # vertical I in channel (rot 1 has cells at x + 2)
g_chan.piece.rot = 1
g_chan.piece.x = 1; g_chan.piece.y = 20
g_chan.hard_drop()
check("hard drop falls cleanly to the floor in narrow channel", g_chan.board[39][3] is not None)

print("\n[3] marine life & fish mechanics")
g_fish = T.Game(seed=100, underwater=True)
blank(g_fish)
check("fish list starts empty", len(g_fish.fishes) == 0)
g_fish.next_fish = time.monotonic() - 1.0
g_fish.update(time.monotonic())
check("fish spawns on schedule", len(g_fish.fishes) == 1, g_fish.fishes)
f = g_fish.fishes[0]
check("fish has valid attributes", f["name"] in [s["name"] for s in T.FISH_SPECIES] and f["dir"] in (-1, 1))

# Advance fish across screen
f["x"] = 4.0; f["y"] = 25
g_fish._update_fishes(time.monotonic(), 1.0)
check("fish moves horizontally with dt", abs(f["x"] - (4.0 + f["dir"] * f["speed"] * 1.0)) < 1e-4)

print("\n[4] protect the fish: instant game over on collision")
# 4a. Moving into fish
g_hit1 = T.Game(seed=201, underwater=True)
blank(g_hit1)
g_hit1.piece = T.Piece("O")
g_hit1.piece.x = 2; g_hit1.piece.y = 25
g_hit1.fishes = [{"name": "Goldfish", "x": 4.0, "y": 25, "dir": 1, "speed": 1.0,
                  "sprite_r": "><>", "sprite_l": "<><", "color": "warn", "announced": True}]
check("game active before collision", g_hit1.state == "play")
g_hit1.move(1, 0)
check("game over triggered when piece touches fish", g_hit1.state == "over")
check("game over reason is fish_crushed", g_hit1.game_over_reason == "fish_crushed")

# 4b. Hard drop hitting fish in path
g_hit2 = T.Game(seed=202, underwater=True)
blank(g_hit2)
for y in range(20, 40):
    for c in range(T.COLS):
        if c not in (4, 5):
            g_hit2.board[y][c] = "I"
g_hit2.piece = T.Piece("O")
g_hit2.piece.x = 4; g_hit2.piece.y = 20
g_hit2.fishes = [{"name": "Clownfish", "x": 4.0, "y": 30, "dir": 1, "speed": 1.0,
                  "sprite_r": ">o>", "sprite_l": "<o<", "color": "accent", "announced": True}]
g_hit2.hard_drop()
check("hard drop onto fish triggers instant game over", g_hit2.state == "over")
check("cause is fish_crushed", g_hit2.game_over_reason == "fish_crushed")

# 4c. Locking onto fish
g_hit3 = T.Game(seed=203, underwater=True)
blank(g_hit3)
g_hit3.piece = T.Piece("O")
g_hit3.piece.x = 4; g_hit3.piece.y = 38
g_hit3.fishes = [{"name": "Guppy", "x": 4.0, "y": 38, "dir": 1, "speed": 1.0,
                  "sprite_r": ">*>", "sprite_l": "<*<", "color": "good", "announced": True}]
g_hit3.lock()
check("locking block onto fish triggers game over", g_hit3.state == "over")

print("\n[5] safe coexistence & normal play")
g_safe = T.Game(seed=301, underwater=True)
blank(g_safe)
fill(g_safe, 39, (9,))
g_safe.piece = T.Piece("O")
g_safe.piece.x = 8; g_safe.piece.y = 38
# Fish swimming high up at row 22
g_safe.fishes = [{"name": "Jellyfish", "x": 2.0, "y": 22, "dir": 1, "speed": 1.0,
                  "sprite_r": "(o)", "sprite_l": "(o)", "color": "hl", "announced": True}]
s0 = g_safe.score
g_safe.lock()
check("normal line clear succeeds when fish is safely away", g_safe.lines == 1 and g_safe.score > s0)
check("game continues in play state", g_safe.state in ("play", "flash"))

# Fish swimming through already-present (static/locked) blocks on board must NOT harm fish
g_static = T.Game(seed=302, underwater=True)
blank(g_static)
for c in range(T.COLS):
    g_static.board[35][c] = "I"  # locked row
g_static.piece = T.Piece("O")
g_static.piece.x = 4; g_static.piece.y = 20  # falling piece high above
g_static.fishes = [{"name": "Goldfish", "x": 5.0, "y": 35, "dir": 1, "speed": 1.0,
                    "sprite_r": "><>", "sprite_l": "<><", "color": "warn", "announced": True}]
g_static.update(time.monotonic())
check("fish passing over static board blocks does not trigger game over", g_static.state == "play")
check("no fish collision detected with static board blocks", not g_static._check_fish_collision())

print("\n[6] determinism and undo recovery")
# Undo after hitting fish
g_undo = T.Game(seed=401, underwater=True)
blank(g_undo)
g_undo.piece = T.Piece("O")
g_undo.piece.x = 2; g_undo.piece.y = 25
g_undo.fishes = [{"name": "Goldfish", "x": 4.0, "y": 25, "dir": 1, "speed": 1.0,
                  "sprite_r": "><>", "sprite_l": "<><", "color": "warn", "announced": True}]
g_undo.history = [g_undo.snapshot()]
snap = g_undo.history[0]
check("snapshot captures underwater state", snap["underwater"] is True and len(snap["fishes"]) == 1)

g_undo.move(1, 0)
check("collision happened", g_undo.state == "over")
check("undo rescues player from fish collision", g_undo.undo())
check("and play resumes", g_undo.state == "play" and g_undo.piece is not None)

print("\n[7] CLI parser and theme integration")
parser = T.build_parser()
args = parser.parse_args(["--underwater", "--theme", "aquatic"])
check("parser accepts --underwater flag", args.underwater is True)
check("parser accepts aquatic theme", args.theme == "aquatic")
check("aquatic theme is in THEMES dictionary", "aquatic" in T.THEMES)

print("\n" + ("UNDERWATER OK" if not fails else ("%d UNDERWATER FAILS" % len(fails))))
sys.exit(1 if fails else 0)
