"""Pydantic models used by the Hierarchical Image Memory service."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator


class MergePolicy(str, Enum):
    """Supported snapshot merge policies."""

    LWW = "lww"
    MANUAL = "manual"


class SnapshotProvenance(BaseModel):
    """Metadata describing the environment used to produce a snapshot."""

    model: str
    code_sha: str
    cuda: Optional[str] = None
    driver: Optional[str] = None
    seed: Optional[int] = None


class Snapshot(BaseModel):
    """Snapshot description returned to clients."""

    snapshot_id: str = Field(..., serialization_alias="snapshot_id")
    parents: List[str] = Field(default_factory=list)
    created_at: datetime
    tags: Dict[str, str] = Field(default_factory=dict)
    provenance: SnapshotProvenance
    merge_policy: MergePolicy = MergePolicy.LWW


class SnapshotCreate(BaseModel):
    """Request body for creating a snapshot."""

    snapshot_id: str
    parents: List[str] = Field(default_factory=list)
    tags: Dict[str, str] = Field(default_factory=dict)
    provenance: SnapshotProvenance
    merge_policy: MergePolicy = MergePolicy.LWW


class TilePayload(BaseModel):
    """Tile payload container."""

    bytes_b64: str = Field(..., description="Tile payload encoded as base64")


class TileMeta(BaseModel):
    """Metadata that describes a tile stored in the system."""

    tile_id: str
    stream: str
    snapshot_id: str
    level: int
    x: int
    y: int
    shape: Tuple[int, int, int]
    dtype: str
    parent_tile_id: Optional[str] = None
    halo: Optional[int] = None
    checksum: str
    size_bytes: int


class TileIngestRecord(BaseModel):
    """Single tile ingest request."""

    stream: str
    snapshot_id: str
    level: int
    x: int
    y: int
    shape: Tuple[int, int, int]
    dtype: str
    payload: TilePayload
    halo: Optional[int] = None
    parent_tile_id: Optional[str] = None


class TileIngestRequest(RootModel[List[TileIngestRecord]]):
    """Bulk tile ingest request."""

    root: List[TileIngestRecord]

    @model_validator(mode="after")
    def validate_non_empty(cls, model: "TileIngestRequest") -> "TileIngestRequest":
        if not model.root:
            msg = "Tile ingest payload must contain at least one tile"
            raise ValueError(msg)
        return model


class QueryRequest(BaseModel):
    """Request body for `/v1/query`."""

    goal: str
    snapshot_id: str
    stream: str = Field(default="kv_cache", description="Data stream to query")
    budget_ms: int = Field(gt=0, description="Maximum budget in milliseconds")
    max_tiles: int = Field(default=8, gt=0, le=32)
    level_range: Tuple[int, int] = Field(default=(2, 0), description="Inclusive pyramid levels to consider")

    @field_validator("level_range")
    def validate_level_range(cls, value: Tuple[int, int]) -> Tuple[int, int]:
        upper, lower = value
        if upper < lower:
            raise ValueError("level_range must be provided as (max_level, min_level)")
        return value


class QueryTile(BaseModel):
    """Tile suggestion returned as part of a query plan."""

    tile_id: str
    stream: str = Field(default="kv_cache")
    snapshot_id: str
    level: int
    x: int
    y: int


class QueryPlan(BaseModel):
    """Response model for `/v1/query`."""

    tile_ids: List[QueryTile]
    acceptance: float
    budget_ms: int


class QueryHint(BaseModel):
    """Prefetch hint payload."""

    query_id: str
    snapshot_id: str
    stream: str
    level_range: Tuple[int, int]
    bboxes: List[Tuple[int, int, int, int]]
    confidence: float


class QueryHints(RootModel[List[QueryHint]]):
    """Collection of query hints."""

    root: List[QueryHint]

    @model_validator(mode="after")
    def validate_hints(cls, model: "QueryHints") -> "QueryHints":
        if not model.root:
            raise ValueError("At least one hint is required")
        return model
