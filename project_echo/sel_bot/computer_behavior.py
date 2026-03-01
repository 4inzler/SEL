"""Local computer-behavior analysis for adaptive Sel tuning."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _safe_read_lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []


def _normalize_history_line(line: str) -> str:
    raw = (line or "").strip()
    if not raw:
        return ""
    # zsh history format: ": 1700000000:0;command"
    if raw.startswith(": ") and ";" in raw:
        raw = raw.split(";", 1)[1].strip()
    # fish history format can include "- cmd: ..."
    if raw.startswith("- cmd:"):
        raw = raw.split(":", 1)[1].strip()
    return raw


def _command_family(command: str) -> str:
    if not command:
        return ""
    token = command.split()[0].strip().lower()
    if "/" in token:
        token = token.rsplit("/", 1)[-1]
    return token


def _anonymize(value: str) -> str:
    digest = hashlib.sha256(f"sel-profile:{value}".encode("utf-8")).hexdigest()
    return digest[:16]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class ComputerBehaviorSnapshot:
    profile_path: Path
    profile: Dict[str, Any]
    trigger: str


class ComputerBehaviorAnalyzer:
    """
    Analyze local shell + filesystem behavior and infer adaptation hints.
    """

    def __init__(
        self,
        settings: Any,
        *,
        repo_root: Optional[Path] = None,
        history_paths: Optional[List[Path]] = None,
        scan_roots: Optional[List[Path]] = None,
    ) -> None:
        self.settings = settings
        self.repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        data_dir = Path(getattr(settings, "sel_data_dir", "./sel_data")).expanduser()
        if not data_dir.is_absolute():
            data_dir = (self.repo_root / data_dir).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        self.profile_path = data_dir / "computer_behavior_profile.json"

        if history_paths is not None:
            self.history_paths = history_paths
        else:
            home = Path.home()
            self.history_paths = [
                home / ".bash_history",
                home / ".zsh_history",
                home / ".local" / "share" / "fish" / "fish_history",
            ]

        if scan_roots is not None:
            self.scan_roots = scan_roots
        else:
            self.scan_roots = [
                self.repo_root / "project_echo",
                self.repo_root / "agents",
                self.repo_root / "sel_data",
            ]

    def _max_history_lines(self) -> int:
        raw = getattr(self.settings, "sel_behavior_max_history_lines", 8000)
        try:
            value = int(raw)
        except Exception:
            value = 8000
        return max(200, min(200_000, value))

    def _window_days(self) -> int:
        raw = getattr(self.settings, "sel_behavior_window_days", 30)
        try:
            value = int(raw)
        except Exception:
            value = 30
        return max(3, min(365, value))

    @staticmethod
    def _sample_confidence(commands_total: int, files_considered: int) -> float:
        cmd_conf = min(1.0, max(0.0, float(commands_total) / 800.0))
        fs_conf = min(1.0, max(0.0, float(files_considered) / 400.0))
        return _clamp((cmd_conf * 0.55) + (fs_conf * 0.45), 0.0, 1.0)

    @staticmethod
    def _derive_rhythm(top_hours: List[int]) -> str:
        if not top_hours:
            return "unknown"
        night_hours = {22, 23, 0, 1, 2, 3, 4}
        morning_hours = {5, 6, 7, 8, 9, 10}
        day_hours = {11, 12, 13, 14, 15, 16, 17}
        evening_hours = {18, 19, 20, 21}
        sample = top_hours[:5]
        night_ratio = sum(1 for h in sample if h in night_hours) / len(sample)
        morning_ratio = sum(1 for h in sample if h in morning_hours) / len(sample)
        day_ratio = sum(1 for h in sample if h in day_hours) / len(sample)
        evening_ratio = sum(1 for h in sample if h in evening_hours) / len(sample)
        if night_ratio >= 0.45:
            return "night_owl"
        if morning_ratio >= 0.45:
            return "morning"
        if day_ratio >= 0.45:
            return "daytime"
        if evening_ratio >= 0.45:
            return "evening"
        return "mixed"

    @staticmethod
    def _derive_interaction_style(avg_tokens: float, technicality_bias: float) -> str:
        if avg_tokens <= 2.8:
            return "direct"
        if technicality_bias >= 0.65 or avg_tokens >= 6.8:
            return "technical"
        if avg_tokens >= 5.2:
            return "exploratory"
        return "balanced"

    @staticmethod
    def _derive_global_targets(
        *,
        technicality_bias: float,
        coding_ratio: float,
        media_ratio: float,
        browsing_ratio: float,
        gaming_ratio: float,
        rhythm: str,
    ) -> Dict[str, float]:
        rhythm_energy = {
            "night_owl": 0.42,
            "morning": 0.58,
            "daytime": 0.6,
            "evening": 0.5,
            "mixed": 0.5,
            "unknown": 0.5,
        }.get(rhythm, 0.5)
        social_ratio = _clamp(media_ratio + (gaming_ratio * 0.8) + (browsing_ratio * 0.45), 0.0, 1.0)
        direct_ratio = _clamp((coding_ratio * 0.85) + (technicality_bias * 0.35), 0.0, 1.0)
        targets = {
            "verbosity": _clamp(0.28 + (technicality_bias * 0.55), 0.2, 0.95),
            "emoji_rate": _clamp(0.14 + (social_ratio * 0.62) - (direct_ratio * 0.26), 0.0, 1.0),
            "teasing_level": _clamp(0.16 + (gaming_ratio * 0.30) + (media_ratio * 0.10) - (direct_ratio * 0.14), 0.0, 1.0),
            "playfulness": _clamp(0.26 + (social_ratio * 0.48) - (direct_ratio * 0.16), 0.0, 1.0),
            "empathy": _clamp(0.40 + ((1.0 - direct_ratio) * 0.28) + (browsing_ratio * 0.12), 0.0, 1.0),
            "randomness": _clamp(0.08 + (media_ratio * 0.26) + (gaming_ratio * 0.24) - (coding_ratio * 0.08), 0.0, 1.0),
            "confidence": _clamp(0.44 + (technicality_bias * 0.34), 0.0, 1.0),
            "vulnerability_level": _clamp(0.34 + ((1.0 - direct_ratio) * 0.24) + (rhythm_energy * 0.12), 0.0, 1.0),
        }
        return targets

    @staticmethod
    def _query_terms_from_text(text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", (text or "").lower())
        stop = {
            "search",
            "find",
            "look",
            "with",
            "from",
            "about",
            "http",
            "https",
            "www",
            "com",
            "net",
            "org",
            "query",
            "page",
            "result",
            "what",
            "when",
            "where",
            "which",
        }
        return [token for token in tokens if token not in stop]

    def _collect_web_behavior(self) -> Dict[str, Any]:
        log_path = self.profile_path.parent / "web_behavior_log.jsonl"
        if not log_path.exists():
            return {
                "events_total": 0,
                "top_domains": [],
                "top_query_terms": [],
                "avg_images_detected": 0.0,
                "vision_events": 0,
            }

        lines = _safe_read_lines(log_path)
        lines = lines[-2000:]
        domain_counts = Counter()
        term_counts = Counter()
        mode_counts = Counter()
        image_counts: List[int] = []
        vision_events = 0
        total_events = 0

        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except Exception:
                continue
            if not isinstance(event, dict):
                continue
            total_events += 1
            mode = str(event.get("mode", "")).strip().lower()
            if mode:
                mode_counts[mode] += 1
            query = str(event.get("query", "")).strip()
            for term in self._query_terms_from_text(query):
                term_counts[term] += 1
            domains = event.get("domains", [])
            if isinstance(domains, list):
                for domain in domains:
                    value = str(domain).strip().lower()
                    if value:
                        domain_counts[value] += 1
            image_count = event.get("image_count")
            try:
                image_total = int(image_count)
            except Exception:
                image_total = 0
            image_total = max(0, image_total)
            image_counts.append(image_total)
            if bool(event.get("vision_used", False)):
                vision_events += 1

        top_domains = [
            {"domain": domain, "count": count}
            for domain, count in domain_counts.most_common(8)
        ]
        top_terms = [
            {"term": term, "count": count}
            for term, count in term_counts.most_common(10)
        ]
        avg_images = 0.0
        if image_counts:
            avg_images = round(sum(image_counts) / len(image_counts), 3)
        return {
            "events_total": total_events,
            "mode_counts": dict(mode_counts),
            "top_domains": top_domains,
            "top_query_terms": top_terms,
            "avg_images_detected": avg_images,
            "vision_events": vision_events,
        }

    def _collect_shell_commands(self) -> List[str]:
        all_lines: List[str] = []
        for path in self.history_paths:
            if not path.exists() or not path.is_file():
                continue
            lines = _safe_read_lines(path)
            all_lines.extend(lines)
        trimmed = all_lines[-self._max_history_lines() :]
        commands: List[str] = []
        for line in trimmed:
            normalized = _normalize_history_line(line)
            if not normalized:
                continue
            commands.append(normalized)
        return commands

    @staticmethod
    def _command_category(command_name: str) -> str:
        coding = {
            "python",
            "python3",
            "pytest",
            "git",
            "uv",
            "poetry",
            "pip",
            "npm",
            "node",
            "cargo",
            "go",
            "make",
            "cmake",
            "gcc",
            "g++",
            "clang",
            "java",
            "javac",
            "docker",
            "docker-compose",
            "kubectl",
            "rg",
            "sed",
            "awk",
            "cat",
            "less",
            "tail",
            "head",
        }
        media = {"vlc", "mpv", "ffmpeg", "yt-dlp", "spotify"}
        browse = {"firefox", "chrome", "chromium", "brave", "wget", "curl"}
        gaming = {"steam", "lutris"}
        if command_name in coding:
            return "coding"
        if command_name in media:
            return "media"
        if command_name in browse:
            return "browsing"
        if command_name in gaming:
            return "gaming"
        return "other"

    def _collect_filesystem_activity(self) -> Dict[str, Any]:
        now = _utc_now()
        cutoff = now - dt.timedelta(days=self._window_days())
        hour_counts = Counter()
        weekday_counts = Counter()
        ext_counts = Counter()
        scanned = 0
        considered = 0

        for root in self.scan_roots:
            root_path = root.expanduser()
            if not root_path.exists():
                continue
            if root_path.is_file():
                paths = [root_path]
            else:
                paths = root_path.rglob("*")

            for path in paths:
                if not path.is_file():
                    continue
                scanned += 1
                if scanned > 120_000:
                    break
                try:
                    mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
                except Exception:
                    continue
                if mtime < cutoff:
                    continue
                considered += 1
                hour_counts[mtime.hour] += 1
                weekday_counts[mtime.weekday()] += 1
                ext = path.suffix.lower() or "(none)"
                ext_counts[ext] += 1

        top_hours = [hour for hour, _ in hour_counts.most_common(5)]
        top_weekdays = [day for day, _ in weekday_counts.most_common(4)]
        top_extensions = [
            {"extension": ext, "count": count}
            for ext, count in ext_counts.most_common(12)
        ]
        hour_hist = {str(hour): count for hour, count in sorted(hour_counts.items())}
        return {
            "files_scanned": scanned,
            "files_considered": considered,
            "top_active_hours_utc": top_hours,
            "top_active_weekdays": top_weekdays,
            "top_extensions": top_extensions,
            "hour_histogram_utc": hour_hist,
        }

    @staticmethod
    def _infer_reply_length(avg_tokens: float, coding_ratio: float) -> str:
        if avg_tokens <= 2.8 and coding_ratio < 0.35:
            return "short"
        if avg_tokens >= 7.0 or coding_ratio >= 0.55:
            return "long"
        return "medium"

    @staticmethod
    def _derive_keywords(top_commands: List[str], top_extensions: List[Dict[str, Any]]) -> List[str]:
        keywords: List[str] = []
        for cmd in top_commands:
            value = cmd.strip().lower()
            if not value:
                continue
            if value in keywords:
                continue
            keywords.append(value)
            if len(keywords) >= 10:
                break
        ext_map = {
            ".py": "python",
            ".rs": "rust",
            ".js": "javascript",
            ".ts": "typescript",
            ".md": "docs",
            ".json": "json",
            ".toml": "config",
            ".yml": "config",
            ".yaml": "config",
        }
        for entry in top_extensions:
            ext = str(entry.get("extension", "")).lower()
            mapped = ext_map.get(ext)
            if not mapped or mapped in keywords:
                continue
            keywords.append(mapped)
            if len(keywords) >= 14:
                break
        return keywords

    def analyze(self) -> Dict[str, Any]:
        now = _utc_now()
        shell_commands = self._collect_shell_commands()
        command_families = [_command_family(cmd) for cmd in shell_commands]
        command_families = [name for name in command_families if name]
        family_counts = Counter(command_families)
        category_counts = Counter(self._command_category(name) for name in command_families)
        total = max(1, len(command_families))
        avg_tokens = (
            sum(len(cmd.split()) for cmd in shell_commands) / max(1, len(shell_commands))
        )
        coding_ratio = category_counts.get("coding", 0) / total
        media_ratio = category_counts.get("media", 0) / total
        browsing_ratio = category_counts.get("browsing", 0) / total
        gaming_ratio = category_counts.get("gaming", 0) / total
        technicality_bias = _clamp(coding_ratio + (0.05 if avg_tokens > 5 else 0.0), 0.0, 1.0)

        fs_activity = self._collect_filesystem_activity()
        preferred_length = self._infer_reply_length(avg_tokens=avg_tokens, coding_ratio=coding_ratio)
        top_commands = [name for name, _ in family_counts.most_common(12)]
        keywords = self._derive_keywords(top_commands, fs_activity.get("top_extensions", []))
        rhythm = self._derive_rhythm(fs_activity.get("top_active_hours_utc", []))
        interaction_style = self._derive_interaction_style(avg_tokens, technicality_bias)
        sample_confidence = self._sample_confidence(
            commands_total=len(shell_commands),
            files_considered=int(fs_activity.get("files_considered", 0) or 0),
        )
        adaptation_strength = _clamp(0.35 + (sample_confidence * 0.55), 0.2, 0.95)

        web_behavior = self._collect_web_behavior()
        top_query_terms = [
            str(entry.get("term", "")).strip().lower()
            for entry in web_behavior.get("top_query_terms", [])
            if isinstance(entry, dict)
        ]
        top_query_terms = [term for term in top_query_terms if term]
        for term in top_query_terms[:6]:
            if term not in keywords:
                keywords.append(term)
        top_domains = [
            str(entry.get("domain", "")).strip().lower()
            for entry in web_behavior.get("top_domains", [])
            if isinstance(entry, dict)
        ]
        domain_hint_bonus = 0.0
        for domain in top_domains:
            if any(marker in domain for marker in ("github", "stackoverflow", "docs", "developer")):
                domain_hint_bonus += 0.02
        if domain_hint_bonus:
            technicality_bias = _clamp(technicality_bias + min(0.12, domain_hint_bonus), 0.0, 1.0)

        global_targets = self._derive_global_targets(
            technicality_bias=technicality_bias,
            coding_ratio=coding_ratio,
            media_ratio=media_ratio,
            browsing_ratio=browsing_ratio,
            gaming_ratio=gaming_ratio,
            rhythm=rhythm,
        )

        profile = {
            "generated_at_utc": now.isoformat(),
            "window_days": self._window_days(),
            "shell": {
                "history_paths": [str(path) for path in self.history_paths if path.exists()],
                "commands_total": len(shell_commands),
                "family_counts_top": [
                    {"command": name, "count": count}
                    for name, count in family_counts.most_common(15)
                ],
                "category_counts": dict(category_counts),
                "average_command_tokens": round(avg_tokens, 2),
            },
            "filesystem": fs_activity,
            "web_behavior": web_behavior,
            "adaptation": {
                "technicality_bias": round(technicality_bias, 3),
                "preferred_reply_length": preferred_length,
                "suggested_keywords": keywords,
                "active_hours_utc": fs_activity.get("top_active_hours_utc", []),
                "active_rhythm": rhythm,
                "interaction_style": interaction_style,
                "adaptation_strength": round(adaptation_strength, 3),
                "category_ratios": {
                    "coding": round(coding_ratio, 3),
                    "media": round(media_ratio, 3),
                    "browsing": round(browsing_ratio, 3),
                    "gaming": round(gaming_ratio, 3),
                },
                "global_targets": global_targets,
                "search_domains": top_domains[:8],
            },
            "anonymized_host_id": _anonymize(str(Path.home())),
        }
        return profile

    def analyze_and_save(self, *, trigger: str = "manual") -> ComputerBehaviorSnapshot:
        profile = self.analyze()
        payload = dict(profile)
        payload["trigger"] = trigger
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return ComputerBehaviorSnapshot(
            profile_path=self.profile_path,
            profile=payload,
            trigger=trigger,
        )

    def load_profile(self) -> Dict[str, Any]:
        if not self.profile_path.exists():
            return {}
        try:
            data = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def apply_global_tuning(global_state: Any, profile: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Apply adaptive tuning from behavior profile to global state.
        """
        changes: Dict[str, Dict[str, Any]] = {}
        adaptation = profile.get("adaptation", {}) if isinstance(profile, dict) else {}
        if not isinstance(adaptation, dict) or not adaptation:
            return changes

        preferred = str(adaptation.get("preferred_reply_length", "")).strip().lower()
        if preferred in {"short", "medium", "long"} and preferred != getattr(global_state, "preferred_length", None):
            old = getattr(global_state, "preferred_length", "medium")
            global_state.preferred_length = preferred
            changes["preferred_length"] = {"from": old, "to": preferred}

        try:
            technicality = float(adaptation.get("technicality_bias", 0.0))
        except Exception:
            technicality = 0.0
        technicality = _clamp(technicality, 0.0, 1.0)
        try:
            adaptation_strength = float(adaptation.get("adaptation_strength", 0.55))
        except Exception:
            adaptation_strength = 0.55
        adaptation_strength = _clamp(adaptation_strength, 0.2, 0.95)
        full_adaptation = bool(adaptation.get("full_adaptation", True))
        env_weight = 1.0 if full_adaptation else (0.30 + (adaptation_strength * 0.60))
        target_verbosity = 0.40 + (technicality * 0.30)
        old_verbosity = float(getattr(global_state, "verbosity", 0.5))
        new_verbosity = _clamp((old_verbosity * (1.0 - env_weight)) + (target_verbosity * env_weight), 0.2, 0.9)
        if abs(new_verbosity - old_verbosity) > 0.01:
            global_state.verbosity = new_verbosity
            changes["verbosity"] = {"from": round(old_verbosity, 3), "to": round(new_verbosity, 3)}

        if full_adaptation:
            global_targets = adaptation.get("global_targets", {})
            if isinstance(global_targets, dict):
                for field in (
                    "emoji_rate",
                    "teasing_level",
                    "playfulness",
                    "empathy",
                    "randomness",
                    "confidence",
                    "vulnerability_level",
                ):
                    if field not in global_targets or not hasattr(global_state, field):
                        continue
                    try:
                        target = float(global_targets.get(field))
                    except Exception:
                        continue
                    target = _clamp(target, 0.0, 1.0)
                    old_value = float(getattr(global_state, field))
                    blended = _clamp(
                        (old_value * (1.0 - env_weight)) + (target * env_weight),
                        0.0,
                        1.0,
                    )
                    if abs(blended - old_value) > 0.01:
                        setattr(global_state, field, blended)
                        changes[field] = {"from": round(old_value, 3), "to": round(blended, 3)}

        raw_keywords = adaptation.get("suggested_keywords", [])
        if isinstance(raw_keywords, list):
            extra_keywords = [str(x).strip().lower() for x in raw_keywords if str(x).strip()]
        else:
            extra_keywords = []
        current = list(getattr(global_state, "continuation_keywords", []) or [])
        limit = 60 if full_adaptation else 30
        merged = list(dict.fromkeys([*current, *extra_keywords]))[:limit]
        if merged != current:
            global_state.continuation_keywords = merged
            changes["continuation_keywords"] = {"from_count": len(current), "to_count": len(merged)}

        return changes

    @staticmethod
    def environment_policy(profile: Dict[str, Any], *, now_utc_hour: Optional[int] = None) -> Dict[str, Any]:
        adaptation = profile.get("adaptation", {}) if isinstance(profile, dict) else {}
        if not isinstance(adaptation, dict):
            return {}
        active_hours = adaptation.get("active_hours_utc", [])
        if not isinstance(active_hours, list):
            active_hours = []
        active_hours = [int(x) % 24 for x in active_hours if isinstance(x, int) or str(x).isdigit()]
        if now_utc_hour is None:
            now_utc_hour = _utc_now().hour
        now_utc_hour = int(now_utc_hour) % 24

        alignment = 0.5
        if active_hours:
            min_distance = min(
                min((now_utc_hour - hour) % 24, (hour - now_utc_hour) % 24)
                for hour in active_hours[:6]
            )
            alignment = _clamp(1.0 - (min_distance / 8.0), 0.15, 1.0)

        try:
            technicality = float(adaptation.get("technicality_bias", 0.0))
        except Exception:
            technicality = 0.0
        technicality = _clamp(technicality, 0.0, 1.0)
        interaction_style = str(adaptation.get("interaction_style", "balanced")).strip().lower()

        style_overrides: Dict[str, str] = {}
        if technicality >= 0.65:
            style_overrides.update({"directness": "high", "tone": "focused", "emoji_level": "low"})
        elif technicality <= 0.25:
            style_overrides.update({"tone": "casual"})
        if interaction_style == "direct":
            style_overrides["length"] = "short"
        elif interaction_style == "technical":
            style_overrides["directness"] = "high"

        max_sentences_delta = 0
        if alignment <= 0.35:
            max_sentences_delta = -1
        elif alignment >= 0.80:
            max_sentences_delta = 1

        return {
            "alignment": round(alignment, 3),
            "mode": str(adaptation.get("active_rhythm", "mixed")),
            "temp_multiplier": _clamp(0.82 + (alignment * 0.32), 0.68, 1.22),
            "max_chars_multiplier": _clamp(0.72 + (alignment * 0.58), 0.58, 1.28),
            "max_sentences_delta": max_sentences_delta,
            "force_single": alignment <= 0.30,
            "allow_split_boost": alignment >= 0.70,
            "style_overrides": style_overrides,
        }

    @staticmethod
    def style_hint(profile: Dict[str, Any]) -> str:
        adaptation = profile.get("adaptation", {}) if isinstance(profile, dict) else {}
        if not isinstance(adaptation, dict) or not adaptation:
            return ""
        length = str(adaptation.get("preferred_reply_length", "")).strip().lower()
        if length not in {"short", "medium", "long"}:
            length = ""
        try:
            technicality = float(adaptation.get("technicality_bias", 0.0))
        except Exception:
            technicality = 0.0
        technicality = max(0.0, min(1.0, technicality))
        keywords = adaptation.get("suggested_keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        keyword_text = ", ".join(str(k) for k in keywords[:4])
        rhythm = str(adaptation.get("active_rhythm", "")).strip().lower()
        interaction_style = str(adaptation.get("interaction_style", "")).strip().lower()
        parts: List[str] = []
        if technicality >= 0.5:
            parts.append("User behavior looks highly technical; prioritize pragmatic, tool-oriented phrasing.")
        elif technicality >= 0.3:
            parts.append("User behavior looks moderately technical; keep explanations practical.")
        elif technicality <= 0.2:
            parts.append("User behavior currently looks general-purpose; keep responses natural and low-friction.")
        if length:
            parts.append(f"Default reply length preference from computer behavior: {length}.")
        if interaction_style in {"direct", "technical", "balanced", "exploratory"}:
            parts.append(f"Interaction style inferred from environment: {interaction_style}.")
        if rhythm:
            parts.append(f"Active rhythm inferred from environment: {rhythm}.")
        if keyword_text:
            parts.append(f"Likely recurring topics/tools: {keyword_text}.")
        return " ".join(parts).strip()
