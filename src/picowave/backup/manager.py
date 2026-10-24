"""Backup + rollback.

Before any generated file is (re)written, ``snapshot`` copies the current
version into ``backup/`` with a timestamp. ``last_good`` / ``restore`` support
the compile-fail rollback the pipeline performs in freeform mode: if a newly
generated program fails to compile, the previous known-good source is restored.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


class BackupManager:
    def __init__(self, backup_dir: Path):
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._last_good: Optional[Path] = None

    def snapshot(self, path: Path) -> Optional[Path]:
        """Copy ``path`` into the backup dir; return the backup path (or None)."""
        if not path.exists():
            return None
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest = self.backup_dir / f"{path.stem}.{ts}{path.suffix}.bak"
        shutil.copy2(path, dest)
        return dest

    def mark_good(self, path: Path) -> None:
        """Record ``path`` as the last known-good source for rollback."""
        if path.exists():
            self._last_good = self.snapshot(path)

    @property
    def last_good(self) -> Optional[Path]:
        return self._last_good

    def restore(self, target: Path) -> bool:
        """Restore the last known-good source over ``target``. True if restored."""
        if self._last_good and self._last_good.exists():
            shutil.copy2(self._last_good, target)
            return True
        return False
