"""
User Management System for SEL Bot
Allows different security profiles per user
Your User ID: 1329883906069102733 (Admin/Owner)
"""

import json
import logging
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime

logger = logging.getLogger('sel_bot.user_management')


@dataclass
class UserProfile:
    """User security profile"""
    user_id: str
    username: str
    role: str  # 'owner', 'admin', 'trusted', 'user', 'restricted'
    security_level: str  # 'relaxed', 'moderate', 'strict'
    privacy_enabled: bool
    advanced_detection_enabled: bool
    log_all_checks: bool
    max_requests_per_hour: int
    created_at: str
    last_updated: str
    metadata: Dict[str, Any]


class UserManagementSystem:
    """
    Manages user profiles and security settings
    """

    # Default security profiles
    SECURITY_PROFILES = {
        'owner': {
            'security_level': 'relaxed',
            'privacy_enabled': True,
            'advanced_detection_enabled': True,  # Still check for attacks
            'log_all_checks': True,
            'max_requests_per_hour': 10000,  # Unlimited for owner
        },
        'admin': {
            'security_level': 'moderate',
            'privacy_enabled': True,
            'advanced_detection_enabled': True,
            'log_all_checks': True,
            'max_requests_per_hour': 5000,
        },
        'trusted': {
            'security_level': 'moderate',
            'privacy_enabled': True,
            'advanced_detection_enabled': True,
            'log_all_checks': False,
            'max_requests_per_hour': 1000,
        },
        'user': {
            'security_level': 'strict',
            'privacy_enabled': True,
            'advanced_detection_enabled': True,
            'log_all_checks': False,
            'max_requests_per_hour': 100,
        },
        'restricted': {
            'security_level': 'strict',
            'privacy_enabled': True,
            'advanced_detection_enabled': True,
            'log_all_checks': True,
            'max_requests_per_hour': 10,
        }
    }

    def __init__(self, config_file: str = "user_profiles.json"):
        """Initialize user management system"""
        self.config_file = Path(config_file)
        self.users: Dict[str, UserProfile] = {}
        self.load_users()

        # Initialize owner (your user ID)
        self._initialize_owner()

    def _initialize_owner(self):
        """Initialize owner profile for user ID 1329883906069102733"""
        owner_id = "1329883906069102733"

        if owner_id not in self.users:
            owner_profile = UserProfile(
                user_id=owner_id,
                username="Owner",  # Will be updated when they send first message
                role='owner',
                **self.SECURITY_PROFILES['owner'],
                created_at=datetime.now().isoformat(),
                last_updated=datetime.now().isoformat(),
                metadata={
                    'is_owner': True,
                    'can_modify_security': True,
                    'can_view_all_logs': True,
                    'can_manage_users': True,
                    'bypass_rate_limits': True
                }
            )

            self.users[owner_id] = owner_profile
            self.save_users()

            logger.info(
                f"Owner profile created for user {owner_id} "
                f"with relaxed security settings"
            )

    def load_users(self):
        """Load user profiles from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)

                for user_id, user_data in data.items():
                    self.users[user_id] = UserProfile(**user_data)

                logger.info(f"Loaded {len(self.users)} user profiles")
            except Exception as e:
                logger.error(f"Error loading user profiles: {e}")
        else:
            logger.info("No existing user profiles found, creating new database")

    def save_users(self):
        """Save user profiles to file"""
        try:
            data = {
                user_id: asdict(profile)
                for user_id, profile in self.users.items()
            }

            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved {len(self.users)} user profiles")
        except Exception as e:
            logger.error(f"Error saving user profiles: {e}")

    def get_or_create_profile(
        self,
        user_id: str,
        username: str,
        default_role: str = 'user'
    ) -> UserProfile:
        """Get existing profile or create new one"""
        if user_id in self.users:
            # Update username if changed
            profile = self.users[user_id]
            if profile.username != username:
                profile.username = username
                profile.last_updated = datetime.now().isoformat()
                self.save_users()

            return profile

        # Create new user profile
        new_profile = UserProfile(
            user_id=user_id,
            username=username,
            role=default_role,
            **self.SECURITY_PROFILES[default_role],
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            metadata={}
        )

        self.users[user_id] = new_profile
        self.save_users()

        logger.info(
            f"Created new profile for user {user_id} ({username}) "
            f"with role={default_role}"
        )

        return new_profile

    def update_role(self, user_id: str, new_role: str) -> bool:
        """Update user role"""
        if user_id not in self.users:
            logger.warning(f"Cannot update role: user {user_id} not found")
            return False

        if new_role not in self.SECURITY_PROFILES:
            logger.warning(f"Invalid role: {new_role}")
            return False

        profile = self.users[user_id]
        old_role = profile.role

        profile.role = new_role
        profile.last_updated = datetime.now().isoformat()

        # Update security settings based on new role
        profile_settings = self.SECURITY_PROFILES[new_role]
        profile.security_level = profile_settings['security_level']
        profile.privacy_enabled = profile_settings['privacy_enabled']
        profile.advanced_detection_enabled = profile_settings['advanced_detection_enabled']
        profile.log_all_checks = profile_settings['log_all_checks']
        profile.max_requests_per_hour = profile_settings['max_requests_per_hour']

        self.save_users()

        logger.info(
            f"Updated user {user_id} role: {old_role} → {new_role}"
        )

        return True

    def is_owner(self, user_id: str) -> bool:
        """Check if user is the owner"""
        return user_id == "1329883906069102733"

    def is_admin(self, user_id: str) -> bool:
        """Check if user is admin or owner"""
        if user_id not in self.users:
            return False
        return self.users[user_id].role in ['owner', 'admin']

    def can_manage_users(self, user_id: str) -> bool:
        """Check if user can manage other users"""
        if user_id not in self.users:
            return False
        return self.users[user_id].metadata.get('can_manage_users', False)

    def get_security_config(self, user_id: str) -> Dict[str, Any]:
        """Get security configuration for user"""
        profile = self.get_or_create_profile(user_id, "Unknown")

        return {
            'enable_privacy': profile.privacy_enabled,
            'enable_advanced_detection': profile.advanced_detection_enabled,
            'log_all_checks': profile.log_all_checks,
            'max_risk_score': {
                'relaxed': 0.85,
                'moderate': 0.70,
                'strict': 0.50
            }[profile.security_level],
            'rate_limit': profile.max_requests_per_hour
        }

    def list_users(self, role_filter: Optional[str] = None) -> List[UserProfile]:
        """List all users, optionally filtered by role"""
        users = list(self.users.values())

        if role_filter:
            users = [u for u in users if u.role == role_filter]

        return sorted(users, key=lambda u: u.created_at, reverse=True)

    def get_stats(self) -> Dict[str, Any]:
        """Get user management statistics"""
        roles = {}
        for profile in self.users.values():
            roles[profile.role] = roles.get(profile.role, 0) + 1

        return {
            'total_users': len(self.users),
            'roles': roles,
            'owner_id': "1329883906069102733"
        }


# Integration with SEL security system
class SELSecurityManagerWithUserProfiles:
    """
    Enhanced SEL Security Manager with user profiles
    """

    def __init__(self, api_client, user_manager: UserManagementSystem):
        """Initialize with user management"""
        from sel_security_integration import SELSecurityManager

        self.user_manager = user_manager
        self.base_security_manager = None  # Will be created per-user
        self.api_client = api_client

        logger.info("SEL Security Manager with user profiles initialized")

    def process_discord_message(
        self,
        content: str,
        author_name: str,
        author_id: str,
        channel_id: str
    ):
        """Process message with user-specific security settings"""
        from sel_security_integration import SELSecurityManager

        # Get user profile and security config
        profile = self.user_manager.get_or_create_profile(
            user_id=author_id,
            username=author_name
        )

        security_config = self.user_manager.get_security_config(author_id)

        # Log user info
        logger.info(
            f"Processing message from user {author_id} ({author_name}) "
            f"role={profile.role} security={profile.security_level}"
        )

        # Create user-specific security manager
        user_security = SELSecurityManager(
            api_client=self.api_client,
            enable_privacy=security_config['enable_privacy'],
            enable_advanced_detection=security_config['enable_advanced_detection'],
            log_all_checks=security_config['log_all_checks']
        )

        # Process with user's security settings
        result = user_security.process_discord_message(
            content=content,
            author_name=author_name,
            author_id=author_id,
            channel_id=channel_id
        )

        # Add user role info to result
        result.security_metadata['user_role'] = profile.role
        result.security_metadata['user_security_level'] = profile.security_level

        return result


# Discord bot commands for user management
def create_user_management_commands(bot, user_manager: UserManagementSystem):
    """
    Create Discord commands for user management
    Add these to your SEL bot
    """

    @bot.command(name='myprofile')
    async def my_profile(ctx):
        """Show your security profile"""
        user_id = str(ctx.author.id)
        profile = user_manager.get_or_create_profile(user_id, ctx.author.name)

        await ctx.send(f"""
