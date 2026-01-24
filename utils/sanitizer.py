"""
XSS Prevention / Input Sanitization Module

Sanitizes user input and externally fetched data to prevent XSS attacks.
"""

import html
import re
from urllib.parse import urlparse


def sanitize_text(text, max_length=10000):
    """
    Sanitize text by HTML-escaping special characters.

    This prevents XSS by ensuring that any HTML/JS in the text
    is displayed as literal text rather than being executed.

    Args:
        text: The text to sanitize (can be None)
        max_length: Maximum allowed length (default 10000)

    Returns:
        Sanitized string, truncated if necessary
    """
    if text is None:
        return ''

    if not isinstance(text, str):
        text = str(text)

    # Strip leading/trailing whitespace
    text = text.strip()

    # HTML escape special characters
    text = html.escape(text)

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + '...'

    return text


def sanitize_url(url):
    """
    Sanitize a URL by rejecting dangerous schemes.

    Prevents javascript:, data:, vbscript:, and other dangerous URL schemes
    that could execute code when used in href or src attributes.

    Args:
        url: The URL to validate (can be None)

    Returns:
        The URL if safe, empty string if unsafe or invalid
    """
    if not url:
        return ''

    if not isinstance(url, str):
        return ''

    url = url.strip()

    # Check for dangerous schemes (case-insensitive)
    dangerous_schemes = {
        'javascript', 'data', 'vbscript', 'file',
        'blob', 'about', 'chrome', 'moz-extension'
    }

    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()

        # Only allow http and https
        if scheme and scheme not in ('http', 'https', ''):
            return ''

        # Additional check for encoded javascript:
        url_lower = url.lower()
        for dangerous in dangerous_schemes:
            if dangerous + ':' in url_lower:
                return ''
            # Check for URL-encoded versions
            if dangerous.replace('a', '%61') in url_lower:
                return ''

    except Exception:
        return ''

    return url


def sanitize_recipe_name(name, max_length=200):
    """
    Sanitize a recipe name for safe storage and display.

    Args:
        name: The recipe name to sanitize
        max_length: Maximum allowed length (default 200)

    Returns:
        Sanitized recipe name
    """
    if not name:
        return 'Imported Recipe'

    if not isinstance(name, str):
        name = str(name)

    # Strip whitespace
    name = name.strip()

    # Remove control characters and null bytes
    name = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', name)

    # HTML escape
    name = html.escape(name)

    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name)

    # Truncate if too long
    if len(name) > max_length:
        name = name[:max_length-3] + '...'

    # Return default if empty after cleaning
    if not name:
        return 'Imported Recipe'

    return name


def sanitize_instructions(instructions, max_length=50000):
    """
    Sanitize recipe instructions.

    Preserves newlines for formatting but escapes HTML.

    Args:
        instructions: The instructions text
        max_length: Maximum allowed length (default 50000)

    Returns:
        Sanitized instructions
    """
    if not instructions:
        return ''

    if not isinstance(instructions, str):
        instructions = str(instructions)

    # Strip leading/trailing whitespace
    instructions = instructions.strip()

    # HTML escape (this will escape < > & etc.)
    instructions = html.escape(instructions)

    # Truncate if too long
    if len(instructions) > max_length:
        instructions = instructions[:max_length] + '\n...(truncated)'

    return instructions


def sanitize_ingredient_text(text, max_length=500):
    """
    Sanitize an ingredient line from external sources.

    Args:
        text: Single ingredient line
        max_length: Maximum length (default 500)

    Returns:
        Sanitized ingredient text
    """
    if not text:
        return ''

    if not isinstance(text, str):
        text = str(text)

    # Strip whitespace
    text = text.strip()

    # Remove control characters
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)

    # HTML escape
    text = html.escape(text)

    # Truncate
    if len(text) > max_length:
        text = text[:max_length]

    return text
