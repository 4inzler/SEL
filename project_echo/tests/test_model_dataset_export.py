from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from sel_bot.model_dataset_export import SelModelDatasetExporter


def _make_settings(tmp_path: Path, *, max_snapshots: int = 3):
    return SimpleNamespace(
        sel_model_dataset_dir="./sel_model_dataset",
        sel_model_dataset_max_snapshots=max_snapshots,
        sel_data_dir="./sel_data",
        him_memory_dir="./sel_data/him_store",
        agents_dir="./agents",
        database_url="sqlite+aiosqlite:///./sel.db",
    )


def test_dataset_export_snapshot_collects_runtime_files(tmp_path: Path) -> None:
    (tmp_path / "sel_data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sel_data" / "memory.txt").write_text("memory line\n", encoding="utf-8")
    (tmp_path / "sel_data" / ".env").write_text("SECRET=123\n", encoding="utf-8")
    (tmp_path / "sel_data" / "him_store").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sel_data" / "him_store" / "hormones.json").write_text("{}", encoding="utf-8")
    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agents" / "sel_auto_test.py").write_text("DESCRIPTION='x'\n", encoding="utf-8")
    (tmp_path / "sel.db").write_text("sqlite payload", encoding="utf-8")

    exporter = SelModelDatasetExporter(_make_settings(tmp_path), repo_root=tmp_path)
    snapshot = exporter.create_snapshot(trigger="test")

    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    archive_paths = {entry["archive_path"] for entry in manifest["files"]}

    assert "sel_data/memory.txt" in archive_paths
    assert "sel_data/him_store/hormones.json" in archive_paths
    assert "agents/sel_auto_test.py" in archive_paths
    assert "sel.db" in archive_paths
    assert "sel_data/.env" not in archive_paths
    assert snapshot.files_copied == len(manifest["files"])
    assert (tmp_path / "sel_model_dataset" / "LATEST").exists()


def test_dataset_export_prunes_old_snapshots(tmp_path: Path) -> None:
    (tmp_path / "sel_data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sel_data" / "memory.txt").write_text("memory line\n", encoding="utf-8")
    exporter = SelModelDatasetExporter(_make_settings(tmp_path, max_snapshots=2), repo_root=tmp_path)

    exporter.create_snapshot(trigger="1")
    exporter.create_snapshot(trigger="2")
    exporter.create_snapshot(trigger="3")

    snapshots = sorted((tmp_path / "sel_model_dataset").glob("snapshot_*"))
    assert len(snapshots) == 2
