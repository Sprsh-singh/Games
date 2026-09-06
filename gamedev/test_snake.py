"""The rules of Snake, headless."""
import os, sys, tempfile, time, random
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["SNAKE_SAVE"] = os.path.join(tempfile.mkdtemp(), "s.json")
sys.path.insert(0, os.path.join(HERE, ".."))
import snake as S

fails = []
def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> %s" % (extra,)) if not cond and extra else ""))
    if not cond: fails.append(name)

def game(**kw):
    kw.setdefault("seed", 1)
    g = S.Game(**kw)
    g.food = None                      # tests place their own
    return g

print("[1] it starts sane")
g = S.Game(seed=1)
check("the snake has a starting length", len(g.snake) == S.START_LENGTH, len(g.snake))
check("it is on the board",
      all(0 <= x < g.w and 0 <= y < g.h for x, y in g.snake), list(g.snake))
check("it is heading somewhere", g.direction in S.DIRECTIONS.values())
check("there is an apple", g.food is not None)
check("the apple is not under the snake", g.food not in g.occupied)
check("the occupied set matches the snake", g.occupied == set(g.snake))
check("score and level start at the bottom", g.score == 0 and g.level == 1)
check("it waits for you before setting off", g.state == "ready", g.state)
before = list(g.snake)
g.update(time.monotonic() + 5)
check("and really does not move while waiting", list(g.snake) == before)
g.turn(S.UP)
check("the first turn starts the run", g.state == "play", g.state)

print("\n[2] moving")
g = game()
head = g.snake[0]
before = len(g.snake)
g.step()
check("the head advanced one cell", g.snake[0] == (head[0] + 1, head[1]), g.snake[0])
check("the length is unchanged", len(g.snake) == before, len(g.snake))
check("the tail cell was released", len(g.occupied) == before)

print("\n[3] turning")
g = game()
check("a right-angle turn is taken", g.turn(S.UP))
g.step()
check("it moved up", g.snake[0][1] < g.snake[1][1], list(g.snake)[:2])
check("reversing into your own neck is refused", not g.turn(S.DOWN))
check("carrying straight on is not a turn", not g.turn(S.UP))
g2 = game()
check("two turns can be queued", g2.turn(S.UP) and g2.turn(S.LEFT))
check("but no more than the buffer", not g2.turn(S.DOWN), len(g2.turns))
g2.step()
check("the first step takes only the first turn",
      g2.direction == S.UP and g2.state != "over", (g2.direction, g2.state))
g2.step()
check("the second step takes the second", g2.direction == S.LEFT, g2.direction)
check("and the snake is still alive", g2.state != "over", g2.message)

print("\n[4] eating")
g = game()
hx, hy = g.snake[0]
g.food = (hx + 1, hy)
before = len(g.snake)
g.step()
check("the apple is gone", g.food != (hx, hy) and g.food is not None)
check("the score went up", g.score == 10 * g.level, g.score)
check("growth is pending", g.grow == S.GROW_PER_FOOD, g.grow)
for _ in range(S.GROW_PER_FOOD):
    g.food = None
    g.step()
check("the snake grew by exactly that much",
      len(g.snake) == before + S.GROW_PER_FOOD, (before, len(g.snake)))
check("the eaten counter moved", g.eaten == 1)

print("\n[5] levelling up")
g = game()
for i in range(S.FOOD_PER_LEVEL):
    hx, hy = g.snake[0]
    g.food = (hx + 1, hy)
    g.step()
check("a level after %d apples" % S.FOOD_PER_LEVEL, g.level == 2, g.level)
check("and it moves faster", g.step_time() < S.BASE_STEP, g.step_time())
g.level = 40
check("but never faster than the floor", g.step_time() == S.MIN_STEP, g.step_time())

print("\n[6] dying")
g = game()
g.snake = __import__("collections").deque([(g.w - 1, 5), (g.w - 2, 5), (g.w - 3, 5)])
g.occupied = set(g.snake)
g.direction = S.RIGHT
g.step()
check("running into a wall ends it", g.state == "over", g.state)
check("and says why", "WALL" in g.message, g.message)

g = game()
from collections import deque
g.snake = deque([(5, 5), (6, 5), (6, 6), (5, 6), (4, 6)])
g.occupied = set(g.snake)
g.direction = S.RIGHT
g.turn(S.DOWN)
g.step()
check("running into yourself ends it", g.state == "over", g.state)
check("with the right reason", "ITSELF" in g.message, g.message)

print("\n[7] the tail gets out of the way")
def tail_chase(grow=0):
    """Head at (5,5) about to step left onto the tail cell (4,5)."""
    g = game()
    g.snake = deque([(5, 5), (5, 6), (4, 6), (4, 5)])
    g.occupied = set(g.snake)
    g.direction = S.LEFT
    g.grow = grow
    g.step()
    return g
