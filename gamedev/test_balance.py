"""The economy has a shape. Lock it in so later tuning cannot quietly wreck it."""
import sys, random, statistics as st
sys.path.insert(0, "/Users/sparshgoahit/iCanCode/gamedev")
import sim
from balance import play

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

N = 40
careless = [play(i, 2010, "careless") for i in range(N)]
decent   = [play(i, 2010, "decent")   for i in range(N)]
expert   = [play(i, 2010, "expert")   for i in range(N)]

def broke(rs): return sum(1 for s in rs if s.over) / float(len(rs))
def cash(rs):  return st.median([s.money for s in rs])
def scores(rs): return [r.score for s in rs for r in s.releases]

print("[1] playing badly has consequences")
check("careless studios nearly always fold", broke(careless) > 0.8, broke(careless))
check("careless games review poorly", st.median(scores(careless)) < 5.0, st.median(scores(careless)))

print("\n[2] playing well is rewarded")
check("expert studios survive", broke(expert) < 0.1, broke(expert))
check("expert ends up wealthy", cash(expert) > 2e7, sim.money(cash(expert)))
check("but not instantly - the garage phase is real",
      st.median([s.money for s in [play(i, 1990, "expert") for i in range(20)]]) < 3e6,
      sim.money(st.median([s.money for s in [play(i, 1990, "expert") for i in range(20)]])))

print("\n[3] standing still is not a strategy")
mid = [play(i, 1996, "decent") for i in range(20)]
check("a solo studio can live through the nineties", broke(mid) < 0.25, broke(mid))
check("but the industry outgrows it by 2010", broke(decent) > 0.7, broke(decent))

print("\n[4] scores behave")
sc = scores(expert)
check("every score is inside 1-10", all(1.0 <= x <= 10.0 for x in sc), (min(sc), max(sc)))
check("good play lands in the sevens, not the tens", 6.0 < st.median(sc) < 8.0, st.median(sc))
check("a perfect ten is rare", sum(1 for x in sc if x >= 9.5) / float(len(sc)) < 0.05,
      sum(1 for x in sc if x >= 9.5) / float(len(sc)))
check("expert beats decent on review scores",
      st.median(sc) > st.median(scores(decent)), (st.median(sc), st.median(scores(decent))))

print("\n[5] the world runs its course")
s = play(0, 2010, "expert")
check("consoles came and went", any("discontinued" in m for _, m in s.log))
check("new hardware was announced", any("announces" in m for _, m in s.log))
check("the studio shipped a catalogue", len(s.releases) > 15, len(s.releases))
check("no money appeared from nowhere",
      s.money <= 250000 + s.total_revenue, (s.money, s.total_revenue))

print("\n[6] determinism")
a, b = play(7, 2000, "expert"), play(7, 2000, "expert")
check("same seed, same career", (a.money, len(a.releases)) == (b.money, len(b.releases)))
c = play(8, 2000, "expert")
check("different seed, different career", (a.money, a.best_score) != (c.money, c.best_score))

print("\n" + ("BALANCE OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
