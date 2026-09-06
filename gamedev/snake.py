#!/usr/bin/env python3
"""
Terminal Snake - a complete Snake for a plain text terminal.

No graphics, no dependencies, no network: Python 3 standard library only.

    python3 snake.py             play
    python3 snake.py --help      options

Steer with the arrow keys, WASD or HJKL. Press ? in game for the full list.
"""

import argparse
import curses
import json
import locale
import os
import random
import time
from collections import deque

# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------

SIZES = {"small": (20, 12), "medium": (28, 16), "large": (36, 20)}
SIZE_ORDER = ["small", "medium", "large"]

START_LENGTH = 4
GROW_PER_FOOD = 2
FOOD_PER_LEVEL = 5
BASE_STEP = 0.145            # seconds per move at level 1
SPEED_UP = 0.92              # each level multiplies the step time by this
MIN_STEP = 0.045
BONUS_EVERY = 4              # a golden apple after this many ordinary ones
BONUS_LIFE = 45              # and it sits there for this many moves
TURN_BUFFER = 2              # queued turns, so a fast double-tap is not lost

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)
DIRECTIONS = {"up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}

SCORE_FILE = (os.environ.get("SNAKE_SAVE")
              or os.path.join(os.path.expanduser("~"), ".terminal_snake.json"))


def load_high_score():
    try:
        with open(SCORE_FILE) as fh:
            return int(json.load(fh).get("high_score", 0))
    except Exception:
        return 0


def save_high_score(value):
    try:
        tmp = SCORE_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"high_score": int(value)}, fh)
        os.replace(tmp, SCORE_FILE)
    except Exception:
        pass


