from sel_bot.vision_analysis import (
    VisionAnalysis,
    VisionObject,
    VisionText,
    apply_text_override,
    coerce_vision_analysis,
    render_vision_analysis,
)


def test_coerce_vision_analysis_from_dict() -> None:
    raw = {
        "summary": "A black cat sits on a sofa.",
        "objects": [
            {"label": "cat", "count": 1, "attributes": ["black"]},
            "sofa",
        ],
        "actions": ["sitting"],
        "text": {"present": True, "content": "HELLO", "language": "en", "legibility": "clear", "confidence": 0.9},
        "confidence": 0.8,
    }
    analysis = coerce_vision_analysis(raw)
    assert analysis.summary == "A black cat sits on a sofa."
    assert analysis.objects[0].label == "cat"
    assert analysis.objects[0].count == 1
    assert analysis.text.present is True
    assert analysis.text.content == "HELLO"
    assert analysis.confidence == 0.8


def test_coerce_vision_analysis_from_string() -> None:
    analysis = coerce_vision_analysis("A simple caption.")
    assert analysis.summary == "A simple caption."


def test_render_vision_analysis_compact() -> None:
    analysis = VisionAnalysis(
        summary="A cat on a sofa.",
        actions=["sitting"],
        objects=[VisionObject(label="cat", count=1)],
        text=VisionText(present=True, content="HELLO"),
    )
    rendered = render_vision_analysis(analysis)
    assert "Summary:" in rendered
    assert "Objects:" in rendered
    assert "Actions:" in rendered
    assert "Text:" in rendered


def test_apply_text_override_sets_text() -> None:
    analysis = VisionAnalysis(summary="Test image")
    apply_text_override(analysis, "OVERRIDE TEXT")
    assert analysis.text.present is True
    assert analysis.text.content == "OVERRIDE TEXT"
