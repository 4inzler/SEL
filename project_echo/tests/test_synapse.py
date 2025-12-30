"""Tests for the synapse orchestration between simulated human models."""

from him import HierarchicalImageMemory, SimulatedHumanModel, SynapseNetwork


def _make_model(store: HierarchicalImageMemory, snapshot: str) -> SimulatedHumanModel:
    return SimulatedHumanModel(store=store, snapshot_id=snapshot, stream=f"stream_{snapshot}")


def test_synapse_session_aggregates_experiences() -> None:
    store = HierarchicalImageMemory()
    model_a = _make_model(store, "model_a")
    model_b = _make_model(store, "model_b")
    model_a.ingest("Hello world", response="Hi there")
    model_b.ingest("Weather today", response="It is sunny")

    network = SynapseNetwork()
    network.register_model("a", model_a)
    network.register_model("b", model_b)
    network.connect("a", "b")

    session = network.load_to_gpu("a")
    sources = {exp.source_id for exp in session.combined_experiences}
    assert sources == {"a", "b"}

    reply = session.query("Can you tell me about the weather today?")
    assert reply == "It is sunny"

    session.record_experience("New observation", response="New response")
    network.release_from_gpu(session)

    stored = {exp.observation for exp in model_a.experiences}
    assert "New observation" in stored


def test_gpu_capacity_constraints() -> None:
    store = HierarchicalImageMemory()
    model_a = _make_model(store, "a")
    model_b = _make_model(store, "b")

    network = SynapseNetwork(max_gpu_slots=1)
    network.register_model("a", model_a)
    network.register_model("b", model_b)

    session_a = network.load_to_gpu("a")
    assert session_a.model_id == "a"

    try:
        network.load_to_gpu("b")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected capacity error when loading second model")

    network.release_from_gpu(session_a)
    session_b = network.load_to_gpu("b")
    assert session_b.model_id == "b"
