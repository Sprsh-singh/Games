#!/usr/bin/env python3
"""
Game Dev Tycoon - a terminal management game.

You start in 1986 with a bedroom, some savings and a home computer.  Consoles
arrive, build an audience and die; you decide what to make, who to make it
for, and where to spend the effort.  Reviews land, copies sell, the industry
raises its expectations, and you either grow or get left behind.

    python3 tycoon.py            play
    python3 tycoon.py --help     options

Python 3 standard library only.  No network, no installation.
"""

import argparse
import curses
import json
import locale
import os
import textwrap
import time

import sim
from sim import money, date_str

MIN_W, MIN_H = 80, 26
SAVE = (os.environ.get("GAMEDEV_SAVE")
        or os.path.join(os.path.expanduser("~"), ".gamedev_tycoon.json"))
MAX_SLOTS = 3


def load_saves():
    try:
        with open(SAVE) as fh:
            slots = json.load(fh).get("slots", [])
    except Exception:
        return []
    return [x for x in slots if isinstance(x, dict) and x.get("version")]


def write_saves(slots):
    """Write through a temporary file so an interrupted save cannot eat a career."""
    try:
        tmp = SAVE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"slots": slots[:MAX_SLOTS]}, fh, separators=(",", ":"))
        os.replace(tmp, SAVE)
    except Exception:
        pass


def slot_summary(d):
    games = len(d.get("releases", []))
    return ("%s%s  -  %d game%s" % (d.get("name", "?"),
                                    " (folded)" if d.get("combo_over") else "",
                                    games, "" if games == 1 else "s"),
            "%s  %s" % (sim.date_str(d.get("t", 0)), money(d.get("money", 0))))

PAIR = {}


def setup_colors():
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    spec = [("accent", curses.COLOR_CYAN), ("good", curses.COLOR_GREEN),
            ("warn", curses.COLOR_YELLOW), ("bad", curses.COLOR_RED),
            ("dim", curses.COLOR_WHITE), ("frame", curses.COLOR_WHITE),
            ("hl", curses.COLOR_MAGENTA)]
    for i, (name, col) in enumerate(spec, start=1):
        curses.init_pair(i, col, bg)
        PAIR[name] = curses.color_pair(i)
    PAIR["dim"] |= curses.A_DIM
    PAIR["accent"] |= curses.A_BOLD
    curses.init_pair(20, curses.COLOR_BLACK, curses.COLOR_CYAN)
    PAIR["sel"] = curses.color_pair(20) | curses.A_BOLD


def A(name, extra=0):
    return PAIR.get(name, 0) | extra


class KeyReader(object):
    """Assemble escape sequences ourselves so both arrow-key dialects work."""

    ARROWS = {ord("A"): curses.KEY_UP, ord("B"): curses.KEY_DOWN,
              ord("C"): curses.KEY_RIGHT, ord("D"): curses.KEY_LEFT}

    def __init__(self):
        self.buf = []
        self.started = 0.0

    def flush_stale(self, now):
        """A lone ESC that never grew into a sequence is a real ESC press.

        Returns the key to deliver, or None. Dropping it here is what made
        Esc dead in every menu.
        """
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


UP = (curses.KEY_UP, ord("k"), ord("w"))
DOWN = (curses.KEY_DOWN, ord("j"), ord("s"))
LEFT = (curses.KEY_LEFT, ord("h"), ord("a"))
RIGHT = (curses.KEY_RIGHT, ord("l"), ord("d"))
PICK = (10, 13, curses.KEY_ENTER, ord(" "))
BACK = (27, ord("q"))


