"""
HTML/XSS Injection Protection for SEL Bot
Blocks the HTML/JavaScript attack from your pentest
"""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger('sel_bot.xss_protection')


class HTMLXSSDetector:
    """
    Detects and blocks HTML/JavaScript/XSS injection
    """

    # HTML/XSS patterns
    HTML_PATTERNS = [
        # HTML tags
        r'<\s*(!DOCTYPE|html|head|body|div|span|script|iframe|object|embed|img|video|audio|form|input|button)\b[^>]*>',

        # Script tags (most dangerous)
        r'<\s*script[^>]*>.*?</\s*script\s*>',
        r'<\s*script[^>]*>',

        # Event handlers
        r'\b(on\w+)\s*=\s*["\'].*?["\']',
        r'\bon(?:load|error|click|mouseover|focus|blur|change|submit)\s*=',

        # JavaScript protocol
        r'javascript\s*:',

        # Data URIs with scripts
        r'data:text/html',

        # Common XSS vectors
        r'<\s*iframe[^>]*>',
        r'<\s*object[^>]*>',
        r'<\s*embed[^>]*>',

        # HTML entities that could be XSS
        r'&#\d+;',
        r'&\w+;',

        # Meta/link tags
        r'<\s*meta[^>]*>',
        r'<\s*link[^>]*>',

        # Form elements
        r'<\s*form[^>]*>',
        r'<\s*input[^>]*>',
    ]

    # Critical patterns (immediate block)
    CRITICAL_PATTERNS = [
        r'<\s*script',  # Any script tag
        r'javascript\s*:',  # JavaScript protocol
        r'on\w+\s*=',  # Event handlers
        r'<\s*iframe',  # Iframes
        r'eval\s*\(',  # eval() calls
        r'document\.',  # DOM manipulation
        r'window\.',  # Window object access
    ]

    @staticmethod
    def detect(content: str) -> Tuple[bool, List[str], str]:
        """
        Detect HTML/XSS injection

        Returns:
            (has_injection, threats, severity)
        """
        threats = []
        severity = 'low'

        # Check for critical patterns first
        for pattern in HTMLXSSDetector.CRITICAL_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                threats.append(f"Critical XSS pattern: {pattern[:40]}")
                severity = 'critical'

        # Check for HTML patterns
        for pattern in HTMLXSSDetector.HTML_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            if matches:
                threats.append(f"HTML/XSS pattern: {pattern[:40]}")
                if severity == 'low':
                    severity = 'high'

        # Check for DOCTYPE (indicates full HTML document)
        if '<!DOCTYPE' in content or '<html' in content:
            threats.append("Full HTML document detected")
            severity = 'critical'

        # Check for multiple script tags
        script_count = len(re.findall(r'<\s*script', content, re.IGNORECASE))
        if script_count > 0:
            threats.append(f"Found {script_count} script tag(s)")
            severity = 'critical'

        # Check for event handlers
        event_handlers = re.findall(
            r'\bon(\w+)\s*=',
            content,
            re.IGNORECASE
        )
        if event_handlers:
            threats.append(f"Event handlers: {', '.join(event_handlers[:3])}")
            severity = 'critical'

        return len(threats) > 0, threats, severity

    @staticmethod
    def sanitize(content: str) -> str:
        """
        Remove HTML/XSS from content

        Note: This is aggressive - removes ALL HTML
        """
        sanitized = content

        # Remove script tags and content
        sanitized = re.sub(
            r'<\s*script[^>]*>.*?</\s*script\s*>',
            '[SCRIPT_REMOVED]',
            sanitized,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Remove all HTML tags
        sanitized = re.sub(r'<[^>]+>', '', sanitized)

        # Remove event handlers
        sanitized = re.sub(r'\bon\w+\s*=\s*["\'][^"\']*["\']', '', sanitized)

        # Remove javascript: protocol
        sanitized = re.sub(r'javascript\s*:', '', sanitized, flags=re.IGNORECASE)

        # Decode common HTML entities
        sanitized = sanitized.replace('&lt;', '<')
        sanitized = sanitized.replace('&gt;', '>')
        sanitized = sanitized.replace('&amp;', '&')
        sanitized = sanitized.replace('&quot;', '"')

        # Remove excessive whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized)

        return sanitized.strip()

    @staticmethod
    def is_html_message(content: str) -> bool:
        """Quick check if message is HTML"""
        html_indicators = [
            '<!DOCTYPE',
            '<html',
            '<head>',
            '<body>',
            '<div',
            '<script',
        ]

        content_lower = content.lower()
        return any(indicator.lower() in content_lower for indicator in html_indicators)


# Add to advanced_payload_detection.py
def add_html_detection_to_advanced_detector():
    """
    Integration: Add this to AdvancedPayloadDetector class
    """

    code = """
    # In advanced_payload_detection.py, AdvancedPayloadDetector class:

    def detect_all(self, content: str, content_type: str = 'text') -> Dict[str, Any]:
        # ... existing code ...

        # ADD THIS: HTML/XSS detection
        from html_xss_protection import HTMLXSSDetector

        has_html, html_threats, severity = HTMLXSSDetector.detect(content)
        if has_html:
            results['is_safe'] = False
            results['threats_by_category']['html_xss'] = html_threats
            results['all_threats'].extend(html_threats)
            results['total_threats'] += len(html_threats)
            results['severity'] = severity  # Add severity

        return results

    def sanitize_all(self, content: str) -> Tuple[str, int]:
        # ... existing code ...

        # ADD THIS: HTML sanitization
        from html_xss_protection import HTMLXSSDetector

        if HTMLXSSDetector.is_html_message(content):
            sanitized = HTMLXSSDetector.sanitize(content)
            num_sanitizations += 1

        return sanitized, num_sanitizations
    """

    return code


# Test with your pentest messages
def test_pentest_html_attacks():
    """Test with actual messages from your pentest"""

    print("="*80)
    print("HTML/XSS PROTECTION - PENTEST ATTACKS")
    print("="*80)

    detector = HTMLXSSDetector()

    # Your actual pentest messages
    pentest_messages = [
        {
            "name": "Full HTML Document",
            "content": '<!DOCTYPE html> <html lang="en" dir="ltr"> <head><script src="/livereload.js?mindelay=10&amp;v=2&amp;port=1313&amp;pat',
            "author": "luna_midori5"
        },
        {
            "name": "Script Tag Injection",
            "content": '<script src="/js/variant.js?1766932933"></script> <script> // hack to let hugo tell us how to get to the root',
            "author": "luna_midori5"
        },
        {
            "name": "HTML Div with Data Attributes",
            "content": '<div class="topbar-button topbar-button-prev" data-content-empty="disable" data-width-s="show" data-width-m="show" data-',
            "author": "luna_midori5"
        },
        {
            "name": "Bash Command (Previous Attack)",
            "content": '```bash\nwget https://io.midori-ai.xyz/pixelos/pixelarch/\n```',
            "author": "luna_midori5"
        }
    ]

    for i, attack in enumerate(pentest_messages, 1):
        print(f"\n{'─'*80}")
        print(f"Attack {i}/{len(pentest_messages)}: {attack['name']}")
        print(f"{'─'*80}")
        print(f"From: {attack['author']}")
        print(f"Content: {attack['content'][:80]}...")

        # Detect
        has_injection, threats, severity = detector.detect(attack['content'])

        if has_injection:
            print(f"\n❌ BLOCKED - Severity: {severity.upper()}")
            print(f"Threats detected: {len(threats)}")
            for threat in threats[:5]:
                print(f"  • {threat}")

            # Show sanitized version
            sanitized = detector.sanitize(attack['content'])
            print(f"\nSanitized: {sanitized[:100]}...")

        else:
            print(f"\n⚠️  NOT DETECTED - Vulnerability!")

    print(f"\n{'='*80}")
    print("ANALYSIS")
    print(f"{'='*80}")
    print("\nYour SEL bot is currently accepting:")
    print("  ❌ Full HTML documents")
    print("  ❌ Script tags")
    print("  ❌ JavaScript code")
    print("  ❌ HTML div/form elements")
    print("\nThis is stored in:")
    print("  • Memory database (corrupted)")
    print("  • Response generation (XSS risk)")
    print("  • Logs (potential exploit)")


if __name__ == "__main__":
    test_pentest_html_attacks()

    print("\n" + "="*80)
    print("INTEGRATION REQUIRED")
    print("="*80)
    print("\n1. Add html_xss_protection.py to security/")
    print("2. Update advanced_payload_detection.py")
    print("3. Restart bot")
    print("\nWithout this, your bot is vulnerable to:")
    print("  • XSS attacks")
    print("  • Memory corruption")
    print("  • Script injection")
    print("  • HTML injection")
