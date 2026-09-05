#!/usr/bin/env python3
"""
Terminal Tetris - a complete Tetris that runs in a plain text terminal.

No graphics, no dependencies, no network: Python 3 standard library only.

    python3 tetris.py             play
    python3 tetris.py --help      options

Move with the arrow keys, WASD or HJKL; press ? in game for the full list.

Implements the modern Tetris guideline: 7-bag randomiser, SRS rotation with
wall kicks, hold, 5-piece preview, ghost piece, lock delay with move resets,
soft/hard drop, T-spin and mini T-spin detection, back-to-back bonuses,
combos, perfect clears, a 20-step speed curve and a persistent high score.
"""

import argparse
import curses
import json
import locale
import os
import random
import textwrap
import time

# ---------------------------------------------------------------------------
# Playfield geometry
# ---------------------------------------------------------------------------

COLS = 10
VISIBLE_ROWS = 20
HIDDEN_ROWS = 20                  # spawn buffer above the visible field
ROWS = VISIBLE_ROWS + HIDDEN_ROWS

NEXT_COUNT = 5
LOCK_DELAY = 0.5                  # grounded piece may still be nudged this long
MAX_LOCK_RESETS = 15
CLEAR_ANIM = 0.34                 # line-clear animation length, seconds
LOCK_FLASH = 0.07                 # the piece pulses white as it locks
IMPACT_TIME = 0.10                # what it landed on sparks
SHAKE_TIME = 0.10                 # hard-drop screen bounce
LEVEL_BANNER = 1.2                # how long the LEVEL n banner sits on screen
DANGER_ROWS = 5                   # stack this close to the top = danger
UNDO_KEEP = 16                    # how many piece-starts to remember
POWER_EVERY = 2                   # a superpower every this many levels
POWER_SLOTS = 3                   # how many you can be holding at once
SLOW_TIME = 20.0                  # seconds of half gravity
SLOW_FACTOR = 2.5

# Powers never score. They dig you out of trouble; they do not earn points,
# so there is nothing to farm.
POWERS = ("BOMB", "SLOW", "LINE-I", "COMPACT", "SKIP")
POWER_HELP = {
    "BOMB":    "clears the bottom row",
    "SLOW":    "half gravity for 20 seconds",
    "LINE-I":  "turns the falling piece into an I",
    "COMPACT": "drops every column to close its holes",
    "SKIP":    "throws the current piece away",
}
MAX_LEVEL = 20
MESSAGE_TIME = 2.2

SCORE_FILE = os.path.join(os.path.expanduser("~"), ".terminal_tetris.json")

ORDER = "IOTSZJL"

# kind -> (box size, cells of rotation state 0, spawn x, spawn y)
SPEC = {
    "I": (4, [(0, 1), (1, 1), (2, 1), (3, 1)], 3, HIDDEN_ROWS - 1),
    "O": (2, [(0, 0), (1, 0), (0, 1), (1, 1)], 4, HIDDEN_ROWS),
    "T": (3, [(1, 0), (0, 1), (1, 1), (2, 1)], 3, HIDDEN_ROWS),
    "S": (3, [(1, 0), (2, 0), (0, 1), (1, 1)], 3, HIDDEN_ROWS),
    "Z": (3, [(0, 0), (1, 0), (1, 1), (2, 1)], 3, HIDDEN_ROWS),
    "J": (3, [(0, 0), (0, 1), (1, 1), (2, 1)], 3, HIDDEN_ROWS),
    "L": (3, [(2, 0), (0, 1), (1, 1), (2, 1)], 3, HIDDEN_ROWS),
}


def _rotations(size, cells):
    """Four rotation states; clockwise turn inside the box is (x,y)->(N-1-y,x)."""
    states = []
    cur = list(cells)
    for _ in range(4):
        states.append(tuple(sorted(cur)))
        cur = [(size - 1 - y, x) for (x, y) in cur]
    return tuple(states)


ROTATIONS = {k: _rotations(v[0], v[1]) for k, v in SPEC.items()}

