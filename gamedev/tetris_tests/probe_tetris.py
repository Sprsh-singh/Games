"""Start Tetris from a chosen state, through the real entry point so the probe
cannot drift from the game."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import tetris as T

POWERS = os.environ.get("PROBE_POWERS", "")
FLOOR = os.environ.get("PROBE_FLOOR", "")
LINES = os.environ.get("PROBE_LINES", "")
GAP = os.environ.get("PROBE_GAP", "")
PIECE = os.environ.get("PROBE_PIECE", "")

_reset = T.Game.reset
def reset(self, start_level=None):
    _reset(self, start_level)
    if POWERS:
        self.powers = [p for p in POWERS.split(",") if p in T.POWERS]
    if LINES:
        self.lines = int(LINES)
        self.level = min(T.MAX_LEVEL, self.start_level + self.lines // 10)
    if GAP:
        # a bottom row one cell short of complete, so a single drop levels up
        for c in range(T.COLS):
            if c != int(GAP):
                self.board[T.ROWS - 1][c] = "I"
    if PIECE in T.SPEC:
        self.piece = T.Piece(PIECE)
        if self.history:
            self.history[-1] = self.snapshot()
    if FLOOR:
        rows = int(FLOOR)
        for r in range(T.ROWS - rows, T.ROWS):
            for c in range(T.COLS):
                if c != 9:
                    self.board[r][c] = "SZLJ"[(r + c) % 4]
T.Game.reset = reset

if __name__ == "__main__":
    T.main()
