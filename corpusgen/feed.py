"""Feeder — drip a corpus from one folder into a destination folder over time,
mimicking a central app trickling messages out. Copies the .md reports in
chronological order plus any referenced attachments (so image embeds resolve)."""
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

_FM_TIME = re.compile(r"^tidpunkt:\s*(.+)$", re.MULTILINE)
_EMBED = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")  # standard-Markdown image embed


def _load(src):
    items = []
    for p in sorted(src.glob("*.md")):
        m = _FM_TIME.search(p.read_text(encoding="utf-8"))
        if m:
            items.append((datetime.fromisoformat(m.group(1).strip().strip('"')), p))
    items.sort(key=lambda x: x[0])
    return items


class Feeder:
    def __init__(self, src, dest):
        self.src = Path(src)
        self.dest = Path(dest)
        self.dest.mkdir(parents=True, exist_ok=True)
        self.reports = _load(self.src)
        if not self.reports:
            sys.exit(f"No reports found in {self.src}")
        self.idx = 0
        present = {p.name for p in self.dest.glob("*.md")}
        while self.idx < len(self.reports) and self.reports[self.idx][1].name in present:
            self.idx += 1

    def _copy(self, p):
        shutil.copy2(p, self.dest / p.name)
        text = p.read_text(encoding="utf-8")
        for rel in _EMBED.findall(text):
            img = self.src / rel
            if img.exists():
                out = self.dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img, out)

    def send(self, n=1):
        sent = 0
        while sent < n and self.idx < len(self.reports):
            ts, p = self.reports[self.idx]
            self._copy(p)
            print(f"  + {p.name}   [{ts:%a %Y-%m-%d %H:%M}]")
            self.idx += 1
            sent += 1
        if self.idx >= len(self.reports):
            print("  (all reports delivered)")
        return sent

    def auto(self, minutes=15.0):
        remaining = self.reports[self.idx:]
        if not remaining:
            print("  (all reports already delivered)")
            return
        t0, t1 = remaining[0][0], self.reports[-1][0]
        span = (t1 - t0).total_seconds() or 1.0
        factor = span / (minutes * 60.0)
        print(f"  Replaying {len(remaining)} reports over ~{minutes:.0f} min "
              f"(≈{factor:.0f}× real time). Ctrl-C to pause.")
        try:
            prev = t0
            for ts, p in remaining:
                time.sleep(min(max(0.0, (ts - prev).total_seconds() / factor), minutes * 60.0))
                self._copy(p)
                self.idx += 1
                print(f"  + {p.name}   [{ts:%a %H:%M}]")
                prev = ts
            print("  (replay complete)")
        except KeyboardInterrupt:
            print("\n  paused — back to prompt.")

    def status(self):
        done, total = self.idx, len(self.reports)
        print(f"  Delivered {done}/{total}.")
        if done < total:
            ts, p = self.reports[self.idx]
            print(f"  Next: {p.name} [{ts:%a %Y-%m-%d %H:%M}]")
        print(f"  Span: {self.reports[0][0]:%Y-%m-%d %H:%M} -> {self.reports[-1][0]:%Y-%m-%d %H:%M}")

    def reset(self):
        r = sum(1 for p in self.dest.glob("*.md") for _ in [p.unlink()])
        self.idx = 0
        print(f"  Removed {r} reports. Reset to start.")


def run(src, dest, once=None):
    """Interactive REPL, or a single one-shot action (`once` = ('send', n) etc.)."""
    f = Feeder(src, dest)
    if once:
        cmd, arg = once
        {"send": lambda: f.send(arg or 1), "auto": lambda: f.auto(arg or 15.0),
         "reset": f.reset, "status": f.status}[cmd]()
        return
    print(f"Loaded {len(f.reports)} reports -> {f.dest}")
    f.status()
    print("Commands: send [n] | auto [mins] | status | reset | quit")
    while True:
        try:
            raw = input("7S> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        parts = raw.split()
        cmd = parts[0].lower()
        if cmd in ("quit", "exit", "q"):
            break
        elif cmd == "send":
            f.send(int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1)
        elif cmd == "auto":
            f.auto(float(parts[1]) if len(parts) > 1 else 15.0)
        elif cmd == "status":
            f.status()
        elif cmd == "reset":
            f.reset()
        else:
            print("  ? send [n] | auto [mins] | status | reset | quit")