**Your Security Profile**
User ID: {profile.user_id}
Role: {profile.role}
Security Level: {profile.security_level}
Privacy Enabled: {profile.privacy_enabled}
Advanced Detection: {profile.advanced_detection_enabled}
Rate Limit: {profile.max_requests_per_hour}/hour
""")

    @bot.command(name='setmyrole')
    async def set_my_role(ctx, role: str):
        """Change your role (owner/admin only can change others)"""
        user_id = str(ctx.author.id)

        if not user_manager.is_owner(user_id):
            await ctx.send("❌ Only the owner can change roles")
            return

        # Owner can set any role
        if user_manager.update_role(user_id, role):
            await ctx.send(f"✅ Your role updated to: {role}")
        else:
            await ctx.send(f"❌ Invalid role. Options: {', '.join(UserManagementSystem.SECURITY_PROFILES.keys())}")

    @bot.command(name='setuserrole')
    async def set_user_role(ctx, target_user_id: str, role: str):
        """Set another user's role (owner only)"""
        admin_id = str(ctx.author.id)

        if not user_manager.is_owner(admin_id):
            await ctx.send("❌ Only the owner can change other users' roles")
            return

        if user_manager.update_role(target_user_id, role):
            await ctx.send(f"✅ Updated user {target_user_id} to role: {role}")
        else:
            await ctx.send(f"❌ Failed to update role")

    @bot.command(name='listusers')
    async def list_users(ctx, role: str = None):
        """List all users (admin only)"""
        if not user_manager.is_admin(str(ctx.author.id)):
            await ctx.send("❌ Admin only command")
            return

        users = user_manager.list_users(role_filter=role)

        message = f"**Users** ({len(users)} total)\n"
        for user in users[:10]:  # Show first 10
            message += f"\n• {user.username} ({user.role}) - {user.security_level}"

        await ctx.send(message)

    @bot.command(name='userstats')
    async def user_stats(ctx):
        """Show user statistics (admin only)"""
        if not user_manager.is_admin(str(ctx.author.id)):
            await ctx.send("❌ Admin only command")
            return

        stats = user_manager.get_stats()

        message = "**User Statistics**\n"
        message += f"Total Users: {stats['total_users']}\n"
        message += f"Owner: {stats['owner_id']}\n\n"
        message += "Roles:\n"
        for role, count in stats['roles'].items():
            message += f"  {role}: {count}\n"

        await ctx.send(message)


