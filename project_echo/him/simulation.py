"""Simulation primitives that replace transformer-style processing with HIM."""
from __future__ import annotations

import base64
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from .models import SnapshotCreate, SnapshotProvenance, TileIngestRecord, TilePayload
from .storage import HierarchicalImageMemory


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9']+")


def _tokenize(text: str) -> List[str]:
    """Return normalised tokens for the given text."""

    return _TOKEN_PATTERN.findall(text.lower())


def _cosine_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    """Compute cosine similarity between two token sequences."""

    if not left or not right:
        return 0.0
    left_counts = Counter(left)
    right_counts = Counter(right)
    dot = sum(left_counts[token] * right_counts[token] for token in left_counts)
    if not dot:
        return 0.0
    left_norm = math.sqrt(sum(count * count for count in left_counts.values()))
    right_norm = math.sqrt(sum(count * count for count in right_counts.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


@dataclass(slots=True)
class HumanExperience:
    """Single observation/response pair stored in the hierarchy."""

    observation: str
    response: Optional[str]
    metadata: Dict[str, object]
    tile_id: str
    level: int
    x: int
    y: int

    @property
    def tokens(self) -> List[str]:
        return _tokenize(self.observation)


class SimulatedHumanModel:
    """A retrieval-centric simulator that stands in for transformer models.

    The simulator persists observations and the resulting responses inside the
    hierarchical image memory instead of relying on a conventional transformer
    architecture. At query time, the simulator performs retrieval over the
    stored experiences and surfaces the most compatible human response.
    """

    def __init__(
        self,
        store: HierarchicalImageMemory | None = None,
        *,
        snapshot_id: str = "simulated-human",
        stream: str = "human_experience",
        provenance: SnapshotProvenance | None = None,
    ) -> None:
        self.store = store or HierarchicalImageMemory()
        self.snapshot_id = snapshot_id
        self.stream = stream
        self._provenance = provenance or SnapshotProvenance(
            model="simulated_human", code_sha="development"
        )
        self._ensure_snapshot()
        self._experiences: List[HumanExperience] = list(self._load_experiences())
        self._next_index = max((exp.x for exp in self._experiences), default=-1) + 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def ingest(
        self,
        observation: str,
        *,
        response: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> HumanExperience:
        """Store a new observation/response pair within the hierarchy."""

        metadata = dict(metadata or {})
        payload = {
            "observation": observation,
            "response": response,
            "metadata": metadata,
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        tile = TileIngestRecord(
            stream=self.stream,
            snapshot_id=self.snapshot_id,
            level=0,
            x=self._next_index,
            y=0,
            shape=(len(observation), len(response or ""), 1),
            dtype="human/json",
            payload=TilePayload(bytes_b64=base64.b64encode(encoded).decode("utf-8")),
        )
        meta = self.store.put_tiles([tile])[0]
        experience = HumanExperience(
            observation=observation,
            response=response,
            metadata=metadata,
            tile_id=meta.tile_id,
            level=meta.level,
            x=meta.x,
            y=meta.y,
        )
        self._experiences.append(experience)
        self._next_index += 1
        return experience

    def generate(self, prompt: str) -> str:
        """Produce a response that mimics a human conversation partner."""

        if not self._experiences:
            return self._default_reply(prompt)

        prompt_tokens = _tokenize(prompt)
        scored = [
            (self._score(prompt_tokens, experience), experience)
            for experience in self._experiences
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_score, top_experience = scored[0]
        if top_score > 0 and top_experience.response:
            return top_experience.response
        return self._default_reply(prompt, fallback=top_experience)

    @property
    def experiences(self) -> Sequence[HumanExperience]:
        """Expose the cached experiences for inspection and testing."""

        return tuple(self._experiences)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _ensure_snapshot(self) -> None:
        if self.store.snapshot_exists(self.snapshot_id):
            return
        payload = SnapshotCreate(
            snapshot_id=self.snapshot_id,
            parents=[],
            tags={"purpose": "simulated_human"},
            provenance=self._provenance,
        )
        self.store.create_snapshot(payload)

    def _load_experiences(self) -> Iterable[HumanExperience]:
        metas = self.store.tiles_for_snapshot(self.snapshot_id, stream=self.stream)
        for meta in metas:
            stored = self.store.get_tile(meta.tile_id)
            payload = json.loads(stored.payload_path.read_bytes().decode("utf-8"))
            yield HumanExperience(
                observation=payload.get("observation", ""),
                response=payload.get("response"),
                metadata=payload.get("metadata", {}),
                tile_id=meta.tile_id,
                level=meta.level,
                x=meta.x,
                y=meta.y,
            )

    def _score(self, prompt_tokens: Sequence[str], experience: HumanExperience) -> float:
        return _cosine_similarity(prompt_tokens, experience.tokens)

    def _default_reply(
        self,
        prompt: str,
        *,
        fallback: Optional[HumanExperience] = None,
    ) -> str:
        if fallback and fallback.response:
            return fallback.response
        summary = " ".join(prompt.split()[:16])
        return f"I am reflecting on '{summary}' and forming a response as a human would."


__all__ = ["HumanExperience", "SimulatedHumanModel"]

