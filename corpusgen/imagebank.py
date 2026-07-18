"""The bundled synthetic image bank (``corpusgen/imagebank/``): benign people,
recon/surveillance people, and vehicles-with-plates, each carrying a *role* and
its *facit* in ``bank.json``. Everything is synthetically generated (SDXL people +
composited plate cards) → no GDPR / third-party-IP exposure, safe to ship.

Roles route the attachment so messages make sense:
  - ``plate``  → a vehicle photo with a legible Swedish plate (tests photo→Job A)
  - ``recon``  → a surveillance person (binoculars/camera/…) (tests behaviour→score)
  - ``benign`` → an ordinary person/scene (tests no-false-alarm)

Stdlib only — the generator stays dependency-free (Pillow was only ever needed to
BUILD the bank, via tools/build_bank.py; consuming it is a plain file copy).
"""
import json
import shutil
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "imagebank"


class ImageBank:
    def __init__(self, entries):
        self.by_role = {}
        for e in entries:
            self.by_role.setdefault(e.get("role"), []).append(e)

    @classmethod
    def load(cls):
        """The bundled bank, or None if it wasn't shipped/built."""
        man = _DIR / "bank.json"
        if not man.exists():
            return None
        data = json.loads(man.read_text(encoding="utf-8"))
        return cls(data.get("images", []))

    def has(self, *roles):
        return any(self.by_role.get(r) for r in roles)

    def pick(self, rng, roles):
        """Deterministically choose one image across the given roles, or None."""
        pool = [e for r in roles for e in self.by_role.get(r, [])]
        return rng.choice(pool) if pool else None

    def copy(self, entry, dest_dir):
        """Copy the image into a corpus attachment folder; return its filename."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(_DIR / entry["file"], dest_dir / entry["file"])
        return entry["file"]
