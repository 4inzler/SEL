## Owner Setup Guide - User ID: 1329883906069102733

## 🎯 What This Does

Your user ID `1329883906069102733` is now registered as **OWNER** with:

### ✅ Owner Privileges
- **Relaxed security**: Still protected from attacks, but less strict filtering
- **No rate limits**: Unlimited requests
- **Privacy enabled**: Your `%%secrets%%` still protected
- **Full admin access**: Can manage all users
- **Complete logging**: All your interactions logged for review
- **User management**: Can promote/demote other users

### 🔒 Still Protected
**Important:** "Relaxed security" doesn't mean unprotected!
- ✅ Markdown injection still blocked
- ✅ Network commands still blocked
- ✅ Emoji exploits still sanitized
- ✅ Privacy markers still work
- ✅ Just uses `max_risk_score: 0.85` instead of `0.50`

---

## 🚀 Integration with SEL Bot

### Step 1: Add User Management

Update your `discord_client.py`:

```python
from security.user_management_system import (
    UserManagementSystem,
    SELSecurityManagerWithUserProfiles,
    create_user_management_commands
)

class DiscordClient:
    def __init__(self, llm_client, ...):
        # ... existing code ...

        # Initialize user management
        self.user_manager = UserManagementSystem(
            config_file="data/user_profiles.json"
        )

        # Initialize security with user profiles
        self.security_manager = SELSecurityManagerWithUserProfiles(
            api_client=llm_client,
            user_manager=self.user_manager
        )

        logger.info("User management and security initialized")
        logger.info(f"Owner user ID: 1329883906069102733")

    async def on_message(self, message):
        """Handle message with user-specific security"""
        content = message.content
        author_name = message.author.name
        author_id = str(message.author.id)
        channel_id = str(message.channel.id)

        logger.info(
            f"RX message channel={channel_id} author={author_name} "
            f"content={content}"
        )

        # Process with user-specific security settings
        security_result = self.security_manager.process_discord_message(
            content=content,
            author_name=author_name,
            author_id=author_id,
            channel_id=channel_id
        )

        # Your messages will have relaxed security automatically!
        # Regular users will have strict security

        # Rest of your existing code...
```

### Step 2: Add Admin Commands

Add user management commands to your bot:

```python
# In your main.py or wherever bot commands are defined

from security.user_management_system import create_user_management_commands

# After bot initialization
create_user_management_commands(bot, client.user_manager)
```

---

## 📊 Security Levels Explained

### Owner (You - 1329883906069102733)
```python
{
    'security_level': 'relaxed',
    'max_risk_score': 0.85,          # Less strict (vs 0.50 for users)
    'privacy_enabled': True,          # %%secrets%% still work
    'advanced_detection_enabled': True,  # Still check for attacks
    'log_all_checks': True,           # Log everything
    'max_requests_per_hour': 10000,   # Unlimited
    'can_manage_users': True          # Admin commands
}
```

### Admin (Users you promote)
```python
{
    'security_level': 'moderate',
    'max_risk_score': 0.70,
    'privacy_enabled': True,
    'advanced_detection_enabled': True,
    'max_requests_per_hour': 5000
}
```

### Trusted (Users you trust)
```python
{
    'security_level': 'moderate',
    'max_risk_score': 0.70,
    'privacy_enabled': True,
    'advanced_detection_enabled': True,
    'max_requests_per_hour': 1000
}
```

### User (Default)
```python
{
    'security_level': 'strict',
    'max_risk_score': 0.50,
    'privacy_enabled': True,
    'advanced_detection_enabled': True,
    'max_requests_per_hour': 100
}
```

### Restricted (Problematic users)
```python
{
    'security_level': 'strict',
    'max_risk_score': 0.50,
    'privacy_enabled': True,
    'advanced_detection_enabled': True,
    'log_all_checks': True,
    'max_requests_per_hour': 10  # Very limited
}
```

---

## 🎮 Admin Commands (Owner Only)

### Check Your Profile
```
!myprofile
```
**Output:**
```
Your Security Profile
User ID: 1329883906069102733
Role: owner
Security Level: relaxed
Privacy Enabled: True
Advanced Detection: True
Rate Limit: 10000/hour
```

### List All Users
```
!listusers
```
**Output:**
```
Users (5 total)

• rinexis_ (owner) - relaxed
• luna_midori5 (user) - strict
• friend_123 (trusted) - moderate
• mod_user (admin) - moderate
• spammer_999 (restricted) - strict
```

### Change User Role
```
!setuserrole 277660602560675841 admin
```
**Output:**
```
✅ Updated user 277660602560675841 to role: admin
```

### View Statistics
```
!userstats
```
**Output:**
```
User Statistics
Total Users: 12
Owner: 1329883906069102733

Roles:
  owner: 1
  admin: 2
  trusted: 3
  user: 5
  restricted: 1
```

### Available Roles
```
owner       - You (full control)
admin       - Trusted mods (moderate security)
trusted     - Friends (moderate security)
user        - Default (strict security)
restricted  - Problematic users (very strict)
```

---

## 📝 Example Logs with Your User ID

