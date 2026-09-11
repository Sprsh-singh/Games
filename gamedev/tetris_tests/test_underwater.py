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
max_wobble_observed = 0
for s in range(50):
    g = T.Game(seed=s, underwater=True)
    blank(g)
    g.piece = T.Piece("I")
    g.piece.x = 4; g.piece.y = 20
    orig_x = g.piece.x
    g.hard_drop()
    # In underwater mode, a 19-row drop through open water should experience lateral wobble on some seeds
    if g.fx_lock_cells:
        locked_x = min(x for x, y in g.fx_lock_cells)
        shift = abs(locked_x - orig_x)
        max_wobble_observed = max(max_wobble_observed, shift)
        if shift > 0:
            wobbled = True
check("hard drop plunges with hydrodynamic wobble in open water", wobbled)
check("hard drop wobbles by at most 1 block laterally", max_wobble_observed == 1, f"max_wobble={max_wobble_observed}")

# Test wobble in specific water flow directions
g_flow_r = T.Game(seed=1, underwater=True)
blank(g_flow_r)
g_flow_r.wave_dir = 1
g_flow_r.piece = T.Piece("O")
g_flow_r.piece.x = 4; g_flow_r.piece.y = 20
g_flow_r.rng.random = lambda: 0.1  # ensure wobble triggers
g_flow_r.hard_drop()
locked_x_r = min(x for x, y in g_flow_r.fx_lock_cells)
check("wobble follows rightward water flow by 1 block", locked_x_r == 5, locked_x_r)

g_flow_l = T.Game(seed=1, underwater=True)
blank(g_flow_l)
g_flow_l.wave_dir = -1
g_flow_l.piece = T.Piece("O")
g_flow_l.piece.x = 4; g_flow_l.piece.y = 20
g_flow_l.rng.random = lambda: 0.1  # ensure wobble triggers
g_flow_l.hard_drop()
locked_x_l = min(x for x, y in g_flow_l.fx_lock_cells)
check("wobble follows leftward water flow by 1 block", locked_x_l == 3, locked_x_l)

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

print("\n[3] marine life & fish mechanics (Level >= 2)")
g_fish = T.Game(seed=100, underwater=True, start_level=2)
blank(g_fish)
check("fish list starts empty", len(g_fish.fishes) == 0)
g_fish.next_fish = time.monotonic() - 1.0
g_fish.update(time.monotonic())
check("fish spawns on schedule at level 2", len(g_fish.fishes) == 1, g_fish.fishes)
f = g_fish.fishes[0]
check("fish has valid attributes", f["name"] in [s["name"] for s in T.FISH_SPECIES] and f["dir"] in (-1, 1))

# Advance fish across screen
f["x"] = 4.0; f["y"] = 25
g_fish._update_fishes(time.monotonic(), 1.0)
check("fish moves horizontally with dt", abs(f["x"] - (4.0 + f["dir"] * f["speed"] * 1.0)) < 1e-4)

print("\n[4] protect the fish: instant game over on collision (Level >= 2)")
# 4a. Moving into fish
g_hit1 = T.Game(seed=201, underwater=True, start_level=2)
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
g_hit2 = T.Game(seed=202, underwater=True, start_level=2)
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
g_hit3 = T.Game(seed=203, underwater=True, start_level=2)
blank(g_hit3)
g_hit3.piece = T.Piece("O")
g_hit3.piece.x = 4; g_hit3.piece.y = 38
g_hit3.fishes = [{"name": "Guppy", "x": 4.0, "y": 38, "dir": 1, "speed": 1.0,
                  "sprite_r": ">*>", "sprite_l": "<*<", "color": "good", "announced": True}]
g_hit3.lock()
check("locking block onto fish triggers game over", g_hit3.state == "over")

print("\n[5] safe coexistence & normal play")
g_safe = T.Game(seed=301, underwater=True, start_level=2)
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
g_static = T.Game(seed=302, underwater=True, start_level=2)
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
g_undo = T.Game(seed=401, underwater=True, start_level=2)
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

print("\n[8] upwelling thermal currents, bubble streams & physics tumble (Level >= 3)")
g_up = T.Game(seed=501, underwater=True, start_level=3)
blank(g_up)
check("upwelling timers initialized", g_up.next_upwelling > time.monotonic())
now = time.monotonic()
g_up.next_upwelling = now - 0.1
g_up.update(now)
check("upwelling triggers on schedule at level 3", g_up.upwelling_until > now)

# Reverse buoyancy: piece floats upwards gently during upwelling
g_up.piece = T.Piece("O")
g_up.piece.x = 4
g_up.piece.y = 28
g_up.next_fall = now - 0.1
g_up.update(now)
check("active piece floats upwards during upwelling", g_up.piece.y == 27, g_up.piece.y)

