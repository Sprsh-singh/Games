#!/usr/bin/env python3
"""
Game Dev Tycoon - the simulation.

Pure model: no curses, no printing, no input.  Everything here is
deterministic given a seed, so the balance harness can play thousands of
careers headlessly.  The terminal front end lives in tycoon.py.

Every company, console and franchise below is invented.
"""

import math
import random
import zlib

# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

START_YEAR = 1986
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def ym(year, month):
    """Absolute month index, counting from January of START_YEAR."""
    return (year - START_YEAR) * 12 + (month - 1)


def date_str(t):
    return "%s %d" % (MONTHS[t % 12], START_YEAR + t // 12)


# ---------------------------------------------------------------------------
# Platforms
# ---------------------------------------------------------------------------

class Platform(object):
    """A console, computer or phone you can ship games on.

    `peak` is the install base in millions at the platform's height.  The
    curve ramps up over `ramp` years, holds, then decays over the last two
    years of its life - so shipping late on a dying console is a real mistake.
    """

    def __init__(self, name, maker, launch, end, peak, licence,
                 audience, tech, ramp=3.0):
        self.name = name
        self.maker = maker
        self.launch = launch          # absolute month
        self.end = end                # absolute month, or None for "still alive"
        self.peak = peak
        self.licence = licence
        self.audience = audience      # kids | everyone | mature
        self.tech = tech              # 1-10, how much tech work the market expects
        self.ramp = ramp

    def alive(self, t):
        return t >= self.launch and (self.end is None or t <= self.end)

    def install_base(self, t):
        """Millions of units in players' hands at month t."""
        if not self.alive(t):
            return 0.0
        age = (t - self.launch) / 12.0
        if age < self.ramp:
            frac = (age / self.ramp) ** 1.3
        else:
            frac = 1.0
        if self.end is not None:
            left = (self.end - t) / 12.0
            frac = min(frac, max(0.0, left / 2.0))
        return self.peak * frac

    def dying(self, t):
        return self.end is not None and 0 <= self.end - t <= 18


def _p(name, maker, ly, lm, ey, em, peak, licence, audience, tech, ramp=3.0):
    return Platform(name, maker, ym(ly, lm),
                    None if ey is None else ym(ey, em),
                    peak, licence, audience, tech, ramp)


PLATFORMS = [
    _p("Home PC",     "open",       1982, 1, None, 0,  14,       0, "everyone", 6, 7.0),
    _p("Comet 64",    "Comodo",     1983, 1, 1993, 6,  17,       0, "everyone", 2, 2.5),
    _p("Gamestation", "Nova",       1987, 6, 1995, 1,  31,   45000, "kids",     3),
    _p("Turbo 16",    "Sanko",      1989, 9, 1996, 6,  27,   70000, "everyone", 4),
    _p("Handy Boy",   "Nova",       1990, 4, 1999, 12, 44,   55000, "kids",     2),
    _p("Playbox",     "Sonora",     1995, 3, 2002, 6,  62,  140000, "everyone", 6),
    _p("Nova 64",     "Nova",       1996, 9, 2002, 12, 33,  130000, "kids",     6),
    _p("Vortex",      "Micron",     2001, 3, 2008, 6,  25,  190000, "mature",   7),
    _p("Playbox 2",   "Sonora",     2000, 10, 2011, 6, 150, 240000, "everyone", 7, 4.0),
    _p("Vortex 360",  "Micron",     2005, 11, 2014, 6, 84,  290000, "mature",   8),
    _p("Playbox 3",   "Sonora",     2006, 11, 2015, 6, 87,  310000, "everyone", 8),
    _p("Wave",        "Nova",       2006, 11, 2013, 6, 101, 170000, "kids",     5, 2.0),
    _p("Pocket Glass","Applecore",  2008, 7, None, 0,  260,  25000, "everyone", 5, 5.0),
    _p("Vortex One",  "Micron",     2013, 11, 2023, 6, 58,  340000, "mature",   9),
    _p("Playbox 4",   "Sonora",     2013, 11, 2024, 6, 117, 350000, "everyone", 9),
    _p("Nova Flux",   "Nova",       2017, 3, None, 0,  132, 240000, "everyone", 7),
]

# announced this many months before launch, so you can plan for it
ANNOUNCE_LEAD = 8


# ---------------------------------------------------------------------------
# Genres
# ---------------------------------------------------------------------------

# The nine development fields, three per stage - the same shape the player
# sees as three sliders, three times.
STAGES = (("Engine", "Gameplay", "Story"),
          ("Dialogue", "Level design", "AI"),
          ("World design", "Graphics", "Sound"))


class Genre(object):
    def __init__(self, name, ideal, design, audience):
        self.name = name
        self.ideal = ideal        # 9 weights, 0..1, how much each field matters
        self.design = design      # share of value that is design vs tech
        self.audience = audience  # which crowd it naturally suits

    def stage_ideal(self, s):
        """The three weights for one stage, normalised to percentages."""
        w = self.ideal[s * 3:s * 3 + 3]
        total = float(sum(w)) or 1.0
        return [100.0 * x / total for x in w]


GENRES = [
    #                Eng  Gpl  Sty  Dlg  Lvl   AI  Wld  Gfx  Snd
    Genre("Action",  [0.9, 1.0, 0.4, 0.3, 0.9, 0.7, 0.6, 1.0, 0.7], 0.44, "everyone"),
    Genre("Adventure",[0.4, 0.7, 1.0, 0.9, 0.7, 0.4, 1.0, 0.8, 0.7], 0.62, "everyone"),
    Genre("RPG",     [0.5, 0.8, 1.0, 1.0, 0.8, 0.6, 1.0, 0.7, 0.6], 0.60, "mature"),
    Genre("Simulation",[1.0, 0.9, 0.3, 0.2, 0.7, 1.0, 0.8, 0.7, 0.5], 0.43, "everyone"),
    Genre("Strategy",[0.8, 1.0, 0.4, 0.3, 0.9, 1.0, 0.8, 0.5, 0.4], 0.48, "mature"),
    Genre("Casual",  [0.4, 1.0, 0.3, 0.4, 0.8, 0.3, 0.6, 0.9, 0.8], 0.51, "kids"),
]
GENRE_BY_NAME = {g.name: g for g in GENRES}


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

class Topic(object):
    def __init__(self, name, year, audience, great, bad):
        self.name = name
        self.year = year          # first year it makes sense
        self.audience = audience
        self.great = set(great)   # genres this topic sings in
        self.bad = set(bad)       # genres it fights against

    def fit(self, genre):
        if genre.name in self.great:
            return 1.0
        if genre.name in self.bad:
            return 0.45
        return 0.78


TOPICS = [
    Topic("Space",     1986, "everyone", ["Action", "Strategy", "Simulation"], ["Casual"]),
    Topic("Fantasy",   1986, "everyone", ["RPG", "Adventure"], ["Simulation"]),
    Topic("Racing",    1986, "everyone", ["Action", "Simulation"], ["RPG", "Adventure"]),
    Topic("Sports",    1986, "everyone", ["Simulation", "Action"], ["Adventure", "RPG"]),
    Topic("Military",  1986, "mature",   ["Strategy", "Action"], ["Casual"]),
    Topic("Detective", 1986, "mature",   ["Adventure"], ["Action", "Casual"]),
    Topic("Dungeon",   1986, "everyone", ["RPG", "Strategy"], ["Simulation"]),
    Topic("Pirates",   1986, "everyone", ["Adventure", "Strategy"], ["Simulation"]),
    Topic("Ninja",     1987, "kids",     ["Action"], ["Simulation", "Strategy"]),
    Topic("Horror",    1988, "mature",   ["Adventure", "Action"], ["Casual"]),
    Topic("Airport",   1989, "everyone", ["Simulation"], ["Action", "RPG"]),
    Topic("City",      1989, "everyone", ["Simulation", "Strategy"], ["Action"]),
    Topic("Vampires",  1990, "mature",   ["RPG", "Adventure"], ["Simulation"]),
    Topic("Cooking",   1991, "kids",     ["Casual", "Simulation"], ["Action", "RPG"]),
    Topic("Hospital",  1992, "everyone", ["Simulation"], ["Action", "Casual"]),
    Topic("Music",     1993, "kids",     ["Casual"], ["Strategy", "RPG"]),
    Topic("Superhero", 1994, "kids",     ["Action", "Adventure"], ["Simulation"]),
    Topic("Zombies",   1996, "mature",   ["Action", "Adventure"], ["Casual"]),
    Topic("Farming",   1997, "everyone", ["Simulation", "Casual"], ["Action"]),
    Topic("Startup",   1999, "everyone", ["Simulation", "Strategy"], ["Action"]),
    Topic("Time travel",2001, "everyone",["Adventure", "RPG"], ["Simulation"]),
    Topic("Zoo",       2002, "kids",     ["Simulation", "Casual"], ["Action", "RPG"]),
    Topic("Heist",     2004, "mature",   ["Action", "Strategy"], ["Casual"]),
    Topic("Post-apoc", 2007, "mature",   ["RPG", "Action"], ["Casual"]),
    Topic("Puzzle box",2008, "everyone", ["Casual"], ["Action", "RPG"]),
    Topic("Survival",  2011, "mature",   ["Simulation", "RPG"], ["Casual"]),
]


# ---------------------------------------------------------------------------
# Customer personas
# ---------------------------------------------------------------------------

class Persona(object):
    """A slice of the market with its own taste.

    Critics judge a game against genre convention; customers judge it against
    what they personally wanted.  Those are different targets, which is the
    whole point - a game can be adored and ignored, or panned and bought.
    """

    def __init__(self, name, blurb, wants, genre_love, audience_love, care,
                 hype, review_w, bug_hate, tech_taste, platform_love, era):
        self.name = name
        self.blurb = blurb
        self.wants = wants                 # the one-line product brief
        self.genre_love = genre_love
        self.audience_love = audience_love
        self.care = care                   # 9 field weights
        self.hype = hype                   # how far marketing moves them
        self.review_w = review_w           # exponent on the review score
        self.bug_hate = bug_hate
        self.tech_taste = tech_taste       # the hardware they gravitate to
        self.platform_love = platform_love
        self.era = era                     # (year, relative size) points
        total = float(sum(care)) or 1.0
        self.care_norm = [c / total for c in care]

    def size_at(self, t):
        """This segment's weight in the market at month t."""
        year = START_YEAR + t // 12
        pts = self.era
        if year <= pts[0][0]:
            return pts[0][1]
        if year >= pts[-1][0]:
            return pts[-1][1]
        for (y0, w0), (y1, w1) in zip(pts, pts[1:]):
            if y0 <= year <= y1:
                f = (year - y0) / float(y1 - y0)
                return w0 + (w1 - w0) * f
        return pts[-1][1]

    def pull(self, platform, t):
        """How strongly this segment is present on a given platform."""
        a = self.platform_love.get(platform.audience, 0.5)
        tech = 1.0 - abs(platform.tech - self.tech_taste) / 11.0
        return max(0.02, self.size_at(t) * a * tech)

    def match(self, project):
        """How well the finished game answers this customer, 0..1."""
        mix = project.field_mix()
        overlap = sum(min(m, c) for m, c in zip(mix, self.care_norm))
        m = 0.35 + 0.65 * overlap
        m *= self.genre_love.get(project.genre.name, 0.65)
        m *= self.audience_love.get(project.topic.audience, 0.7)
        m *= max(0.3, 1.0 - project.bug_ratio() * self.bug_hate)
        return max(0.0, min(1.35, m))


#                                     Eng  Gpl  Sty  Dlg  Lvl   AI  Wld  Gfx  Snd
PERSONAS = [
    Persona(
        "Arcade Kid",
        "twelve, plays after school, wants a rush",
        "fast, loud, easy to pick up - depth is wasted on them",
        {"Action": 1.30, "Casual": 1.10, "Adventure": 0.75, "RPG": 0.55,
         "Simulation": 0.50, "Strategy": 0.45},
        {"kids": 1.15, "everyone": 1.0, "mature": 0.7},
        [0.3, 1.0, 0.2, 0.2, 0.9, 0.4, 0.5, 1.0, 0.8],
        hype=1.10, review_w=2.0, bug_hate=1.0, tech_taste=4,
        platform_love={"kids": 1.25, "everyone": 0.85, "mature": 0.45},
        era=[(1986, 1.15), (1995, 1.25), (2005, 0.85), (2015, 0.6), (2026, 0.55)]),
    Persona(
        "Story Seeker",
        "reads the credits, wants to be moved",
        "characters, writing and a world worth staying in",
        {"Adventure": 1.35, "RPG": 1.30, "Action": 0.70, "Strategy": 0.60,
         "Simulation": 0.55, "Casual": 0.45},
        {"mature": 1.1, "everyone": 1.0, "kids": 0.8},
        [0.2, 0.5, 1.0, 1.0, 0.6, 0.3, 1.0, 0.6, 0.7],
        hype=0.45, review_w=3.4, bug_hate=1.0, tech_taste=6,
        platform_love={"everyone": 1.05, "mature": 1.0, "kids": 0.6},
        era=[(1986, 0.7), (1995, 0.9), (2005, 1.05), (2026, 1.1)]),
    Persona(
        "Systems Tinkerer",
        "will read a 40-page manual for fun",
        "deep systems that reward being understood",
        {"Simulation": 1.35, "Strategy": 1.35, "RPG": 0.95, "Adventure": 0.6,
         "Action": 0.5, "Casual": 0.35},
        {"everyone": 1.05, "mature": 1.0, "kids": 0.7},
        [1.0, 0.9, 0.3, 0.2, 0.8, 1.0, 0.8, 0.3, 0.3],
        hype=0.25, review_w=3.8, bug_hate=1.5, tech_taste=6,
        platform_love={"everyone": 1.15, "mature": 0.9, "kids": 0.4},
        era=[(1986, 0.9), (1995, 0.95), (2005, 0.85), (2026, 0.8)]),
    Persona(
        "Tech Showoff",
        "bought the console on day one to prove it was worth it",
        "something that makes the new hardware look expensive",
        {"Action": 1.25, "Simulation": 1.0, "RPG": 0.9, "Strategy": 0.8,
         "Adventure": 0.8, "Casual": 0.4},
        {"mature": 1.1, "everyone": 1.0, "kids": 0.7},
        [1.0, 0.7, 0.3, 0.3, 0.7, 0.9, 0.8, 1.0, 0.8],
        hype=0.95, review_w=2.6, bug_hate=1.2, tech_taste=9,
        platform_love={"mature": 1.2, "everyone": 1.0, "kids": 0.5},
        era=[(1986, 0.45), (1995, 0.8), (2005, 1.1), (2026, 1.0)]),
    Persona(
        "Family Buyer",
        "buying it for someone else and reading the box carefully",
        "safe, cheerful, easy for anyone in the house to start",
        {"Casual": 1.35, "Simulation": 1.10, "Adventure": 0.9, "Action": 0.7,
         "Strategy": 0.6, "RPG": 0.55},
        {"kids": 1.25, "everyone": 1.05, "mature": 0.3},
        [0.3, 1.0, 0.5, 0.5, 0.7, 0.3, 0.7, 0.9, 0.9],
        hype=1.20, review_w=1.9, bug_hate=1.8, tech_taste=5,
        platform_love={"kids": 1.3, "everyone": 1.0, "mature": 0.3},
        era=[(1986, 0.35), (1995, 0.6), (2005, 1.1), (2015, 1.2), (2026, 1.15)]),
    Persona(
        "Commuter",
        "plays in four-minute gaps and will not read a tutorial",
        "instant to start, fine to stop, no manual anywhere",
        {"Casual": 1.40, "Action": 0.85, "Simulation": 0.7, "Adventure": 0.55,
         "Strategy": 0.5, "RPG": 0.4},
        {"everyone": 1.1, "kids": 1.0, "mature": 0.65},
        [0.2, 1.0, 0.2, 0.2, 0.8, 0.2, 0.4, 0.8, 0.9],
        hype=1.35, review_w=1.6, bug_hate=1.1, tech_taste=4,
        platform_love={"everyone": 1.2, "kids": 1.0, "mature": 0.5},
        era=[(1986, 0.15), (2000, 0.3), (2008, 1.0), (2015, 1.5), (2026, 1.6)]),
]
PERSONA_BY_NAME = {p.name: p for p in PERSONAS}

# Naming a target persona is a positioning decision: the game is pitched at
# them, so it reaches them harder and everyone else a little less.
FOCUS_BONUS = 1.55
FOCUS_PENALTY = 0.92


def segments(platform, t):
    """Each persona's share of one platform's audience, summing to 1."""
    pulls = [(p, p.pull(platform, t)) for p in PERSONAS]
    total = sum(w for _, w in pulls) or 1.0
    return [(p, w / total) for p, w in pulls]


TOPIC_INDEX = {}          # filled in below, once TOPICS exists


# ---------------------------------------------------------------------------
# Fashion
# ---------------------------------------------------------------------------

HEAT_FAST = 41.0          # months in the quicker cycle
HEAT_SLOW = 97.0          # and the slower one underneath it
HEAT_SWING = 0.30
HEAT_DRIFT = 0.18


def heat_at(phase, t):
    """A topic's popularity: two slow waves, so fashion drifts rather than jumps.

    Deliberately demand-only - critics judge the craft, the public follows
    fashion. Mixing the two would count the same thing twice.
    """
    return (1.0
            + HEAT_SWING * math.sin(t / HEAT_FAST + phase)
            + HEAT_DRIFT * math.sin(t / HEAT_SLOW + phase * 1.7))


def heat_word(h):
    if h >= 1.28:
        return "red hot"
    if h >= 1.10:
        return "in fashion"
    if h <= 0.72:
        return "nobody wants"
    if h <= 0.90:
        return "going cold"
    return ""


AUDIENCE_FIT = {
    ("kids", "kids"): 1.0, ("kids", "everyone"): 0.85, ("kids", "mature"): 0.55,
    ("everyone", "kids"): 0.85, ("everyone", "everyone"): 1.0, ("everyone", "mature"): 0.85,
    ("mature", "kids"): 0.5, ("mature", "everyone"): 0.85, ("mature", "mature"): 1.0,
}

TOPIC_INDEX.update((x.name, i) for i, x in enumerate(TOPICS))


# ---------------------------------------------------------------------------
# Project sizes
# ---------------------------------------------------------------------------

class Size(object):
    def __init__(self, name, months, cost_per_month, points, price, weight):
        self.name = name
        self.months = months
        self.cost = cost_per_month
        self.points = points          # raw work produced per month, per head
        self.price = price            # what a copy sells for
        self.weight = weight          # how much of the market notices it


SIZES = [
    Size("Small",  3, 9000,   34, 12, 0.55),
    Size("Medium", 6, 22000,  46, 22, 1.00),
    Size("Large",  11, 48000, 58, 38, 1.75),
]
SIZE_BY_NAME = {s.name: s for s in SIZES}


# ---------------------------------------------------------------------------
# How each development field splits into design and tech
# ---------------------------------------------------------------------------

FIELD_DESIGN = (0.00,   # Engine
                0.60,   # Gameplay
                1.00,   # Story
                1.00,   # Dialogue
                0.60,   # Level design
                0.20,   # AI
                0.90,   # World design
                0.10,   # Graphics
                0.30)   # Sound

SIZE_TECH_NEED = {"Small": 3, "Medium": 6, "Large": 8}


def team_output(heads):
    """Two developers are not twice one: coordination eats the difference."""
    return heads ** 0.72

# what the market expects a game of each size to be worth, growing every year
EXPECTATION_GROWTH = 1.055


def era_adjusted(points, t):
    """Work measured in constant terms, so eras can be compared."""
    return points / (EXPECTATION_GROWTH ** (t / 12.0))


def expected_points(size, t):
    years = t / 12.0
    return size.points * size.months * (EXPECTATION_GROWTH ** years)


class Franchise(object):
    """A name the audience already knows, and the expectations that come with it."""

    def __init__(self, name):
        self.name = name
        self.entries = []          # Releases, oldest first

    @property
    def last(self):
        return self.entries[-1] if self.entries else None

    def size(self):
        return len(self.entries)

    def next_title(self):
        return "%s %d" % (self.name, self.size() + 1)


SEQUEL_MIN_GAP = 12       # months before a follow-up stops looking rushed
SEQUEL_FORGET = 84        # months before the audience has moved on


def awareness(prev, t, entries):
    """How much of the last game's audience turns up for the next one."""
    gap = t - prev.released
    if gap >= SEQUEL_FORGET:
        recency = 0.0
    elif gap <= 36:
        recency = 1.0
    else:
        recency = 1.0 - (gap - 36) / float(SEQUEL_FORGET - 36)
    carry = max(0.0, min(1.2, (prev.score - 4.0) / 5.0))
    reach = min(0.80, (prev.units / 80000.0) ** 0.55)
    boost = 1.0 + reach * recency * carry
    boost *= 0.93 ** max(0, entries - 1)            # the well runs dry
    if gap < SEQUEL_MIN_GAP:
        boost *= 0.72 + 0.28 * (gap / float(SEQUEL_MIN_GAP))
    return max(0.6, boost)


class Project(object):
    """A game under development."""

    def __init__(self, name, topic, genre, platform, size, started):
        self.name = name
        self.topic = topic
        self.genre = genre
        self.platform = platform
        self.size = size
        self.started = started
        self.alloc = [None, None, None]     # three percentages per stage
        self.field_work = [0.0] * 9
        self.design = 0.0
        self.tech = 0.0
        self.bugs = 0.0
        self.months_done = 0
        self.hype = 0.0
        self.marketing = 0
        self.polish_months = 0
        self.target = None            # the persona this game is aimed at
        self.franchise = None
        self.sequel_to = None         # the Release this follows, if any

    # -- stage plumbing ----------------------------------------------------

    def stage_at(self, month_index):
        """Which of the three stages month `month_index` belongs to."""
        return min(2, int(month_index * 3 / self.size.months))

    def current_stage(self):
        return self.stage_at(self.months_done)

    def needs_alloc(self):
        """The stage about to start that has no slider settings yet."""
        s = self.current_stage()
        return s if self.alloc[s] is None else None

    def done(self):
        return self.months_done >= self.size.months

    # -- one month of work -------------------------------------------------

    def work_month(self, heads, skill, rng):
        s = self.current_stage()
        alloc = self.alloc[s] or [34, 33, 33]
        output = self.size.points * team_output(heads) * (0.92 + 0.38 * skill)
        for i, share in enumerate(alloc):
            f = s * 3 + i
            amount = output * share / 100.0
            self.field_work[f] += amount
            self.design += amount * FIELD_DESIGN[f]
            self.tech += amount * (1.0 - FIELD_DESIGN[f])
        # sloppier teams leave more behind; bigger games hide more of it
        self.bugs += output * 0.055 * (1.25 - 0.5 * skill) * rng.uniform(0.75, 1.25)
        self.months_done += 1

    def polish(self, heads, skill, rng):
        """An extra month spent only on squashing bugs."""
        removed = self.bugs * (0.45 + 0.12 * heads + 0.2 * skill)
        self.bugs = max(0.0, self.bugs - removed)
        self.polish_months += 1

    # -- how good is it ----------------------------------------------------

    def field_mix(self):
        """Where the effort actually went, as a distribution over the nine fields."""
        total = sum(self.field_work) or 1.0
        return [w / total for w in self.field_work]

    def alignment(self):
        """How closely the sliders matched what the genre wants, 0..1."""
        total = 0.0
        for s in range(3):
            ideal = self.genre.stage_ideal(s)
            got = self.alloc[s] or [34, 33, 33]
            drift = sum(abs(a - b) for a, b in zip(got, ideal))
            total += max(0.0, 1.0 - drift / 150.0)
        return total / 3.0

    def ratio_fit(self):
        """Design-versus-tech balance against what the genre calls for."""
        pts = self.design + self.tech
        if pts <= 0:
            return 0.0
        got = self.design / pts
        return max(0.45, 1.0 - abs(got - self.genre.design) * 1.3)

    def platform_fit(self):
        need = SIZE_TECH_NEED[self.size.name]
        return max(0.6, min(1.0, 1.0 - 0.09 * max(0, need - self.platform.tech)))

    def audience_fit(self):
        return AUDIENCE_FIT[(self.topic.audience, self.platform.audience)]

    def bug_ratio(self):
        pts = self.design + self.tech
        return 0.0 if pts <= 0 else self.bugs / pts

    def sequel_pressure(self, t):
        """What the critics make of a follow-up: progress, or a retread.

        A sequel is held against its predecessor. Putting in less than last
        time reads as lazy; changing what the name means reads as confused.
        """
        prev = self.sequel_to
        if prev is None:
            return 1.0
        before = prev.project
        was = era_adjusted(before.design + before.tech, prev.released)
        now = era_adjusted(self.design + self.tech, t)
        step = now / was if was > 0 else 1.0
        if step >= 1.15:
            mult = 1.06                       # a real step up
        elif step >= 0.98:
            mult = 1.0
        else:
            mult = max(0.62, 0.62 + 0.38 * (step / 0.98))
        if before.genre is not self.genre:
            mult *= 0.84                      # the name no longer means anything
        if before.topic is not self.topic:
            mult *= 0.93
        if t - prev.released < SEQUEL_MIN_GAP:
            mult *= 0.82                      # annualised: more of the same
        return mult

    def team_fit(self, lean):
        """Designers make design-led games better; engineers, tech-led ones."""
        leaning = 0.5 + lean * 0.35
        return max(0.82, min(1.05, 1.05 - abs(leaning - self.genre.design) * 0.6))

    def quality(self, t, skill, lean=0.0):
        pts = self.design + self.tech
        base = pts / expected_points(self.size, t)
        q = (base
             * self.alignment()
             * self.ratio_fit()
             * self.topic.fit(self.genre)
             * self.audience_fit()
             * self.platform_fit()
             * (1.0 + 0.25 * skill))
        q *= max(0.35, 1.0 - self.bug_ratio() * 1.6)
        q *= self.sequel_pressure(t)
        q *= self.team_fit(lean)
        return q

    def review(self, t, skill, rng, lean=0.0):
        q = self.quality(t, skill, lean)
        score = 11.0 * q / (q + 0.55)
        score += rng.uniform(-0.45, 0.45)
        return max(1.0, min(10.0, score))


# ---------------------------------------------------------------------------
# The people
# ---------------------------------------------------------------------------

FIRST_NAMES = ("Priya", "Marek", "Dorotea", "Sam", "Ines", "Kwame", "Yuki",
               "Bo", "Anneke", "Rafi", "Noor", "Tomas", "Ada", "Ola", "Kiran",
               "Sasha", "Lena", "Hugo", "Mina", "Owen", "Tariq", "Fay")
LAST_NAMES = ("Okafor", "Lindqvist", "Ferrari", "Nakamura", "Duarte", "Novak",
              "Bakker", "Haddad", "Sinclair", "Petrov", "Alvarez", "Osei",
              "Kaur", "Moreau", "Rossi", "Yilmaz", "Ellis", "Sorokin")


class Dev(object):
    """Someone on the team. People are not interchangeable headcount."""

    def __init__(self, name, lean, skill, rate):
        self.name = name
        self.lean = lean        # -1 pure engineer .. +1 pure designer
        self.skill = skill      # 0..1
        self.rate = rate        # salary in 1986 money, scaled by era
        self.months = 0

    def salary(self, t):
        return self.rate * era(t)

    def bent(self):
        if self.lean > 0.35:
            return "design"
        if self.lean < -0.35:
            return "tech"
        return "all-round"

    def grade(self):
        return ("junior" if self.skill < 0.35 else
                "solid" if self.skill < 0.55 else
                "strong" if self.skill < 0.75 else "star")


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

COST_GROWTH = 1.05           # making games gets dearer every year
BASE_RATE = 0.00195          # share of an install base an average game reaches
RENT = 2200
SALARY = 5200
HIRE_FEE = 9000
MAX_STAFF = 5

# The industry grows up around you: in the eighties nobody is running a
# five-person studio out of a bedroom, and nobody is shipping an eleven-month
# epic on their own.
STAFF_UNLOCK = ((1986, 0), (1990, 1), (1994, 2), (1999, 3), (2005, 4), (2011, 5))
SIZE_HEADS = {"Small": 1, "Medium": 2, "Large": 3}


def max_staff(t):
    year = START_YEAR + t // 12
    allowed = 0
    for y, n in STAFF_UNLOCK:
        if year >= y:
            allowed = n
    return allowed
SALES_TAIL = 10              # months a game keeps selling


def era(t):
    return COST_GROWTH ** (t / 12.0)


class Release(object):
    """A shipped game, still earning."""

    def __init__(self, project, score, t, potential):
        self.project = project
        self.name = project.name
        self.score = score
        self.released = t
        self.potential = potential
        self.units = 0.0
        self.revenue = 0.0
        self.months_out = 0
        self.breakdown = []           # (persona, projected units, match)
        self.franchise = None

    def month_share(self):
        """Fraction of lifetime sales landing in this month."""
        i = self.months_out
        if i >= SALES_TAIL:
            return 0.0
        return 0.40 * (0.62 ** i)

    def selling(self, t):
        return self.months_out < SALES_TAIL and self.project.platform.alive(t)


class Studio(object):
    def __init__(self, name="Basement Games", seed=None, start=None):
        self.rng = random.Random(seed)
        self.name = name
        self.t = ym(START_YEAR, 1) if start is None else start
        self.money = 250000.0
        self.fans = 0.0
        self.team = [Dev("You", 0.0, 0.30, 0.0)]
        self.shipped_points = 0.0
        self.project = None
        self.polishing = False
        self.releases = []
        self.log = []
        self.over = None               # reason, once the studio folds
        self.seen_platforms = set()
        self.genre_games = {}          # genre name -> games shipped in it
        self.franchises = []
        self.milestones = []           # (month, what happened)
        self.marks = set()             # landmark keys already announced
        self.trend_phase = [self.rng.uniform(0.0, 2.0 * math.pi)
                            for _ in range(len(TOPICS))]
        self.best_score = 0.0
        self.total_revenue = 0.0

    # -- derived -----------------------------------------------------------

    @property
    def heads(self):
        return len(self.team)

    @property
    def staff(self):
        return len(self.team) - 1

    @property
    def skill(self):
        return sum(d.skill for d in self.team) / float(len(self.team))

    def team_lean(self):
        return sum(d.lean for d in self.team) / float(len(self.team))

    def reputation(self):
        return min(1.0, self.shipped_points / 12000.0)

    def payroll(self):
        return sum(d.salary(self.t) for d in self.team)

    def monthly_costs(self):
        return RENT * era(self.t) + self.payroll()

    def dev_cost(self, size):
        return size.cost * era(self.t)

    def hire_cost(self):
        return HIRE_FEE * era(self.t)

    def year(self):
        return START_YEAR + self.t // 12

    def heat(self, topic, t=None):
        """How fashionable a topic is right now, roughly 0.5 to 1.5."""
        i = TOPIC_INDEX.get(topic.name, 0)
        return heat_at(self.trend_phase[i], self.t if t is None else t)

    def trending(self, n=2):
        """The topics the public has decided it wants, hottest first."""
        live = [(self.heat(x), x) for x in self.available_topics()]
        live.sort(key=lambda p: -p[0])
        return [(x, h) for h, x in live[:n]]

    def knows(self, genre):
        """Two games in a genre and the team knows what it needs."""
        return self.genre_games.get(genre.name, 0) >= 2

    # -- the world ---------------------------------------------------------

    def available_platforms(self):
        return [p for p in PLATFORMS if p.alive(self.t)]

    def announced(self):
        return [p for p in PLATFORMS
                if not p.alive(self.t) and 0 < p.launch - self.t <= ANNOUNCE_LEAD]

    def available_topics(self):
        return [x for x in TOPICS if x.year <= self.year()]

    def say(self, text):
        self.log.append((self.t, text))
        del self.log[:-200]

    # -- actions -----------------------------------------------------------

    def sequel_options(self):
        """Releases worth building on: the newest entry of each franchise."""
        out = []
        for f in self.franchises:
            if f.last is not None:
                out.append(f.last)
        out.sort(key=lambda r: -r.units)
        return out

    def size_available(self, size):
        return self.heads >= SIZE_HEADS[size.name]

    def can_start(self, size, platform):
        return (self.project is None and self.over is None
                and self.size_available(size)
                and self.money >= platform.licence + self.dev_cost(size))

    def start_project(self, name, topic, genre, platform, size, sequel_to=None):
        self.money -= platform.licence
        self.project = Project(name, topic, genre, platform, size, self.t)
        if sequel_to is not None:
            self.project.sequel_to = sequel_to
            self.project.franchise = sequel_to.franchise
        if platform.licence:
            self.say("Licensed %s for %s." % (platform.name, money(platform.licence)))
        self.say("Started %s - a %s %s game for %s."
                 % (name, topic.name, genre.name, platform.name))
        return self.project

    def candidates(self, n=3):
        """Who is willing to come and work for you right now."""
        rng = self.rng
        out = []
        for _ in range(n):
            skill = min(0.92, max(0.15, rng.gauss(0.32 + 0.34 * self.reputation(), 0.14)))
            lean = round(rng.uniform(-1.0, 1.0), 2)
            rate = SALARY * (0.55 + 1.45 * skill) * rng.uniform(0.9, 1.15)
            name = "%s %s" % (rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES))
            out.append(Dev(name, lean, skill, rate))
        return out

    def can_hire(self):
        return self.staff < max_staff(self.t) and self.money >= self.hire_cost()

    def hire(self, dev):
        if not self.can_hire():
            return False
        self.money -= self.hire_cost()
        self.team.append(dev)
        self.say("%s joins the team (%s, %s)." % (dev.name, dev.grade(), dev.bent()))
        return True

    def fire(self, dev):
        if dev not in self.team or dev is self.team[0]:
            return False
        pay = dev.salary(self.t) * 2
        self.money -= pay
        self.team.remove(dev)
        self.say("%s leaves. Severance %s." % (dev.name, money(pay)))
        return True

    def market(self, amount):
        p = self.project
        if p is None or amount <= 0 or amount > self.money:
            return False
        self.money -= amount
        p.marketing += amount
        budget = amount / (12000.0 * era(self.t))
        p.hype = min(1.6, p.hype + 0.42 * math.sqrt(budget))
        self.say("Spent %s on marketing for %s." % (money(amount), p.name))
        return True

    # -- release -----------------------------------------------------------

    def release(self):
        p = self.project
        score = p.review(self.t, self.skill, self.rng, self.team_lean())
        pot, breakdown = self.demand(p, score, self.t)
        pot *= self.rng.uniform(0.55, 1.65)      # hits and flops
        rel = Release(p, score, self.t, pot)
        rel.breakdown = breakdown
        self.releases.append(rel)
        self.shipped_points += p.design + p.tech
        self.genre_games[p.genre.name] = self.genre_games.get(p.genre.name, 0) + 1
        if p.franchise is None:
            p.franchise = Franchise(p.name)
            self.franchises.append(p.franchise)
        rel.franchise = p.franchise
        p.franchise.entries.append(rel)
        if p.sequel_to is not None:
            step = score - p.sequel_to.score
            if step < -0.8:
                self.fans *= 0.88          # a bad sequel costs you believers
                self.say("%s disappoints the people who liked the last one."
                         % p.name)
            elif step > 0.8:
                self.say("%s is a step up on the last one." % p.name)
        self.best_score = max(self.best_score, score)
        gained = pot * (score - 5.5) / 900.0
        self.fans = max(0.0, self.fans + gained)
        self.say("%s ships. Reviews: %.1f/10." % (p.name, score))
        self.project = None
        self.polishing = False
        return rel

    def demand(self, p, score, t):
        """Add up what each slice of the market wants, not one blended average.

        Reviews are the critics' verdict; this is the customers'. A game can
        be adored by reviewers and wanted by nobody.
        """
        base = p.platform.install_base(t) * 1e6 * self.heat(p.topic, t)
        fanbase = 1.0 + self.fans / 150000.0
        if p.sequel_to is not None:
            fanbase *= awareness(p.sequel_to, t, p.franchise.size() if p.franchise else 1)
        rows = []
        total = 0.0
        for persona, share in segments(p.platform, t):
            match = persona.match(p)
            appeal = (score / 10.0) ** persona.review_w
            units = (BASE_RATE * base * share * p.size.weight
                     * (match ** 1.6) * appeal
                     * (1.0 + p.hype * persona.hype)
                     * fanbase)
            if p.target is persona:
                units *= FOCUS_BONUS
            elif p.target is not None:
                units *= FOCUS_PENALTY
            rows.append((persona, units, match))
            total += units
        rows.sort(key=lambda r: -r[1])
        return total, rows

    def _mark(self, key, text):
        if key in self.marks:
            return
        self.marks.add(key)
        self.milestones.append((self.t, text))
        self.say(text)

    def _check_landmarks(self):
        """Career landmarks, announced in the news rather than on a screen of
        their own - the reward is seeing it happen, not another menu."""
        if not self.releases:
            return
        best = max(self.releases, key=lambda r: r.score)
        if best.score >= 8.0:
            self._mark("acclaim", "%s is being called one of the year's best."
                       % best.name)
        if best.score >= 9.0:
            self._mark("masterpiece", "%s reviews at %.1f. People are calling it a "
                       "landmark." % (best.name, best.score))
        top = max(self.releases, key=lambda r: r.units)
        if top.units >= 100000:
            self._mark("hit", "%s passes a hundred thousand copies." % top.name)
        if top.units >= 1000000:
            self._mark("million", "%s passes a million copies sold." % top.name)
        for n in (10, 25, 50):
            if len(self.releases) >= n:
                self._mark("catalogue%d" % n,
                           "That is %d games shipped." % n)
        for amount, label in ((1e6, "a million"), (1e7, "ten million"),
                              (1e8, "a hundred million")):
            if self.total_revenue >= amount:
                self._mark("revenue%d" % amount,
                           "The studio has earned %s dollars, all told." % label)
        if self.t % 12 == 11:                      # December
            year_start = self.t - 11
            of_year = [r for r in self.releases if year_start <= r.released <= self.t]
            if of_year:
                champ = max(of_year, key=lambda r: r.score)
                if champ.score >= 8.5:
                    self._mark("goty%d" % (START_YEAR + self.t // 12),
                               "%s takes Game of the Year." % champ.name)

    # -- the tick ----------------------------------------------------------

    def advance(self):
        """One month. Returns the list of things that happened."""
        if self.over:
            return []
        before = len(self.log)
        self.t += 1

        for p in PLATFORMS:
            if p.launch == self.t:
                self.say("%s launches the %s." % (p.maker, p.name))
            elif p.end is not None and p.end == self.t:
                self.say("The %s is discontinued." % p.name)
            elif p.launch - self.t == ANNOUNCE_LEAD:
                self.say("%s announces the %s, out %s."
                         % (p.maker, p.name, date_str(p.launch)))

        self.money -= self.monthly_costs()

        if self.project is not None:
            self.money -= self.dev_cost(self.project.size)
            if self.polishing:
                self.project.polish(self.heads, self.skill, self.rng)
                self.polishing = False
            elif not self.project.done():
                self.project.work_month(self.heads, self.skill, self.rng)
                for d in self.team:
                    d.months += 1
                    d.skill = min(0.95, d.skill + 0.0016)

        earned = 0.0
        for r in self.releases:
            if not r.selling(self.t):
                continue
            units = r.potential * r.month_share()
            r.units += units
            cash = units * r.project.size.price
            r.revenue += cash
            earned += cash
            r.months_out += 1
        if earned:
            self.money += earned
            self.total_revenue += earned

        self.fans *= 0.995
        self._check_landmarks()

        if self.money < 0:
            self.over = "bankrupt"
            self.say("Out of money. %s closes its doors." % self.name)
        return self.log[before:]


def money(x):
    """Compact currency, the way a tycoon HUD wants it."""
    x = float(x)
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e9:
        return "%s$%.2fb" % (sign, x / 1e9)
    if x >= 1e6:
        return "%s$%.2fm" % (sign, x / 1e6)
    if x >= 1e3:
        return "%s$%.0fk" % (sign, x / 1e3)
    return "%s$%.0f" % (sign, x)


# ---------------------------------------------------------------------------
# What the reviewers say
# ---------------------------------------------------------------------------

def stable_seed(*parts):
    """A seed that does not move between runs, unlike hash() on strings."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))


OPENERS = (
    (9.0, ("A genuine landmark.", "The one everything else gets measured against.",
           "Hard to fault and harder to put down.")),
    (8.0, ("Confident, polished, and clearly made by people who cared.",
           "Does what it sets out to do, and then some.",
           "One of the year's best.")),
    (6.5, ("Solid, if not surprising.", "Well made, if a little safe.",
           "Does the job without ever quite thrilling.")),
    (5.0, ("Competent, and not much more.", "There is a good game in here somewhere.",
           "Passes the time.")),
    (3.5, ("Rough going.", "Ambition well ahead of execution.",
           "Hard to recommend at this price.")),
    (0.0, ("A misfire.", "Nothing here works.", "Best forgotten.")),
)

PRAISE = {
    "sliders": ("the priorities are spot on", "every hour went somewhere useful",
                "it knows exactly what kind of game it is"),
    "balance": ("the craft and the ideas pull together",
                "technically sound and thoughtfully designed"),
    "topic": ("the subject and the genre were made for each other",
              "an obvious pairing nobody had done this well"),
    "audience": ("pitched perfectly at the people who own this machine",),
    "platform": ("it wrings a lot out of the hardware",
                 "you would not think the machine had this in it"),
    "bugs": ("it is remarkably clean", "we did not hit a single problem"),
}

GRIPE = {
    "sliders": ("the effort went to the wrong places",
                "it never decides what it wants to be"),
    "balance": ("all technology and no idea, or the reverse",
                "the pieces do not add up"),
    "topic": ("the subject fights the genre at every turn",
              "this premise does not belong in this kind of game"),
    "audience": ("nobody who owns this machine asked for this",
                 "aimed at an audience that is not here"),
    "platform": ("the hardware is plainly not up to it",
                 "it is asking too much of the machine"),
    "bugs": ("it is held together with tape", "we lost progress twice to crashes"),
}


def review_quote(p, score, t):
    """Two lines of verdict, derived from the same numbers the score came from."""
    rng = random.Random(stable_seed(p.name, round(score, 3), t))
    factors = [
        ("sliders", p.alignment()),
        ("balance", p.ratio_fit()),
        ("topic", p.topic.fit(p.genre)),
        ("audience", p.audience_fit()),
        ("platform", p.platform_fit()),
        ("bugs", max(0.0, 1.0 - p.bug_ratio() * 1.6)),
    ]
    best = max(factors, key=lambda f: f[1])
    worst = min(factors, key=lambda f: f[1])
    for bar, lines in OPENERS:
        if score >= bar:
            opener = rng.choice(lines)
            break
    tail = []
    if best[1] >= 0.92:
        tail.append(rng.choice(PRAISE[best[0]]))
    if worst[1] <= 0.80:
        tail.append(rng.choice(GRIPE[worst[0]]))
    if not tail:
        tail.append("it lands somewhere in the middle of everything")
    second = tail[0]
    if len(tail) > 1:
        second = "%s, but %s" % (tail[0], tail[1])
    return opener, second[0].upper() + second[1:] + "."


# ---------------------------------------------------------------------------
# Landmarks
# ---------------------------------------------------------------------------

def _fmt_units(n):
    return ("%.1fm" % (n / 1e6)) if n >= 1e6 else ("%.0fk" % (n / 1e3))


# ---------------------------------------------------------------------------
# Saving a career
# ---------------------------------------------------------------------------

SAVE_VERSION = 1


def _dump_dev(d):
    return {"name": d.name, "lean": d.lean, "skill": d.skill,
            "rate": d.rate, "months": d.months}


def _load_dev(d):
    dev = Dev(d["name"], d["lean"], d["skill"], d["rate"])
    dev.months = d["months"]
    return dev


def _dump_project(p, fr_index, rel_index, archived=False):
    """A project in flight needs its whole working state.

    One already shipped is only ever read for six things - what it was, how
    much went into it, and what it followed - so the rest is not written.
    That is most of a save file once a catalogue gets long.
    """
    if p is None:
        return None
    d = {
        "name": p.name, "topic": p.topic.name, "genre": p.genre.name,
        "platform": p.platform.name, "size": p.size.name, "started": p.started,
        "design": p.design, "tech": p.tech,
        "franchise": fr_index.get(id(p.franchise)),
        "sequel_to": rel_index.get(id(p.sequel_to)),
    }
    if not archived:
        d.update({
            "alloc": p.alloc, "field_work": p.field_work, "bugs": p.bugs,
            "months_done": p.months_done, "hype": p.hype,
            "marketing": p.marketing, "polish_months": p.polish_months,
            "target": p.target.name if p.target else None,
        })
    return d


def _load_project(d, franchises):
    if d is None:
        return None
    topic = next(x for x in TOPICS if x.name == d["topic"])
    platform = next(x for x in PLATFORMS if x.name == d["platform"])
    p = Project(d["name"], topic, GENRE_BY_NAME[d["genre"]], platform,
                SIZE_BY_NAME[d["size"]], d["started"])
    p.design, p.tech = d["design"], d["tech"]
    p.alloc = d.get("alloc", [None, None, None])
    p.field_work = d.get("field_work", [0.0] * 9)
    p.bugs = d.get("bugs", 0.0)
    p.months_done = d.get("months_done", p.size.months)
    p.hype = d.get("hype", 0.0)
    p.marketing = d.get("marketing", 0)
    p.polish_months = d.get("polish_months", 0)
    p.target = PERSONA_BY_NAME.get(d.get("target")) if d.get("target") else None
    if d["franchise"] is not None:
        p.franchise = franchises[d["franchise"]]
    return p


def save_state(st):
    """The whole career as plain data - no object graph, only indices."""
    rel_index = dict((id(r), i) for i, r in enumerate(st.releases))
    fr_index = dict((id(f), i) for i, f in enumerate(st.franchises))
    rng = st.rng.getstate()
    return {
        "version": SAVE_VERSION,
        "name": st.name, "t": st.t, "money": st.money, "fans": st.fans,
        "team": [_dump_dev(d) for d in st.team],
        "shipped_points": st.shipped_points,
        "genre_games": st.genre_games,
        "milestones": [[t, text] for t, text in st.milestones],
        "marks": sorted(st.marks),
        "trend_phase": st.trend_phase,
        "best_score": st.best_score,
        "total_revenue": st.total_revenue,
        "combo_over": st.over,
        "polishing": st.polishing,
        "log": [[t, text] for t, text in st.log[-60:]],
        "rng": [rng[0], list(rng[1]), rng[2]],
        "franchises": [{"name": f.name,
                        "entries": [rel_index[id(r)] for r in f.entries]}
                       for f in st.franchises],
        "releases": [{"project": _dump_project(r.project, fr_index, rel_index, True),
                      "score": r.score, "released": r.released,
                      "potential": r.potential, "units": r.units,
                      "revenue": r.revenue, "months_out": r.months_out,
                      "franchise": fr_index.get(id(r.franchise))}
                     for r in st.releases],
        "project": _dump_project(st.project, fr_index, rel_index),
    }


def load_state(d):
    st = Studio(name=d["name"])
    rng = d["rng"]
    st.rng.setstate((rng[0], tuple(rng[1]), rng[2]))
    st.t = d["t"]
    st.money = d["money"]
    st.fans = d["fans"]
    st.team = [_load_dev(x) for x in d["team"]]
    st.shipped_points = d["shipped_points"]
    st.genre_games = dict(d["genre_games"])
    st.milestones = [(t, text) for t, text in d.get("milestones", [])]
    st.marks = set(d.get("marks", []))
    if d.get("trend_phase"):
        st.trend_phase = list(d["trend_phase"])
    st.best_score = d["best_score"]
    st.total_revenue = d["total_revenue"]
    st.over = d["combo_over"]
    st.polishing = d["polishing"]
    st.log = [(t, text) for t, text in d["log"]]

    st.franchises = [Franchise(f["name"]) for f in d["franchises"]]
    st.releases = []
    for rd in d["releases"]:
        p = _load_project(rd["project"], st.franchises)
        r = Release(p, rd["score"], rd["released"], rd["potential"])
        r.units, r.revenue = rd["units"], rd["revenue"]
        r.months_out = rd["months_out"]
        if rd["franchise"] is not None:
            r.franchise = st.franchises[rd["franchise"]]
        st.releases.append(r)
    # second pass: the links that point backwards into the list
    for rd, r in zip(d["releases"], st.releases):
        idx = rd["project"].get("sequel_to") if rd["project"] else None
        if idx is not None:
            r.project.sequel_to = st.releases[idx]
    for f, fd in zip(st.franchises, d["franchises"]):
        f.entries = [st.releases[i] for i in fd["entries"]]
    st.project = _load_project(d["project"], st.franchises)
    if st.project is not None and d["project"].get("sequel_to") is not None:
        st.project.sequel_to = st.releases[d["project"]["sequel_to"]]
    return st
