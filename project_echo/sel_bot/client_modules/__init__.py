"""
Discord Client Modules

Refactored from monolithic discord_client.py (1859 lines) into focused modules.

Modules:
- text_utils: Text processing utilities (clamping, keyword extraction, etc.)
- hormone_decay: Hormone decay loop management
- inactivity_tracker: User inactivity detection and pinging
- message_processor: Message handling and response logic
"""

from .text_utils import *
from .hormone_decay import *
from .inactivity_tracker import *

__all__ = [
    # Re-export key functions for backward compatibility
    "clamp",
    "extract_opener",
    "name_called",
    "safe_to_split_reply",
    "split_reply_for_cadence",
    "followup_delay",
    "extract_topic_keywords",
    "add_human_touches",
    "adjust_repeated_opener",
    "build_channel_dynamics",
    "match_agent_request",
    "bash_command_from_keywords",
    "is_authorized",
]
