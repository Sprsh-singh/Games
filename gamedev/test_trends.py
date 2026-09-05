"""Fashion: it moves what sells, and nothing else."""
import sys, json, math, random
sys.path.insert(0, "/Users/sparshgoahit/iCanCode/gamedev")
import sim, balance

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

print("[1] heat stays in a sane band")
st = sim.Studio(seed=3)
lo, hi = 9, -9
for t in range(0, 12 * 45):
    for topic in sim.TOPICS:
        h = st.heat(topic, t)
        lo, hi = min(lo, h), max(hi, h)
check("never negative", lo > 0.3, lo)
check("never runaway", hi < 1.7, hi)
check("and it does swing", hi - lo > 0.6, (lo, hi))
print("       across 45 years and %d topics: %.2f to %.2f" % (len(sim.TOPICS), lo, hi))

print("\n[2] fashion drifts, it does not jump")
worst = 0.0
for topic in sim.TOPICS:
    for t in range(0, 12 * 40):
        worst = max(worst, abs(st.heat(topic, t + 1) - st.heat(topic, t)))
check("no month changes it by more than a few points", worst < 0.02, worst)
check("but a long project can outlive the fashion it started in",
      max(abs(st.heat(sim.TOPICS[0], t + 11) - st.heat(sim.TOPICS[0], t))
          for t in range(0, 400)) > 0.10)

print("\n[3] every career gets its own fashions")
a, b = sim.Studio(seed=3), sim.Studio(seed=9)
same = sum(1 for x in sim.TOPICS if abs(a.heat(x, 100) - b.heat(x, 100)) < 0.01)
check("two careers do not share a cycle", same < 3, same)
c = sim.Studio(seed=3)
check("the same seed does", all(abs(a.heat(x, 100) - c.heat(x, 100)) < 1e-12
                                for x in sim.TOPICS))

print("\n[4] fashion moves sales, never the review")
plat = [x for x in sim.PLATFORMS if x.name == "Playbox 2"][0]
genre = sim.GENRE_BY_NAME["Action"]
topic = [x for x in sim.TOPICS if x.name == "Space"][0]
t = sim.ym(2004, 6)

def build_once():
    p = sim.Project("X", topic, genre, plat, sim.SIZES[1], t)
    for i in range(3):
        p.alloc[i] = genre.stage_ideal(i)
    rng = random.Random(1)
    for _ in range(p.size.months):
        p.work_month(3, .5, rng)
    return p

# identical game, identical month - only the fashion differs
i = sim.TOPIC_INDEX[topic.name]
runs = []
for want_hot in (True, False):
    st2 = sim.Studio(seed=3)
    st2.t = t
    # solve the phase that puts this topic at the top or bottom of its cycle
    best, bestv = 0.0, (-9 if want_hot else 9)
    for k in range(360):
        ph = k * math.pi / 180.0
        v = sim.heat_at(ph, t)
        if (v > bestv) if want_hot else (v < bestv):
            best, bestv = ph, v
    st2.trend_phase[i] = best
    proj = build_once()
    score = proj.review(t, .5, random.Random(2))
    total, _ = st2.demand(proj, score, t)
    runs.append((score, total, st2.heat(topic, t)))

hot, cold = runs[0], runs[1]
check("a hot topic outsells a cold one", hot[1] > cold[1] * 1.8,
      (int(cold[1]), int(hot[1])))
check("the review is untouched by fashion", abs(hot[0] - cold[0]) < 1e-12,
      (cold[0], hot[0]))
print("       same game, same month: heat %.2f -> %d copies, heat %.2f -> %d copies"
      % (hot[2], hot[1], cold[2], cold[1]))
print("       both reviewed %.1f" % hot[0])

print("\n[5] it survives a save")
s = balance.play(4, 2000, "expert")
r = sim.load_state(json.loads(json.dumps(sim.save_state(s))))
check("phases round-trip", all(abs(x - y) < 1e-12
                               for x, y in zip(s.trend_phase, r.trend_phase)))
check("so the same topics are hot", [x.name for x, _ in s.trending(4)]
      == [x.name for x, _ in r.trending(4)])

print("\n[6] the player can see it coming")
st = sim.Studio(seed=3); st.t = sim.ym(1995, 1)
hot = st.trending(3)
check("something is always trending", len(hot) == 3)
check("and it is labelled", any(sim.heat_word(h) for _, h in hot),
      [(x.name, round(h, 2), sim.heat_word(h)) for x, h in hot])
check("words match the numbers",
      sim.heat_word(1.35) == "red hot" and sim.heat_word(1.0) == ""
      and sim.heat_word(0.6) == "nobody wants")

print("\n" + ("TRENDS OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
