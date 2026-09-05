"""Play thousands of careers headlessly and see whether the economy holds up."""
import random, statistics as st, sys
sys.path.insert(0, "/Users/sparshgoahit/iCanCode/gamedev")
import sim


def pick_platform(s, rng, smart=True):
    live = [p for p in s.available_platforms()]
    if not live:
        return None
    if not smart:
        return rng.choice(live)
    ok = [p for p in live if not p.dying(s.t)] or live
    return max(ok, key=lambda p: p.install_base(s.t))


def pick_pair(s, platform, rng, smart=True):
    topics = s.available_topics()
    if not smart:
        return rng.choice(topics), rng.choice(sim.GENRES)
    best, bestv = None, -1
    for tp in topics:
        for g in sim.GENRES:
            v = tp.fit(g) * sim.AUDIENCE_FIT[(tp.audience, platform.audience)]
            if v > bestv:
                best, bestv = (tp, g), v
    return best


def pick_size(s, rng, smart=True):
    if not smart:
        return rng.choice(sim.SIZES)
    for size in reversed(sim.SIZES):
        if s.size_available(size) and s.money > (s.dev_cost(size) * size.months) * 1.6:
            return size
    return sim.SIZES[0]


def play(seed, end_year, style):
    s = sim.Studio(seed=seed)
    rng = random.Random(seed * 7919 + 13)
    return resume(s, rng, end_year, style)


def resume(s, rng, end_year, style):
    """Drive an existing studio forward - used by play() and by the save tests."""
    smart = style != "careless"
    end = sim.ym(end_year, 12)
    while s.t < end and not s.over:
        if s.project is None:
            plat = pick_platform(s, rng, smart)
            if plat is not None:
                size = pick_size(s, rng, smart)
                if s.can_start(size, plat):
                    tp, g = pick_pair(s, plat, rng, smart)
                    s.start_project("G%d" % (len(s.releases) + 1), tp, g, plat, size)
        p = s.project
        if p is not None:
            st_i = p.needs_alloc()
            if st_i is not None:
                if smart:
                    p.alloc[st_i] = p.genre.stage_ideal(st_i)
                else:
                    a = [rng.randint(5, 60) for _ in range(3)]
                    tot = float(sum(a))
                    p.alloc[st_i] = [100.0 * x / tot for x in a]
            if p.done():
                if style == "expert" and p.bug_ratio() > 0.08 and p.polish_months < 2:
                    s.polishing = True
                else:
                    if style == "expert" and p.marketing == 0 and s.money > 120000:
                        s.market(min(s.money * 0.12, 90000 * sim.era(s.t)))
                    s.release()
        if style == "expert" and s.project is None and s.can_hire() \
                and s.money > s.hire_cost() * 14:
            best = max(s.candidates(), key=lambda d: d.skill)
            s.hire(best)
        s.advance()
    return s


def report(style, end_year=2010, n=120):
    outs = [play(i, end_year, style) for i in range(n)]
    broke = sum(1 for s in outs if s.over)
    money = sorted(s.money for s in outs)
    scores = [r.score for s in outs for r in s.releases]
    games = [len(s.releases) for s in outs]
    print("  %-9s bankrupt %3.0f%%   median cash %-9s  p10 %-9s p90 %-9s  "
          "games %2.0f  score med %.1f  best %.1f"
          % (style, 100.0 * broke / n, sim.money(st.median(money)),
             sim.money(money[n // 10]), sim.money(money[-n // 10]),
             st.median(games), st.median(scores) if scores else 0,
             max(scores) if scores else 0))
    return outs, scores


if __name__ == "__main__":
    print("careers run to end of %d\n" % 2010)
    for style in ("careless", "decent", "expert"):
        report(style)
    
    print("\nscore distribution (expert):")
    _, sc = report("expert", n=120)
    buckets = [0] * 11
    for x in sc:
        buckets[int(x)] += 1
    for i in range(1, 11):
        if buckets[i]:
            print("   %2d  %-40s %d" % (i, "#" * min(40, buckets[i] // 3), buckets[i]))
    
    
    print("\n\ncareer trajectory - median cash at each checkpoint (60 careers)")
    import statistics as _st
    CHECKS = [1990, 1995, 2000, 2005, 2010]
    for style in ("decent", "expert"):
        rows = {y: [] for y in CHECKS}
        deaths = []
        for seed in range(60):
            s = sim.Studio(seed=seed)
            rng = random.Random(seed * 7919 + 13)
            smart = True
            for y in CHECKS:
                end = sim.ym(y, 12)
                while s.t < end and not s.over:
                    if s.project is None:
                        plat = pick_platform(s, rng, smart)
                        if plat is not None:
                            size = pick_size(s, rng, smart)
                            if s.can_start(size, plat):
                                tp, g = pick_pair(s, plat, rng, smart)
                                s.start_project("G", tp, g, plat, size)
                    p = s.project
                    if p is not None:
                        i = p.needs_alloc()
                        if i is not None:
                            p.alloc[i] = p.genre.stage_ideal(i)
                        if p.done():
                            if style == "expert" and p.bug_ratio() > 0.08 and p.polish_months < 2:
                                s.polishing = True
                            else:
                                if style == "expert" and p.marketing == 0 and s.money > 120000:
                                    s.market(min(s.money * 0.12, 90000 * sim.era(s.t)))
                                s.release()
                    if style == "expert" and s.project is None and s.staff < sim.max_staff(s.t) \
                            and s.money > s.hire_cost() * 14:
                        s.hire(max(s.candidates(), key=lambda d: d.skill))
                    s.advance()
                rows[y].append(s.money)
                if s.over and not deaths:
                    pass
            if s.over:
                deaths.append(s.t)
        line = "  %-8s" % style
        for y in CHECKS:
            line += "  %s %-9s" % (y, sim.money(_st.median(rows[y])))
        print(line)
        if deaths:
            yrs = sorted(sim.START_YEAR + d // 12 for d in deaths)
            print("           folded: %d/60, median year %d, range %d-%d"
                  % (len(deaths), yrs[len(yrs)//2], yrs[0], yrs[-1]))
        else:
            print("           folded: none")