class Game(object):
    """All of the rules. Knows nothing about the screen."""

    def __init__(self, size="medium", seed=None, wrap=False, maze=0):
        self.w, self.h = SIZES[size]
        self.size = size
        self.wrap = wrap
        self.maze = maze
        self.rng = random.Random(seed)
        self.high = load_high_score()
        self.reset()

    # -- setup -------------------------------------------------------------

    def reset(self):
        now = time.monotonic()
        cx, cy = self.w // 2, self.h // 2
        self.snake = deque([(cx - i, cy) for i in range(START_LENGTH)])
        self.occupied = set(self.snake)
        self.direction = RIGHT
        self.turns = deque()
        self.grow = 0
        self.score = 0
        self.eaten = 0
        self.level = 1
        self.state = "ready"           # ready | play | over | paused
        self.message = ""
        self.message_until = 0.0
        self.walls = self._build_maze()
        self.food = None
        self.bonus = None
        self.bonus_left = 0
        self.best_length = len(self.snake)
        self.start_time = now
        self.paused_at = None
        self.new_record = False
        self.next_step = now + self.step_time()
        self.place_food()

    def _build_maze(self):
        """Scattered blocks to weave around, if asked for."""
        walls = set()
        if not self.maze:
            return walls
        safe = set()
        cy = self.h // 2
        for x in range(self.w):
            safe.update({(x, cy), (x, cy - 1), (x, cy + 1)})
        target = int(self.w * self.h * self.maze / 100.0)
        guard = 0
        while len(walls) < target and guard < target * 40:
            guard += 1
            x = self.rng.randrange(1, self.w - 1)
            y = self.rng.randrange(1, self.h - 1)
            if (x, y) in safe or (x, y) in walls:
                continue
            walls.add((x, y))
        return walls

    # -- helpers -----------------------------------------------------------

    def step_time(self):
        return max(MIN_STEP, BASE_STEP * (SPEED_UP ** (self.level - 1)))

    def elapsed(self):
        if self.paused_at is not None:
            return self.paused_at - self.start_time
        return time.monotonic() - self.start_time

    def free_cells(self):
        taken = self.occupied | self.walls
        if self.food:
            taken = taken | {self.food}
        if self.bonus:
            taken = taken | {self.bonus}
        return [(x, y) for x in range(self.w) for y in range(self.h)
                if (x, y) not in taken]

    def place_food(self):
        free = self.free_cells()
        if not free:
            self.state = "over"          # the board is full: a perfect game
            self.say("BOARD FULL")
            return
        self.food = self.rng.choice(free)

    def place_bonus(self):
        free = self.free_cells()
        if free:
            self.bonus = self.rng.choice(free)
            self.bonus_left = BONUS_LIFE

    def say(self, text):
        self.message = text
        self.message_until = time.monotonic() + 2.5

    # -- input -------------------------------------------------------------

    def turn(self, d):
        """Queue a turn. Reversing into your own neck is refused.

        The first turn also starts the run - a snake that sets off the moment
        the window opens has crossed the board before you have looked at it.
        """
        if self.state == "ready":
            self.state = "play"
            self.next_step = time.monotonic() + self.step_time()
        if self.state != "play":
            return False
        last = self.turns[-1] if self.turns else self.direction
        if (d[0] == -last[0] and d[1] == -last[1]) or d == last:
            return False
        if len(self.turns) >= TURN_BUFFER:
            return False
        self.turns.append(d)
        return True

    # -- the tick ----------------------------------------------------------

    def ahead(self):
        """The cell the head is about to enter, or None if that is off-board.

        Reads the committed direction only. Peeking at the queue here would
        apply the *next* turn on top of the one step() just committed to, so
        two buffered turns would happen in a single move - which drives the
        head straight into its own neck.
        """
        d = self.direction
        hx, hy = self.snake[0]
        nx, ny = hx + d[0], hy + d[1]
        if self.wrap:
            return (nx % self.w, ny % self.h)
        if 0 <= nx < self.w and 0 <= ny < self.h:
            return (nx, ny)
        return None

    def step(self):
        if self.state in ("over", "paused"):
            return
        if self.turns:
            self.direction = self.turns.popleft()
        head = self.ahead()
        if head is None:
            return self.die("HIT THE WALL")

        tail = self.snake[-1]
        # the tail cell frees up on the same move, unless the snake is growing
        body = self.occupied if self.grow else (self.occupied - {tail})
        if head in body or head in self.walls:
            return self.die("ATE ITSELF" if head in body else "HIT A BLOCK")

        self.snake.appendleft(head)
        self.occupied.add(head)
        if self.grow:
            self.grow -= 1
        else:
            self.snake.pop()
            self.occupied.discard(tail)
        self.best_length = max(self.best_length, len(self.snake))

        if self.bonus is not None:
            self.bonus_left -= 1
            if head == self.bonus:
                worth = int((50 + 10 * self.level) * (0.4 + 0.6 * self.bonus_left / BONUS_LIFE))
                self.score += worth
                self.grow += GROW_PER_FOOD
                self.bonus, self.bonus_left = None, 0
                self.say("+%d BONUS" % worth)
            elif self.bonus_left <= 0:
                self.bonus = None

        if head == self.food:
            self.score += 10 * self.level
            self.grow += GROW_PER_FOOD
            self.eaten += 1
            if self.eaten % FOOD_PER_LEVEL == 0:
                self.level += 1
                self.say("LEVEL %d" % self.level)
            if self.eaten % BONUS_EVERY == 0 and self.bonus is None:
                self.place_bonus()
            self.place_food()

    def die(self, why):
        self.state = "over"
        self.paused_at = time.monotonic()
        self.say(why)
        if self.score > self.high:
            self.high = self.score
            self.new_record = True
            save_high_score(self.high)

    def update(self, now):
        if self.state != "play":
            return
        guard = 0
        while now >= self.next_step and guard < 8:
            guard += 1
            self.step()
            if self.state != "play":
                return
            self.next_step += self.step_time()
        if now - self.next_step > 1.0:
            self.next_step = now + self.step_time()

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
            self.next_step += delta
            self.message_until += delta


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------

PAIR = {}
THEMES = {
    "classic": None,
    "neon":      {"head": 51,  "body": 45,  "tail": 39,  "food": 197,
                  "bonus": 226, "wall": 99,  "frame": 63,  "grid": 238},
    "orchard":   {"head": 118, "body": 76,  "tail": 34,  "food": 196,
                  "bonus": 220, "wall": 94,  "frame": 65,  "grid": 22},
    "dracula":   {"head": 84,  "body": 78,  "tail": 72,  "food": 203,
                  "bonus": 228, "wall": 61,  "frame": 103, "grid": 238},
    "desert":    {"head": 214, "body": 208, "tail": 172, "food": 197,
                  "bonus": 227, "wall": 137, "frame": 180, "grid": 58},
    "mono":      {"head": 255, "body": 250, "tail": 244, "food": 253,
                  "bonus": 231, "wall": 240, "frame": 244, "grid": 237},
}
THEME_ORDER = ["classic", "neon", "orchard", "dracula", "desert", "mono"]


