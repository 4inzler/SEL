"""Local dataset snapshots for future Sel-model research/training."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)

_IGNORE_PARTS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    "htmlcov",
    "node_modules",
}
_IGNORE_SUFFIXES = {".pyc", ".pyo", ".tmp"}


@dataclass(frozen=True)
class SelDatasetSnapshot:
    snapshot_dir: Path
    manifest_path: Path
    files_copied: int
    bytes_copied: int
    trigger: str
    created_at_utc: str


class SelModelDatasetExporter:
    """
    Collect runtime Sel data into a local snapshot folder with a JSON manifest.

    Secrets are excluded by default (`.env*`, key/cert-like files).
    """

    def __init__(self, settings: Any, *, repo_root: Optional[Path] = None) -> None:
        self.settings = settings
        self.repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()

        output_root = Path(getattr(settings, "sel_model_dataset_dir", "./sel_model_dataset")).expanduser()
        if not output_root.is_absolute():
            output_root = (self.repo_root / output_root).resolve()
        self.output_root = output_root

    @staticmethod
    def _is_sqlite_url(database_url: str) -> bool:
        value = (database_url or "").strip().lower()
        return value.startswith("sqlite://")

    def _sqlite_path_from_database_url(self) -> Optional[Path]:
        database_url = str(getattr(self.settings, "database_url", "") or "").strip()
        if not self._is_sqlite_url(database_url):
            return None

        path_part = database_url
        if ":///" in path_part:
            path_part = path_part.split(":///", 1)[1]
        path_part = path_part.split("?", 1)[0].strip()
        if not path_part:
            return None
        path_part = unquote(path_part)

        candidate = Path(path_part).expanduser()
        if not candidate.is_absolute():
            candidate = (self.repo_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        return candidate

    def _normalize_path(self, raw: str | Path | None) -> Optional[Path]:
        if raw is None:
            return None
        value = str(raw).strip()
        if not value:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (self.repo_root / path).resolve()
        else:
            path = path.resolve()
        return path

    def _candidate_sources(self) -> List[Path]:
        candidates: List[Path] = []

        raw_candidates: List[str | Path] = [
            getattr(self.settings, "sel_data_dir", "./sel_data"),
            getattr(self.settings, "him_memory_dir", "./sel_data/him_store"),
            getattr(self.settings, "agents_dir", "./agents"),
            self.repo_root / "sel_data",
            self.repo_root / "project_echo" / "sel_data",
            self.repo_root / "project_echo" / "data",
            self.repo_root / "agents",
            self.repo_root / "project_echo" / "agents",
            self.repo_root / "project_echo" / "data" / "him.db",
            self.repo_root / "sel.db",
            self.repo_root / "project_echo" / "sel.db",
        ]

        sqlite_path = self._sqlite_path_from_database_url()
        if sqlite_path is not None:
            raw_candidates.append(sqlite_path)

        seen: set[str] = set()
        for raw in raw_candidates:
            normalized = self._normalize_path(raw)
            if normalized is None:
                continue
            key = str(normalized)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(normalized)
        return candidates

    @staticmethod
    def _is_secretish_file(path: Path) -> bool:
        name = path.name.lower()
        if name.startswith(".env"):
            return True
        if name.endswith(".pem") or name.endswith(".key"):
            return True
        if "token" in name and name.endswith(".txt"):
            return True
        return False

    @staticmethod
    def _should_ignore_path(path: Path) -> bool:
        lowered_parts = [part.lower() for part in path.parts]
        if any(part in _IGNORE_PARTS for part in lowered_parts):
            return True
        if any(part.startswith(".env") for part in lowered_parts):
            return True
        if path.suffix.lower() in _IGNORE_SUFFIXES:
            return True
        return False

    def _source_label(self, source: Path) -> str:
        try:
            rel = source.relative_to(self.repo_root)
            return rel.as_posix()
        except Exception:
            sanitized = "__abs__/" + "/".join(part for part in source.parts if part not in {"/", "\\"})
            return sanitized.strip("/") or source.name

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _iter_files(self, source: Path) -> Iterable[Path]:
        if source.is_file():
            if not self._should_ignore_path(source) and not self._is_secretish_file(source):
                yield source
            return

        for path in source.rglob("*"):
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            if self._should_ignore_path(path):
                continue
            if self._is_secretish_file(path):
                continue
            if self.output_root in path.parents:
                continue
            yield path

    def _prune_old_snapshots(self) -> None:
        max_snapshots = int(getattr(self.settings, "sel_model_dataset_max_snapshots", 90))
        max_snapshots = max(1, min(10_000, max_snapshots))
        if not self.output_root.exists():
            return
        snapshots = sorted(
            [p for p in self.output_root.iterdir() if p.is_dir() and p.name.startswith("snapshot_")],
            key=lambda p: p.name,
        )
        if len(snapshots) <= max_snapshots:
            return
        for old in snapshots[: len(snapshots) - max_snapshots]:
            shutil.rmtree(old, ignore_errors=True)

    def create_snapshot(self, *, trigger: str = "manual") -> SelDatasetSnapshot:
        now = dt.datetime.now(dt.timezone.utc)
        stamp = now.strftime("%Y%m%d_%H%M%S_%fZ")
        snapshot_dir = self.output_root / f"snapshot_{stamp}"
        dataset_root = snapshot_dir / "dataset"
        dataset_root.mkdir(parents=True, exist_ok=False)

        files_copied = 0
        bytes_copied = 0
        file_entries: List[Dict[str, Any]] = []
        source_entries: List[Dict[str, Any]] = []

        for source in self._candidate_sources():
            if source == self.output_root or self.output_root in source.parents:
                continue
            if not source.exists():
                continue
            if self._should_ignore_path(source):
                continue
            if self._is_secretish_file(source):
                continue

            label = self._source_label(source)
            source_entries.append(
                {
                    "source": str(source),
                    "label": label,
                    "kind": "directory" if source.is_dir() else "file",
                }
            )

            for file_path in self._iter_files(source):
                if source.is_dir():
                    rel = file_path.relative_to(source)
                    archive_rel = Path(label) / rel
                else:
                    archive_rel = Path(label)
                dest = dataset_root / archive_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)
                size = int(dest.stat().st_size)
                files_copied += 1
                bytes_copied += size
                file_entries.append(
                    {
                        "archive_path": archive_rel.as_posix(),
                        "source_path": str(file_path),
                        "size_bytes": size,
                        "sha256": self._sha256(dest),
                    }
                )

        manifest = {
            "schema_version": 1,
            "created_at_utc": now.isoformat(),
            "trigger": trigger,
            "repo_root": str(self.repo_root),
            "snapshot_dir": str(snapshot_dir),
            "files_copied": files_copied,
            "bytes_copied": bytes_copied,
            "sources": source_entries,
            "files": file_entries,
            "notes": [
                "This export intentionally excludes .env files and key/cert-like files.",
                "Use manifest checksums for integrity when preparing future Sel-model datasets.",
            ],
        }
        manifest_path = snapshot_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (self.output_root / "LATEST").write_text(f"{snapshot_dir}\n", encoding="utf-8")

        self._prune_old_snapshots()
        logger.info(
            "Sel dataset snapshot created: %s files=%d bytes=%d trigger=%s",
            snapshot_dir,
            files_copied,
            bytes_copied,
            trigger,
        )

        return SelDatasetSnapshot(
            snapshot_dir=snapshot_dir,
            manifest_path=manifest_path,
            files_copied=files_copied,
            bytes_copied=bytes_copied,
            trigger=trigger,
            created_at_utc=now.isoformat(),
        )
