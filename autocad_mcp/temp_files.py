"""Cemengal: where this repo's logs and temporary artefacts go (root decision 0031, docs/decisions/0003).

Never beside a script or under ACC: %TEMP%\\Cemengal\\AutocadMCP\\<name>-yyyyMMdd.log, and
%TEMP%\\Cemengal\\AutocadMCP\\<Kind>\\ for artefacts. The folder prunes itself on the first write of each
process: files older than 7 days, then the oldest until it is under 50 MB. Locked files are skipped and
pruning never raises.

exports\\ has its own rule, outside the 50 MB cap (docs/decisions/0006, known gap 16): the newest export file
(.json or .failed.json) and the newest complete .json are never pruned; the others are kept up to 3 files in
all, and only while under 7 days old. A .json.partial (a job running) stays while under 7 days old.

The prune never follows, and never deletes through, a reparse point (a junction or a symlink): other accounts may
be able to write in %TEMP%\\Cemengal (SEC-1, CWE-59).
"""
import os
import stat
import tempfile
import time
from datetime import date
from pathlib import Path

APP = "AutocadMCP"
MAX_AGE_DAYS = 7.0
MAX_BYTES = 50 * 1024 * 1024
EXPORTS = "exports"
MAX_EXPORTS = 3

_pruned_roots = set()  # once per process, whichever instance writes first
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _reparse(info) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & REPARSE_POINT) or stat.S_ISLNK(info.st_mode)


def is_reparse(path) -> bool:
    """A junction, a symlink or any other reparse point (SEC-1, CWE-59). A path that cannot be read counts as one."""
    try:
        return _reparse(os.lstat(path))
    except FileNotFoundError:
        return False
    except OSError:
        return True


class TempFolder:
    def __init__(self, app: str = APP, base=None, max_age_days: float = MAX_AGE_DAYS, max_bytes: int = MAX_BYTES,
                 max_exports: int = MAX_EXPORTS):
        self.root = Path(base or tempfile.gettempdir()) / "Cemengal" / app
        self.max_age_days = max_age_days
        self.max_bytes = max_bytes
        self.max_exports = max_exports

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
        """Delete files older than max_age_days, then the oldest until under max_bytes; exports\\ by its own
        rule (prune_exports). Never follows or deletes through a reparse point (SEC-1). Never raises."""
        try:
            now = now or time.time()
            if not self._safe_root():
                return
            files, folders = self._walk(self.root, skip=self.root / EXPORTS)
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
            self.prune_exports(now)
            for folder in sorted(folders, reverse=True):
                if self._safe(folder):
                    try:
                        folder.rmdir()  # only succeeds when empty
                    except OSError:
                        pass
        except Exception:
            pass

    def prune_exports(self, now: float = None) -> None:
        """exports\\: keep the newest export, and the newest complete .json at any age, then the newest others up to
        max_exports files while under max_age_days; a .partial only while under max_age_days. Never follows or
        deletes through a reparse point (SEC-1). Never raises."""
        try:
            now = now or time.time()
            folder = self.root / EXPORTS
            if not self._safe_root() or not folder.is_dir() or is_reparse(folder):
                return
            made, others = [], []
            for mtime, _, path in self._walk(folder, recurse=False)[0]:
                (made if path.name.endswith(".json") else others).append((mtime, path))
            made.sort(key=lambda f: f[0], reverse=True)
            keep = [p for _, p in made[:1]]
            complete = [p for _, p in made if not p.name.endswith(".failed.json")][:1]  # QA-1: the newest one only
            keep += [p for p in complete if p not in keep]
            for mtime, path in made:
                if len(keep) >= self.max_exports:
                    break
                if path not in keep and now - mtime <= self.max_age_days * 86400:
                    keep.append(path)
            for _, path in made:
                if path not in keep:
                    self._delete(path)
            for mtime, path in others:
                if now - mtime > self.max_age_days * 86400:
                    self._delete(path)
        except Exception:
            pass

    def _safe_root(self) -> bool:
        """The root and its Cemengal parent are real folders, not junctions or links to somewhere else."""
        return self.root.is_dir() and not is_reparse(self.root.parent) and not is_reparse(self.root)

    def _safe(self, path: Path) -> bool:
        """No reparse point from the root's parent down to path, checked again just before a delete."""
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return False
        current = self.root
        if is_reparse(self.root.parent) or is_reparse(current):
            return False
        for part in relative.parts:
            current = current / part
            if is_reparse(current):
                return False
        return True

    @staticmethod
    def _walk(folder: Path, skip: Path = None, recurse: bool = True):
        """(files as (mtime, size, path), subfolders) under folder; reparse points are neither listed nor entered."""
        files, folders, pending = [], [], [folder]
        while pending:
            current = pending.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if _reparse(info):
                    continue
                path = Path(entry.path)
                if stat.S_ISDIR(info.st_mode):
                    if recurse and path != skip:
                        folders.append(path)
                        pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    files.append((info.st_mtime, info.st_size, path))
        return files, folders

    def _prepare(self, folder: Path) -> None:
        if any(part.lower() == "accdocs" for part in folder.parts):
            raise ValueError(f"Refusing to write under ACC: {folder}")
        self._refuse_reparse(folder)
        key = str(self.root).lower()
        if key not in _pruned_roots:
            _pruned_roots.add(key)
            self.prune()
        folder.mkdir(parents=True, exist_ok=True)
        self._refuse_reparse(folder)  # again: one may have been swapped in meanwhile (known gap 17)

    def _refuse_reparse(self, folder: Path) -> None:
        """Never write through a junction or link at Cemengal, the root or the artefact folder (known gap 17)."""
        for path in dict.fromkeys((self.root.parent, self.root, folder)):
            if is_reparse(path):
                raise ValueError(f"Refusing to write through a junction or link: {path} "
                                 "(it may point outside the temp folder; remove it, then retry)")

    def _delete(self, path: Path) -> bool:
        if not self._safe(path):  # never through a junction or link, even one swapped in since the walk
            return False
        try:
            path.unlink()
            return True
        except Exception:  # locked, in use, or gone: skip it
            return False
