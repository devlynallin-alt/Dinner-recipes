"""
Parsing Service

Functions for parsing ingredient text and fractions from recipe data.
"""

import re
from constants import UNIT_MAPPINGS, NOTE_KEYWORDS, UNICODE_FRACTIONS, COMMON_FRACTIONS


def float_to_fraction(value):
    """Convert float to fraction string for display."""
    if value is None or value == 0:
        return '0'
    # Check if it's a whole number
    if value == int(value):
        return str(int(value))
    # Split into whole and decimal parts
    whole = int(value)
    decimal = value - whole
    # Check common fractions (with tolerance)
    for dec, frac in COMMON_FRACTIONS.items():
        if abs(decimal - dec) < 0.02:
            if whole > 0:
                return f"{whole} {frac}"
            return frac
    # Fall back to decimal
    if whole > 0:
        return f"{value:.2f}".rstrip('0').rstrip('.')
    return f"{value:.2f}".rstrip('0').rstrip('.')


def normalize_fractions(text):
    """Replace Unicode fraction characters with decimal equivalents."""
    # First, normalize all whitespace (including non-breaking spaces) to regular spaces
    text = re.sub(r'[\s\u00a0\u2000-\u200b]+', ' ', text)

    for char, value in UNICODE_FRACTIONS.items():
        if char in text:
            # Check if preceded by a number (mixed fraction like "1½" or "1 ½")
            pattern = r'(\d+)\s*' + re.escape(char)
            match = re.search(pattern, text)
            if match:
                whole = float(match.group(1))
                replacement = str(whole + value)
                text = re.sub(pattern, replacement, text)
            else:
                text = text.replace(char, str(value))
    return text


def _parse_fraction_str(s):
    """Convert fraction string to float. Handles: 1, 1.5, 1/2, 1 1/2, ½, 1½"""
    s = s.strip()
    if not s:
        return 1.0

    # First normalize any Unicode fractions
    s = normalize_fractions(s)

    # Check for mixed fraction like "1 1/2"
    mixed_match = re.match(r'^(\d+)\s+(\d+)\s*/\s*(\d+)$', s)
    if mixed_match:
        whole = float(mixed_match.group(1))
        num = float(mixed_match.group(2))
        denom = float(mixed_match.group(3))
        return whole + (num / denom)

    # Check for simple fraction like "1/2"
    frac_match = re.match(r'^(\d+)\s*/\s*(\d+)$', s)
    if frac_match:
        num = float(frac_match.group(1))
        denom = float(frac_match.group(2))
        return num / denom

    # Otherwise it's a whole number or decimal
    try:
        return float(s)
    except (ValueError, TypeError):
        return 1.0


def parse_fraction(value, default=1.0, min_val=None):
    """
    Parse a fraction string like '1 1/2' or '1/4' into a float.
    Also handles plain numbers like '2' or '0.5'.
    """
    if not value:
        return default

    value = str(value).strip()
    total = 0.0

    try:
        # Try plain float first
        total = float(value)
    except ValueError:
        # Parse as fraction(s)
        parts = value.split()
        for part in parts:
            if '/' in part:
                try:
                    num, den = part.split('/')
                    total += float(num) / float(den)
                except (ValueError, ZeroDivisionError):
                    pass
            else:
                try:
                    total += float(part)
                except ValueError:
                    pass

    if total <= 0:
        total = default
    if min_val is not None and total < min_val:
        total = min_val

    return total


def parse_ingredient(text):
    """Parse ingredient text like '2 cups flour' into (quantity, unit, name)."""
    text = text.strip()
    if not text:
        return None, None, None

    # Normalize Unicode fractions first (e.g., ½ → 0.5, 1½ → 1.5)
    text = normalize_fractions(text)

    # Remove ALL bracketed content - parentheses, square brackets, curly braces
    # Run multiple times to handle nested/double brackets
    for _ in range(3):
        text = re.sub(r'\s*\([^)]*\)?', '', text)  # (content)
        text = re.sub(r'\s*\[[^\]]*\]?', '', text)  # [content]
        text = re.sub(r'\s*\{[^}]*\}?', '', text)   # {content}

    # Remove leading slashes, dashes, numbers that might be left
    text = re.sub(r'^[/\-\s]+', '', text)

    # Clean up any leftover bracket chars
    text = re.sub(r'[(){}\[\]]+', '', text)

    # Only remove comma content if it's a note (contains certain keywords)
    # Keep commas that are part of the ingredient name like "boneless, skinless"
    comma_match = re.search(r',\s*(.*)$', text)
    if comma_match:
        after_comma = comma_match.group(1).lower()
        if any(keyword in after_comma for keyword in NOTE_KEYWORDS):
            text = re.sub(r',.*$', '', text)

    # Try to extract quantity - order matters! Mixed fractions first, then simple fractions, then numbers
    qty_pattern = r'^(\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+\.?\d*)\s*'
    qty_match = re.match(qty_pattern, text)

    quantity = 1.0
    if qty_match:
        qty_str = qty_match.group(1).strip()
        text = text[qty_match.end():].strip()
        quantity = _parse_fraction_str(qty_str)

    # Aggressively remove any remaining fraction-like patterns from the start of text
    # Remove Unicode fractions
    for char in UNICODE_FRACTIONS.keys():
        text = text.replace(char, '')
    # Remove ASCII fractions like "1/2" anywhere at the start
    text = re.sub(r'^[\d\s/]+(?=\s*[a-zA-Z])', '', text)
    text = text.strip()

    # Try to extract unit
    unit = 'EA'
    words = text.split()
    if words:
        first_word = words[0].lower().rstrip('.')
        if first_word in UNIT_MAPPINGS:
            unit = UNIT_MAPPINGS[first_word]
            text = ' '.join(words[1:])

    # Clean up ingredient name
    name = text.strip()
    # Capitalize first letter of each word
    name = ' '.join(word.capitalize() for word in name.split())

    return quantity, unit, name
