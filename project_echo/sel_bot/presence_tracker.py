"""
Discord presence tracker for SEL
Tracks user status, activities, and provides context about who's around
"""
from typing import Dict, List, Optional
import discord
from datetime import datetime, timezone


class PresenceTracker:
    """Track Discord user presence and activity"""

    def __init__(self):
        self._cached_presence: Dict[int, Dict] = {}

    def update_presence(self, member: discord.Member):
        """
        Update cached presence for a member

        Args:
            member: Discord member object
        """
        presence_data = {
            "user_id": member.id,
            "name": member.display_name,
            "status": str(member.status),  # online, idle, dnd, offline
            "activities": [],
            "last_updated": datetime.now(timezone.utc)
        }

        # Extract activities
        for activity in member.activities:
            activity_data = {
                "type": activity.type.name if hasattr(activity, 'type') else "unknown",
                "name": activity.name if hasattr(activity, 'name') else "unknown"
            }

            # Add details based on activity type
            if isinstance(activity, discord.Game):
                activity_data["details"] = f"Playing {activity.name}"
            elif isinstance(activity, discord.Streaming):
                activity_data["details"] = f"Streaming {activity.name}"
                activity_data["url"] = activity.url if hasattr(activity, 'url') else None
            elif isinstance(activity, discord.Spotify):
                activity_data["details"] = f"Listening to {activity.title} by {activity.artist}"
            elif isinstance(activity, discord.CustomActivity):
                activity_data["details"] = activity.name or "Custom status"
            elif isinstance(activity, discord.Activity):
                # Rich presence
                if hasattr(activity, 'details') and activity.details:
                    activity_data["details"] = activity.details
                if hasattr(activity, 'state') and activity.state:
                    activity_data["state"] = activity.state

            presence_data["activities"].append(activity_data)

        self._cached_presence[member.id] = presence_data

    def get_presence(self, user_id: int) -> Optional[Dict]:
        """
        Get cached presence for a user

        Args:
            user_id: Discord user ID

        Returns:
            Presence data or None
        """
        return self._cached_presence.get(user_id)

    def get_online_users(self, guild: discord.Guild) -> List[Dict]:
        """
        Get all online users in a guild

        Args:
            guild: Discord guild object

        Returns:
            List of online user presence data
        """
        online = []
        for member in guild.members:
            if member.bot:
                continue  # Skip bots

            if member.status != discord.Status.offline:
                self.update_presence(member)
                presence = self.get_presence(member.id)
                if presence:
                    online.append(presence)

        return online

    def get_presence_summary(self, guild: discord.Guild, limit: int = 10) -> str:
        """
        Get formatted summary of who's online and what they're doing

        Args:
            guild: Discord guild object
            limit: Max users to show

        Returns:
            Formatted presence summary
        """
        online_users = self.get_online_users(guild)

        if not online_users:
            return "No one is currently online."

        # Sort by status priority (online > idle > dnd)
        status_priority = {"online": 0, "idle": 1, "dnd": 2, "offline": 3}
        online_users.sort(key=lambda u: status_priority.get(u["status"], 99))

        lines = [f"👥 **{len(online_users)} users online:**\n"]

        for user in online_users[:limit]:
            status_emoji = self._status_to_emoji(user["status"])
            name = user["name"]

            # Build activity string
            activity_str = ""
            if user["activities"]:
                activity = user["activities"][0]  # Show first activity
                details = activity.get("details", activity.get("name", ""))
                if details:
                    activity_str = f" - {details}"

            lines.append(f"{status_emoji} **{name}**{activity_str}")

        if len(online_users) > limit:
            lines.append(f"\n...and {len(online_users) - limit} more")

        return "\n".join(lines)

    def get_user_activity(self, user_id: int) -> str:
        """
        Get formatted activity string for a specific user

        Args:
            user_id: Discord user ID

        Returns:
            Formatted activity string
        """
        presence = self.get_presence(user_id)

        if not presence:
            return "User not found or offline"

        name = presence["name"]
        status = presence["status"]
        status_emoji = self._status_to_emoji(status)

        if not presence["activities"]:
            return f"{status_emoji} **{name}** is {status}"

        # Show all activities
        lines = [f"{status_emoji} **{name}** ({status}):"]
        for activity in presence["activities"]:
            details = activity.get("details", activity.get("name", "Unknown"))
            lines.append(f"  • {details}")

        return "\n".join(lines)

    def who_is_playing(self, game_name: str, guild: discord.Guild) -> List[str]:
        """
        Find who is playing a specific game

        Args:
            game_name: Game to search for
            guild: Discord guild

        Returns:
            List of user names playing the game
        """
        online_users = self.get_online_users(guild)
        players = []

        game_lower = game_name.lower()

        for user in online_users:
            for activity in user["activities"]:
                activity_name = activity.get("name", "").lower()
                details = activity.get("details", "").lower()

                if game_lower in activity_name or game_lower in details:
                    players.append(user["name"])
                    break

        return players

    def _status_to_emoji(self, status: str) -> str:
        """Convert status to emoji"""
        emoji_map = {
            "online": "🟢",
            "idle": "🟡",
            "dnd": "🔴",
            "offline": "⚫"
        }
        return emoji_map.get(status, "⚪")

    def get_context_for_prompt(self, guild: discord.Guild, limit: int = 5) -> str:
        """
        Get presence context for LLM prompt

        Args:
            guild: Discord guild
            limit: Max users to include

        Returns:
            Formatted context string
        """
        online_users = self.get_online_users(guild)

        if not online_users:
            return "DISCORD PRESENCE:\nNo one else is currently online.\n\n"

        # Sort by status
        status_priority = {"online": 0, "idle": 1, "dnd": 2}
        online_users.sort(key=lambda u: status_priority.get(u["status"], 99))

        lines = [f"DISCORD PRESENCE ({len(online_users)} online):"]

        for user in online_users[:limit]:
            name = user["name"]
            status = user["status"]

            # Get primary activity
            activity_str = ""
            if user["activities"]:
                activity = user["activities"][0]
                details = activity.get("details", activity.get("name", ""))
                if details:
                    activity_str = f" - {details}"

            lines.append(f"  • {name} ({status}){activity_str}")

        if len(online_users) > limit:
            lines.append(f"  ... and {len(online_users) - limit} more")

        lines.append("")  # Empty line
        return "\n".join(lines) + "\n"
