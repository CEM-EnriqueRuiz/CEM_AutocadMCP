"""Cemengal: where this repo's logs and temporary artefacts go (root decision 0031, docs/decisions/0003).

Never beside a script or under ACC: %TEMP%\\Cemengal\\AutocadMCP\\<name>-yyyyMMdd.log, and
%TEMP%\\Cemengal\\AutocadMCP\\<Kind>\\ for artefacts. The folder prunes itself on the first write of each
process: files older than 7 days, then the oldest until it is under 50 MB. Locked files are skipped and
pruning never raises.
"""
import tempfile
import time
from datetime import date
from pathlib import Path

APP = "AutocadMCP"
MAX_AGE_DAYS = 7.0
MAX_BYTES = 50 * 1024 * 1024

_pruned_roots = set()  # once per process, whichever instance writes first


class TempFolder:
    def __init__(self, app: str = APP, base=None, max_age_days: float = MAX_AGE_DAYS, max_bytes: int = MAX_BYTES):
        self.root = Path(base or tempfile.gettempdir()) / "Cemengal" / app
        self.max_age_days = max_age_days
        self.max_bytes = max_bytes

    def log_path(self, name: str, ext: str = ".log", day: date = None) -> Path:
        """The day's log file, e.g. diag-20261024.log. Append to it; the folder exists."""
        self._prepare(self.root)
        return self.root / f"{name}-{(day or date.today()):%Y%m%d}{ext}"

    def artefact_dir(self, kind: str) -> Path:
        """A subfolder for one kind of temporary artefact (screenshots, scripts, exports)."""
        folder = self.root / kind
        self._prepare(folder)
        return folder

    def prune(self, now: float = None) -> None:
        """Delete files older than max_age_days, then the oldest until under max_bytes. Never raises."""
        try:
            now = now or time.time()
            files = []
            for path in self.root.rglob("*"):
                try:
                    if path.is_file():
                        stat = path.stat()
                        files.append((stat.st_mtime, stat.st_size, path))
                except OSError:
                    continue
            files.sort()
            kept = []
            for mtime, size, path in files:
                if now - mtime > self.max_age_days * 86400 and self._delete(path):
                    continue
                kept.append((mtime, size, path))
            total = sum(size for _, size, _ in kept)
            for mtime, size, path in kept:
                if total < self.max_bytes:
                    break
                if self._delete(path):
                    total -= size
            for folder in sorted((p for p in self.root.rglob("*") if p.is_dir()), reverse=True):
                try:
                    folder.rmdir()  # only succeeds when empty
                except OSError:
                    pass
        except Exception:
            pass

    def _prepare(self, folder: Path) -> None:
        if any(part.lower() == "accdocs" for part in folder.parts):
            raise ValueError(f"Refusing to write under ACC: {folder}")
        key = str(self.root).lower()
        if key not in _pruned_roots:
            _pruned_roots.add(key)
            self.prune()
        folder.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _delete(path: Path) -> bool:
        try:
            path.unlink()
            return True
        except Exception:  # locked, in use, or gone: skip it
            return False
