"""FastAPI application exposing the Hierarchical Image Memory service."""
from __future__ import annotations

import base64
import datetime as dt
import json
import math
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .models import (
    QueryHints,
    QueryPlan,
    QueryRequest,
    Snapshot,
    SnapshotCreate,
    SnapshotProvenance,
    TileIngestRecord,
    TileIngestRequest,
    TileMeta,
    TilePayload,
)
from .planner import QueryPlanner
from .storage import HierarchicalImageMemory


# Hormone API models
class HormoneState(BaseModel):
    """Hormone state for a channel."""
    channel_id: str
    hormones: Dict[str, float] = Field(default_factory=dict)
    focus_topic: Optional[str] = None
    energy_level: float = 0.5
    messages_since_response: int = 0
    last_response_ts: Optional[str] = None
    last_updated: Optional[str] = None


class HormoneUpdate(BaseModel):
    """Request body for updating hormone state."""
    hormones: Dict[str, float]
    focus_topic: Optional[str] = None
    energy_level: Optional[float] = None
    messages_since_response: Optional[int] = None
    last_response_ts: Optional[str] = None


class HormoneHistoryItem(BaseModel):
    """Single hormone history entry."""
    timestamp: str
    hormones: Dict[str, float]
    metadata: Dict[str, Any] = Field(default_factory=dict)