# Super Rotation System wall kicks, already converted to screen coordinates
# (y grows downward).  Key is (from_state, to_state).
KICKS_JLSTZ = {
    (0, 1): [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
    (1, 0): [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
    (1, 2): [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
    (2, 1): [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
    (2, 3): [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
    (3, 2): [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
    (3, 0): [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
    (0, 3): [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
}
KICKS_I = {
    (0, 1): [(0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)],
    (1, 0): [(0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)],
    (1, 2): [(0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)],
    (2, 1): [(0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)],
    (2, 3): [(0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)],
    (3, 2): [(0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)],
    (3, 0): [(0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)],
    (0, 3): [(0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)],
}
# 180 degree spins are not part of classic SRS; this is a common permissive set.
KICKS_180 = [(0, 0), (1, 0), (-1, 0), (0, -1), (1, -1), (-1, -1),
             (0, 1), (2, 0), (-2, 0)]


def gravity_for(level):
    """Seconds per row, the guideline curve."""
    lv = min(level, MAX_LEVEL)
    return max((0.8 - (lv - 1) * 0.007) ** (lv - 1), 0.0008)


# ---------------------------------------------------------------------------
# Game model
# ---------------------------------------------------------------------------

class Piece(object):
    __slots__ = ("kind", "rot", "x", "y")

    def __init__(self, kind):
        self.kind = kind
        self.rot = 0
        self.x = SPEC[kind][2]
        self.y = SPEC[kind][3]

    def cells(self, rot=None, x=None, y=None):
        r = self.rot if rot is None else rot
        px = self.x if x is None else x
        py = self.y if y is None else y
        return [(px + cx, py + cy) for cx, cy in ROTATIONS[self.kind][r]]


class Game(object):
    """All of the rules; knows nothing about the screen."""

    def __init__(self, start_level=1, seed=None, undo_limit=3, powers=True):
        self.rng = random.Random(seed)
        self.start_level = max(1, min(MAX_LEVEL, start_level))
        self.undo_limit = max(0, undo_limit)
        self.power_limit = bool(powers)
        self.high = load_high_score()
        self.reset()

    # -- setup -------------------------------------------------------------

    def reset(self, start_level=None):
        if start_level is not None:
            self.start_level = max(1, min(MAX_LEVEL, start_level))
        now = time.monotonic()
        self.board = [[None] * COLS for _ in range(ROWS)]
        self.queue = []
        self._refill()
        self.hold = None
        self.can_hold = True
        self.piece = None
        self.score = 0
        self.lines = 0
        self.level = self.start_level
        self.combo = -1
        self.b2b = 0
        self.state = "play"           # play | flash | paused | over
        self.message = ""
        self.message_until = 0.0
        self.flash_rows = []
        self.flash_start = 0.0
        self.flash_until = 0.0
        self.lock_start = None
        self.lock_resets = 0
        self.lowest_y = -99
        self.last_was_rotation = False
        self.last_kick = 0
        self.pieces_placed = 0
        self.tally = {"single": 0, "double": 0, "triple": 0, "tetris": 0,
                      "tspin": 0, "perfect": 0}
        self.start_time = now
        self.paused_at = None
        self.new_record = False
        self.fx_lock_cells = []
        self.fx_lock_until = 0.0
        self.fx_impact_cells = []
        self.fx_impact_until = 0.0
        self.fx_shake_until = 0.0
        self.fx_shake_mag = 0
        self.fx_level_until = 0.0
        self.fx_level_value = 0
        self.sounds = []              # event names, drained by the UI layer
        self.history = []             # a snapshot at the start of each piece
        self.undos_left = self.undo_limit
        self.powers = []              # superpowers in hand, front one first
        self.slow_until = 0.0
        self.next_fall = now + gravity_for(self.level)
        self.spawn()

    def _refill(self):
        while len(self.queue) < NEXT_COUNT + 1:
            bag = list(ORDER)
            self.rng.shuffle(bag)
            self.queue.extend(bag)

    # -- helpers -----------------------------------------------------------

    def elapsed(self):
        if self.paused_at is not None:
            return self.paused_at - self.start_time
        return time.monotonic() - self.start_time

    def collides(self, cells):
        for x, y in cells:
            if x < 0 or x >= COLS or y >= ROWS:
                return True
            if y >= 0 and self.board[y][x] is not None:
                return True
        return False

    def grounded(self):
        p = self.piece
        return p is None or self.collides(p.cells(y=p.y + 1))

    def ghost_y(self):
        p = self.piece
        if p is None:
            return 0
        y = p.y
        while not self.collides(p.cells(y=y + 1)):
            y += 1
        return y

    def gravity(self):
        g = gravity_for(self.level)
        if time.monotonic() < self.slow_until:
            g *= SLOW_FACTOR
        return g

    def stack_top(self):
        """Board row of the highest filled cell, ROWS when the board is empty."""
        for y in range(ROWS):
            if any(c is not None for c in self.board[y]):
                return y
        return ROWS

    def danger(self):
        return self.stack_top() < HIDDEN_ROWS + DANGER_ROWS

    def say(self, text):
        self.message = text
        self.message_until = time.monotonic() + MESSAGE_TIME

    # -- piece flow --------------------------------------------------------

    def snapshot(self):
        """Everything needed to put this piece back at the top of the well.

        The random state goes in too, so undoing does not hand you a
        different bag - you replay the same piece and the same future.
        """
        return {
            "board": [row[:] for row in self.board],
            "queue": list(self.queue),
            "hold": self.hold,
            "can_hold": self.can_hold,
            "kind": self.piece.kind if self.piece is not None else None,
            "score": self.score, "lines": self.lines, "level": self.level,
            "combo": self.combo, "b2b": self.b2b,
            "pieces_placed": self.pieces_placed,
            "tally": dict(self.tally),
            "powers": list(self.powers),
            "rng": self.rng.getstate(),
        }

    def restore(self, snap):
        self.board = [row[:] for row in snap["board"]]
        self.queue = list(snap["queue"])
        self.hold = snap["hold"]
        self.can_hold = snap["can_hold"]
        self.score = snap["score"]
        self.lines = snap["lines"]
        self.level = snap["level"]
        self.combo = snap["combo"]
        self.b2b = snap["b2b"]
        self.pieces_placed = snap["pieces_placed"]
        self.tally = dict(snap["tally"])
        self.powers = list(snap.get("powers", []))
        self.rng.setstate(snap["rng"])
        self.piece = Piece(snap["kind"]) if snap["kind"] else None
        self.state = "play"
        self.paused_at = None
        self.flash_rows = []
        self.lock_start = None
        self.lock_resets = 0
        self.lowest_y = self.piece.y if self.piece else -99
        self.last_was_rotation = False
        self.fx_lock_cells = []
        self.fx_impact_cells = []
        self.fx_shake_until = 0.0
        self.fx_level_until = 0.0
        self.next_fall = time.monotonic() + self.gravity()

    def undo(self):
        """Take back the most recently locked piece and replay it.

        Which snapshot that is depends on whether a piece is in play. With one
        falling, the last *completed* placement is the one before it. With none
        - mid clear-animation, or topped out - the piece that just locked is
        the last snapshot itself. Getting this wrong takes back two pieces.
        """
        if self.undos_left <= 0 or self.state not in ("play", "flash", "over"):
            return False
        if self.piece is None:
            if not self.history:
                return False
        else:
            if len(self.history) < 2:
                return False
            self.history.pop()
        self.restore(self.history[-1])
        self.undos_left -= 1
        self.say("UNDO  %d" % self.undos_left)
        return True

    def spawn(self, kind=None):
        if kind is None:
            kind = self.queue.pop(0)
            self._refill()
        self.piece = Piece(kind)
        self.pieces_placed += 1
        self.lock_start = None
        self.lock_resets = 0
        self.lowest_y = self.piece.y
        self.last_was_rotation = False
        self.next_fall = time.monotonic() + self.gravity()
        if self.undo_limit:
            self.history.append(self.snapshot())
            del self.history[:-UNDO_KEEP]
        if self.collides(self.piece.cells()):
            self.game_over()

    def game_over(self):
        self.state = "over"
        self.sounds.append("over")
        self.paused_at = time.monotonic()
        if self.score > self.high:
            self.high = self.score
            self.new_record = True
        save_high_score(self.high)

    def _after_action(self, rotated):
        """Lock-delay bookkeeping after a successful move or rotation."""
        self.last_was_rotation = rotated
        if self.grounded():
            now = time.monotonic()
            if self.lock_start is None:
                self.lock_start = now
            elif self.lock_resets < MAX_LOCK_RESETS:
                self.lock_start = now
                self.lock_resets += 1
        else:
            self.lock_start = None

    def move(self, dx, dy):
        p = self.piece
        if p is None or self.state != "play":
            return False
        if self.collides(p.cells(x=p.x + dx, y=p.y + dy)):
            return False
        p.x += dx
        p.y += dy
        if p.y > self.lowest_y:          # a new lowest row refreshes the resets
            self.lowest_y = p.y
            self.lock_resets = 0
        if dy > 0:
            self.last_was_rotation = False
            self.lock_start = time.monotonic() if self.grounded() else None
        else:
            self._after_action(False)
        return True

    def rotate(self, turns):
        p = self.piece
        if p is None or self.state != "play":
            return False
        frm = p.rot
        to = (p.rot + turns) % 4
        if turns == 2:
            kicks = KICKS_180
        elif p.kind == "I":
            kicks = KICKS_I[(frm, to)]
        else:
            kicks = KICKS_JLSTZ[(frm, to)]
        for i, (kx, ky) in enumerate(kicks):
            if not self.collides(p.cells(rot=to, x=p.x + kx, y=p.y + ky)):
                p.rot = to
                p.x += kx
                p.y += ky
                self.last_kick = i
                self._after_action(True)
                return True
        return False

    def soft_drop(self):
        if self.move(0, 1):
            self.score += 1
            self.next_fall = time.monotonic() + self.gravity()
            return True
        return False

    def hard_drop(self):
        if self.piece is None or self.state != "play":
            return
        dist = 0
        while self.move(0, 1):
            dist += 1
        self.score += 2 * dist
        if dist:
            self.last_was_rotation = False
            self.fx_shake_until = time.monotonic() + SHAKE_TIME
            self.fx_shake_mag = 1 if dist < 9 else 2
        self.lock()

    def hold_piece(self):
        if self.piece is None or self.state != "play" or not self.can_hold:
            return
        kind = self.piece.kind
        if self.hold is None:
            self.hold = kind
            self.spawn()
        else:
            self.hold, kind = kind, self.hold
            self.spawn(kind)
        self.can_hold = False

    # -- locking, clearing, scoring ---------------------------------------

    def grant_power(self):
        if len(self.powers) >= POWER_SLOTS:
            return None
        name = self.rng.choice(POWERS)
        self.powers.append(name)
        self.say(name)
        self.sounds.append("level")
        return name

    def _strip_full_rows(self):
        """Remove completed rows without scoring them - powers do not pay."""
        full = [y for y in range(ROWS) if all(c is not None for c in self.board[y])]
        for y in full:
            del self.board[y]
            self.board.insert(0, [None] * COLS)
        return len(full)

    def use_power(self):
        """Spend the power at the front of the queue."""
        if not self.powers or self.state != "play":
            return None
        name = self.powers[0]
        if name == "LINE-I":
            fresh = Piece("I")
            if self.piece is None or self.collides(fresh.cells()):
                return None
            self.piece = fresh
        elif name == "SKIP":
            if self.piece is None:
                return None
            self.piece = None
            self.spawn()
        elif name == "BOMB":
            if all(c is None for c in self.board[ROWS - 1]):
                return None                      # nothing down there to clear
            del self.board[ROWS - 1]
            self.board.insert(0, [None] * COLS)
        elif name == "COMPACT":
            moved = False
            for x in range(COLS):
                stack = [self.board[y][x] for y in range(ROWS)
                         if self.board[y][x] is not None]
                for y in range(ROWS):
                    if self.board[y][x] is not None:
                        moved = True
                    self.board[y][x] = None
                for i, v in enumerate(reversed(stack)):
                    self.board[ROWS - 1 - i][x] = v
            if not moved:
                return None
            self._strip_full_rows()
        elif name == "SLOW":
            self.slow_until = time.monotonic() + SLOW_TIME
        self.powers.pop(0)
        self.say(name + " USED")
        if self.piece is not None and self.collides(self.piece.cells()):
            self.piece.y -= 1                    # never bury the falling piece
        return name

    def _occupied(self, x, y):
        if x < 0 or x >= COLS or y >= ROWS:
            return True                    # walls and floor count as filled
        if y < 0:
            return False                   # open sky does not
        return self.board[y][x] is not None

    def detect_tspin(self):
        p = self.piece
        if p.kind != "T" or not self.last_was_rotation:
            return False, False
        cx, cy = p.x + 1, p.y + 1
        corners = {
            "nw": self._occupied(cx - 1, cy - 1), "ne": self._occupied(cx + 1, cy - 1),
            "sw": self._occupied(cx - 1, cy + 1), "se": self._occupied(cx + 1, cy + 1),
        }
        if sum(corners.values()) < 3:
            return False, False
        front = {0: ("nw", "ne"), 1: ("ne", "se"),
                 2: ("sw", "se"), 3: ("nw", "sw")}[p.rot]
        full = corners[front[0]] and corners[front[1]]
        mini = not full and self.last_kick != 4   # the 5th kick promotes a mini
        return True, mini

    def lock(self):
        p = self.piece
        if p is None:
            return
        tspin, mini = self.detect_tspin()
        cells = p.cells()
        for x, y in cells:
            if 0 <= y < ROWS:
                self.board[y][x] = p.kind
        self.piece = None
        self.can_hold = True

        now = time.monotonic()
        self.fx_lock_cells = [(x, y) for x, y in cells if 0 <= y < ROWS]
        self.fx_lock_until = now + LOCK_FLASH
        lowest = {}
        for x, y in cells:
            lowest[x] = max(lowest.get(x, -99), y)
        self.fx_impact_cells = [(x, y + 1) for x, y in lowest.items()
                                if 0 <= y + 1 < ROWS and self.board[y + 1][x] is not None]
        self.fx_impact_until = now + IMPACT_TIME

        full = [y for y in range(ROWS) if all(c is not None for c in self.board[y])]
        n = len(full)
        self._score_clear(n, tspin, mini, full)

        if all(y < HIDDEN_ROWS for x, y in cells) and n == 0:
            self.game_over()               # lock out: entirely above the field
            return
        if n:
            self.flash_rows = full
            self.flash_start = time.monotonic()
            self.flash_until = self.flash_start + CLEAR_ANIM
            self.state = "flash"
        else:
            self.spawn()

    def _score_clear(self, n, tspin, mini, full):
        names = ["", "SINGLE", "DOUBLE", "TRIPLE", "TETRIS"]
        if tspin and not mini:
            base = {0: 400, 1: 800, 2: 1200, 3: 1600}[n]
            label = "T-SPIN" + ((" " + names[n]) if n else "")
        elif tspin and mini:
            base = {0: 100, 1: 200, 2: 400, 3: 400}[n]
            label = "MINI T-SPIN" + ((" " + names[n]) if n else "")
        else:
            base = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}[n]
            label = names[n]

        difficult = (n == 4) or (tspin and n > 0)
        if n > 0:
            if difficult:
                if self.b2b > 0:
                    base = int(base * 1.5)
                    label = "B2B " + label
                self.b2b += 1
            else:
                self.b2b = 0
            self.combo += 1
        else:
            self.combo = -1

        gained = base * self.level
        if self.combo > 0:
            gained += 50 * self.combo * self.level

        # perfect clear: everything that is filled is inside a cleared row
        if n > 0:
            rest = set(range(ROWS)) - set(full)
            empty_after = all(all(c is None for c in self.board[y]) for y in rest)
            if empty_after:
                pc = {1: 800, 2: 1200, 3: 1800, 4: 2000}[n]
                if n == 4 and self.b2b > 1:
                    pc = 3200
                gained += pc * self.level
                self.tally["perfect"] += 1
                label = "PERFECT CLEAR"

        self.score += gained
        if n:
            self.lines += n
            was = self.level
            self.level = min(MAX_LEVEL, self.start_level + self.lines // 10)
            self.tally[["", "single", "double", "triple", "tetris"][n]] += 1
            self.sounds.append("big" if (n == 4 or tspin) else "clear")
            if self.level > was:
                self.fx_level_value = self.level
                self.fx_level_until = time.monotonic() + LEVEL_BANNER
                self.sounds.append("level")
                if self.power_limit and self.level % POWER_EVERY == 0:
                    self.grant_power()
        if tspin:
            self.tally["tspin"] += 1
        if label:
            extra = ""
            if self.combo > 0:
                extra = "  COMBO x%d" % self.combo
            self.say(label + extra)

    def apply_clear(self):
        for y in sorted(self.flash_rows):
            del self.board[y]
            self.board.insert(0, [None] * COLS)
        self.flash_rows = []

    # -- per-frame ---------------------------------------------------------

    def update(self, now):
        if self.state == "flash":
            if now >= self.flash_until:
                self.apply_clear()
                self.state = "play"
                self.spawn()
            return
        if self.state != "play" or self.piece is None:
            return

        interval = self.gravity()
        guard = 0
        while now >= self.next_fall and guard < ROWS:
            guard += 1
            if self.move(0, 1):
                self.next_fall += interval
            else:
                self.next_fall = now + interval
                break

        if self.grounded():
            if self.lock_start is None:
                self.lock_start = now
            elif now - self.lock_start >= LOCK_DELAY:
                self.lock()
        else:
            self.lock_start = None

    def toggle_pause(self):
        now = time.monotonic()
        if self.state == "play":
            self.state = "paused"
            self.paused_at = now
        elif self.state == "paused":
            delta = now - self.paused_at
            self.paused_at = None
            self.state = "play"
            self.start_time += delta
            self.next_fall += delta
            self.flash_start += delta
            self.flash_until += delta
            if self.lock_start is not None:
                self.lock_start += delta
            self.message_until += delta
            for name in ("fx_lock_until", "fx_impact_until",
                         "fx_shake_until", "fx_level_until"):
                setattr(self, name, getattr(self, name) + delta)


# ---------------------------------------------------------------------------
# High score file
# ---------------------------------------------------------------------------

def load_high_score():
    try:
        with open(SCORE_FILE, "r") as fh:
            return int(json.load(fh).get("high_score", 0))
    except Exception:
        return 0


def save_high_score(value):
    try:
        with open(SCORE_FILE, "w") as fh:
            json.dump({"high_score": int(value)}, fh)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

GAP = 2

# name -> (cell width in columns, cell height in rows).  A terminal cell is
# roughly twice as tall as it is wide, so 2x1 and 4x2 come out square.
SCALES = {"small": (2, 1), "medium": (3, 1), "big": (4, 2)}
SCALE_ORDER = ["small", "medium", "big"]


class Layout(object):
    """Every screen coordinate, derived from one cell size."""

    def __init__(self, cw, ch):
        self.cw, self.ch = cw, ch
        self.panel_w = max(12, 4 * cw + 4)
        self.pf_w = COLS * cw + 2
        self.pf_h = VISIBLE_ROWS * ch + 2
        self.pf_x = self.panel_w + GAP
        self.right_x = self.pf_x + self.pf_w + GAP
        self.w = self.right_x + self.panel_w
        self.h = self.pf_h + 2                 # title line above, hints below
        self.hold_h = 2 * ch + 2
        self.next_h = NEXT_COUNT * 2 * ch + (NEXT_COUNT - 1) + 2
        self.stats_y = 1 + self.hold_h + 2
        self.hint_y = self.pf_h + 1

    def slot_y(self, i):
        return 2 + i * (2 * self.ch + 1)


def pick_layout(h, w, forced=None):
    """Largest cell size the terminal can hold, unless one was asked for."""
    if forced:
        return Layout(*SCALES[forced])
    best = Layout(*SCALES["small"])
    for name in SCALE_ORDER[1:]:
        cand = Layout(*SCALES[name])
        if h >= cand.h and w >= cand.w:
            best = cand
    return best


BLOCK_STYLES = ["inset", "solid", "shade", "dots", "round", "ascii", "hash"]

# A block style is a fill character (repeated across the cell) plus a ghost
# character. "inset" is the odd one out: it is built from half- and
# quarter-blocks so each cell is drawn a fraction smaller than its slot,
# which is what puts a seam between neighbouring pieces.
STYLE_FILL = {
    "solid": "\u2588",     # full block
    "shade": "\u2593",     # dark shade
    "dots":  "\u28ff",     # full braille cell
    "round": "\u25cf",     # filled circle
    "hash":  "#",
}

# The ghost is the same piece, hollowed out - so it has to follow the block
# style, not sit at a fixed glyph. A circle's ghost is an empty circle.
STYLE_GHOST = {
    "inset": "\u2592",     # medium shade
    "solid": "\u2592",
    "shade": "\u2591",     # light shade, against the block's dark shade
    "dots":  "\u2836",     # a sparse braille cell against the full one
    "round": "\u25cb",     # hollow circle
    "ascii": ":",
    "hash":  ":",
}
UNICODE_STYLES = ("inset", "solid", "shade", "dots", "round")


class Glyphs(object):
    """The characters one playfield cell is made of, at a given cell size.

    Styles other than "inset" simply repeat one fill character. Inset uses the
    half- and quarter-block glyphs to draw the cell a little smaller than its
    slot, so neighbouring blocks show a seam instead of merging into one slab.
    Full blocks are kept for the line-clear flash, where a solid bar reads
    better whatever the style.
    """

    def __init__(self, unicode_ok, cw, ch, style="inset"):
        if not unicode_ok and style in UNICODE_STYLES:
            style = "ascii" if style == "inset" else "hash"
        self.style = style
        if unicode_ok:
            self.tl, self.tr, self.bl, self.br = "\u250c", "\u2510", "\u2514", "\u2518"
            self.h, self.v = "\u2500", "\u2502"
            self.left, self.right = "\u2190", "\u2192"
            self.down, self.up = "\u2193", "\u2191"
            dot = "\u00b7"
        else:
            self.tl = self.tr = self.bl = self.br = "+"
            self.h, self.v = "-", "|"
            self.left, self.right, self.down, self.up = "<", ">", "v", "^"
            dot = "."

        if style == "inset" and cw >= 2:
            mid = "\u2590" + "\u2588" * (cw - 2) + "\u258c"
            if ch >= 2:
                top = "\u2597" + "\u2584" * (cw - 2) + "\u2596"
                bot = "\u259d" + "\u2580" * (cw - 2) + "\u2598"
                solid = [top] + [mid] * (ch - 2) + [bot]
            else:
                solid = [mid]
        elif style == "ascii":
            body = ("[" + "=" * (cw - 2) + "]") if cw >= 2 else "#"
            solid = [body] * ch
        else:
            solid = [STYLE_FILL.get(style, "\u2588") * cw] * ch

        mark = STYLE_GHOST.get(style, "\u2592") if unicode_ok else ":"
        if cw >= 3 and style in ("inset", "ascii"):
            ghost = [" " + mark * (cw - 2) + " "] * ch
        else:
            ghost = [mark * cw] * ch

        pad = " " * cw
        self.solid = solid
        self.ghost = ghost
        self.full = [("\u2588" if unicode_ok else "#") * cw] * ch
        # one grid dot per cell, on its top row
        self.empty = [" " * (cw // 2) + dot + " " * (cw - cw // 2 - 1)] + [pad] * (ch - 1)
        self.blank = [pad] * ch


PAIR = {}

# 256-colour palettes.  "classic" is the terminal's own basic colours, which is
# also what every theme degrades to when the terminal cannot do 256.
THEMES = {
    "classic": None,
    "neon":       {"I": 51,  "O": 226, "T": 207, "S": 118, "Z": 197, "J": 63,  "L": 208,
                   "accent": 207, "grid": 238, "frame": 99,  "danger": 197},
    "dracula":    {"I": 117, "O": 228, "T": 141, "S": 84,  "Z": 203, "J": 61,  "L": 215,
                   "accent": 212, "grid": 238, "frame": 103, "danger": 203},
    "nord":       {"I": 110, "O": 222, "T": 139, "S": 144, "Z": 131, "J": 67,  "L": 173,
                   "accent": 110, "grid": 239, "frame": 145, "danger": 131},
    "gruvbox":    {"I": 108, "O": 214, "T": 175, "S": 142, "Z": 203, "J": 109, "L": 208,
                   "accent": 214, "grid": 237, "frame": 246, "danger": 203},
    "candy":      {"I": 123, "O": 229, "T": 213, "S": 121, "Z": 210, "J": 147, "L": 216,
                   "accent": 213, "grid": 96,  "frame": 182, "danger": 210},
    "solarized":  {"I": 37,  "O": 136, "T": 125, "S": 64,  "Z": 160, "J": 33,  "L": 166,
                   "accent": 37,  "grid": 240, "frame": 244, "danger": 160},
    # Okabe & Ito (2008), the standard colour-vision-safe qualitative palette.
    # Verified with tetris_tests/palette_check.py: the closest two pieces sit at
    # dE 12.9 under protanopia and 17.9 under deuteranopia - the deficiencies
    # that affect roughly one man in twelve.
    "accessible": {"I": 74,  "O": 221, "T": 175, "S": 35,  "Z": 166, "J": 25,  "L": 178,
                   "accent": 74,  "grid": 239, "frame": 245, "danger": 166},
    "gameboy":    {"I": 194, "O": 157, "T": 120, "S": 114, "Z": 71,  "J": 65,  "L": 151,
                   "accent": 157, "grid": 22,  "frame": 65,  "danger": 191},
    # the two below are deliberately hard: one hue, told apart by brightness
    "amber":      {"I": 220, "O": 214, "T": 208, "S": 215, "Z": 202, "J": 172, "L": 209,
                   "accent": 220, "grid": 94,  "frame": 136, "danger": 202},
    "matrix":     {"I": 46,  "O": 118, "T": 82,  "S": 40,  "Z": 34,  "J": 71,  "L": 154,
                   "accent": 46,  "grid": 22,  "frame": 28,  "danger": 118},
    "mono":       {"I": 255, "O": 250, "T": 245, "S": 252, "Z": 247, "J": 242, "L": 253,
                   "accent": 255, "grid": 237, "frame": 244, "danger": 250},
}
THEME_ORDER = ["classic", "neon", "dracula", "nord", "gruvbox", "candy",
               "solarized", "accessible", "gameboy", "amber", "matrix", "mono"]

THEME_EVERY = 4          # the look changes this often, in levels
# The single-hue themes are a deliberate handicap - fine to choose, unkind to
# be dropped into halfway up a stack - so the rotation steps over them.
HARD_THEMES = ("mono", "amber", "matrix")
THEME_ROTATION = [t for t in THEME_ORDER if t not in HARD_THEMES]


def next_theme(current):
    """The look that follows this one when the level rolls over."""
    try:
        i = THEME_ROTATION.index(current)
    except ValueError:
        return THEME_ROTATION[0]
    return THEME_ROTATION[(i + 1) % len(THEME_ROTATION)]


def basic_palette():
    orange = 208 if curses.COLORS >= 256 else curses.COLOR_WHITE
    grey = 244 if curses.COLORS >= 256 else curses.COLOR_WHITE
    return {"I": curses.COLOR_CYAN, "O": curses.COLOR_YELLOW,
            "T": curses.COLOR_MAGENTA, "S": curses.COLOR_GREEN,
            "Z": curses.COLOR_RED, "J": curses.COLOR_BLUE, "L": orange,
            "accent": curses.COLOR_CYAN, "grid": grey,
            "frame": curses.COLOR_WHITE, "danger": curses.COLOR_RED}


def setup_colors(theme="classic"):
    PAIR.clear()
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    spec = THEMES.get(theme)
    if not spec or curses.COLORS < 256:
        spec = basic_palette()
    for i, k in enumerate(ORDER, start=1):
        curses.init_pair(i, spec[k], bg)
        PAIR[k] = curses.color_pair(i)
    curses.init_pair(8, spec["grid"], bg)
    PAIR["grid"] = curses.color_pair(8) | curses.A_DIM
    curses.init_pair(9, curses.COLOR_BLACK, curses.COLOR_WHITE)
    PAIR["flash"] = curses.color_pair(9) | curses.A_BOLD
    curses.init_pair(10, spec["accent"], bg)
    PAIR["accent"] = curses.color_pair(10) | curses.A_BOLD
    curses.init_pair(11, spec["frame"], bg)
    PAIR["frame"] = curses.color_pair(11)
    curses.init_pair(12, curses.COLOR_YELLOW, bg)
    PAIR["spark"] = curses.color_pair(12) | curses.A_BOLD
    curses.init_pair(13, spec["danger"], bg)
    PAIR["danger"] = curses.color_pair(13) | curses.A_BOLD


def attr(name, fallback=0):
    return PAIR.get(name, fallback)


class Screen(object):
    def __init__(self, stdscr, unicode_ok, layout, show_ghost=True, style="inset"):
        self.s = stdscr
        self.unicode = unicode_ok
        self.show_ghost = show_ghost
        self.style = style
        self.allow_shake = True
        self.shake_dy = 0
        self.ox = self.oy = 0
        self.set_layout(layout)

    def set_layout(self, layout):
        self.L = layout
        self.g = Glyphs(self.unicode, layout.cw, layout.ch, self.style)

    def recenter(self):
        h, w = self.s.getmaxyx()
        self.ox = max(0, (w - self.L.w) // 2)
        self.oy = max(0, (h - self.L.h) // 2)
        return h >= self.L.h and w >= self.L.w

    def put(self, y, x, text, a=0):
        h, w = self.s.getmaxyx()
        y += self.oy
        x += self.ox
        if y < 0 or y >= h or x >= w:
            return
        if x < 0:
            text = text[-x:]
            x = 0
        room = w - x - (1 if y == h - 1 else 0)
        if room <= 0:
            return
        try:
            self.s.addstr(y, x, text[:room], a)
        except curses.error:
            pass

    def block(self, y, x, kind, mode="solid"):
        """One playfield cell: cw columns by ch rows."""
        g = self.g
        if mode == "flash":
            rows, a = g.full, attr("flash", curses.A_REVERSE)
        elif mode == "spark":
            rows, a = g.solid, attr("spark", curses.A_BOLD)
        elif mode == "ghost":
            rows, a = g.ghost, attr(kind, 0) | curses.A_DIM
        elif mode == "dim":                       # held piece you cannot use yet
            rows, a = g.solid, attr("grid", 0) | curses.A_DIM
        elif mode == "empty":
            rows, a = g.empty, attr("grid", curses.A_DIM)
        elif mode == "blank":
            rows, a = g.blank, 0
        else:
            rows, a = g.solid, attr(kind, curses.A_BOLD) | curses.A_BOLD
        for i, row in enumerate(rows):
            self.put(y + i, x, row, a)

    def field_cell(self, r, c, kind, mode="solid"):
        L = self.L
        self.block(1 + 1 + r * L.ch, L.pf_x + 1 + c * L.cw, kind, mode)

    def frame(self, y, x, w, h, title="", a=None):
        g = self.g
        a = attr("frame", 0) if a is None else a
        top = g.h * (w - 2)
        if title:
            label = " " + title + " "
            top = g.h + label + g.h * (w - 3 - len(label))
        self.put(y, x, g.tl + top + g.tr, a)
        for i in range(1, h - 1):
            self.put(y + i, x, g.v, a)
            self.put(y + i, x + w - 1, g.v, a)
        self.put(y + h - 1, x, g.bl + g.h * (w - 2) + g.br, a)

    def mini(self, y, x, kind, dim=False):
        """A piece drawn small, inside a 4-cell by 2-cell slot."""
        if kind is None:
            return
        L = self.L
        cells = ROTATIONS[kind][0]
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        offx = (4 - (max(xs) - min(xs) + 1)) // 2 - min(xs)
        offy = (2 - (max(ys) - min(ys) + 1)) // 2 - min(ys)
        for cx, cy in cells:
            self.block(y + (offy + cy) * L.ch, x + (offx + cx) * L.cw,
                       kind, "dim" if dim else "solid")


def shake_offset(game, now):
    """Rows to bounce the board by after a hard drop: down, up, down, settle."""
    if now >= game.fx_shake_until or not game.fx_shake_mag:
        return 0
    mag = game.fx_shake_mag
    elapsed = SHAKE_TIME - (game.fx_shake_until - now)
    phase = min(3, max(0, int(elapsed / (SHAKE_TIME / 4.0))))
    return (mag, -mag, 1, 0)[phase]


def clear_phase(game, now):
    """Where the line-clear animation is: (strobe on?, columns opened)."""
    span = max(1e-6, game.flash_until - game.flash_start)
    p = min(1.0, max(0.0, (now - game.flash_start) / span))
    if p < 0.4:                                   # blink the full rows twice
        return int(p / 0.1) % 2 == 0, 0
    return True, int(((p - 0.4) / 0.6) * (COLS // 2 + 1))   # then sweep open


def draw(scr, game):
    s = scr.s
    g = scr.g
    L = scr.L
    now = time.monotonic()
    s.erase()
    if not scr.recenter():
        h, w = s.getmaxyx()
        for i, msg in enumerate([
                "Terminal too small: need %dx%d, have %dx%d" % (L.w, L.h, w, h),
                "Resize the window, try --scale small, or press q to quit."]):
            try:
                s.addstr(i, 0, msg[:max(0, w - 1)])
            except curses.error:
                pass
        s.refresh()
        return

    # a hard drop bounces the whole board, if the window has room for it.
    # Moving every row at once is more than the incremental update can be
    # trusted with, so each change of offset forces a clean full repaint.
    dy = shake_offset(game, now) if scr.allow_shake else 0
    if dy and not (0 <= scr.oy + dy and scr.oy + dy + L.h <= s.getmaxyx()[0]):
        dy = 0
    if dy != scr.shake_dy:
        scr.shake_dy = dy
        s.clearok(True)
    scr.oy += dy

    title = "T E T R I S"
    scr.put(0, (L.w - len(title)) // 2, title, attr("accent", curses.A_BOLD))

    # ---- playfield -------------------------------------------------------
    danger = game.danger() and game.state == "play"
    frame_attr = None
    if danger:
        frame_attr = attr("danger", curses.A_BOLD)
        if int(now * 3) % 2:
            frame_attr |= curses.A_DIM
    scr.frame(1, L.pf_x, L.pf_w, L.pf_h, a=frame_attr)
    ghost = game.ghost_y() if (game.piece is not None and scr.show_ghost) else None
    live = set(game.piece.cells()) if game.piece is not None else set()
    ghosted = set(game.piece.cells(y=ghost)) if ghost is not None else set()
    flash = set(game.flash_rows)
    strobe, opened = clear_phase(game, now) if flash else (False, 0)
    locked = set(game.fx_lock_cells) if now < game.fx_lock_until else set()
    impact = set(game.fx_impact_cells) if now < game.fx_impact_until else set()

    for r in range(VISIBLE_ROWS):
        by = HIDDEN_ROWS + r
        for c in range(COLS):
            if by in flash:
                if min(c, COLS - 1 - c) >= COLS // 2 - opened:
                    scr.field_cell(r, c, None, "empty")      # swept away
                elif strobe:
                    scr.field_cell(r, c, None, "flash")
                else:
                    scr.field_cell(r, c, game.board[by][c], "spark")
                continue
            if (c, by) in locked:
                scr.field_cell(r, c, None, "flash")      # the piece just landed
                continue
            if (c, by) in impact:
                scr.field_cell(r, c, None, "spark")      # what it landed on
                continue
            k = game.board[by][c]
            if k is not None:
                scr.field_cell(r, c, k)
            elif (c, by) in live:
                scr.field_cell(r, c, game.piece.kind)
            elif (c, by) in ghosted:
                scr.field_cell(r, c, game.piece.kind, "ghost")
            else:
                scr.field_cell(r, c, None, "empty")

    # ---- hold + stats ----------------------------------------------------
    scr.frame(1, 0, L.panel_w, L.hold_h, "HOLD")
    scr.mini(2, 2, game.hold, dim=not game.can_hold)

    lab = attr("grid", curses.A_DIM)
    val = curses.A_BOLD
    num = "%" + str(L.panel_w - 2) + "s"
    y = L.stats_y
    scr.put(y, 0, "SCORE", lab)
    scr.put(y + 1, 0, num % "{:,}".format(game.score), val)
    scr.put(y + 2, 0, "HIGH", lab)
    scr.put(y + 3, 0, num % "{:,}".format(max(game.high, game.score)), 0)
    scr.put(y + 5, 0, "LEVEL %4d" % game.level, val)
    scr.put(y + 6, 0, "LINES %4d" % game.lines, 0)
    secs = int(game.elapsed())
    scr.put(y + 7, 0, "TIME %5s" % ("%d:%02d" % (secs // 60, secs % 60)), 0)
    if game.combo > 0:
        scr.put(y + 9, 0, "COMBO  x%d" % game.combo, attr("accent", curses.A_BOLD))
    if game.b2b > 1:
        scr.put(y + 10, 0, "B2B    x%d" % (game.b2b - 1), attr("accent", curses.A_BOLD))
    if game.undo_limit:
        scr.put(y + 11, 0, "UNDO    %2d" % game.undos_left,
                attr("accent", curses.A_BOLD) if game.undos_left
                else attr("grid", curses.A_DIM))
    scr.put(y + 14, 0, "PIECES%4d" % game.pieces_placed, lab)
    scr.put(y + 15, 0, "TETRIS%4d" % game.tally["tetris"], lab)
    if game.message and now < game.message_until:
        for i, line in enumerate(textwrap.wrap(game.message, L.panel_w - 1)[:2]):
            scr.put(y + 12 + i, 0, line, attr("accent", curses.A_BOLD))

    # ---- next queue ------------------------------------------------------
    scr.frame(1, L.right_x, L.panel_w, L.next_h, "NEXT")
    for i in range(NEXT_COUNT):
        scr.mini(L.slot_y(i), L.right_x + 2, game.queue[i])

    # ---- powers, in a box of their own so they are never missed ----------
    if game.power_limit:
        py = 1 + L.next_h
        scr.frame(py, L.right_x, L.panel_w, POWER_SLOTS + 3, "POWERS")
        for i in range(POWER_SLOTS):
            row = py + 1 + i
            if i < len(game.powers):
                mark, a = ("f " if i == 0 else "  "), (attr("hl", curses.A_BOLD)
                                                       if i == 0 else 0)
                scr.put(row, L.right_x + 1, (mark + game.powers[i])[:L.panel_w - 2], a)
            else:
                scr.put(row, L.right_x + 1, "  -", attr("grid", curses.A_DIM))
        left = game.slow_until - now
        if left > 0:
            scr.put(py + POWER_SLOTS + 1, L.right_x + 1, "SLOW %3.0fs" % left,
                    attr("accent", curses.A_BOLD))

    short = "ad/%s%s move   w/z rot   SPC drop   c hold   ? help" % (g.left, g.right)
    long_ = ("a d %s%s move   s/%s soft   SPACE drop   w z e rotate"
             "   c hold   p pause   ? help" % (g.left, g.right, g.down))
    hint = long_ if len(long_) <= L.w else short
    scr.put(L.hint_y, max(0, (L.w - len(hint)) // 2), hint, lab)

    if now < game.fx_level_until and game.state != "over":
        banner(scr, "L E V E L   %d" % game.fx_level_value)

    if game.state == "paused":
        overlay(scr, ["", "P A U S E D", "", "p  resume", "r  restart", "q  quit", ""])
    elif game.state == "over":
        lines = ["", "G A M E   O V E R", "",
                 "SCORE   %s" % "{:,}".format(game.score),
                 "LINES   %d" % game.lines,
                 "LEVEL   %d" % game.level,
                 "TETRIS  %d" % game.tally["tetris"]]
        if game.new_record:
            lines += ["", "*  NEW HIGH SCORE  *"]
        lines += ["", "r  play again", "q  quit", ""]
        overlay(scr, lines)

    s.refresh()


def banner(scr, text):
    """A single line laid across the middle of the field, over whatever is there."""
    L = scr.L
    y = 1 + L.pf_h // 2 - 1
    inner = L.pf_w - 2
    pad = " " * inner
    for i in range(3):
        scr.put(y + i, L.pf_x + 1, pad)
    scr.put(y + 1, L.pf_x + 1 + max(0, (inner - len(text)) // 2), text,
            attr("accent", curses.A_BOLD))


def overlay(scr, lines):
    L = scr.L
    w = max(L.pf_w + 6, max(len(t) for t in lines) + 6)
    x = L.pf_x + (L.pf_w - w) // 2
    h = len(lines) + 2
    y = 1 + (L.pf_h - h) // 2
    blank = " " * (w - 2)
    scr.frame(y, x, w, h)
    for i, text in enumerate(lines):
        scr.put(y + 1 + i, x + 1, blank)
        a = attr("accent", curses.A_BOLD) if i == 1 else 0
        scr.put(y + 1 + i, x + 1 + (w - 2 - len(text)) // 2, text, a)


def draw_help(scr):
    s = scr.s
    g = scr.g
    L = scr.L
    s.erase()
    scr.recenter()
    scr.put(0, (L.w - 8) // 2, "CONTROLS", attr("accent", curses.A_BOLD))
    keys = [
        ("a  d     %s %s" % (g.left, g.right), "move / hold to slide"),
        ("s        %s" % g.down, "soft drop  (+1 per cell)"),
        ("SPACE", "hard drop  (+2 per cell)"),
        ("w  x  k  %s" % g.up, "rotate clockwise"),
        ("z", "rotate counter-clockwise"),
        ("e", "rotate 180"),
        ("c", "hold piece (once per drop)"),
        ("f", "use the superpower you hold"),
        ("u", "undo the last piece"),
        ("g", "toggle ghost piece"),
        ("m", "cycle block style"),
        ("t", "cycle colour theme by hand"),
        ("b", "sound on / off"),
        ("p", "pause / resume"),
        ("r", "restart"),
        ("q", "quit"),
    ]
    notes = ["A superpower every %d levels; the look changes every %d."
             % (POWER_EVERY, THEME_EVERY),
             "Hold a direction to slide the piece along.",
             "Line clears score 100/300/500/800 x level;",
             "T-spins, back-to-back and combos score more."]
    bw = min(L.w - 2, 52)
    bx = (L.w - bw) // 2
    scr.frame(2, bx, bw, len(keys) + len(notes) + 3)
    for i, (k, d) in enumerate(keys):
        scr.put(3 + i, bx + 2, "%-16s" % k, attr("accent", curses.A_BOLD))
        scr.put(3 + i, bx + 19, d, 0)
    for i, note in enumerate(notes):
        scr.put(4 + len(keys) + i, bx + 2, note, attr("grid", 0))
    tail = "press any key to return"
    scr.put(len(keys) + len(notes) + 6, (L.w - len(tail)) // 2, tail,
            attr("grid", curses.A_DIM))
    s.refresh()


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class KeyReader(object):
    """Normalise getch() output, assembling escape sequences ourselves.

    ncurses only recognises the arrow sequence its terminfo entry names, which
    for xterm is the application-cursor form ESC O C.  A terminal left in
    normal cursor mode sends ESC [ C instead, and that would otherwise reach
    the game as the plain letters '[' and 'C' - firing hold instead of moving
    right.  Buffering ESC ourselves makes both forms work and keeps a stray
    escape byte from triggering anything.
    """

    ARROWS = {ord("A"): curses.KEY_UP, ord("B"): curses.KEY_DOWN,
              ord("C"): curses.KEY_RIGHT, ord("D"): curses.KEY_LEFT}
    STALE = 0.05

    def __init__(self):
        self.buf = []
        self.started = 0.0

    def flush_stale(self, now):
        """Drop a half-finished sequence, e.g. the user just pressed ESC."""
        if self.buf and now - self.started > self.STALE:
            self.buf = []

    def feed(self, ch):
        if not self.buf:
            if ch == 27:
                self.buf = [ch]
                self.started = time.monotonic()
                return None
            return ch
        if ch > 255:                      # a real key code, not sequence bytes
            self.buf = []
            return ch
        if len(self.buf) == 1:
            if ch in (ord("["), ord("O")):
                self.buf.append(ch)
                return None
            self.buf = []
            return None if ch == 27 else ch
        if self.buf[1] == ord("[") and 0x30 <= ch <= 0x3F:
            self.buf.append(ch)           # CSI parameter byte, keep reading
            return None
        self.buf = []
        return self.ARROWS.get(ch)


class AutoRepeat(object):
    """Hold a direction and the piece slides; a tap still moves exactly one cell.

    A terminal reports key presses but never releases, so "still held" has to
    be inferred from the terminal's own repeat.  Every real key event always
    moves the piece once - that keeps rapid taps, and events the terminal
    buffered up while we were busy, exact.  On top of that, once repeats show
    the key is genuinely down, each one is credited with an extra cell or two,
    spread across the repeat interval so the slide looks smooth.  Crediting
    real events rather than free-running on a timer is what bounds the cost of
    never seeing the release: at most the last event's credit, one or two
    cells.  A tap produces no repeats at all, so it can never run away.
    """

    MIN_ARR = 0.015          # never faster than ~66 cells a second
    MAX_GAP = 0.30           # a longer silence than this means a fresh press

    def __init__(self):
        self.reset()

    def reset(self):
        self.key = None
        self.last = 0.0
        self.gap = 0.0
        self.pending = 0
        self.next = 0.0

    @property
    def active(self):
        return self.pending > 0

    def cells_per_repeat(self):
        """A slow terminal repeat is worth more cells, to even out the feel."""
        return 2 if self.gap < 0.07 else 3

    def arr(self):
        if not self.gap:
            return self.MIN_ARR
        return max(self.MIN_ARR, self.gap / self.cells_per_repeat())

    def note(self, key, now):
        """Record a key event.  The caller always moves once for it."""
        if key == self.key and now - self.last <= self.MAX_GAP:
            gap = now - self.last                  # the terminal is repeating
            self.gap = gap if not self.gap else self.gap * 0.6 + gap * 0.4
            self.last = now
            self.pending = self.cells_per_repeat() - 1      # on top of this one
            self.next = now + self.arr()
        else:
            self.key = key                         # a fresh press
            self.last = now
            self.gap = 0.0
            self.pending = 0

    def due(self, now):
        """An extra cell of slide to apply now, or None."""
        if self.pending <= 0 or now < self.next:
            return None
        self.pending -= 1
        step = self.arr()
        # keep the cadence rather than re-basing on the frame clock, which
        # would round every interval up to the frame length; but never let a
        # stalled loop bank up a burst of moves
        self.next = (self.next + step) if (now - self.next) < step else (now + step)
        return self.key


def apply_move(game, action):
    if action == "left":
        game.move(-1, 0)
    elif action == "right":
        game.move(1, 0)
    else:
        game.soft_drop()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(stdscr, args):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    theme = args.theme
    setup_colors(theme)
    sound = not args.quiet
    rotate_every = max(0, args.theme_every)
    last_level = 0

    unicode_ok = (not args.ascii) and "utf" in (
        locale.getpreferredencoding(False) or "").lower().replace("-", "")
    forced = None if args.scale == "auto" else args.scale
    size = stdscr.getmaxyx()
    style = args.blocks
    if args.no_margins and style == "inset":
        style = "solid"
    scr = Screen(stdscr, unicode_ok, pick_layout(size[0], size[1], forced),
                 show_ghost=not args.no_ghost, style=style)
    scr.allow_shake = not args.no_shake
    game = Game(start_level=args.level, seed=args.seed,
                undo_limit=args.undo, powers=not args.no_powers)
    keys = KeyReader()
    repeat = AutoRepeat()
    helping = False

    while True:
        keys.flush_stale(time.monotonic())
        while True:
            raw = stdscr.getch()
            if raw == -1:
                break
            ch = keys.feed(raw)
            if ch is None:
                continue
            if ch == curses.KEY_RESIZE:
                stdscr.clear()
                continue

            if ch in (ord("q"), ord("Q")):
                return
            if helping:                    # any other key closes the help
                helping = False
                stdscr.clear()
                continue
            if ch in (ord("?"), ord("/"), curses.KEY_F1):
                helping = True
                stdscr.clear()
                if game.state == "play":
                    game.toggle_pause()
                continue
            if ch in (ord("r"), ord("R")):
                game.reset()
                repeat.reset()
                continue
            if ch in (ord("p"), ord("P")):
                game.toggle_pause()
                repeat.reset()
                continue
            if ch in (ord("f"), ord("F")):
                if game.powers:
                    if game.use_power() is None:
                        game.say("NO EFFECT")
                else:
                    game.say("NO POWER")
                continue
            if ch in (ord("u"), ord("U")):
                if not game.undo():
                    game.say("NO UNDOS" if game.undo_limit else "UNDO OFF")
                continue
            if ch in (ord("g"), ord("G")):
                scr.show_ghost = not scr.show_ghost
                continue
            if ch in (ord("m"), ord("M")):
                i = BLOCK_STYLES.index(scr.style) if scr.style in BLOCK_STYLES else 0
                scr.style = BLOCK_STYLES[(i + 1) % len(BLOCK_STYLES)]
                scr.set_layout(scr.L)
                game.say(scr.g.style.upper())
                stdscr.clear()
                continue
            if ch in (ord("t"), ord("T")):
                theme = THEME_ORDER[(THEME_ORDER.index(theme) + 1) % len(THEME_ORDER)]
                setup_colors(theme)
                game.say(theme.upper())
                stdscr.clear()
                continue
            if ch in (ord("b"), ord("B")):
                sound = not sound
                game.say("SOUND " + ("ON" if sound else "OFF"))
                continue
            if game.state in ("over", "paused"):
                continue

            if ch in (curses.KEY_LEFT, ord("a"), ord("A"), ord("h")):
                action = "left"
            elif ch in (curses.KEY_RIGHT, ord("d"), ord("D"), ord("l")):
                action = "right"
            elif ch in (curses.KEY_DOWN, ord("s"), ord("S"), ord("j")):
                action = "down"
            else:
                action = None
            if action is not None:
                repeat.note(action, time.monotonic())
                apply_move(game, action)
                continue

            if ch in (curses.KEY_UP, ord("w"), ord("W"),
                        ord("x"), ord("X"), ord("k")):
                game.rotate(1)
            elif ch in (ord("z"), ord("Z")):
                game.rotate(3)
            elif ch in (ord("e"), ord("E")):
                game.rotate(2)
            elif ch == ord(" "):
                game.hard_drop()
            elif ch in (ord("c"), ord("C")):
                game.hold_piece()

        # the look moves on with the level, unless that was switched off
        if rotate_every and game.level > last_level and game.level % rotate_every == 0:
            theme = next_theme(theme)
            setup_colors(theme)
            game.say(theme.upper())
            stdscr.clear()
        last_level = game.level

        if game.sounds:
            if sound:
                for name in game.sounds:
                    curses.beep()
                    if name in ("big", "over"):
                        curses.beep()          # two for a tetris or a game over
            del game.sounds[:]

        if helping or game.state in ("paused", "over"):
            repeat.reset()
        else:
            # kept ticking through the clear animation, where the moves are
            # no-ops, so a held key carries on sliding once play resumes
            now = time.monotonic()
            action = repeat.due(now)
            while action is not None:
                apply_move(game, action)
                action = repeat.due(now)

        now_size = stdscr.getmaxyx()
        if now_size != size:               # window resized: re-fit the board
            size = now_size
            want = pick_layout(size[0], size[1], forced)
            if (want.cw, want.ch) != (scr.L.cw, scr.L.ch):
                scr.set_layout(want)
            stdscr.clear()

        if helping:
            draw_help(scr)
        else:
            game.update(time.monotonic())
            draw(scr, game)
        time.sleep(0.012)


def build_parser():
    ap = argparse.ArgumentParser(
        description="Terminal Tetris - offline, stdlib only.")
    ap.add_argument("--level", type=int, default=1,
                    help="starting level 1-%d (default 1)" % MAX_LEVEL)
    ap.add_argument("--seed", type=int, default=None,
                    help="fixed piece sequence, for practice or testing")
    ap.add_argument("--scale", choices=["auto"] + SCALE_ORDER, default="auto",
                    help="block size; auto picks the biggest your window fits")
    ap.add_argument("--theme", choices=THEME_ORDER, default="classic",
                    help="colour scheme (needs a 256-colour terminal; "
                         "otherwise falls back to classic)")
    ap.add_argument("--undo", type=int, default=3, metavar="N",
                    help="take-backs per game (default 3, 0 turns it off)")
    ap.add_argument("--no-shake", action="store_true",
                    help="hold the board still on a hard drop (reduced motion)")
    ap.add_argument("--quiet", action="store_true",
                    help="no terminal bell on clears, level ups or game over")
    ap.add_argument("--theme-every", type=int, default=THEME_EVERY, metavar="N",
                    help="change the look every N levels (0 keeps one look)")
    ap.add_argument("--no-powers", action="store_true",
                    help="no superpowers every %d levels" % POWER_EVERY)
    ap.add_argument("--blocks", choices=BLOCK_STYLES, default="inset",
                    help="what a block is drawn with (default inset)")
    ap.add_argument("--no-margins", action="store_true",
                    help="shorthand for --blocks solid")
    ap.add_argument("--ascii", action="store_true",
                    help="plain ASCII blocks instead of Unicode")
    ap.add_argument("--no-ghost", action="store_true",
                    help="start with the ghost piece hidden")
    return ap


def main():
    args = build_parser().parse_args()

    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(run, args)
    except KeyboardInterrupt:
        pass
    print("Thanks for playing. High score: %s" % "{:,}".format(load_high_score()))


if __name__ == "__main__":
    main()