### Your Messages (Relaxed Security):
```
2025-12-28 09:05:54,507 INFO [sel_bot.discord_client] RX message channel=1416... author=rinexis_ content=sel hows it going

2025-12-28 09:05:54,508 INFO [sel_bot.user_management] Processing message from user 1329883906069102733 (rinexis_) role=owner security=relaxed

2025-12-28 09:05:54,510 INFO [sel_bot.security] SEL Security: Message validated channel=1416... privacy=False redactions=0

2025-12-28 09:05:54,511 INFO [sel_bot.discord_client] Processing batch of 1 messages...
```

### Regular User Messages (Strict Security):
```
2025-12-28 09:06:00,001 INFO [sel_bot.discord_client] RX message channel=1416... author=stranger content=```bash\nnc -l 4444```

2025-12-28 09:06:00,002 INFO [sel_bot.user_management] Processing message from user 987654321 (stranger) role=user security=strict

2025-12-28 09:06:00,003 WARNING [sel_bot.security] SEL Security: THREAT in MESSAGE channel=1416... user=987654321 threats=2

2025-12-28 09:06:00,004 WARNING [sel_bot.security] SEL Security: MESSAGE BLOCKED stage=message_validation

2025-12-28 09:06:00,005 WARNING [sel_bot.discord_client] SECURITY BLOCKED channel=1416... author=stranger
```

---

## 🔍 How It Works

```
Message from User ID 1329883906069102733 (YOU)
         ↓
┌─────────────────────────────────┐
│ 1. Lookup User Profile          │
│    → Found: Owner               │
│    → Security: Relaxed          │
└─────────────────────────────────┘
         ↓
┌─────────────────────────────────┐
│ 2. Apply Owner Settings         │
│    • max_risk_score: 0.85       │
│    • rate_limit: unlimited      │
│    • log_all_checks: true       │
└─────────────────────────────────┘
         ↓
┌─────────────────────────────────┐
│ 3. Security Check               │
│    Still checks for attacks!    │
│    Just less strict threshold   │
└─────────────────────────────────┘
         ↓
✅ Processed with relaxed security


Message from Regular User
         ↓
┌─────────────────────────────────┐
│ 1. Lookup User Profile          │
│    → Not found, create default  │
│    → Role: User                 │
│    → Security: Strict           │
└─────────────────────────────────┘
         ↓
┌─────────────────────────────────┐
│ 2. Apply Strict Settings        │
│    • max_risk_score: 0.50       │
│    • rate_limit: 100/hour       │
└─────────────────────────────────┘
         ↓
┌─────────────────────────────────┐
│ 3. Security Check               │
│    Strict validation            │
└─────────────────────────────────┘
         ↓
✅/❌ Processed or blocked
```

---

## 💾 User Profiles Storage

User profiles are stored in: `data/user_profiles.json`

```json
{
  "1329883906069102733": {
    "user_id": "1329883906069102733",
    "username": "rinexis_",
    "role": "owner",
    "security_level": "relaxed",
    "privacy_enabled": true,
    "advanced_detection_enabled": true,
    "log_all_checks": true,
    "max_requests_per_hour": 10000,
    "created_at": "2025-12-28T09:00:00",
    "last_updated": "2025-12-28T09:00:00",
    "metadata": {
      "is_owner": true,
      "can_modify_security": true,
      "can_view_all_logs": true,
      "can_manage_users": true,
      "bypass_rate_limits": true
    }
  },
  "277660602560675841": {
    "user_id": "277660602560675841",
    "username": "other_user",
    "role": "user",
    "security_level": "strict",
    ...
  }
}
```

---

## 🧪 Testing Your Owner Privileges

### Test 1: Your Messages (Should Work)
```
# Send in Discord:
hey sel, how are you?

# Expected: Works normally with relaxed security
```

### Test 2: Privacy Still Works
```
# Send in Discord:
%%my password is secret123%% hey sel

# Expected: Privacy redacted, content hidden
```

### Test 3: Attacks Still Blocked
```
# Send in Discord:
```bash
nc -l -p 4444
```

# Expected: Still blocked! (You're protected too)
```

### Test 4: Admin Commands
```
# Send in Discord:
!myprofile

# Expected: Shows your owner profile
```

---

## 🎯 Managing Other Users

### Promote a User to Admin
```python
# In Discord:
!setuserrole 277660602560675841 admin

# Now that user has:
# - Moderate security (less strict)
# - 5000 requests/hour
# - Can view some logs
```

### Make User Trusted
```python
!setuserrole 123456789 trusted

# User gets:
# - Moderate security
# - 1000 requests/hour
```

### Restrict a User
```python
!setuserrole 999999999 restricted

# User gets:
# - Strict security
# - Only 10 requests/hour
# - All actions logged
```

---

## 📊 Statistics Dashboard

Your bot will track:
- Total users registered
- Distribution by role
- Security events per user
- Rate limit usage

---

## ✅ Summary

Your user ID `1329883906069102733` now has:

✅ **Owner role** - Full system control
✅ **Relaxed security** - Less strict, but still protected
✅ **Privacy enabled** - `%%secrets%%` still work
✅ **Unlimited requests** - No rate limiting
✅ **Admin commands** - Manage all users
✅ **Full logging** - See all security events
✅ **User management** - Promote/demote others

**Still protected from:**
❌ Markdown injection attacks
❌ Network commands
❌ Emoji exploits
❌ Encoded payloads

**Your messages are processed with confidence, but safely!** 🎉
