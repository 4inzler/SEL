"""
System Agent - DISABLED FOR SECURITY

This agent has been disabled to prevent shell command execution.
Original file renamed to system_agent.DISABLED.py

SECURITY: SEL should NOT have shell access in production environments.
"""

DESCRIPTION = "System access is disabled for security. SEL cannot execute shell commands."

async def run(prompt: str, user_id: str, **kwargs):
    """Disabled system agent - returns security message"""
    return {
        "success": False,
        "response": "🔒 System access is disabled for security. SEL cannot execute shell commands in this sandboxed environment.",
        "metadata": {
            "disabled": True,
            "reason": "Security: Shell execution disabled"
        }
    }
