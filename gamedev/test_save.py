"""A saved career must come back the same, and carry on the same."""
import sys, json, random, copy
sys.path.insert(0, "/Users/sparshgoahit/iCanCode/gamedev")
import sim, balance

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

def roundtrip(st):
    return sim.load_state(json.loads(json.dumps(sim.save_state(st))))

print("[1] the save is plain JSON")
st = balance.play(3, 1998, "expert")
blob = json.dumps(sim.save_state(st))
check("it serialises without help", isinstance(blob, str) and len(blob) > 1000)
check("and parses straight back", json.loads(blob)["name"] == st.name)
check("it is small enough to write every month", len(blob) < 400000, len(blob))

print("\n[2] the studio comes back intact")
r = roundtrip(st)
for field in ("name", "t", "money", "fans", "shipped_points", "best_score",
              "total_revenue", "over", "polishing"):
    check("%s survives" % field, getattr(r, field) == getattr(st, field),
          (getattr(st, field), getattr(r, field)))
check("the team comes back", [d.name for d in r.team] == [d.name for d in st.team])
check("with their skills", all(abs(a.skill - b.skill) < 1e-12
                               for a, b in zip(r.team, st.team)))
check("and their salaries", all(a.rate == b.rate for a, b in zip(r.team, st.team)))
check("genre experience is kept", r.genre_games == st.genre_games)
check("the news log is kept", [m for _, m in r.log] == [m for _, m in st.log[-60:]])

print("\n[3] the catalogue and its links")
check("every release is back", len(r.releases) == len(st.releases))
check("scores match", all(abs(a.score - b.score) < 1e-12
                          for a, b in zip(r.releases, st.releases)))
check("units and revenue match",
      all(abs(a.units - b.units) < 1e-9 and abs(a.revenue - b.revenue) < 1e-9
          for a, b in zip(r.releases, st.releases)))
check("franchises are back", len(r.franchises) == len(st.franchises))
check("franchise entries point at real releases",
      all(all(e in r.releases for e in f.entries) for f in r.franchises))
check("entry order is preserved",
      [[r.releases.index(e) for e in f.entries] for f in r.franchises]
      == [[st.releases.index(e) for e in f.entries] for f in st.franchises])
check("topics and genres are the shared objects, not copies",
      all(rel.project.genre is sim.GENRE_BY_NAME[rel.project.genre.name]
          for rel in r.releases))

print("\n[4] a career resumes exactly where it left off")
a = balance.play(11, 1996, "expert")
b = roundtrip(a)
ra = random.Random(999)
rb = random.Random(999)
a2 = balance.resume(a, ra, 2006, "expert")
b2 = balance.resume(b, rb, 2006, "expert")
check("same money ten years later", abs(a2.money - b2.money) < 1e-6,
      (sim.money(a2.money), sim.money(b2.money)))
check("same number of games", len(a2.releases) == len(b2.releases),
      (len(a2.releases), len(b2.releases)))
check("same reviews, one by one",
      all(abs(x.score - y.score) < 1e-12 for x, y in zip(a2.releases, b2.releases)))
check("same team", [d.name for d in a2.team] == [d.name for d in b2.team])
check("same fans", abs(a2.fans - b2.fans) < 1e-9)
print("       resumed career: %s vs %s after ten more years"
      % (sim.money(a2.money), sim.money(b2.money)))

print("\n[5] saving mid-development")
st = sim.Studio(seed=5)
plat = max(st.available_platforms(), key=lambda p: p.install_base(st.t))
topic = st.available_topics()[0]
genre = sim.GENRE_BY_NAME["Action"]
st.start_project("Half Done", topic, genre, plat, sim.SIZES[1])
st.project.target = sim.PERSONA_BY_NAME["Arcade Kid"]
st.project.alloc[0] = [50.0, 30.0, 20.0]
for _ in range(3):
    st.advance()
mid = roundtrip(st)
p, q = st.project, mid.project
check("the project is still in flight", q is not None and q.name == p.name)
check("months done match", q.months_done == p.months_done, (p.months_done, q.months_done))
check("locked sliders survive", q.alloc == p.alloc, (p.alloc, q.alloc))
check("work done survives", all(abs(x - y) < 1e-9
                                for x, y in zip(q.field_work, p.field_work)))
check("design and tech survive", abs(q.design - p.design) < 1e-9 and abs(q.tech - p.tech) < 1e-9)
check("bugs survive", abs(q.bugs - p.bugs) < 1e-9)
check("the target persona survives", q.target is p.target, (p.target, q.target))
check("it is the shared persona object", q.target is sim.PERSONA_BY_NAME["Arcade Kid"])

print("\n[6] saving a sequel in development")
st = balance.play(7, 1994, "expert")
prev = st.sequel_options()[0]
while st.project is not None:
    st.advance()
    if st.project and st.project.needs_alloc() is not None:
        st.project.alloc[st.project.needs_alloc()] = [34.0, 33.0, 33.0]
    if st.project and st.project.done():
        st.release()
st.start_project("Follow Up", prev.project.topic, prev.project.genre,
                 prev.project.platform, sim.SIZES[0], sequel_to=prev)
mid = roundtrip(st)
check("the sequel link survives", mid.project.sequel_to is not None)
check("it points at the right game",
      st.releases.index(st.project.sequel_to) == mid.releases.index(mid.project.sequel_to))
check("and the franchise came with it",
      mid.project.franchise is not None
      and mid.project.franchise.name == st.project.franchise.name)
check("the restored predecessor still scores the sequel the same",
      abs(mid.project.sequel_pressure(mid.t) - st.project.sequel_pressure(st.t)) < 1e-12)

print("\n[7] a finished career saves too")
dead = balance.play(0, 2010, "careless")
d2 = roundtrip(dead)
check("a folded studio round-trips", d2.over == dead.over and d2.over is not None, d2.over)

print("\n" + ("SAVE OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
