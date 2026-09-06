"""A pseudo-terminal plus enough of a VT to read back what curses actually drew.

Tests that only check game state miss the bugs that matter in a terminal app -
tearing, overflow, stale cells. This reconstructs the real screen instead.
"""
import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time

H, W = 30, 90


def spawn(argv, rows=None, cols=None):
    rows = rows or H
    cols = cols or W
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.environ["LINES"] = str(rows)
        os.environ["COLUMNS"] = str(cols)
        os.environ["LC_ALL"] = "en_US.UTF-8"
        os.execvp(sys.executable, [sys.executable] + argv)
        os._exit(1)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    return pid, fd


def drain(fd, seconds):
    out = b""
    end = time.time() + seconds
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.02)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    return out


def stop(pid, fd):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


class VT(object):
    """Enough of a terminal to see what was drawn, colours included."""

    def __init__(self, h=None, w=None):
        self.h = h or H
        self.w = w or W
        self.g = [[" "] * self.w for _ in range(self.h)]
        self.a = [[""] * self.w for _ in range(self.h)]
        self.sgr = ""
        self.y = self.x = 0

    def _clamp(self):
        self.y = max(0, min(self.h - 1, self.y))
        self.x = max(0, min(self.w - 1, self.x))

    def feed(self, text):
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ch == "\x1b":
                m = re.match(r"\x1b\[([0-9;?]*)([A-Za-z])", text[i:])
                if m:
                    params, cmd = m.group(1), m.group(2)
                    nums = [int(p) for p in params.split(";") if p.isdigit()]
                    a = nums[0] if nums else 0
                    if cmd in "Hf":
                        self.y = (nums[0] - 1) if nums else 0
                        self.x = (nums[1] - 1) if len(nums) > 1 else 0
                    elif cmd == "A": self.y -= max(1, a)
                    elif cmd == "B": self.y += max(1, a)
                    elif cmd == "C": self.x += max(1, a)
                    elif cmd == "D": self.x -= max(1, a)
                    elif cmd == "G": self.x = max(0, a - 1)
                    elif cmd == "d": self.y = max(0, a - 1)
                    elif cmd == "m":
                        self.sgr = "0" if params in ("", "0") else params
                    elif cmd == "K":
                        if a == 0:   self.g[self.y][self.x:] = [" "] * (self.w - self.x)
                        elif a == 1: self.g[self.y][:self.x + 1] = [" "] * (self.x + 1)
                        else:        self.g[self.y] = [" "] * self.w
                    elif cmd == "X":
                        k = max(1, a)
                        self.g[self.y][self.x:self.x + k] = [" "] * min(k, self.w - self.x)
                    elif cmd == "P":
                        k = max(1, a); row = self.g[self.y]
                        del row[self.x:self.x + k]; row.extend([" "] * k)
                    elif cmd == "@":
                        k = max(1, a); row = self.g[self.y]
                        for _ in range(k): row.insert(self.x, " ")
                        del row[self.w:]
                    elif cmd == "L":
                        for _ in range(max(1, a)):
                            self.g.insert(self.y, [" "] * self.w); self.g.pop()
                    elif cmd == "M":
                        for _ in range(max(1, a)):
                            self.g.pop(self.y); self.g.append([" "] * self.w)
                    elif cmd == "J":
                        if a == 2:
                            self.g = [[" "] * self.w for _ in range(self.h)]
                        else:
                            self.g[self.y][self.x:] = [" "] * (self.w - self.x)
                            for yy in range(self.y + 1, self.h):
                                self.g[yy] = [" "] * self.w
                    self._clamp(); i += m.end(); continue
                m = re.match(r"\x1b[()][A-Za-z0-9]", text[i:]) or re.match(r"\x1b.", text[i:])
                i += m.end() if m else 1
                continue
            if ch == "\r": self.x = 0
            elif ch == "\n": self.y += 1; self._clamp()
            elif ch == "\b": self.x = max(0, self.x - 1)
            elif ch == "\t": self.x = min(self.w - 1, (self.x // 8 + 1) * 8)
            elif ch in "\x0e\x0f": pass
            elif ord(ch) >= 32:
                self._clamp()
                self.g[self.y][self.x] = ch
                self.a[self.y][self.x] = self.sgr
                self.x += 1
                if self.x >= self.w: self.x = self.w - 1
            i += 1

    def dump(self):
        return "\n".join("".join(row).rstrip() for row in self.g)

    def attr_at(self, y, x):
        if 0 <= y < self.h and 0 <= x < self.w:
            return self.a[y][x]
        return ""

    def colours(self):
        return set(a for row in self.a for a in row if a)
