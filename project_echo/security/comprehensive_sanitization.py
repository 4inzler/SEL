"""
Comprehensive Content Sanitization for SEL Bot
Removes all malicious patterns before processing or storage
"""

import re
import html
import unicodedata
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ComprehensiveSanitizer:
    """
    Multi-layer sanitization for all content types
    """

    # Dangerous HTML/JavaScript patterns
    HTML_PATTERNS = [
        r'<\s*script[^>]*>.*?</\s*script\s*>',  # Script tags with content
        r'<\s*script[^>]*>',  # Script tags
        r'<\s*/\s*script\s*>',  # Closing script tags
        r'<\s*iframe[^>]*>',  # Iframes
        r'<\s*object[^>]*>',  # Objects
        r'<\s*embed[^>]*>',  # Embeds
        r'<\s*applet[^>]*>',  # Applets
        r'<\s*meta[^>]*>',  # Meta tags
        r'<\s*link[^>]*>',  # Link tags
        r'<\s*style[^>]*>.*?</\s*style\s*>',  # Style tags
        r'<!DOCTYPE[^>]*>',  # Doctype
        r'<\s*html[^>]*>',  # HTML tag
        r'<\s*head[^>]*>',  # Head tag
        r'<\s*body[^>]*>',  # Body tag
        r'<\s*form[^>]*>',  # Forms
        r'<\s*input[^>]*>',  # Inputs
        r'<\s*button[^>]*>',  # Buttons
    ]

    # Event handlers and JavaScript
    JS_PATTERNS = [
        r'\bon\w+\s*=\s*["\'][^"\']*["\']',  # Event handlers
        r'\bon\w+\s*=\s*\w+',  # Event handlers without quotes
        r'javascript\s*:',  # JavaScript protocol
        r'vbscript\s*:',  # VBScript protocol
        r'data\s*:\s*text/html',  # Data URI HTML
        r'eval\s*\(',  # eval()
        r'setTimeout\s*\(',  # setTimeout
        r'setInterval\s*\(',  # setInterval
        r'Function\s*\(',  # Function constructor
    ]

    # Command injection patterns
    COMMAND_PATTERNS = [
        r';\s*(?:rm|dd|mkfs|fdisk|wget|curl)\s',  # Dangerous commands
        r'\|\s*(?:sh|bash|zsh|fish)\s',  # Piped shells
        r'`[^`]*`',  # Backticks
        r'\$\([^)]+\)',  # Command substitution
        r'&&\s*(?:rm|dd|mkfs)',  # Chained dangerous commands
    ]

    # Encoding patterns (for detecting obfuscation)
    ENCODING_PATTERNS = [
        r'\\x[0-9a-fA-F]{2}',  # Hex encoding
        r'\\u[0-9a-fA-F]{4}',  # Unicode escapes
        r'\\U[0-9a-fA-F]{8}',  # Long unicode
        r'%[0-9a-fA-F]{2}',  # URL encoding (multiple)
        r'&#\d+;',  # HTML entities (numeric)
        r'&[a-zA-Z]+;',  # HTML entities (named)
    ]

    # Dangerous unicode ranges
    DANGEROUS_UNICODE_RANGES = [
        (0x200B, 0x200F),  # Zero-width characters
        (0x202A, 0x202E),  # Direction overrides
        (0x2060, 0x2064),  # Invisible formatting
        (0xFEFF, 0xFEFF),  # Zero-width no-break space
        (0xFFF9, 0xFFFB),  # Interlinear annotation
    ]

    @staticmethod
    def sanitize_content(
        content: str,
        aggressive: bool = True,
        log_changes: bool = True
    ) -> Tuple[str, bool]:
        """
        Sanitize content with multiple layers

        Args:
            content: Content to sanitize
            aggressive: If True, removes all HTML. If False, only dangerous patterns
            log_changes: Log when sanitization occurs

        Returns:
            (sanitized_content, was_modified)
        """
        if not content:
            return content, False

        original = content
        modified = False

        # Layer 1: Remove dangerous HTML/JavaScript
        for pattern in ComprehensiveSanitizer.HTML_PATTERNS:
            new_content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
            if new_content != content:
                modified = True
                content = new_content

        # Layer 2: Remove JavaScript patterns
        for pattern in ComprehensiveSanitizer.JS_PATTERNS:
            new_content = re.sub(pattern, '', content, flags=re.IGNORECASE)
            if new_content != content:
                modified = True
                content = new_content

        # Layer 3: Remove command injection patterns
        for pattern in ComprehensiveSanitizer.COMMAND_PATTERNS:
            new_content = re.sub(pattern, '', content)
            if new_content != content:
                modified = True
                content = new_content

        # Layer 4: Aggressive HTML removal (all tags)
        if aggressive:
            new_content = re.sub(r'<[^>]+>', '', content)
            if new_content != content:
                modified = True
                content = new_content

        # Layer 5: Remove dangerous unicode
        content, unicode_modified = ComprehensiveSanitizer._sanitize_unicode(content)
        if unicode_modified:
            modified = True

        # Layer 6: Decode excessive encoding
        content, encoding_modified = ComprehensiveSanitizer._sanitize_encoding(content)
        if encoding_modified:
            modified = True

        # Layer 7: Normalize whitespace
        content = re.sub(r'\s+', ' ', content).strip()

        # Layer 8: Remove null bytes
        content = content.replace('\x00', '')

        if modified and log_changes:
            logger.warning(
                f"Content sanitized: {original[:50]}... -> {content[:50]}..."
            )

        return content, modified

    @staticmethod
    def _sanitize_unicode(content: str) -> Tuple[str, bool]:
        """Remove dangerous unicode characters and fix encoding issues"""
        modified = False

        # Additional problematic unicode characters
        BAD_CHARS = [
            "\ufffd",  # Replacement character (indicates encoding error)
            "\ufeff",  # Zero-width no-break space (BOM)
            "\u200b",  # Zero-width space
            "\u200c",  # Zero-width non-joiner
            "\u200d",  # Zero-width joiner
            "\u200e",  # Left-to-right mark
            "\u200f",  # Right-to-left mark
            "\u202a",  # Left-to-right embedding
            "\u202b",  # Right-to-left embedding
            "\u202c",  # Pop directional formatting
            "\u202d",  # Left-to-right override
            "\u202e",  # Right-to-left override
            "\u2060",  # Word joiner
            "\u2061",  # Function application
            "\u2062",  # Invisible times
            "\u2063",  # Invisible separator
            "\u2064",  # Invisible plus
            "\ufff9",  # Interlinear annotation anchor
            "\ufffa",  # Interlinear annotation separator
            "\ufffb",  # Interlinear annotation terminator
        ]

        # Remove known bad characters first
        temp_content = content
        for char in BAD_CHARS:
            if char in temp_content:
                temp_content = temp_content.replace(char, "")
                modified = True

        # Handle surrogate encoding issues
        try:
            # Try to encode/decode to catch invalid surrogates
            temp_content = temp_content.encode("utf-8", "surrogateescape").decode("utf-8", "ignore")
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Fallback: remove characters that can't be encoded
            temp_content = temp_content.encode("utf-8", "ignore").decode("utf-8", "ignore")
            modified = True

        # Remove dangerous unicode ranges
        result = []
        for char in temp_content:
            code = ord(char)
            is_dangerous = False

            for start, end in ComprehensiveSanitizer.DANGEROUS_UNICODE_RANGES:
                if start <= code <= end:
                    is_dangerous = True
                    modified = True
                    break

            if not is_dangerous:
                result.append(char)

        return ''.join(result), modified

    @staticmethod
    def _sanitize_encoding(content: str) -> Tuple[str, bool]:
        """Detect and limit excessive encoding"""
        modified = False

        # Count encoding patterns
        encoding_count = 0
        for pattern in ComprehensiveSanitizer.ENCODING_PATTERNS:
            matches = re.findall(pattern, content)
            encoding_count += len(matches)

        # If more than 5 encoded sequences, it might be obfuscation
        if encoding_count > 5:
            # Decode HTML entities
            try:
                decoded = html.unescape(content)
                if decoded != content:
                    modified = True
                    content = decoded
            except:
                pass

            # Remove excessive URL encoding
            if content.count('%') > 5:
                content = re.sub(r'%[0-9a-fA-F]{2}', '', content)
                modified = True

        return content, modified

    @staticmethod
    def sanitize_username(username: str) -> str:
        """Sanitize usernames to prevent display issues"""
        if not username:
            return "Unknown"

        # Remove dangerous unicode
        sanitized, _ = ComprehensiveSanitizer._sanitize_unicode(username)

        # Remove HTML
        sanitized = re.sub(r'<[^>]+>', '', sanitized)

        # Limit length
        if len(sanitized) > 32:
            sanitized = sanitized[:32]

        # Remove leading/trailing whitespace
        sanitized = sanitized.strip()

        # Fallback if empty
        if not sanitized:
            return "Unknown"

        return sanitized

    @staticmethod
    def sanitize_for_logging(content: str, max_length: int = 200) -> str:
        """
        Sanitize content before logging to prevent log injection
        """
        if not content:
            return ""

        # Remove newlines (prevents log injection)
        sanitized = content.replace('\n', '\\n').replace('\r', '\\r')

        # Remove control characters
        sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\t\n\r')

        # Truncate
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "..."

        return sanitized

    @staticmethod
    def sanitize_url(url: str) -> Optional[str]:
        """
        Sanitize and validate URLs
        """
        if not url:
            return None

        # Remove javascript: and data: protocols
        if re.match(r'^\s*(javascript|data|vbscript):', url, re.IGNORECASE):
            logger.warning(f"Blocked dangerous URL protocol: {url[:50]}")
            return None

        # Only allow http(s) and safe protocols
        if not re.match(r'^\s*(https?|ftp)://', url, re.IGNORECASE):
            # Not a URL, return as is
            return url

        return url

    @staticmethod
    def is_safe_content(content: str) -> Tuple[bool, list]:
        """
        Check if content is safe without modifying it

        Returns:
            (is_safe, list_of_threats)
        """
        threats = []

        # Check for HTML
        for pattern in ComprehensiveSanitizer.HTML_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                threats.append(f"HTML pattern: {pattern[:30]}")

        # Check for JavaScript
        for pattern in ComprehensiveSanitizer.JS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                threats.append(f"JavaScript pattern: {pattern[:30]}")

        # Check for commands
        for pattern in ComprehensiveSanitizer.COMMAND_PATTERNS:
            if re.search(pattern, content):
                threats.append(f"Command pattern: {pattern[:30]}")

        # Check for dangerous unicode
        for char in content:
            code = ord(char)
            for start, end in ComprehensiveSanitizer.DANGEROUS_UNICODE_RANGES:
                if start <= code <= end:
                    threats.append(f"Dangerous unicode: U+{code:04X}")
                    break

        return len(threats) == 0, threats

    @staticmethod
    def clean_item(item: any) -> str:
        """
        Clean any item (string, object, etc) for safe processing
        Handles encoding issues, surrogates, and unsafe tokens

        Args:
            item: Any item to clean (will be converted to string)

        Returns:
            Cleaned string safe for processing
        """
        # Convert to string
        temp_item = str(item)

        # Remove unsafe patterns first (basic pre-sanitization)
        unsafe_patterns = [
            '\x00',  # Null byte
            '\r\n',  # CRLF injection
            '\x1b',  # Escape sequences
            '\x7f',  # DEL character
        ]
        for pattern in unsafe_patterns:
            temp_item = temp_item.replace(pattern, '')

        # Handle surrogate encoding issues
        try:
            # Use surrogateescape to preserve data, then decode properly
            cleaned_item = temp_item.encode("utf-8", "surrogateescape").decode("utf-8", "ignore")
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Fallback: aggressive cleaning
            bad_chars = [
                "\ufffd",  # Replacement character
                "\ufeff",  # BOM
                "\u200b",  # Zero-width space
                "\u200c",  # Zero-width non-joiner
                "\u200d",  # Zero-width joiner
            ]
            for char in bad_chars:
                temp_item = temp_item.replace(char, "")

            # Try again with ignore
            try:
                cleaned_item = temp_item.encode("utf-8", "ignore").decode("utf-8", "ignore")
            except:
                # Last resort: filter to printable ASCII
                cleaned_item = ''.join(c for c in temp_item if 32 <= ord(c) <= 126 or c in '\n\t')

        # Apply comprehensive sanitization
        cleaned_item, _ = ComprehensiveSanitizer.sanitize_content(cleaned_item, aggressive=True)

        return cleaned_item


# Convenience functions
def sanitize(content: str, aggressive: bool = True) -> str:
    """Quick sanitization"""
    sanitized, _ = ComprehensiveSanitizer.sanitize_content(content, aggressive)
    return sanitized


def is_safe(content: str) -> bool:
    """Quick safety check"""
    safe, _ = ComprehensiveSanitizer.is_safe_content(content)
    return safe


def sanitize_all(content: str, username: str = None, url: str = None) -> dict:
    """Sanitize multiple fields at once"""
    result = {
        'content': sanitize(content),
        'content_modified': False,
    }

    if username:
        result['username'] = ComprehensiveSanitizer.sanitize_username(username)

    if url:
        result['url'] = ComprehensiveSanitizer.sanitize_url(url)

    return result