class Screen(object):
    def __init__(self, stdscr):
        self.s = stdscr
        self.keys = KeyReader()
        self.ox = self.oy = 0

    # -- plumbing ----------------------------------------------------------

    def fits(self):
        h, w = self.s.getmaxyx()
        self.ox = max(0, (w - MIN_W) // 2)
        self.oy = max(0, (h - MIN_H) // 2)
        return h >= MIN_H and w >= MIN_W

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
        a = A("frame") if a is None else a
        top = "─" * (w - 2)
        if title:
            lbl = " " + title + " "
            top = "─" + lbl + "─" * (w - 3 - len(lbl))
        self.put(y, x, "┌" + top + "┐", a)
        for i in range(1, h - 1):
            self.put(y + i, x, "│", a)
            self.put(y + i, x + w - 1, "│", a)
            self.put(y + i, x + 1, " " * (w - 2))
        self.put(y + h - 1, x, "└" + "─" * (w - 2) + "┘", a)

    def bar(self, y, x, width, frac, a=0, fill="█", empty="░"):
        frac = max(0.0, min(1.0, frac))
        n = int(round(width * frac))
        self.put(y, x, fill * n, a)
        self.put(y, x + n, empty * (width - n), A("dim"))

    def fresh(self):
        """Force one full repaint - a modal replaces the whole screen, which is
        more than the incremental update can be relied on to cover."""
        self.s.clearok(True)

    def wait_key(self):
        """One normalised keypress, blocking."""
        while True:
            stale = self.keys.flush_stale(time.monotonic())
            if stale is not None:
                return stale
            ch = self.s.getch()
            if ch == -1:
                continue
            if ch == curses.KEY_RESIZE:
                self.s.clear()
                return None
            k = self.keys.feed(ch)
            if k is not None:
                return k

    # -- reusable widgets --------------------------------------------------

    def menu(self, y, x, w, items, title, note="", start=0):
        """A scrolling picker. Returns an index, or None if cancelled."""
        self.fresh()
        idx = start
        rows = min(len(items), MIN_H - y - 6)
        top = 0
        while True:
            self.s.erase()
            if not self.fits():
                self.too_small()
                continue
            self.frame(y - 2, x - 2, w + 4, rows + 6, title)
            if note:
                self.put(y - 1, x, note[:w], A("dim"))
            top = min(max(0, idx - rows + 2), max(0, len(items) - rows))
            top = min(top, idx)
            for i in range(rows):
                n = top + i
                if n >= len(items):
                    break
                label, hint = items[n]
                sel = (n == idx)
                self.put(y + i + 1, x - 1, ("▸ " if sel else "  ") + label[:w - 22].ljust(w - 22),
                         A("sel") if sel else 0)
                self.put(y + i + 1, x + w - 19, hint[:19], A("sel") if sel else A("dim"))
            more = ""
            if len(items) > rows:
                more = "  %d-%d of %d" % (top + 1, min(top + rows, len(items)), len(items))
            self.put(y + rows + 2, x, "↑↓ choose   enter select   esc back" + more, A("dim"))
            self.s.refresh()
            k = self.wait_key()
            if k is None:
                continue
            if k in UP:
                idx = (idx - 1) % len(items)
            elif k in DOWN:
                idx = (idx + 1) % len(items)
            elif k in PICK:
                return idx
            elif k in BACK:
                return None

    def ask_text(self, y, x, w, title, prompt, default=""):
        self.fresh()
        buf = list(default)
        while True:
            self.s.erase()
            if not self.fits():
                self.too_small()
                continue
            self.frame(y, x, w, 7, title)
            self.put(y + 2, x + 2, prompt, A("dim"))
            self.put(y + 3, x + 2, "".join(buf) + "_", A("accent"))
            self.put(y + 5, x + 2, "enter accept    esc cancel", A("dim"))
            self.s.refresh()
            k = self.wait_key()
            if k is None:
                continue
            if k in (10, 13, curses.KEY_ENTER):
                name = "".join(buf).strip()
                if name:
                    return name
            elif k == 27:
                return None
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                if buf:
                    buf.pop()
            elif 32 <= k < 127 and len(buf) < w - 6:
                buf.append(chr(k))

    def too_small(self):
        h, w = self.s.getmaxyx()
        try:
            self.s.addstr(0, 0, "Terminal too small: need %dx%d, have %dx%d"
                          % (MIN_W, MIN_H, w, h)[:max(0, w - 1)])
            self.s.addstr(1, 0, "Resize the window, or press q to quit."[:max(0, w - 1)])
        except curses.error:
            pass
        self.s.refresh()
        if self.s.getch() in (ord("q"), ord("Q")):
            raise KeyboardInterrupt


# ---------------------------------------------------------------------------
# The game
# ---------------------------------------------------------------------------

SHORT_AUDIENCE = {"kids": "kids", "everyone": "all", "mature": "18+"}


def best_genre(persona):
    return max(persona.genre_love.items(), key=lambda kv: kv[1])[0]


def score_attr(x):
    if x >= 8.5:
        return A("good", curses.A_BOLD)
    if x >= 6.5:
        return A("good")
    if x >= 4.5:
        return A("warn")
    return A("bad")


class Tycoon(object):
    def __init__(self, scr, studio, slot=None):
        self.scr = scr
        self.st = studio
        self.slot = slot
        self.flash = ""
        self.flash_until = 0.0
        self._candidates = []

    def say(self, text):
        self.flash = text
        self.flash_until = time.monotonic() + 6

    def checkpoint(self):
        """Persist the career. Called whenever something worth keeping happens."""
        if self.slot is None:
            return
        slots = load_saves()
        while len(slots) <= self.slot:
            slots.append({})
        slots[self.slot] = sim.save_state(self.st)
        write_saves(slots)

    # -- dashboard ---------------------------------------------------------

    def draw(self):
        s, st = self.scr, self.st
        s.s.erase()
        if not s.fits():
            s.too_small()
            return False

        # header - fixed columns, so nothing collides as the numbers grow
        s.frame(0, 0, MIN_W, 3, st.name)
        s.put(1, 2, date_str(st.t), A("accent"))
        s.put(1, 12, money(st.money).rjust(9),
              A("good", curses.A_BOLD) if st.money > 0 else A("bad", curses.A_BOLD))
        s.put(1, 24, "fans " + compact(st.fans), A("dim"))
        s.put(1, 37, "team %d" % st.heads, A("dim"))
        s.put(1, 46, "skill", A("dim"))
        s.bar(1, 52, 10, st.skill, A("good"))
        cost = st.monthly_costs() + (st.dev_cost(st.project.size) if st.project else 0)
        s.put(1, 65, ("burn " + money(cost)).rjust(13), A("dim"))

        self.draw_project(3, 0, 50)
        self.draw_market(3, 52, 28)
        self.draw_news(14, 0, MIN_W)
        self.draw_keys()
        s.s.refresh()
        return True

    def draw_project(self, y, x, w):
        s, st = self.scr, self.st
        p = st.project
        if p is None:
            s.frame(y, x, w, 11, "Studio")
            s.put(y + 2, x + 2, "No project in development.", A("dim"))
            s.put(y + 4, x + 2, "Press  n  to start a new game.", A("accent"))
            if st.releases:
                last = st.releases[-1]
                s.put(y + 6, x + 2, "Last release", A("dim"))
                s.put(y + 7, x + 2, "%-22s %.1f/10" % (last.name[:22], last.score),
                      score_attr(last.score))
                s.put(y + 8, x + 2, "%s copies, %s" % (compact(last.units), money(last.revenue)),
                      A("dim"))
            return
        ready = p.done()
        s.frame(y, x, w, 11, "Development" + ("  -  READY TO SHIP" if ready else ""),
                A("good", curses.A_BOLD) if ready else None)
        s.put(y + 1, x + 2, p.name[:w - 4], A("accent"))
        s.put(y + 2, x + 2, "%s / %s / %s / %s"
              % (p.topic.name, p.genre.name, p.platform.name, p.size.name), A("dim"))
        if ready:
            s.put(y + 4, x + 2, "Development complete.", A("good"))
        else:
            s.put(y + 4, x + 2, "Stage %d of 3   month %d of %d"
                  % (p.current_stage() + 1, p.months_done + 1, p.size.months))
        s.put(y + 5, x + 2, "progress ", A("dim"))
        s.bar(y + 5, x + 11, 26, p.months_done / float(p.size.months), A("accent"))
        s.put(y + 6, x + 2, "design %-6.0f tech %-6.0f" % (p.design, p.tech))
        s.put(y + 7, x + 2, "bugs     ", A("dim"))
        br = p.bug_ratio()
        s.bar(y + 7, x + 11, 16, min(1.0, br * 4),
              A("bad") if br > 0.12 else A("warn") if br > 0.06 else A("good"))
        s.put(y + 7, x + 29, "%.0f%%" % (br * 100), A("dim"))
        if p.hype > 0:
            s.put(y + 8, x + 2, "hype     ", A("dim"))
            s.bar(y + 8, x + 11, 16, p.hype / 1.6, A("hl"))

    def draw_market(self, y, x, w):
        s, st = self.scr, self.st
        s.frame(y, x, w, 11, "Market")
        rows = sorted(st.available_platforms(),
                      key=lambda p: -p.install_base(st.t))[:6]
        for i, p in enumerate(rows):
            note, a = SHORT_AUDIENCE[p.audience], 0
            if p.dying(st.t):
                note, a = "dying", A("bad")
            elif st.t - p.launch < 12:
                note, a = "new", A("good")
            s.put(y + 1 + i, x + 2, "%-11s %4.0fM %-5s"
                  % (p.name[:11], p.install_base(st.t), note), a or 0)
        hot = st.trending(2)
        if hot:
            s.put(y + 8, x + 2, ("hot: " + ", ".join(tp.name for tp, _ in hot))[:w - 4],
                  A("hl"))
        soon = st.announced()
        if soon:
            p = soon[0]
            s.put(y + 9, x + 2, ("soon: %s %s" % (p.name, date_str(p.launch)))[:w - 4],
                  A("accent"))

    def draw_news(self, y, x, w):
        s, st = self.scr, self.st
        s.frame(y, x, w, 9, "News")
        recent = st.log[-7:]
        for i, (t, text) in enumerate(recent):
            s.put(y + 1 + i, x + 2, "%-9s %s" % (date_str(t), text[:w - 14]),
                  0 if i == len(recent) - 1 else A("dim"))

    def draw_keys(self):
        s, st = self.scr, self.st
        p = st.project
        keys = []
        if p is None:
            keys.append("[n] new game")
        elif p.done():
            keys += ["[r] ship it", "[b] fix bugs", "[m] marketing"]
        else:
            keys.append("[m] marketing")
        if st.staff < sim.max_staff(st.t):
            keys.append("[h] hire")
        keys.append("[t] team")
        keys += ["[space] next month", "[c] catalogue", "[?] help", "[q] quit"]
        line = "  ".join(keys)
        s.put(MIN_H - 2, max(0, (MIN_W - len(line)) // 2), line[:MIN_W], A("dim"))
        if self.flash and time.monotonic() < self.flash_until:
            s.put(MIN_H - 3, max(0, (MIN_W - len(self.flash)) // 2), self.flash[:MIN_W],
                  A("accent"))

    # -- starting a project ------------------------------------------------

    def new_project(self):
        s, st = self.scr, self.st
        prev = None
        options = st.sequel_options()
        if options:
            options = options[:8]
            items = [("A brand new game", "no audience yet")]
            for r in options:
                items.append(("%-20s %s" % (r.franchise.next_title()[:20],
                                            sim.date_str(r.released)),
                              "%.1f/10  %s sold" % (r.score, compact(r.units))))
            i = s.menu(6, 12, 54, items, "New game, or a follow-up?",
                       "a known name brings its audience - and its expectations")
            if i is None:
                return
            prev = None if i == 0 else options[i - 1]

        sizes = [sz for sz in sim.SIZES if st.size_available(sz)]
        if not sizes:
            self.say("You need a bigger team for that.")
            return
        items = [("%-8s %2d months" % (sz.name, sz.months),
                  "%s/mo" % money(st.dev_cost(sz))) for sz in sizes]
        locked = [sz for sz in sim.SIZES if not st.size_available(sz)]
        note = "budget %s" % money(st.money)
        if locked:
            note += "   (%s needs %d people)" % (
                locked[0].name, sim.SIZE_HEADS[locked[0].name])
        i = s.menu(6, 12, 52, items, "How big a game?", note)
        if i is None:
            return
        size = sizes[i]

        plats = [p for p in st.available_platforms()
                 if st.money >= p.licence + st.dev_cost(size)]
        if not plats:
            self.say("Not enough cash to licence any platform.")
            return
        plats.sort(key=lambda p: -p.install_base(st.t))
        items = []
        for p in plats:
            tag = "dying" if p.dying(st.t) else p.audience
            items.append(("%-13s %5.0fM  tech %d  %s" %
                          (p.name, p.install_base(st.t), p.tech, tag),
                          money(p.licence)))
        i = s.menu(6, 12, 52, items, "Which platform?",
                   "a big install base sells more; a dying one sells less")
        if i is None:
            return
        platform = plats[i]

        topics = st.available_topics()
        items = []
        for tp in topics:
            word = sim.heat_word(st.heat(tp))
            note = "%s%s" % (SHORT_AUDIENCE[tp.audience],
                             ("  " + word) if word else "")
            if prev is not None and prev.project.topic is tp:
                note = "same as last"
            items.append((tp.name, note))
        start = 0
        if prev is not None and prev.project.topic in topics:
            start = topics.index(prev.project.topic)
        hint = ("changing what the name means costs you" if prev is not None
                else "fashion moves what sells, not what reviews well")
        i = s.menu(6, 12, 52, items, "Pick a topic", hint, start=start)
        if i is None:
            return
        topic = topics[i]

        items = []
        for g in sim.GENRES:
            f = topic.fit(g)
            word = "great fit" if f >= 1.0 else ("poor fit" if f < 0.6 else "ok")
            if prev is not None and prev.project.genre is g:
                word = "same as last"
            items.append(("%-11s  %2.0f%% design" % (g.name, g.design * 100), word))
        gstart = sim.GENRES.index(prev.project.genre) if prev is not None else 0
        i = s.menu(6, 12, 52, items, "Pick a genre for %s" % topic.name,
                   "audience: %s" % topic.audience, start=gstart)
        if i is None:
            return
        genre = sim.GENRES[i]

        segs = sim.segments(platform, st.t)
        items = [("Nobody in particular", "broad, unfocused")]
        for persona, share in segs:
            items.append(("%-18s %2.0f%% of %s" % (persona.name, share * 100,
                                                   platform.name[:9]),
                          "loves " + best_genre(persona)))
        i = s.menu(5, 10, 58, items, "Who is this game for?",
                   "aiming at a segment reaches them harder, everyone else less")
        if i is None:
            return
        target = None if i == 0 else segs[i - 1][0]

        default = (prev.franchise.next_title() if prev is not None
                   else "%s %s" % (topic.name, genre.name))
        name = s.ask_text(8, 16, 48, "Name your game", "Working title:", default)
        if name is None:
            return
        if not st.can_start(size, platform):
            self.say("Cannot afford that project.")
            return
        st.start_project(name, topic, genre, platform, size, sequel_to=prev)
        st.project.target = target
        if target is not None:
            st.say("Aimed at the %s: %s" % (target.name, target.wants))
        self.say("%s is in development." % name)

    # -- the three development stages --------------------------------------

    def set_alloc(self, stage):
        s, st = self.scr, self.st
        p = st.project
        fields = sim.STAGES[stage]
        s.fresh()
        vals = [34, 33, 33]
        known = st.knows(p.genre)
        ideal = p.genre.stage_ideal(stage)
        want = None
        if p.target is not None:
            w = p.target.care[stage * 3:stage * 3 + 3]
            tot = float(sum(w)) or 1.0
            want = [100.0 * x / tot for x in w]
        cur = 0
        while True:
            s.s.erase()
            if not s.fits():
                s.too_small()
                continue
            s.frame(3, 8, 64, 19, "%s  -  stage %d of 3" % (p.name, stage + 1))
            s.put(4, 10, "%s / %s / %s / %s"
                  % (p.topic.name, p.genre.name, p.platform.name, p.size.name), A("dim"))
            s.put(6, 10, "Where should the effort go?", A("accent"))
            for i, f in enumerate(fields):
                y = 8 + i * 4
                sel = (i == cur)
                s.put(y, 10, ("▸ " if sel else "  ") + f.ljust(14),
                      A("sel") if sel else 0)
                s.bar(y, 26, 30, vals[i] / 100.0, A("accent") if sel else A("hl"))
                s.put(y, 58, "%3d%%" % vals[i], A("accent") if sel else 0)
                if known:
                    mark = int(round(30 * ideal[i] / 100.0))
                    s.put(y + 1, 26 + min(29, mark), "▲", A("good"))
                    s.put(y + 1, 58, "%3.0f%%" % ideal[i], A("good"))
                if want is not None:
                    mark = int(round(30 * want[i] / 100.0))
                    s.put(y + 2, 26 + min(29, mark), "◆", A("hl"))
                    s.put(y + 2, 58, "%3.0f%%" % want[i], A("hl"))
            legend = []
            if known:
                legend.append(("▲ critics expect", A("good")))
            if want is not None:
                legend.append(("◆ the %s wants" % p.target.name, A("hl")))
            if legend:
                col = 10
                for text, a in legend:
                    s.put(19, col, text, a)
                    col += len(text) + 4
            else:
                s.put(19, 10, ("ship two %s games and the team will learn its needs"
                               % p.genre.name)[:58], A("dim"))
            s.put(20, 10, "↑↓ pick a field   ←→ shift effort   enter lock it in", A("dim"))
            s.s.refresh()
            k = s.wait_key()
            if k is None:
                continue
            if k in UP:
                cur = (cur - 1) % 3
            elif k in DOWN:
                cur = (cur + 1) % 3
            elif k in LEFT:
                vals = shift(vals, cur, -5)
            elif k in RIGHT:
                vals = shift(vals, cur, +5)
            elif k in PICK or k == 27:
                p.alloc[stage] = [float(v) for v in vals]
                return

    # -- shipping ----------------------------------------------------------

    def ship(self):
        s, st = self.scr, self.st
        p = st.project
        s.fresh()
        before = st.fans
        rel = st.release()
        self.say("%s shipped at %.1f/10." % (rel.name, rel.score))
        total = sum(u for _, u, _ in rel.breakdown) or 1.0
        quote = sim.review_quote(p, rel.score, rel.released)
        while True:
            s.s.erase()
            if not s.fits():
                s.too_small()
                continue
            s.frame(1, 8, 68, 25, "Release")
            s.put(3, 11, rel.name[:44], A("accent"))
            s.put(4, 11, "%s / %s / %s / %s" % (p.topic.name, p.genre.name,
                                                p.platform.name, p.size.name), A("dim"))
            if p.target is not None:
                s.put(5, 11, "aimed at the %s" % p.target.name, A("hl"))
            s.put(7, 11, "REVIEW SCORE   %.1f / 10" % rel.score, score_attr(rel.score))
            for i, line in enumerate(quote):
                s.put(8 + i, 11, line[:56], A("hl") if i == 0 else A("dim"))

            s.put(11, 11, "what the reviewers noticed", A("dim"))
            y = 12
            for label, val in (("slider choices", p.alignment()),
                               ("design/tech balance", p.ratio_fit()),
                               ("topic suits genre", p.topic.fit(p.genre)),
                               ("audience match", p.audience_fit()),
                               ("platform up to it", p.platform_fit()),
                               ("free of bugs", max(0.0, 1.0 - p.bug_ratio() * 1.6))):
                s.put(y, 13, "%-21s" % label, A("dim"))
                s.bar(y, 35, 12, val,
                      A("good") if val > 0.85 else A("warn") if val > 0.6 else A("bad"))
                s.put(y, 49, "%3.0f%%" % (val * 100), A("dim"))
                y += 1

            s.put(19, 11, "who actually bought it", A("dim"))
            y = 20
            for persona, units, match in rel.breakdown[:4]:
                mark = A("hl") if persona is p.target else 0
                s.put(y, 13, "%-18s" % persona.name, mark)
                s.bar(y, 32, 10, units / total, A("accent"))
                s.put(y, 43, "%3.0f%% of sales" % (100.0 * units / total), A("dim"))
                s.put(y, 58, "fit %3.0f%%" % (match * 100),
                      A("good") if match > 0.9 else A("warn") if match > 0.6 else A("bad"))
                y += 1

            s.put(24, 11, "new fans %s        press any key"
                  % compact(max(0.0, st.fans - before)), A("dim"))
            s.s.refresh()
            if s.wait_key() is not None:
                return

    def catalogue(self):
        s, st = self.scr, self.st
        if not st.releases:
            self.say("You have not shipped anything yet.")
            return
        items = []
        for r in reversed(st.releases):
            items.append(("%-18s %-11s %4.1f" % (r.name[:18],
                                                 r.project.platform.name[:11], r.score),
                          "%7s %9s" % (compact(r.units), money(r.revenue))))
        s.menu(5, 10, 58, items, "Your games (%d)" % len(st.releases),
               "lifetime %s from %s copies"
               % (money(sum(r.revenue for r in st.releases)),
                  compact(sum(r.units for r in st.releases))))

    def help_screen(self):
        s = self.scr
        s.fresh()
        body = [
            ("How it works", A("accent")),
            ("", 0),
            ("Every turn is one month. Costs come out whether or not you", 0),
            ("are shipping, so an idle studio bleeds money.", 0),
            ("", 0),
            ("A game is topic + genre + platform + size. Topics suit some", 0),
            ("genres and fight others; the pairing is most of your score.", 0),
            ("", 0),
            ("Fashion moves separately. A hot topic sells more copies but", 0),
            ("earns no extra credit from the critics - and it will cool.", 0),
            ("", 0),
            ("Development runs in three stages. Each one asks where the", 0),
            ("effort goes. Every genre wants a different mix - ship two", 0),
            ("games in a genre and your team learns what it needs.", 0),
            ("", 0),
            ("Consoles build an audience over a few years, then fade.", 0),
            ("Shipping on a dying platform wastes a good game.", 0),
            ("", 0),
            ("The industry expects more every year. Standing still is a", 0),
            ("slow way to go under - hire, and make bigger games.", 0),
            ("", 0),
            ("n new game   space next month   h hire   m marketing", A("dim")),
            ("r ship   b fix bugs   c catalogue   q quit", A("dim")),
            ("", 0),
            ("press any key", A("dim")),
        ]
        while True:
            s.s.erase()
            if not s.fits():
                s.too_small()
                continue
            s.frame(1, 8, 64, 24, "Game Dev Tycoon")
            for i, (text, a) in enumerate(body):
                s.put(3 + i, 11, text, a)
            s.s.refresh()
            if s.wait_key() is not None:
                return

    def game_over(self):
        s, st = self.scr, self.st
        s.fresh()
        best = max(st.releases, key=lambda r: r.score) if st.releases else None
        lines = [
            ("%s  -  %s" % (st.name, date_str(st.t)), A("accent")),
            ("", 0),
            ("The studio is out of money.", A("bad", curses.A_BOLD)),
            ("", 0),
            ("games shipped     %d" % len(st.releases), 0),
            ("copies sold       %s" % compact(sum(r.units for r in st.releases)), 0),
            ("lifetime revenue  %s" % money(st.total_revenue), 0),
            ("best review       %.1f/10 %s" % (
                (best.score, best.name[:20]) if best else (0, "-")), 0),
            ("", 0),
            ("r  start again        q  quit", A("dim")),
        ]
        while True:
            s.s.erase()
            if not s.fits():
                s.too_small()
                continue
            s.frame(6, 14, 52, 14, "Game over")
            for i, (text, a) in enumerate(lines):
                s.put(8 + i, 17, text, a)
            s.s.refresh()
            k = s.wait_key()
            if k in (ord("r"), ord("R")):
                return "restart"
            if k in (ord("q"), ord("Q")):
                self.checkpoint()
                return "quit"

    # -- main loop ---------------------------------------------------------

    def loop(self):
        st = self.st
        while True:
            if st.over:
                what = self.game_over()
                if what == "quit":
                    return
                self.st = st = sim.Studio(name=st.name, seed=None)
                st.say("%s opens for business." % st.name)
                self.checkpoint()
                continue
            p = st.project
            if p is not None and not p.done():
                stage = p.needs_alloc()
                if stage is not None:
                    self.set_alloc(stage)
                    self.checkpoint()
                    self.scr.fresh()
                    continue
            if not self.draw():
                continue
            k = self.scr.wait_key()
            if k is None:
                continue
            if k in (ord("q"), ord("Q")):
                self.checkpoint()
                return
            elif k in (ord("?"), ord("/")):
                self.help_screen()
                self.scr.fresh()
            elif k in (ord("c"), ord("C")):
                self.catalogue()
                self.scr.fresh()
            elif k in (ord("n"), ord("N")) and st.project is None:
                self.new_project()
                self.checkpoint()
                self.scr.fresh()
            elif k in (ord("h"), ord("H")):
                self.hire_screen()
                self.checkpoint()
                self.scr.fresh()
            elif k in (ord("t"), ord("T")):
                self.team_screen()
                self.checkpoint()
                self.scr.fresh()
            elif k in (ord("m"), ord("M")) and st.project is not None:
                self.marketing()
                self.scr.fresh()
            elif k in (ord("b"), ord("B")) and st.project and st.project.done():
                st.polishing = True
                st.advance()
                self.say("Spent a month on bug fixing.")
                self.checkpoint()
            elif k in (ord("r"), ord("R")) and st.project and st.project.done():
                self.ship()
                self.checkpoint()
                self.scr.fresh()
            elif k in PICK:
                st.advance()
                self.checkpoint()

    def hire_screen(self):
        s, st = self.scr, self.st
        if st.staff >= sim.max_staff(st.t):
            self.say("No room for another desk yet - the industry is still small.")
            return
        if st.money < st.hire_cost():
            self.say("Hiring costs %s up front." % money(st.hire_cost()))
            return
        if not self._candidates:
            self._candidates = st.candidates()
        items = []
        for d in self._candidates:
            items.append(("%-18s %-7s %-9s" % (d.name[:18], d.grade(), d.bent()),
                          "%s/mo" % money(d.salary(st.t))))
        i = s.menu(7, 12, 54, items, "Who do you want?",
                   "signing fee %s   designers suit design-led genres"
                   % money(st.hire_cost()))
        if i is None:
            return
        dev = self._candidates[i]
        if st.hire(dev):
            self._candidates = []
            self.say("%s joins the team." % dev.name)

    def team_screen(self):
        s, st = self.scr, self.st
        while True:
            items = []
            for d in st.team:
                role = "you" if d is st.team[0] else d.grade()
                pay = d.salary(st.t)
                items.append(("%-18s %-7s %-9s skill %2.0f%%"
                              % (d.name[:18], role, d.bent(), d.skill * 100),
                              ("%s/mo" % money(pay)) if pay else "-"))
            i = s.menu(6, 12, 56, items, "The team (%d)" % st.heads,
                       "payroll %s/mo   pick someone to let them go"
                       % money(st.payroll()))
            if i is None or i == 0:
                return
            if st.fire(st.team[i]):
                pass

    def marketing(self):
        s, st = self.scr, self.st
        opts = [25000, 75000, 200000]
        items = []
        for amount in opts:
            cost = amount * sim.era(st.t)
            items.append((money(cost), "affordable" if cost <= st.money else "too dear"))
        i = s.menu(8, 18, 42, items, "Marketing push",
                   "hype sells copies; it does not raise your score")
        if i is None:
            return
        cost = opts[i] * sim.era(st.t)
        if st.market(cost):
            self.say("Marketing booked.")
        else:
            self.say("Cannot afford that campaign.")


def shift(vals, i, delta):
    """Move effort onto slider i, taking it from the others."""
    vals = list(vals)
    new = max(0, min(100, vals[i] + delta))
    moved = new - vals[i]
    vals[i] = new
    others = [j for j in range(3) if j != i]
    pool = sum(vals[j] for j in others)
    if pool <= 0:
        for j in others:
            vals[j] = max(0, -moved // 2)
    else:
        left = -moved
        for n, j in enumerate(others):
            take = int(round(left * (vals[j] / float(pool)))) if n == 0 else left
            vals[j] = max(0, vals[j] + take)
            left -= take
    total = sum(vals)
    if total != 100:
        vals[i] += 100 - total
        vals[i] = max(0, min(100, vals[i]))
    return vals


def compact(n):
    n = float(n)
    if n >= 1e6:
        return "%.1fm" % (n / 1e6)
    if n >= 1e3:
        return "%.1fk" % (n / 1e3)
    return "%.0f" % n


def title_screen(scr, args):
    """Returns (studio, slot_index) - a resumed career, or a fresh one."""
    slots = load_saves()
    while True:
        items = []
        for d in slots:
            head, tail = slot_summary(d)
            items.append(("Continue  " + head, tail))
        items.append(("Start a new studio", "1986, a bedroom, $250k"))
        items.append(("Quit", ""))
        i = scr.menu(8, 10, 64, items, "Game Dev Tycoon",
                     "pick up where you left off, or begin again")
        if i is None or i == len(items) - 1:
            return None, None
        if i == len(items) - 2:
            name = scr.ask_text(9, 18, 44, "A new studio",
                                "What are you calling it?", args.name)
            if name is None:
                continue
            st = sim.Studio(name=name, seed=args.seed)
            st.say("%s opens for business." % name)
            slots.append(sim.save_state(st))
            if len(slots) > MAX_SLOTS:
                slots.pop(0)
            write_saves(slots)
            return st, len(slots) - 1
        try:
            return sim.load_state(slots[i]), i
        except Exception:
            slots.pop(i)              # a save we can no longer read
            write_saves(slots)


def run(stdscr, args):
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.timeout(60)
    # ncurses holds a bare ESC for a full second by default, deciding whether
    # an arrow-key sequence follows it - which makes Esc feel dead in menus.
    if hasattr(curses, "set_escdelay"):
        curses.set_escdelay(25)
    setup_colors()
    scr = Screen(stdscr)
    studio, slot = title_screen(scr, args)
    if studio is None:
        return
    Tycoon(scr, studio, slot).loop()


def build_parser():
    ap = argparse.ArgumentParser(description="Game Dev Tycoon - offline, stdlib only.")
    ap.add_argument("--name", default="Basement Games", help="your studio's name")
    ap.add_argument("--seed", type=int, default=None, help="fixed run, for practice")
    return ap


def main():
    args = build_parser().parse_args()
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(run, args)
    except KeyboardInterrupt:
        pass
    print("Thanks for playing.")


if __name__ == "__main__":
    main()
