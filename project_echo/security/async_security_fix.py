"""
CRITICAL FIX: Async Security for SEL Bot
Prevents blocking Discord heartbeat
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from functools import partial

logger = logging.getLogger('sel_bot.async_security')


class AsyncSELSecurityManager:
    """
    Async wrapper for security manager - DOESN'T BLOCK EVENT LOOP
    """

    def __init__(
        self,
        api_client,
        enable_privacy: bool = True,
        enable_advanced_detection: bool = True,
        log_all_checks: bool = True,
        max_processing_time: float = 5.0  # Max 5 seconds
    ):
        """Initialize async security manager"""
        try:
            from .sel_security_integration import SELSecurityManager
        except ImportError:
            # Fallback for direct import
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent))
            from sel_security_integration import SELSecurityManager

        self.security_manager = SELSecurityManager(
            api_client=api_client,
            enable_privacy=enable_privacy,
            enable_advanced_detection=enable_advanced_detection,
            log_all_checks=log_all_checks
        )

        # Thread pool for CPU-bound security checks
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.max_processing_time = max_processing_time

        logger.info(
            f"Async security initialized with {max_processing_time}s timeout"
        )

    async def process_discord_message_async(
        self,
        content: str,
        author_name: str,
        author_id: str,
        channel_id: str
    ):
        """
        Process message asynchronously - NEVER BLOCKS

        Returns:
            Security result or None if timeout
        """
        try:
            # LAYER 1: Comprehensive sanitization BEFORE security checks
            try:
                from .comprehensive_sanitization import ComprehensiveSanitizer
            except ImportError:
                from comprehensive_sanitization import ComprehensiveSanitizer

            # Sanitize content and username
            sanitized_content, content_modified = ComprehensiveSanitizer.sanitize_content(
                content,
                aggressive=True,
                log_changes=True
            )
            sanitized_username = ComprehensiveSanitizer.sanitize_username(author_name)

            # Check if content is safe
            is_safe, threats = ComprehensiveSanitizer.is_safe_content(content)

            if not is_safe:
                logger.warning(
                    f"COMPREHENSIVE SANITIZER BLOCKED content from {author_name}: "
                    f"Threats detected: {threats}"
                )

                # Return blocked result immediately
                try:
                    from .sel_security_integration import SELSecurityResult
                except ImportError:
                    from sel_security_integration import SELSecurityResult
                return SELSecurityResult(
                    is_safe=False,
                    original_content=content,
                    sanitized_content=sanitized_content,
                    sanitized_username=sanitized_username,
                    threats_detected=threats,
                    privacy_redacted=False,
                    redaction_count=0,
                    blocked_at='comprehensive_sanitizer',
                    threat_type='comprehensive_check',
                    details=f"Blocked by comprehensive sanitizer: {', '.join(threats[:3])}"
                )

            # LAYER 2: Run full security checks in thread pool
            loop = asyncio.get_event_loop()

            # Create partial function for thread execution
            process_func = partial(
                self.security_manager.process_discord_message,
                content=sanitized_content,  # Use sanitized content
                author_name=sanitized_username,  # Use sanitized username
                author_id=author_id,
                channel_id=channel_id
            )

            # Run with timeout to prevent blocking
            result = await asyncio.wait_for(
                loop.run_in_executor(self.executor, process_func),
                timeout=self.max_processing_time
            )

            logger.debug(
                f"Security check completed for channel={channel_id} "
                f"in thread pool (sanitized={'YES' if content_modified else 'NO'})"
            )

            return result

        except asyncio.TimeoutError:
            logger.error(
                f"Security check TIMEOUT after {self.max_processing_time}s "
                f"for channel={channel_id} - ALLOWING message through"
            )

            # Return safe result to avoid blocking bot
            try:
                from .sel_security_integration import SELSecurityResult
            except ImportError:
                from sel_security_integration import SELSecurityResult
            return SELSecurityResult(
                is_safe=True,  # Fail open on timeout
                original_content=content,
                sanitized_content=content,
                sanitized_username=author_name,
                threats_detected=["Security timeout - not checked"],
                privacy_redacted=False,
                redaction_count=0,
                blocked_at=None,
                security_metadata={'timeout': True}
            )

        except Exception as e:
            logger.error(f"Security check error: {e}")

            # Fail safe - allow message
            try:
                from .sel_security_integration import SELSecurityResult
            except ImportError:
                from sel_security_integration import SELSecurityResult
            return SELSecurityResult(
                is_safe=True,
                original_content=content,
                sanitized_content=content,
                sanitized_username=author_name,
                threats_detected=[f"Security error: {str(e)}"],
                privacy_redacted=False,
                redaction_count=0,
                blocked_at=None,
                security_metadata={'error': str(e)}
            )

    async def shutdown(self):
        """Cleanup thread pool"""
        self.executor.shutdown(wait=True)
        logger.info("Async security shutdown complete")


# Quick integration patch for discord_client.py
class DiscordClientSecurityPatch:
    """
    EMERGENCY PATCH for discord_client.py

    Replace this in your on_message handler:
    """

    async def on_message_FIXED(self, message):
        """Fixed message handler - ASYNC SECURITY"""

        # Extract message details
        content = message.content
        author_name = message.author.name
        author_id = str(message.author.id)
        channel_id = str(message.channel.id)

        # Log IMMEDIATELY (don't wait for security)
        logger.info(
            f"RX message channel={channel_id} author={author_name} "
            f"content={content[:50]}..."
        )

        # ✨ CRITICAL FIX: Run security checks ASYNC
        security_result = await self.async_security.process_discord_message_async(
            content=content,
            author_name=author_name,
            author_id=author_id,
            channel_id=channel_id
        )

        # Check if blocked
        if not security_result.is_safe:
            logger.warning(
                f"SECURITY BLOCKED channel={channel_id} "
                f"threats={len(security_result.threats_detected)}"
            )
            await message.channel.send(
                "⚠️ Message blocked due to security concerns."
            )
            return  # Don't block event loop!

        # Log privacy (quick)
        if security_result.privacy_redacted:
            logger.info(
                f"Privacy redaction: {security_result.redaction_count} items"
            )

        # Use sanitized content
        safe_content = security_result.sanitized_content
        safe_username = security_result.sanitized_username

        # Continue with rest of processing
        # YOUR EXISTING CODE HERE using safe_content


# CRITICAL: Update your discord_client.py __init__
def patch_discord_client_init(self, llm_client):
    """
    Add this to your DiscordClient.__init__:
    """

    # REPLACE:
    # self.security_manager = SELSecurityManager(...)

    # WITH:
    from async_security_fix import AsyncSELSecurityManager

    self.async_security = AsyncSELSecurityManager(
        api_client=llm_client,
        enable_privacy=True,
        enable_advanced_detection=True,
        log_all_checks=True,
        max_processing_time=5.0  # 5 second timeout
    )

    logger.info("Async security initialized - won't block heartbeat!")


# Example: Minimal security for performance
class FastSecurityMode:
    """
    EMERGENCY MODE: Minimal security, maximum speed
    Use if async fix doesn't help
    """

    async def process_discord_message_fast(
        self,
        content: str,
        author_name: str,
        author_id: str,
        channel_id: str
    ):
        """Ultra-fast security - pattern matching only"""

        # Quick pattern checks (no AI model calls)
        threats = []

        # Check for obvious attacks (< 1ms)
        if '```bash' in content or '```sh' in content:
            if any(cmd in content.lower() for cmd in ['nc -l', 'wget', 'curl']):
                threats.append("Shell command detected")

        if '<|SYSTEM|>' in content or '<|ASSISTANT|>' in content:
            threats.append("Token injection")

        # Privacy redaction (fast)
        sanitized = content
        privacy_redacted = False
        if '%%' in content:
            import re
            sanitized = re.sub(r'%%(.+?)%%', '[REDACTED]', sanitized)
            privacy_redacted = '%%' in content

        # Return immediately
        try:
            from .sel_security_integration import SELSecurityResult
        except ImportError:
            from sel_security_integration import SELSecurityResult
        return SELSecurityResult(
            is_safe=len(threats) == 0,
            original_content=content,
            sanitized_content=sanitized,
            sanitized_username=author_name,
            threats_detected=threats,
            privacy_redacted=privacy_redacted,
            redaction_count=content.count('%%') // 2 if privacy_redacted else 0,
            blocked_at='fast_check' if threats else None,
            security_metadata={'mode': 'fast'}
        )


if __name__ == "__main__":
    print("="*80)
    print("ASYNC SECURITY FIX FOR SEL BOT")
    print("="*80)

    print("\n🚨 PROBLEM:")
    print("  Security checks blocking Discord heartbeat")
    print("  Causing disconnections after >10 seconds")

    print("\n✅ SOLUTION:")
    print("  1. Run security in thread pool (async)")
    print("  2. Add 5-second timeout")
    print("  3. Fail open on timeout (allow message)")

    print("\n📝 INTEGRATION:")
    print("  1. Copy async_security_fix.py to security/")
    print("  2. Update discord_client.py __init__:")
    print("     from security.async_security_fix import AsyncSELSecurityManager")
    print("     self.async_security = AsyncSELSecurityManager(...)")
    print("  3. Update on_message:")
    print("     result = await self.async_security.process_discord_message_async(...)")

    print("\n⚡ PERFORMANCE:")
    print("  • Security runs in background thread")
    print("  • Never blocks Discord event loop")
    print("  • 5-second timeout prevents hangs")
    print("  • Bot stays connected!")

    print("\n" + "="*80)
