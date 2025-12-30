import json

from him import HierarchicalImageMemory, SimulatedHumanModel


def test_simulated_human_ingest_and_generate(tmp_path) -> None:
    store = HierarchicalImageMemory(tmp_path)
    model = SimulatedHumanModel(store=store, snapshot_id="session-1")

    model.ingest("hello there", response="Hi! It's nice to meet you.")
    model.ingest("what is your plan today?", response="I'm planning the next set of experiments.")

    reply = model.generate("hello friend")
    assert "nice" in reply or "Hi" in reply

    metas = store.tiles_for_snapshot("session-1", stream=model.stream)
    assert len(metas) == 2
    stored = store.get_tile_by_coordinate(
        stream=model.stream,
        snapshot_id="session-1",
        level=0,
        x=0,
        y=0,
    )
    payload = json.loads(stored.payload_path.read_bytes().decode("utf-8"))
    assert payload["observation"] == "hello there"
    assert payload["response"].startswith("Hi!")


def test_simulated_human_rehydrates_from_store(tmp_path) -> None:
    store = HierarchicalImageMemory(tmp_path)
    model = SimulatedHumanModel(store=store, snapshot_id="session-2")
    model.ingest("Describe the lab status", response="All systems are green.")

    restored = SimulatedHumanModel(store=store, snapshot_id="session-2")
    assert len(restored.experiences) == 1
    assert restored.generate("status of the lab") == "All systems are green."
