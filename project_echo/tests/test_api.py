from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from him.api import create_app
from him.models import QueryRequest, SnapshotCreate, SnapshotProvenance
from him.storage import HierarchicalImageMemory


def make_client(tmp_path: Path) -> tuple[TestClient, HierarchicalImageMemory]:
    store = HierarchicalImageMemory(tmp_path)
    app = create_app(store)
    return TestClient(app), store


def test_snapshot_lifecycle(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    payload = SnapshotCreate(
        snapshot_id="snp_api",
        tags={},
        parents=[],
        provenance=SnapshotProvenance(model="test", code_sha="feedface"),
    )
    response = client.post("/v1/snapshots", json=payload.model_dump(mode="json"))
    assert response.status_code == 201, response.text
    snapshot = response.json()
    assert snapshot["snapshot_id"] == "snp_api"

    response = client.get("/v1/snapshots", params={"limit": 5})
    assert response.status_code == 200
    snapshots = response.json()
    assert any(item["snapshot_id"] == "snp_api" for item in snapshots)

    response = client.get("/v1/snapshots/snp_api")
    assert response.status_code == 200


def test_tile_ingest_prefetch_and_query(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    payload = SnapshotCreate(
        snapshot_id="snp_tiles",
        tags={},
        parents=[],
        provenance=SnapshotProvenance(model="test", code_sha="cafebabe"),
    )
    client.post("/v1/snapshots", json=payload.model_dump(mode="json"))

    tile_payload = {
        "stream": "kv_cache",
        "snapshot_id": "snp_tiles",
        "level": 1,
        "x": 2,
        "y": 3,
        "shape": [512, 512, 1],
        "dtype": "fp16",
        "payload": {"bytes_b64": base64.b64encode(b"bytes").decode("utf-8")},
    }
    response = client.post("/v1/tiles", json=[tile_payload])
    assert response.status_code == 201, response.text
    tile_meta = response.json()[0]

    hint_payload = [
        {
            "query_id": "q-api",
            "snapshot_id": "snp_tiles",
            "stream": "kv_cache",
            "level_range": [2, 0],
            "bboxes": [[2, 3, 1, 1]],
            "confidence": 0.95,
        }
    ]
    response = client.post("/v1/prefetch", json=hint_payload)
    assert response.status_code == 202

    query_request = QueryRequest(goal="find", snapshot_id="snp_tiles", budget_ms=150, max_tiles=1)
    response = client.post("/v1/query", json=query_request.model_dump(mode="json"))
    assert response.status_code == 200
    plan = response.json()
    assert plan["tile_ids"], "Expected planner to return tiles"
    assert plan["tile_ids"][0]["tile_id"] == tile_meta["tile_id"]
    assert plan["acceptance"] > 0.5

    response = client.get("/v1/tiles/kv_cache/snp_tiles/1/2/3")
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["tile_id"] == tile_meta["tile_id"]

    # Prefetch hints should be persisted in the backing store.
    logged_hints = list(store.iter_hints())
    assert any(hint.query_id == "q-api" for hint in logged_hints)


def test_tile_ingest_unknown_snapshot(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    tile_payload = {
        "stream": "kv_cache",
        "snapshot_id": "missing",
        "level": 0,
        "x": 0,
        "y": 0,
        "shape": [512, 512, 1],
        "dtype": "fp16",
        "payload": {"bytes_b64": base64.b64encode(b"bytes").decode("utf-8")},
    }
    response = client.post("/v1/tiles", json=[tile_payload])
    assert response.status_code == 400
