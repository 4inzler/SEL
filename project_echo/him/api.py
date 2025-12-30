"""FastAPI application exposing the Hierarchical Image Memory service."""
from __future__ import annotations

import base64
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response

from .models import (
    QueryHints,
    QueryPlan,
    QueryRequest,
    Snapshot,
    SnapshotCreate,
    TileIngestRequest,
    TileMeta,
)
from .planner import QueryPlanner
from .storage import HierarchicalImageMemory


def create_app(store: HierarchicalImageMemory | None = None) -> FastAPI:
    store = store or HierarchicalImageMemory()
    planner = QueryPlanner(store)
    app = FastAPI(title="Hierarchical Image Memory")

    @app.get("/v1/snapshots", response_model=List[Snapshot])
    def list_snapshots(limit: int | None = None) -> List[Snapshot]:
        snapshots = store.list_snapshots()
        if limit is not None and limit > 0:
            return snapshots[:limit]
        return snapshots

    @app.post("/v1/snapshots", response_model=Snapshot, status_code=201)
    def create_snapshot(payload: SnapshotCreate) -> Snapshot:
        try:
            return store.create_snapshot(payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/snapshots/{snapshot_id}", response_model=Snapshot)
    def get_snapshot(snapshot_id: str) -> Snapshot:
        try:
            return store.get_snapshot(snapshot_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/tiles", response_model=List[TileMeta], status_code=201)
    def put_tiles(request: TileIngestRequest) -> List[TileMeta]:
        try:
            return store.put_tiles(request.root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/tiles/{stream}/{snapshot}/{level}/{x}/{y}")
    def get_tile(stream: str, snapshot: str, level: int, x: int, y: int) -> Response:
        try:
            stored = store.get_tile_by_coordinate(
                stream=stream,
                snapshot_id=snapshot,
                level=level,
                x=x,
                y=y,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        data = stored.payload_path.read_bytes()
        return JSONResponse(
            {
                "metadata": stored.metadata.model_dump(mode="json"),
                "payload": base64.b64encode(data).decode("utf-8"),
            }
        )

    @app.post("/v1/query", response_model=QueryPlan)
    def query_tiles(request: QueryRequest) -> QueryPlan:
        return planner.plan(request)

    @app.post("/v1/prefetch", status_code=202)
    def prefetch(hints: QueryHints) -> None:
        store.log_hints(hints.root)

    @app.post("/v1/snapshots/{snapshot_id}/merge")
    def merge_snapshot(snapshot_id: str) -> dict:
        # A placeholder merge implementation.
        if not store.snapshot_exists(snapshot_id):
            raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")
        return {"status": "merge_scheduled", "snapshot_id": snapshot_id}

    @app.post("/v1/replay")
    def replay(snapshot_id: str, trace_id: str) -> dict:
        # Real deterministic replay requires GPU capture; here we simply acknowledge the request.
        if not store.snapshot_exists(snapshot_id):
            raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")
        return {"status": "replay_scheduled", "snapshot_id": snapshot_id, "trace_id": trace_id}

    return app


__all__ = ["create_app"]
