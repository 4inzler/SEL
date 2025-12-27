"""Synapse orchestration for coordinating multiple simulated human models."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, MutableMapping, Optional, Sequence, Tuple

from .simulation import HumanExperience, SimulatedHumanModel

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9']+")


def _tokenize(text: str) -> List[str]:
    """Return a normalised bag-of-words representation for scoring."""

    return _TOKEN_PATTERN.findall(text.lower())


def _cosine_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    """Compute cosine similarity between two tokenised sequences."""

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
class SynapseExperience:
    """Wrapper tying a stored experience back to its source model."""

    source_id: str
    experience: HumanExperience

    @property
    def tokens(self) -> Sequence[str]:
        return self.experience.tokens


@dataclass
class SynapseSession:
    """Represents a model temporarily loaded into a GPU-like workspace."""

    network: "SynapseNetwork"
    model_id: str
    connected_ids: Tuple[str, ...]
    _experiences: Tuple[SynapseExperience, ...]
    _pending: List[Tuple[str, Optional[str], Dict[str, object]]] = field(default_factory=list)
    _closed: bool = False

    @property
    def combined_experiences(self) -> Sequence[SynapseExperience]:
        """Expose the context made available to the loaded model."""

        return self._experiences

    @property
    def closed(self) -> bool:
        return self._closed

    def record_experience(
        self,
        observation: str,
        *,
        response: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> None:
        """Queue an experience to be persisted when the session is released."""

        self._require_open()
        self._pending.append((observation, response, dict(metadata or {})))

    def query(self, prompt: str) -> str:
        """Retrieve the best matching response from the synapse context."""

        self._require_open()
        prompt_tokens = _tokenize(prompt)
        best_score = 0.0
        best_response: Optional[str] = None
        for synapse_experience in self._experiences:
            response = synapse_experience.experience.response
            if not response:
                continue
            score = _cosine_similarity(prompt_tokens, synapse_experience.tokens)
            if score > best_score:
                best_score = score
                best_response = response
        if best_response is not None:
            return best_response
        return self.network.models[self.model_id].generate(prompt)

    def flush(self) -> None:
        """Persist all pending experiences back to the underlying model."""

        self._require_open()
        model = self.network.models[self.model_id]
        for observation, response, metadata in self._pending:
            model.ingest(observation, response=response, metadata=metadata)
        self._pending.clear()

    def close(self, *, commit: bool = True) -> None:
        """Release the session back to the network, committing if requested."""

        if self._closed:
            return
        self.network.release_from_gpu(self, commit=commit)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Synapse session has already been closed")


class SynapseNetwork:
    """Coordinate multiple simulated human models via synaptic links."""

    def __init__(self, *, max_gpu_slots: Optional[int] = None) -> None:
        self.models: Dict[str, SimulatedHumanModel] = {}
        self._edges: MutableMapping[str, Dict[str, float]] = defaultdict(dict)
        self._sessions: Dict[str, SynapseSession] = {}
        self.max_gpu_slots = max_gpu_slots

    # ------------------------------------------------------------------
    # Graph management
    # ------------------------------------------------------------------
    def register_model(self, model_id: str, model: SimulatedHumanModel) -> None:
        """Register a model so it can participate in the network."""

        self.models[model_id] = model

    def connect(self, left_id: str, right_id: str, *, weight: float = 1.0) -> None:
        """Create a bidirectional synaptic connection between two models."""

        if left_id not in self.models or right_id not in self.models:
            raise KeyError("Both models must be registered before connecting them")
        self._edges[left_id][right_id] = weight
        self._edges[right_id][left_id] = weight

    def neighbors(self, model_id: str) -> Sequence[str]:
        """Return the connected model identifiers for the given node."""

        return tuple(self._edges.get(model_id, {}))

    # ------------------------------------------------------------------
    # GPU lifecycle management
    # ------------------------------------------------------------------
    def load_to_gpu(self, model_id: str) -> SynapseSession:
        """Load a model and its synapses into the simulated GPU workspace."""

        if model_id not in self.models:
            raise KeyError(f"Model '{model_id}' has not been registered")
        if model_id in self._sessions:
            return self._sessions[model_id]
        if self.max_gpu_slots is not None and len(self._sessions) >= self.max_gpu_slots:
            raise RuntimeError("No GPU slots available for additional models")

        connected_ids = self.neighbors(model_id)
        aggregated = list(self._gather_experiences(model_id, connected_ids))
        session = SynapseSession(
            network=self,
            model_id=model_id,
            connected_ids=tuple(connected_ids),
            _experiences=tuple(aggregated),
        )
        self._sessions[model_id] = session
        return session

    def release_from_gpu(self, session: SynapseSession, *, commit: bool = True) -> None:
        """Release a session, optionally committing queued experiences."""

        active = self._sessions.get(session.model_id)
        if active is not session:
            raise RuntimeError("Unknown or already released synapse session")
        if commit:
            session.flush()
        session._closed = True
        self._sessions.pop(session.model_id, None)

    def active_sessions(self) -> Sequence[SynapseSession]:
        """Return the currently loaded GPU sessions."""

        return tuple(self._sessions.values())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _gather_experiences(
        self, model_id: str, neighbor_ids: Sequence[str]
    ) -> Iterable[SynapseExperience]:
        for experience in self.models[model_id].experiences:
            yield SynapseExperience(source_id=model_id, experience=experience)
        for neighbor_id in neighbor_ids:
            for experience in self.models[neighbor_id].experiences:
                yield SynapseExperience(source_id=neighbor_id, experience=experience)


__all__ = ["SynapseExperience", "SynapseNetwork", "SynapseSession"]