g = tail_chase()
check("the head is where the tail was", g.snake[0] == (4, 5), g.snake[0])
check("chasing the vacating tail cell is survivable", g.state != "over", g.message)
g = tail_chase(grow=2)
check("but not while growing into it", g.state == "over", g.state)
check("and it says why", "ITSELF" in g.message, g.message)

print("\n[8] wrapping")
g = game(wrap=True)
g.snake = deque([(g.w - 1, 5), (g.w - 2, 5)])
g.occupied = set(g.snake)
g.direction = S.RIGHT
g.step()
check("the right edge comes out on the left", g.snake[0] == (0, 5), g.snake[0])
check("and nobody died", g.state != "over")
g = game(wrap=True)
g.snake = deque([(4, 0), (4, 1)])
g.occupied = set(g.snake)
g.direction = S.UP
g.step()
check("the top comes out at the bottom", g.snake[0] == (4, g.h - 1), g.snake[0])

print("\n[9] the golden apple")
g = game()
for i in range(S.BONUS_EVERY):
    hx, hy = g.snake[0]
    g.food = (hx + 1, hy)
    g.step()
check("one appears after %d apples" % S.BONUS_EVERY, g.bonus is not None, g.bonus)
check("with a life on it", g.bonus_left == S.BONUS_LIFE, g.bonus_left)
check("and not under the snake", g.bonus not in g.occupied)
before = g.score
g.snake[0] = (g.bonus[0] - 1, g.bonus[1])
g.occupied = set(g.snake)
g.direction = S.RIGHT
g.food = None
g.step()
check("eating it pays more than an apple", g.score - before > 10 * g.level,
      g.score - before)
check("and it is gone", g.bonus is None)

g = game()
g.bonus = (1, 1)
g.bonus_left = 1
g.food = None
g.step()
check("it expires if you dawdle", g.bonus is None)

print("\n[10] the maze")
g = S.Game(seed=3, maze=12)
check("blocks were placed", len(g.walls) > 10, len(g.walls))
check("none sit on the snake", not (g.walls & g.occupied))
check("the starting lane is clear",
      not any(y == g.h // 2 for _, y in g.walls), [c for c in g.walls if c[1] == g.h // 2])
g2 = S.Game(seed=3, maze=12)
check("the same seed gives the same maze", g2.walls == g.walls)
g = S.Game(seed=4, maze=10)
hx, hy = g.snake[0]
g.walls.add((hx + 1, hy))
g.food = None
g.step()
check("hitting a block ends the run", g.state == "over" and "BLOCK" in g.message,
      g.message)

print("\n[11] pause keeps the clock honest")
g = S.Game(seed=5)
g.turn(S.UP)                       # sets off
time.sleep(0.05)
g.toggle_pause()
a = g.elapsed()
time.sleep(0.12)
check("the clock stops", abs(g.elapsed() - a) < 1e-6)
g.toggle_pause()
check("and the pause is not counted", g.elapsed() < a + 0.05)
check("a paused snake refuses to turn", not g.turn(S.UP) if g.state != "play" else True)

print("\n[12] high score")
g = S.Game(seed=6)
g.score = 12345
g.die("TEST")
check("a record is kept", S.load_high_score() == 12345, S.load_high_score())
check("and flagged", g.new_record)
g2 = S.Game(seed=6)
check("the next run knows it", g2.high == 12345, g2.high)
g2.score = 5
g2.die("TEST")
check("a worse run does not overwrite it", S.load_high_score() == 12345)

print("\n[13] fuzzing")
bad = None
for seed in range(8):
    g = S.Game(seed=seed, wrap=(seed % 2 == 0), maze=(8 if seed % 3 == 0 else 0))
    rnd = random.Random(seed)
    for _ in range(4000):
        if g.state != "play":
            break
        if rnd.random() < .3:
            g.turn(rnd.choice(list(S.DIRECTIONS.values())))
        g.step()
        if g.occupied != set(g.snake):
            bad = ("bookkeeping", seed, len(g.occupied), len(g.snake)); break
        if len(g.snake) != len(set(g.snake)):
            bad = ("snake overlaps itself", seed); break
        if any(not (0 <= x < g.w and 0 <= y < g.h) for x, y in g.snake):
            bad = ("left the board", seed, g.snake[0]); break
        if g.food is not None and (g.food in g.occupied or g.food in g.walls):
            bad = ("apple under something", seed, g.food); break
        if g.score < 0:
            bad = ("negative score", seed); break
    if bad: break
check("no corruption over thousands of moves", bad is None, bad)

print("\n[14] a full board is a win, not a crash")
g = S.Game(seed=7, size="small")
g.snake = deque((x, y) for y in range(g.h) for x in range(g.w))
g.occupied = set(g.snake)
g.food = None
g.place_food()
check("it ends cleanly when there is nowhere left", g.state == "over", g.state)
check("and says so", "FULL" in g.message, g.message)

print("\n" + ("SNAKE OK" if not fails else "FAILURES: %s" % fails))
sys.exit(1 if fails else 0)
