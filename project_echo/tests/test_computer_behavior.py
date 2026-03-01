from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sel_bot.computer_behavior import ComputerBehaviorAnalyzer


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        sel_data_dir="./sel_data",
        sel_behavior_max_history_lines=500,
        sel_behavior_window_days=60,
    )


def test_analyze_and_save_profile(tmp_path: Path) -> None:
    history = tmp_path / "bash_history"
    history.write_text(
        "\n".join(
            [
                "git status",
                ": 1700000000:0;pytest -q",
                "- cmd: python script.py",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    scan_root = tmp_path / "project_echo"
    scan_root.mkdir(parents=True, exist_ok=True)
    (scan_root / "main.py").write_text("print('x')\n", encoding="utf-8")
    (scan_root / "README.md").write_text("notes\n", encoding="utf-8")

    analyzer = ComputerBehaviorAnalyzer(
        _settings(),
        repo_root=tmp_path,
        history_paths=[history],
        scan_roots=[scan_root],
    )

    snapshot = analyzer.analyze_and_save(trigger="test")
    profile = snapshot.profile

    assert snapshot.profile_path.exists()
    assert profile["trigger"] == "test"
    assert profile["shell"]["commands_total"] == 3
    assert profile["adaptation"]["preferred_reply_length"] == "long"
    assert profile["filesystem"]["files_considered"] >= 1
    assert "global_targets" in profile["adaptation"]
    assert "interaction_style" in profile["adaptation"]
    assert "adaptation_strength" in profile["adaptation"]
    assert len(profile["anonymized_host_id"]) == 16

    hint = analyzer.style_hint(profile)
    assert hint

    loaded = analyzer.load_profile()
    assert loaded.get("trigger") == "test"


def test_apply_global_tuning_updates_state() -> None:
    global_state = SimpleNamespace(
        preferred_length="medium",
        verbosity=0.45,
        continuation_keywords=["time"],
        emoji_rate=0.6,
        playfulness=0.6,
    )
    profile = {
        "adaptation": {
            "preferred_reply_length": "long",
            "technicality_bias": 0.9,
            "adaptation_strength": 0.9,
            "suggested_keywords": ["git", "pytest", "time"],
            "global_targets": {
                "emoji_rate": 0.1,
                "playfulness": 0.2,
            },
        }
    }

    changes = ComputerBehaviorAnalyzer.apply_global_tuning(global_state, profile)

    assert global_state.preferred_length == "long"
    assert global_state.verbosity > 0.45
    assert global_state.continuation_keywords[:3] == ["time", "git", "pytest"]
    assert "preferred_length" in changes
    assert "verbosity" in changes
    assert "continuation_keywords" in changes
    assert global_state.emoji_rate == 0.1
    assert global_state.playfulness == 0.2


def test_apply_global_tuning_handles_empty_profile() -> None:
    global_state = SimpleNamespace(
        preferred_length="medium",
        verbosity=0.5,
        continuation_keywords=[],
    )

    changes = ComputerBehaviorAnalyzer.apply_global_tuning(global_state, {})

    assert changes == {}
    assert ComputerBehaviorAnalyzer.style_hint({}) == ""


def test_environment_policy_alignment() -> None:
    profile = {
        "adaptation": {
            "active_hours_utc": [23, 0, 1],
            "technicality_bias": 0.8,
            "interaction_style": "technical",
            "active_rhythm": "night_owl",
        }
    }
    policy = ComputerBehaviorAnalyzer.environment_policy(profile, now_utc_hour=23)
    assert policy["alignment"] > 0.8
    assert policy["style_overrides"]["directness"] == "high"
