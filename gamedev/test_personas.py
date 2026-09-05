"""The persona market: shape, drift, and whether targeting is a real decision."""
import sys, random
sys.path.insert(0, "/Users/sparshgoahit/iCanCode/gamedev")
import sim

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

print("[1] the personas are well formed")
check("every persona rates every genre",
      all(set(p.genre_love) == {g.name for g in sim.GENRES} for p in sim.PERSONAS),
      [p.name for p in sim.PERSONAS if set(p.genre_love) != {g.name for g in sim.GENRES}])
check("every persona cares about all nine fields",
      all(len(p.care) == 9 for p in sim.PERSONAS))
check("care weights normalise to 1",
      all(abs(sum(p.care_norm) - 1.0) < 1e-9 for p in sim.PERSONAS))
check("every persona rates every topic audience",
      all(set(p.audience_love) == {"kids", "everyone", "mature"} for p in sim.PERSONAS))
check("each has a one-line brief", all(p.wants and p.blurb for p in sim.PERSONAS))

print("\n[2] segments always partition the market")
bad = []
for year in range(1986, 2027, 2):
    t = sim.ym(year, 6)
    for plat in sim.PLATFORMS:
        if not plat.alive(t):
            continue
        shares = sim.segments(plat, t)
        if abs(sum(w for _, w in shares) - 1.0) > 1e-9:
            bad.append((year, plat.name))
        if any(w < 0 for _, w in shares):
            bad.append((year, plat.name, "negative"))
check("shares sum to 1 on every live platform, every era", not bad, bad[:3])

print("\n[3] the market moves under you")
def share_of(name, year, plat_name):
    t = sim.ym(year, 6)
    plat = [p for p in sim.PLATFORMS if p.name == plat_name][0]
    return dict((p.name, w) for p, w in sim.segments(plat, t))[name]
kid_88 = share_of("Arcade Kid", 1988, "Comet 64")
kid_12 = share_of("Arcade Kid", 2012, "Pocket Glass")
com_88 = share_of("Commuter", 1988, "Comet 64")
com_12 = share_of("Commuter", 2012, "Pocket Glass")
check("the Arcade Kid shrinks over the decades", kid_12 < kid_88, (kid_88, kid_12))
check("the Commuter barely exists in 1988", com_88 < 0.10, com_88)
check("and dominates mobile by 2012", com_12 > 0.20, com_12)
check("kids consoles skew to kids",
      share_of("Arcade Kid", 1993, "Handy Boy") > share_of("Story Seeker", 1993, "Handy Boy"))

print("\n[4] building for a customer is a real decision")
st = sim.Studio(seed=1)
def build(year, plat_name, topic_name, genre_name, target, size_i=0, heads=2):
    t = sim.ym(year, 6); st.t = t
    plat = [p for p in sim.PLATFORMS if p.name == plat_name][0]
    topic = [x for x in sim.TOPICS if x.name == topic_name][0]
    g = sim.GENRE_BY_NAME[genre_name]
    p = sim.Project("x", topic, g, plat, sim.SIZES[size_i], t)
    p.target = target
    for i in range(3):
        if target is None:
            p.alloc[i] = g.stage_ideal(i)
        else:
            w = target.care[i * 3:i * 3 + 3]; tot = float(sum(w)) or 1.0
            p.alloc[i] = [100.0 * x / tot for x in w]
    rng = random.Random(1)
    for _ in range(p.size.months):
        p.work_month(heads, .5, rng)
    score = p.review(t, .5, random.Random(2))
    total, rows = st.demand(p, score, t)
    return score, total, rows

kid = sim.PERSONA_BY_NAME["Arcade Kid"]
tink = sim.PERSONA_BY_NAME["Systems Tinkerer"]
generic = build(1993, "Handy Boy", "Ninja", "Action", None)
aimed = build(1993, "Handy Boy", "Ninja", "Action", kid)
wrong = build(1993, "Handy Boy", "Ninja", "Action", tink)
check("aiming at the right mass audience sells more", aimed[1] > generic[1] * 1.05,
      (int(generic[1]), int(aimed[1])))
check("even though the critics like it less", aimed[0] < generic[0], (generic[0], aimed[0]))
check("aiming at the wrong audience is punished", wrong[1] < generic[1] * 0.7,
      (int(generic[1]), int(wrong[1])))
check("the targeted segment leads the sales", aimed[2][0][0] is kid, aimed[2][0][0].name)

seeker = sim.PERSONA_BY_NAME["Story Seeker"]
g2 = build(2003, "Playbox 2", "Fantasy", "RPG", None, 1, 3)
a2 = build(2003, "Playbox 2", "Fantasy", "RPG", seeker, 1, 3)
check("review-driven segments punish ignoring the critics", a2[1] < g2[1],
      (int(g2[1]), int(a2[1])))

print("\n[5] the breakdown is honest")
score, total, rows = build(2003, "Playbox 2", "Fantasy", "RPG", None, 1, 3)
check("segment units add up to the total", abs(sum(u for _, u, _ in rows) - total) < 1e-6)
check("every segment is represented", len(rows) == len(sim.PERSONAS))
check("it is sorted by who bought most",
      all(rows[i][1] >= rows[i + 1][1] for i in range(len(rows) - 1)))
check("match never goes negative", all(m >= 0 for _, _, m in rows))

print("\n" + ("PERSONAS OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
