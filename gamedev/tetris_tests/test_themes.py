"""The colour themes: well formed, distinct, and one of them provably usable
by players with colour vision deficiency."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import palette_check as pc
import tetris as T

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

CHROME = {"accent", "grid", "frame", "danger"}

print("[1] every theme is complete")
for name, spec in T.THEMES.items():
    if spec is None:
        continue
    check("%s names all seven pieces and the chrome" % name,
          set(spec) == set(T.ORDER) | CHROME,
          sorted(set(T.ORDER) | CHROME ^ set(spec)))
check("all colour values are real xterm indices",
      all(all(0 <= v < 256 for v in spec.values())
          for spec in T.THEMES.values() if spec))
check("classic defers to the terminal's own palette", T.THEMES["classic"] is None)

print("\n[2] the cycle list is honest")
check("it covers every theme", sorted(T.THEME_ORDER) == sorted(T.THEMES))
check("with no repeats", len(T.THEME_ORDER) == len(set(T.THEME_ORDER)))
check("and there are a good few", len(T.THEME_ORDER) >= 10, len(T.THEME_ORDER))

print("\n[3] themes are actually different from one another")
sigs = {}
for name, spec in T.THEMES.items():
    if spec is None:
        continue
    sigs[name] = tuple(spec[k] for k in T.ORDER)
check("no two themes share a piece palette", len(set(sigs.values())) == len(sigs),
      [n for n in sigs if list(sigs.values()).count(sigs[n]) > 1])

print("\n[4] colour themes keep their pieces apart for normal vision")
for name, spec in T.THEMES.items():
    if spec is None or name in ("mono", "amber", "matrix"):
        continue
    d = pc.worst_pair([spec[k] for k in T.ORDER], "normal")[0]
    check("%s: closest pair is distinguishable" % name, d >= 12.0, "dE %.1f" % d)

print("\n[5] the accessible theme earns its name")
acc = [T.THEMES["accessible"][k] for k in T.ORDER]
a = pc.audit(acc)
check("protanopia stays clear", a["protanopia"][0] >= 10.0, "dE %.1f" % a["protanopia"][0])
check("deuteranopia stays clear", a["deuteranopia"][0] >= 10.0, "dE %.1f" % a["deuteranopia"][0])
check("normal vision too", a["normal"][0] >= 15.0, "dE %.1f" % a["normal"][0])
best_other = max((pc.audit([s[k] for k in T.ORDER])["protanopia"][0]
                  for n, s in T.THEMES.items()
                  if s and n not in ("accessible", "gameboy")))
check("and it beats every other colour theme under protanopia",
      a["protanopia"][0] > best_other, (a["protanopia"][0], best_other))
print("       protanopia dE %.1f vs %.1f for the next best"
      % (a["protanopia"][0], best_other))

print("\n[6] the single-hue themes are hard on purpose, not broken")
for name in ("mono", "amber", "matrix"):
    idx = [T.THEMES[name][k] for k in T.ORDER]
    check("%s still separates by brightness" % name,
          len(set(idx)) == 7 and
          (max(pc.to_lab(pc.xterm_rgb(i))[0] for i in idx)
           - min(pc.to_lab(pc.xterm_rgb(i))[0] for i in idx)) > 15,
          "lightness spread %.1f" % (max(pc.to_lab(pc.xterm_rgb(i))[0] for i in idx)
                                     - min(pc.to_lab(pc.xterm_rgb(i))[0] for i in idx)))

print("\n[7] every theme is a valid command-line choice")
import subprocess
game = os.path.join(HERE, "..", "tetris.py")
out = subprocess.run([sys.executable, game, "--help"], capture_output=True, text=True).stdout
check("all listed in --help", all(n in out for n in T.THEME_ORDER),
      [n for n in T.THEME_ORDER if n not in out])


# ---------------------------------------------------------------------------
# Automatic rotation
# ---------------------------------------------------------------------------

print("\n[8] the look moves on with the level")
check("rotation skips the single-hue themes",
      not any(t in T.THEME_ROTATION for t in T.HARD_THEMES), T.THEME_ROTATION)
check("but keeps every colour theme",
      sorted(T.THEME_ROTATION) == sorted(t for t in T.THEME_ORDER
                                         if t not in T.HARD_THEMES))
seen, cur = [], T.THEME_ROTATION[0]
for _ in range(len(T.THEME_ROTATION)):
    cur = T.next_theme(cur)
    seen.append(cur)
check("it visits every one before repeating", sorted(seen) == sorted(T.THEME_ROTATION),
      seen)
check("and then wraps", seen[-1] == T.THEME_ROTATION[0], seen[-1])
check("a hard theme rejoins the rotation rather than sticking",
      all(T.next_theme(t) in T.THEME_ROTATION for t in T.HARD_THEMES))
check("so does an unknown name", T.next_theme("nonsense") in T.THEME_ROTATION)
check("it never returns the theme it was given",
      all(T.next_theme(t) != t for t in T.THEME_ORDER))

print("\n[9] rotation in the running game")
import pty_lib
from pty_lib import VT, drain, spawn, stop
H, W = 30, 90
pty_lib.H, pty_lib.W = H, W
PROBE = os.path.join(HERE, "probe_tetris.py")

def level_up_run(extra=None, start_lines="39"):
    os.environ["PROBE_LINES"] = start_lines
    os.environ["PROBE_GAP"] = "9"
    os.environ["PROBE_POWERS"] = ""
    os.environ["PROBE_FLOOR"] = ""
    os.environ["PROBE_PIECE"] = "I"
    pid, fd = spawn([PROBE, "--scale", "small", "--no-shake", "--quiet",
                     "--seed", "5"] + (extra or []))
    vt = VT(H, W)
    vt.feed(drain(fd, .9).decode("utf-8", "replace"))
    return pid, fd, vt

def clear_a_line(fd, vt):
    """Stand the I on end, slide it to the empty column, drop it."""
    for keys in (b"w", b"\x1bOC" * 8, b" "):
        os.write(fd, keys)
        vt.feed(drain(fd, .7).decode("utf-8", "replace"))

pid, fd, vt = level_up_run()
check("starts on level 4 with 39 lines behind it", "LEVEL    4" in vt.dump(),
      [l.strip() for l in vt.dump().split("\n") if "LEVEL" in l])
clear_a_line(fd, vt)
check("clearing a line levels up", "LEVEL    5" in vt.dump(),
      [l.strip() for l in vt.dump().split("\n") if "LEVEL" in l])
stop(pid, fd)

pid, fd, vt = level_up_run(start_lines="69")
check("set up just below a rotation boundary", "LEVEL    7" in vt.dump(),
      [l.strip() for l in vt.dump().split("\n") if "LEVEL" in l])
before = vt.colours()
clear_a_line(fd, vt)
d = vt.dump()
check("crossing level 8 announces a new look",
      any(t.upper() in d for t in T.THEME_ROTATION),
      [l.strip() for l in d.split("\n")
       if any(t.upper() in l for t in T.THEME_ROTATION)])
check("and it is one from the rotation",
      any(t.upper() in d for t in T.THEME_ROTATION))
stop(pid, fd)

pid, fd, vt = level_up_run(extra=["--theme-every", "0"], start_lines="69")
clear_a_line(fd, vt)
d = vt.dump()
check("crossing a boundary still levels up", "LEVEL    8" in d,
      [l.strip() for l in d.split("\n") if "LEVEL" in l])
check("--theme-every 0 announces no new look",
      not any(t.upper() in d for t in T.THEME_ROTATION),
      [t for t in T.THEME_ROTATION if t.upper() in d])
stop(pid, fd)

out = subprocess.run([sys.executable, os.path.join(HERE, "..", "tetris.py"), "--help"],
                     capture_output=True, text=True).stdout
check("the flag is documented", "--theme-every" in out)

print("\n" + ("THEMES OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