def basic_palette():
    bright = 82 if curses.COLORS >= 256 else curses.COLOR_GREEN
    return {"head": bright, "body": curses.COLOR_GREEN, "tail": curses.COLOR_GREEN,
            "food": curses.COLOR_RED, "bonus": curses.COLOR_YELLOW,
            "wall": curses.COLOR_BLUE, "frame": curses.COLOR_WHITE,
            "grid": 244 if curses.COLORS >= 256 else curses.COLOR_WHITE}


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
    for i, key in enumerate(("head", "body", "tail", "food", "bonus",
                             "wall", "frame", "grid"), start=1):
        curses.init_pair(i, spec[key], bg)
        PAIR[key] = curses.color_pair(i)
    PAIR["head"] |= curses.A_BOLD
    PAIR["food"] |= curses.A_BOLD
    PAIR["bonus"] |= curses.A_BOLD
    PAIR["grid"] |= curses.A_DIM
    curses.init_pair(20, curses.COLOR_BLACK, curses.COLOR_WHITE)
    PAIR["flash"] = curses.color_pair(20) | curses.A_BOLD


def attr(name, fallback=0):
    return PAIR.get(name, fallback)


class KeyReader(object):
    """Assemble escape sequences ourselves so both arrow dialects work, and a
    lone Esc is never swallowed."""

    ARROWS = {ord("A"): "up", ord("B"): "down", ord("C"): "right", ord("D"): "left"}

    def __init__(self):
        self.buf = []
        self.started = 0.0

    def flush_stale(self, now):
        if self.buf and now - self.started > 0.05:
            lone = len(self.buf) == 1
            self.buf = []
            return 27 if lone else None
        return None

    def feed(self, ch):
        if not self.buf:
            if ch == 27:
                self.buf = [ch]
                self.started = time.monotonic()
                return None
            return ch
        if ch > 255:
            self.buf = []
            return ch
        if len(self.buf) == 1:
            if ch in (ord("["), ord("O")):
                self.buf.append(ch)
                return None
            self.buf = []
            return None if ch == 27 else ch
        if self.buf[1] == ord("[") and 0x30 <= ch <= 0x3F:
            self.buf.append(ch)
            return None
        self.buf = []
        return self.ARROWS.get(ch)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

PANEL_W = 14
GAP = 2


class Layout(object):
    def __init__(self, gw, gh):
        self.gw, self.gh = gw, gh
        self.field_w = gw * 2 + 2
        self.field_h = gh + 2
        self.w = self.field_w + GAP + PANEL_W
        self.h = max(self.field_h + 2, 18)
        self.hint_y = self.h - 1
        self.panel_x = self.field_w + GAP


def pick_size(h, w, forced=None):
    if forced:
        return forced
    best = "small"
    for name in SIZE_ORDER:
        L = Layout(*SIZES[name])
        if h >= L.h and w >= L.w:
            best = name
    return best


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

class Glyphs(object):
    def __init__(self, unicode_ok):
        if unicode_ok:
            self.head, self.body, self.tail = "██", "██", "▓▓"
            self.food, self.bonus, self.wall = "◆◆", "★★", "▒▒"
            self.empty = "· "
            self.tl, self.tr, self.bl, self.br = "┌", "┐", "└", "┘"
            self.h, self.v = "─", "│"
        else:
            self.head, self.body, self.tail = "[]", "[]", "()"
            self.food, self.bonus, self.wall = "<>", "**", "##"
            self.empty = ". "
            self.tl = self.tr = self.bl = self.br = "+"
            self.h, self.v = "-", "|"


class Screen(object):
    def __init__(self, stdscr, glyphs, layout):
        self.s = stdscr
        self.g = glyphs
        self.L = layout
        self.keys = KeyReader()
        self.ox = self.oy = 0

    def fits(self):
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

    def frame(self, y, x, w, h, title="", a=None):
        g = self.g
        a = attr("frame") if a is None else a
        top = g.h * (w - 2)
        if title:
            label = " " + title + " "
            top = g.h + label + g.h * (w - 3 - len(label))
        self.put(y, x, g.tl + top + g.tr, a)
        for i in range(1, h - 1):
            self.put(y + i, x, g.v, a)
            self.put(y + i, x + w - 1, g.v, a)
        self.put(y + h - 1, x, g.bl + g.h * (w - 2) + g.br, a)

    def cell(self, gx, gy, text, a=0):
        self.put(2 + gy, 1 + gx * 2, text, a)