# Rising bubble streams during upwelling
g_up._update_bubbles(now, 0.05)
check("bubbles spawn during upwelling", len(g_up.bubbles) > 0, len(g_up.bubbles))
b = g_up.bubbles[0]
y_before = b["y"]
g_up._update_bubbles(now, 0.1)
check("bubbles rise upwards over time", b["y"] < y_before, f"before={y_before}, after={b['y']}")

# Physics-based tumble: loose overhang block tilts/flips into adjacent void
g_tumble = T.Game(seed=502, underwater=True, start_level=3)
blank(g_tumble)
# Place a pillar with an unsupported loose overhang at (4, 35)
g_tumble.board[36][3] = "I"
g_tumble.board[35][3] = "I"
g_tumble.board[35][4] = "O"  # loose overhang block: no support at (4, 36)
g_tumble.wave_dir = 1       # push rightward
g_tumble._upwelling_physics_tumble()
check("loose overhang block tumbled/flipped into lower space",
      g_tumble.board[35][4] is None or g_tumble.board[36][4] == "O" or g_tumble.board[36][5] == "O")

# Undo restores upwelling state & bubbles
g_undo_up = T.Game(seed=503, underwater=True, start_level=3)
blank(g_undo_up)
g_undo_up.upwelling_until = now + 6.0
g_undo_up.bubbles = [{"x": 3.0, "y": 30.0, "char": "o", "speed": 6.0}]
snap = g_undo_up.snapshot()
check("snapshot captures upwelling state and bubbles",
      "upwelling_until" in snap and snap["upwelling_until"] > now and len(snap["bubbles"]) == 1)
g_undo_up.upwelling_until = 0.0
g_undo_up.bubbles = []
g_undo_up.restore(snap)
check("restore recovers upwelling timer and bubbles",
      g_undo_up.upwelling_until > now and len(g_undo_up.bubbles) == 1)

print("\n[9] 3-tier cumulative level progression")
# Level 1: waves & wobble active, NO fish spawn, NO upwelling
g_l1 = T.Game(seed=601, underwater=True, start_level=1)
blank(g_l1)
g_l1.next_fish = now - 1.0
g_l1.next_upwelling = now - 1.0
g_l1.update(now)
check("level 1: no fish spawn even after timer expires", len(g_l1.fishes) == 0)
check("level 1: upwelling does not trigger", g_l1.upwelling_until <= now)
# Place a fish artificially to verify level 1 is safe from fish collisions
g_l1.fishes = [{"name": "Goldfish", "x": 4.0, "y": 25, "dir": 1, "speed": 1.0,
                "sprite_r": "><>", "sprite_l": "<><", "color": "warn", "announced": True}]
g_l1.piece = T.Piece("O")
g_l1.piece.x = 4; g_l1.piece.y = 25
check("level 1: piece over fish does not collide", not g_l1._check_fish_collision())
g_l1.move(0, 0)
check("level 1: game remains in play state despite touching fish", g_l1.state == "play")

# Level transition: Level 1 -> Level 2
g_trans = T.Game(seed=701, underwater=True, start_level=1)
blank(g_trans)
# Clearing 10 lines advances from Level 1 to Level 2
g_trans.lines = 9
for c in range(T.COLS):
    g_trans.board[39][c] = "I"
g_trans.flash_rows = [39]
g_trans._score_clear(1, False, False, [39])
check("reaching 10 lines advances level to 2", g_trans.level == 2)
check("level 2 announcement displayed", "PROTECT THE FISH" in g_trans.message)

# Level 2 has fish active, but NO upwelling
g_l2 = T.Game(seed=602, underwater=True, start_level=2)
blank(g_l2)
g_l2.next_fish = now - 1.0
g_l2.next_upwelling = now - 1.0
g_l2.update(now)
check("level 2: fish spawns on schedule", len(g_l2.fishes) == 1)
check("level 2: upwelling still does not trigger", g_l2.upwelling_until <= now)

# Level transition: Level 2 -> Level 3
g_trans2 = T.Game(seed=702, underwater=True, start_level=1)
blank(g_trans2)
g_trans2.lines = 19
for c in range(T.COLS):
    g_trans2.board[39][c] = "I"
g_trans2.flash_rows = [39]
g_trans2._score_clear(1, False, False, [39])
check("reaching 20 lines advances level to 3", g_trans2.level == 3)
check("level 3 announcement displayed", "UPWELLING UNLEASHED" in g_trans2.message)

# Level 3 has upwelling active
g_l3 = T.Game(seed=603, underwater=True, start_level=3)
blank(g_l3)
g_l3.next_upwelling = now - 1.0
g_l3.update(now)
check("level 3: upwelling triggers on schedule", g_l3.upwelling_until > now)

print("\n" + ("UNDERWATER OK" if not fails else ("%d UNDERWATER FAILS" % len(fails))))
sys.exit(1 if fails else 0)
