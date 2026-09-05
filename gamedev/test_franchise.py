"""Sequels: a known name brings its audience, and its expectations."""
import sys, random
sys.path.insert(0, "/Users/sparshgoahit/iCanCode/gamedev")
import sim

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

PLAT = [p for p in sim.PLATFORMS if p.name == "Playbox 2"][0]
TOPIC = [x for x in sim.TOPICS if x.name == "Fantasy"][0]
RPG = sim.GENRE_BY_NAME["RPG"]
ACTION = sim.GENRE_BY_NAME["Action"]

def studio_at(year):
    st = sim.Studio(seed=4)
    st.t = sim.ym(year, 6)
    st.money = 5e6
    for _ in range(2):
        st.team.append(sim.Dev("Colleague", 0.0, 0.5, sim.SALARY))
    return st

def build(st, genre, size_i, heads, months=None, sequel_to=None, topic=TOPIC):
    p = sim.Project("G", topic, genre, PLAT, sim.SIZES[size_i], st.t)
    p.sequel_to = sequel_to
    p.franchise = sequel_to.franchise if sequel_to else None
    for i in range(3):
        p.alloc[i] = genre.stage_ideal(i)
    rng = random.Random(1)
    for _ in range(months or p.size.months):
        p.work_month(heads, .6, rng)
    st.project = p
    return p

def ship(st, p):
    st.project = p
    return st.release()

print("[1] a first game creates a franchise")
st = studio_at(2002)
p1 = build(st, RPG, 1, 3)
r1 = ship(st, p1)
check("the release names a franchise", r1.franchise is not None and r1.franchise.name == "G")
check("it is the first entry", r1.franchise.size() == 1)
check("and it shows up as sequel material", st.sequel_options() == [r1], st.sequel_options())

print("\n[2] a good sequel outsells a standalone")
def sequel_run(gap_months, size_i, genre, heads=3, topic=TOPIC):
    st = studio_at(2002)
    p1 = build(st, RPG, 1, 3)
    r1 = ship(st, p1)
    for _ in range(24):
        st.advance()                       # let the first game sell through
    st.t = r1.released + gap_months
    p2 = build(st, genre, size_i, heads, sequel_to=r1, topic=topic)
    score = p2.review(st.t, .6, random.Random(2))
    total, _ = st.demand(p2, score, st.t)
    return r1, p2, score, total

def standalone(gap_months, size_i, genre, heads=3):
    st = studio_at(2002)
    st.t = sim.ym(2002, 6) + gap_months
    p = build(st, genre, size_i, heads)
    score = p.review(st.t, .6, random.Random(2))
    total, _ = st.demand(p, score, st.t)
    return score, total

def paired(gap_months, size_i, genre, heads=3, topic=TOPIC):
    """Identical game at the same moment, once as a sequel and once as new IP."""
    st = studio_at(2002)
    r1 = ship(st, build(st, RPG, 1, 3))
    for _ in range(24):
        st.advance()
    st.t = r1.released + gap_months
    out = []
    for prev in (r1, None):
        p = build(st, genre, size_i, heads, sequel_to=prev, topic=topic)
        sc = p.review(st.t, .6, random.Random(2))
        tot, _ = st.demand(p, sc, st.t)
        out.append((sc, tot, p))
    return r1, out[0], out[1]

r1, (sc_seq, tot_seq, p2), (sc_new, tot_new, _) = paired(30, 1, RPG)
check("the sequel reaches more people", tot_seq > tot_new * 1.05,
      (int(tot_new), int(tot_seq)))
check("with a comparable review", abs(sc_seq - sc_new) < 0.6, (sc_new, sc_seq))
print("       same game as new IP %d copies -> as a sequel %d copies"
      % (tot_new, tot_seq))

print("\n[3] the audience forgets")
_, (_, soon, _), _ = paired(30, 1, RPG)
_, (_, late, _), _ = paired(90, 1, RPG)
check("a sequel nine years later has lost the room", late < soon * 0.85,
      (int(soon), int(late)))

print("\n[4] critics hold a sequel to the last one")
_, (sc_big, tot_big, _), _ = paired(30, 1, RPG)     # same size as predecessor
_, (sc_small, _, _), _ = paired(30, 0, RPG)        # a smaller follow-up
check("a smaller follow-up reviews worse", sc_small < sc_big - 0.5, (sc_big, sc_small))
_, (sc_switch, _, _), _ = paired(30, 1, ACTION)
check("switching genre under the same name is punished", sc_switch < sc_big,
      (sc_big, sc_switch))
_, (sc_rush, tot_rush, _), _ = paired(6, 1, RPG)
check("rushing it out reviews worse", sc_rush < sc_big, (sc_big, sc_rush))
check("and reaches fewer people", tot_rush < tot_big, (int(tot_big), int(tot_rush)))

print("\n[5] milking a franchise stops working")
st = studio_at(2002)
prev = ship(st, build(st, RPG, 1, 3))
totals = []
for n in range(5):
    for _ in range(18):
        st.advance()
    p = build(st, RPG, 1, 3, sequel_to=prev)
    st.project = p
    score = p.review(st.t, .6, random.Random(2))
    total, _ = st.demand(p, score, st.t)
    totals.append(total)
    prev = ship(st, p)
check("each further entry pulls a smaller crowd than the reach it inherits",
      totals[-1] < totals[0], [int(x) for x in totals])
check("the franchise keeps a running record", prev.franchise.size() == 6,
      prev.franchise.size())
print("       entries 2..6 reached %s" % ", ".join(str(int(x)) for x in totals))

print("\n[6] a bad sequel costs you fans")
st = studio_at(2002)
r = ship(st, build(st, RPG, 1, 4))
st.fans = 40000.0
before = st.fans
p = build(st, RPG, 0, 1, sequel_to=r)       # much weaker follow-up
p.field_work = [w * 0.3 for w in p.field_work]
st.project = p
r2 = st.release()
check("a clear step down loses believers", st.fans < before, (before, st.fans))
check("and the log says so", any("disappoint" in m for _, m in st.log[-4:]),
      [m for _, m in st.log[-3:]])

print("\n" + ("FRANCHISES OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