def draw(scr, game):
    s, g, L = scr.s, scr.g, scr.L
    now = time.monotonic()
    s.erase()
    if not scr.fits():
        h, w = s.getmaxyx()
        try:
            s.addstr(0, 0, ("Terminal too small: need %dx%d, have %dx%d"
                            % (L.w, L.h, w, h))[:max(0, w - 1)])
            s.addstr(1, 0, "Resize, try --size small, or press q to quit."[:max(0, w - 1)])
        except curses.error:
            pass
        s.refresh()
        return False

    title = "S N A K E"
    scr.put(0, (L.w - len(title)) // 2, title, attr("head", curses.A_BOLD))

    danger = game.state == "over"
    scr.frame(1, 0, L.field_w, L.field_h,
              "WRAP" if game.wrap else "", attr("food") if danger else None)
    for gy in range(L.gh):
        for gx in range(L.gw):
            scr.cell(gx, gy, g.empty, attr("grid"))
    for cellpos in game.walls:
        scr.cell(cellpos[0], cellpos[1], g.wall, attr("wall"))
    body = list(game.snake)
    for i, (x, y) in enumerate(body):
        if i == 0:
            scr.cell(x, y, g.head, attr("head"))
        elif i > len(body) - 3:
            scr.cell(x, y, g.tail, attr("tail"))
        else:
            scr.cell(x, y, g.body, attr("body"))
    if game.food:
        scr.cell(game.food[0], game.food[1], g.food, attr("food"))
    if game.bonus:
        blink = attr("bonus") if int(now * 6) % 2 or game.bonus_left > 12 else attr("flash")
        scr.cell(game.bonus[0], game.bonus[1], g.bonus, blink)

    px = L.panel_x
    lab, val = attr("grid"), curses.A_BOLD
    scr.put(1, px, "SCORE", lab)
    scr.put(2, px, "%12s" % "{:,}".format(game.score), val)
    scr.put(3, px, "BEST", lab)
    scr.put(4, px, "%12s" % "{:,}".format(max(game.high, game.score)), 0)
    scr.put(6, px, "LEVEL %6d" % game.level, val)
    scr.put(7, px, "LENGTH%6d" % len(game.snake), 0)
    scr.put(8, px, "EATEN %6d" % game.eaten, 0)
    secs = int(game.elapsed())
    scr.put(9, px, "TIME %7s" % ("%d:%02d" % (secs // 60, secs % 60)), 0)
    if game.bonus is not None:
        scr.put(11, px, "BONUS %5d" % game.bonus_left, attr("bonus"))
    if game.message and now < game.message_until:
        scr.put(13, px, game.message[:PANEL_W - 1], attr("head", curses.A_BOLD))

    hint = "wasd/arrows turn   p pause   t theme   ? help   q quit"
    scr.put(L.hint_y, max(0, (L.w - len(hint)) // 2), hint, lab)

    if game.state == "ready":
        # a banner, not a box - you want to see your snake before you commit
        msg = "press a direction to set off"
        # clear of the middle row, where the snake is sitting
        scr.put(1 + L.field_h // 2 + 2, max(1, (L.field_w - len(msg)) // 2), msg,
                attr("head", curses.A_BOLD))
    elif game.state == "paused":
        overlay(scr, ["", "P A U S E D", "", "p  resume", "r  restart", "q  quit", ""])
    elif game.state == "over":
        lines = ["", "G A M E   O V E R", "",
                 "SCORE    %s" % "{:,}".format(game.score),
                 "LENGTH   %d" % game.best_length,
                 "EATEN    %d" % game.eaten,
                 "LEVEL    %d" % game.level]
        if game.new_record:
            lines += ["", "*  NEW BEST  *"]
        lines += ["", "r  play again", "q  quit", ""]
        overlay(scr, lines)
    s.refresh()
    return True


def overlay(scr, lines):
    L = scr.L
    w = max(24, max(len(t) for t in lines) + 6)
    x = max(0, (L.field_w - w) // 2)
    h = len(lines) + 2
    y = 1 + max(0, (L.field_h - h) // 2)
    blank = " " * (w - 2)
    scr.frame(y, x, w, h)
    for i, text in enumerate(lines):
        scr.put(y + 1 + i, x + 1, blank)
        a = attr("head", curses.A_BOLD) if i == 1 else 0
        scr.put(y + 1 + i, x + 1 + (w - 2 - len(text)) // 2, text, a)


def draw_help(scr, game):
    s, L = scr.s, scr.L
    s.erase()
    scr.fits()
    scr.put(0, (L.w - 8) // 2, "CONTROLS", attr("head", curses.A_BOLD))
    keys = [
        ("w a s d", "turn"),
        ("arrows", "turn"),
        ("h j k l", "turn"),
        ("p", "pause / resume"),
        ("t", "cycle colour theme"),
        ("r", "restart"),
        ("?", "this help"),
        ("q", "quit"),
    ]
    notes = ["An apple grows you by %d and speeds you up every %d apples."
             % (GROW_PER_FOOD, FOOD_PER_LEVEL),
             "A golden apple appears every %d and is worth more the" % BONUS_EVERY,
             "sooner you reach it.",
             "You cannot turn back into your own neck.",
             "%s" % ("Edges wrap around." if game.wrap
                     else "Hitting an edge ends the run - try --wrap.")]
    bw = min(L.w - 2, 54)
    bx = max(0, (L.w - bw) // 2)
    scr.frame(2, bx, bw, len(keys) + len(notes) + 4)
    for i, (k, d) in enumerate(keys):
        scr.put(3 + i, bx + 3, "%-10s" % k, attr("head", curses.A_BOLD))
        scr.put(3 + i, bx + 15, d, 0)
    for i, note in enumerate(notes):
        scr.put(4 + len(keys) + i, bx + 3, note[:bw - 5], attr("grid"))
    tail = "press any key to return"
    scr.put(len(keys) + len(notes) + 7, max(0, (L.w - len(tail)) // 2), tail,
            attr("grid"))
    s.refresh()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

TURN_KEYS = {
    curses.KEY_UP: "up", curses.KEY_DOWN: "down",
    curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right",
    ord("w"): "up", ord("s"): "down", ord("a"): "left", ord("d"): "right",
    ord("k"): "up", ord("j"): "down", ord("h"): "left", ord("l"): "right",
}


def run(stdscr, args):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    if hasattr(curses, "set_escdelay"):
        curses.set_escdelay(25)
    theme = args.theme
    setup_colors(theme)

    unicode_ok = (not args.ascii) and "utf" in (
        locale.getpreferredencoding(False) or "").lower().replace("-", "")
    h, w = stdscr.getmaxyx()
    size = pick_size(h, w, args.size if args.size != "auto" else None)
    game = Game(size=size, seed=args.seed, wrap=args.wrap, maze=args.maze)
    scr = Screen(stdscr, Glyphs(unicode_ok), Layout(*SIZES[size]))
    helping = False

    while True:
        stale = scr.keys.flush_stale(time.monotonic())
        pending = [stale] if stale is not None else []
        while True:
            raw = stdscr.getch()
            if raw == -1:
                break
            if raw == curses.KEY_RESIZE:
                stdscr.clear()
                continue
            k = scr.keys.feed(raw)
            if k is not None:
                pending.append(k)

        for k in pending:
            if k in ("up", "down", "left", "right"):
                game.turn(DIRECTIONS[k])
                continue
            if k in (ord("q"), ord("Q")):
                return
            if helping:
                helping = False
                stdscr.clear()
                continue
            if k in (ord("?"), ord("/")):
                helping = True
                stdscr.clear()
                if game.state == "play":
                    game.toggle_pause()
            elif k in (ord("r"), ord("R")):
                game.reset()
            elif k in (ord("p"), ord("P")):
                game.toggle_pause()
            elif k in (ord("t"), ord("T")):
                theme = THEME_ORDER[(THEME_ORDER.index(theme) + 1) % len(THEME_ORDER)]
                setup_colors(theme)
                game.say(theme.upper())
                stdscr.clear()
            elif k in TURN_KEYS:
                game.turn(DIRECTIONS[TURN_KEYS[k]])

        if helping:
            draw_help(scr, game)
        else:
            game.update(time.monotonic())
            draw(scr, game)
        time.sleep(0.012)


def build_parser():
    ap = argparse.ArgumentParser(description="Terminal Snake - offline, stdlib only.")
    ap.add_argument("--size", choices=["auto"] + SIZE_ORDER, default="auto",
                    help="board size; auto picks the biggest your window fits")
    ap.add_argument("--wrap", action="store_true",
                    help="edges wrap around instead of killing you")
    ap.add_argument("--maze", type=int, default=0, metavar="PCT",
                    help="fill this %% of the board with blocks to weave around")
    ap.add_argument("--theme", choices=THEME_ORDER, default="classic",
                    help="colour scheme (256-colour terminals)")
    ap.add_argument("--seed", type=int, default=None, help="fixed run, for practice")
    ap.add_argument("--ascii", action="store_true", help="plain ASCII glyphs")
    return ap


def main():
    args = build_parser().parse_args()
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(run, args)
    except KeyboardInterrupt:
        pass
    print("Thanks for playing. Best: %s" % "{:,}".format(load_high_score()))


if __name__ == "__main__":
    main()