HORMONE_STREAM = "hormonal_state"
HORMONE_DTYPE = "hormonal_vector/json;v1"


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

    # ----------------------------------------------------------------
    # Hormone API endpoints
    # ----------------------------------------------------------------

    def _ensure_hormone_snapshot(channel_id: str) -> None:
        """Ensure HIM snapshot exists for hormone state."""
        snapshot_id = str(channel_id)
        if store.snapshot_exists(snapshot_id):
            return
        provenance = SnapshotProvenance(model="sel-hormone-state", code_sha="local")
        payload = SnapshotCreate(
            snapshot_id=snapshot_id,
            parents=[],
            tags={"channel_id": snapshot_id, "type": "hormonal_state"},
            provenance=provenance,
        )
        store.create_snapshot(payload)

    def _time_bucket_to_coords(timestamp: dt.datetime, level: int) -> tuple:
        """Map timestamp to tile coordinates."""
        epoch = int(timestamp.timestamp())
        if level == 0:
            bucket = epoch // 300
        elif level == 1:
            bucket = epoch // 3600
        elif level == 2:
            bucket = epoch // 86400
        else:
            bucket = epoch // 604800
        x = bucket % (2**31)
        y = 0
        return x, y

    def _generate_hormone_shapes(hormones: Dict[str, float]) -> List[dict]:
        """Generate visual shapes for HIM tile visualization."""
        shapes = []
        hormone_list = list(hormones.items())
        for idx, (name, value) in enumerate(hormone_list):
            angle = (idx / max(1, len(hormone_list))) * 2 * math.pi
            radius = max(0.05, min(0.15, abs(value) * 0.4))
            cx = 0.5 + math.cos(angle) * 0.35 * value
            cy = 0.5 + math.sin(angle) * 0.35 * value
            intensity = max(0.0, min(1.0, (value + 1.0) / 2.0))
            color = f"#{int(255 * intensity):02x}{int(180 * (1 - intensity)):02x}{int(200 * abs(value)):02x}"
            shapes.append({
                "kind": "circle",
                "center": [cx, cy],
                "radius": radius,
                "stroke": color,
                "fill": color,
                "hormone": name,
                "value": value,
            })
        return shapes

    @app.get("/v1/hormones/{channel_id}", response_model=HormoneState)
    def get_hormone_state(channel_id: str) -> HormoneState:
        """Get current hormone state for a channel."""
        snapshot_id = str(channel_id)

        if not store.snapshot_exists(snapshot_id):
            # Return default state
            return HormoneState(
                channel_id=channel_id,
                hormones={},
                focus_topic=None,
                energy_level=0.5,
                messages_since_response=0,
                last_response_ts=None,
                last_updated=None,
            )

        try:
            metas = store.tiles_for_snapshot(
                snapshot_id,
                stream=HORMONE_STREAM,
                level_range=(0, 0),
            )
            if not metas:
                return HormoneState(channel_id=channel_id, hormones={})

            # Get latest tile by x coordinate (time bucket)
            metas_sorted = sorted(metas, key=lambda m: m.x, reverse=True)
            latest_meta = metas_sorted[0]
            stored = store.get_tile(latest_meta.tile_id)
            payload = json.loads(stored.payload_path.read_bytes().decode("utf-8"))

            metadata = payload.get("metadata", {})
            return HormoneState(
                channel_id=channel_id,
                hormones=payload.get("hormones", {}),
                focus_topic=metadata.get("focus_topic"),
                energy_level=metadata.get("energy_level", 0.5),
                messages_since_response=metadata.get("messages_since_response", 0),
                last_response_ts=metadata.get("last_response_ts"),
                last_updated=payload.get("timestamp"),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.put("/v1/hormones/{channel_id}", response_model=HormoneState)
    def update_hormone_state(channel_id: str, update: HormoneUpdate) -> HormoneState:
        """Update hormone state for a channel."""
        try:
            _ensure_hormone_snapshot(channel_id)
            snapshot_id = str(channel_id)
            timestamp = dt.datetime.now(dt.timezone.utc)
            time_bucket = int(timestamp.timestamp()) // 300

            # Build payload
            shapes = _generate_hormone_shapes(update.hormones)
            payload = {
                "format": "hormonal_state_v1",
                "channel_id": channel_id,
                "timestamp": timestamp.isoformat(),
                "time_bucket": time_bucket,
                "hormones": update.hormones,
                "metadata": {
                    "focus_topic": update.focus_topic,
                    "energy_level": update.energy_level or 0.5,
                    "messages_since_response": update.messages_since_response or 0,
                    "last_response_ts": update.last_response_ts,
                },
                "shapes": shapes,
            }
            payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            encoded_payload = base64.b64encode(payload_bytes).decode("utf-8")

            # Build tile records for levels 0-3
            records = []
            from blake3 import blake3
            parent_tile_id = None
            for level in range(4):
                x, y = _time_bucket_to_coords(timestamp, level)
                digest = blake3()
                for part in (HORMONE_STREAM, snapshot_id, str(level), str(x), str(y)):
                    digest.update(part.encode("utf-8"))
                digest.update(payload_bytes)
                tile_id = digest.hexdigest()

                record = TileIngestRecord(
                    stream=HORMONE_STREAM,
                    snapshot_id=snapshot_id,
                    level=level,
                    x=x,
                    y=y,
                    shape=(1, 1, 1),
                    dtype=HORMONE_DTYPE,
                    payload=TilePayload(bytes_b64=encoded_payload),
                    halo=None,
                    parent_tile_id=parent_tile_id,
                )
                records.append(record)
                parent_tile_id = tile_id

            store.put_tiles(records)

            return HormoneState(
                channel_id=channel_id,
                hormones=update.hormones,
                focus_topic=update.focus_topic,
                energy_level=update.energy_level or 0.5,
                messages_since_response=update.messages_since_response or 0,
                last_response_ts=update.last_response_ts,
                last_updated=timestamp.isoformat(),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/hormones/{channel_id}/history", response_model=List[HormoneHistoryItem])
    def get_hormone_history(
        channel_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        level: int = 0,
        limit: int = 100,
    ) -> List[HormoneHistoryItem]:
        """Get hormone history for a channel within a time range."""
        snapshot_id = str(channel_id)

        if not store.snapshot_exists(snapshot_id):
            return []

        try:
            metas = store.tiles_for_snapshot(
                snapshot_id,
                stream=HORMONE_STREAM,
                level_range=(level, level),
            )

            # Filter by time range if provided
            if start:
                start_time = dt.datetime.fromisoformat(start)
                x_start, _ = _time_bucket_to_coords(start_time, level)
                metas = [m for m in metas if m.x >= x_start]

            if end:
                end_time = dt.datetime.fromisoformat(end)
                x_end, _ = _time_bucket_to_coords(end_time, level)
                metas = [m for m in metas if m.x <= x_end]

            # Sort by time (x coordinate) descending
            metas = sorted(metas, key=lambda m: m.x, reverse=True)[:limit]

            results = []
            for meta in metas:
                try:
                    stored = store.get_tile(meta.tile_id)
                    payload = json.loads(stored.payload_path.read_bytes().decode("utf-8"))
                    results.append(HormoneHistoryItem(
                        timestamp=payload.get("timestamp", ""),
                        hormones=payload.get("hormones", {}),
                        metadata=payload.get("metadata", {}),
                    ))
                except Exception:
                    continue

            # Sort chronologically
            results.sort(key=lambda x: x.timestamp)
            return results
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


__all__ = ["create_app"]