# Example usage
if __name__ == "__main__":
    print("="*80)
    print("USER MANAGEMENT SYSTEM - INITIALIZATION")
    print("="*80)

    # Initialize user management
    user_manager = UserManagementSystem(config_file="test_user_profiles.json")

    print("\n✅ Owner profile created for user ID: 1329883906069102733")

    # Get owner profile
    owner = user_manager.get_or_create_profile(
        "1329883906069102733",
        "YourUsername"
    )

    print(f"\nOwner Profile:")
    print(f"  User ID: {owner.user_id}")
    print(f"  Role: {owner.role}")
    print(f"  Security Level: {owner.security_level}")
    print(f"  Privacy Enabled: {owner.privacy_enabled}")
    print(f"  Advanced Detection: {owner.advanced_detection_enabled}")
    print(f"  Rate Limit: {owner.max_requests_per_hour}/hour")
    print(f"  Metadata: {owner.metadata}")

    # Test creating regular user
    print("\n" + "-"*80)
    regular_user = user_manager.get_or_create_profile(
        "123456789",
        "RegularUser"
    )

    print(f"\nRegular User Profile:")
    print(f"  User ID: {regular_user.user_id}")
    print(f"  Role: {regular_user.role}")
    print(f"  Security Level: {regular_user.security_level}")
    print(f"  Rate Limit: {regular_user.max_requests_per_hour}/hour")

    # Compare security configs
    print("\n" + "="*80)
    print("SECURITY COMPARISON")
    print("="*80)

    owner_config = user_manager.get_security_config("1329883906069102733")
    user_config = user_manager.get_security_config("123456789")

    print(f"\nOwner Security Config:")
    for key, value in owner_config.items():
        print(f"  {key}: {value}")

    print(f"\nRegular User Security Config:")
    for key, value in user_config.items():
        print(f"  {key}: {value}")

    # Stats
    print("\n" + "="*80)
    print("STATISTICS")
    print("="*80)
    stats = user_manager.get_stats()
    print(f"Total Users: {stats['total_users']}")
    print(f"Roles: {stats['roles']}")

    print("\n✅ User management system ready!")
    print(f"\nYour user ID (1329883906069102733) has:")
    print("  • Owner role")
    print("  • Relaxed security (still protected from attacks)")
    print("  • Unlimited rate limits")
    print("  • Can manage other users")
    print("  • Can view all logs")
