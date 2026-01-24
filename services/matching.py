"""
Ingredient Matching Service

Functions for normalizing ingredient names and finding matches in the database.
"""

import re
from constants import INGREDIENT_ALIASES, UNIT_CONVERSIONS, INGREDIENT_PREFERRED_UNITS


def convert_unit(quantity, from_unit, to_unit):
    """Convert quantity from one unit to another."""
    from_unit = from_unit.upper()
    to_unit = to_unit.upper()

    if from_unit == to_unit:
        return quantity, to_unit

    # Check if conversion is possible
    if from_unit not in UNIT_CONVERSIONS or to_unit not in UNIT_CONVERSIONS:
        return quantity, from_unit  # Can't convert, return original

    from_base, from_factor = UNIT_CONVERSIONS[from_unit]
    to_base, to_factor = UNIT_CONVERSIONS[to_unit]

    # Only convert if same base unit type (volume or weight)
    if from_base != to_base:
        return quantity, from_unit  # Different types, can't convert

    # Convert: from_unit -> base -> to_unit
    base_qty = quantity * from_factor
    new_qty = base_qty / to_factor

    return round(new_qty, 2), to_unit


def get_preferred_unit(ingredient_name):
    """Get the preferred unit for an ingredient based on keywords."""
    name_lower = ingredient_name.lower()
    for keyword, unit in INGREDIENT_PREFERRED_UNITS.items():
        if keyword in name_lower:
            return unit
    return None  # No preference


def standardize_unit(quantity, unit, ingredient_name):
    """Convert to preferred unit if one exists for this ingredient."""
    preferred = get_preferred_unit(ingredient_name)
    if preferred and preferred != unit.upper():
        new_qty, new_unit = convert_unit(quantity, unit, preferred)
        return new_qty, new_unit
    return quantity, unit


def normalize_ingredient_name(name):
    """Normalize ingredient name for matching."""
    # Lowercase and strip
    normalized = name.lower().strip()

    # Remove special characters (asterisks, etc.)
    normalized = re.sub(r'[*#@!]+', '', normalized)

    # Remove leading/trailing dashes, slashes, and punctuation
    normalized = normalized.strip('-/.,;: ')

    # Remove leading numbers and fractions that might be left over
    normalized = re.sub(r'^[\d\s/.-]+', '', normalized).strip()

    # Remove common descriptors (set for O(1) lookup)
    remove_words = {'fresh', 'dried', 'chopped', 'diced', 'sliced', 'minced',
                    'large', 'small', 'medium', 'whole', 'raw', 'cooked',
                    'boneless', 'skinless', 'organic', 'frozen', 'canned',
                    'a', 'an', 'the', 'of'}
    words = normalized.split()
    words = [w for w in words if w not in remove_words]
    normalized = ' '.join(words)

    # Singularize common plurals
    singular_map = {
        'eggs': 'egg',
        'onions': 'onion',
        'tomatoes': 'tomato',
        'potatoes': 'potato',
        'carrots': 'carrot',
        'peppers': 'pepper',
        'cloves': 'clove',
        'breasts': 'breast',
        'thighs': 'thigh',
        'slices': 'slice',
        'stalks': 'stalk',
        'leaves': 'leaf',
        'berries': 'berry',
        'apples': 'apple',
        'lemons': 'lemon',
        'limes': 'lime',
        'oranges': 'orange',
        'bananas': 'banana',
        'mushrooms': 'mushroom',
        'tortillas': 'tortilla',
        'noodles': 'noodle',
    }

    words = normalized.split()
    words = [singular_map.get(w, w) for w in words]

    # Handle generic -s plural if not in map (preserve words that end in 's' naturally)
    no_strip_s = {'cheese', 'rice', 'grass', 'molasses', 'hummus'}
    singularized = []
    for w in words:
        if w.endswith('s') and len(w) > 3 and w not in no_strip_s:
            singularized.append(w[:-1])
        else:
            singularized.append(w)
    words = singularized

    normalized = ' '.join(words)

    # Check exact aliases
    if normalized in INGREDIENT_ALIASES:
        return INGREDIENT_ALIASES[normalized]

    # Capitalize each word for display
    return ' '.join(word.capitalize() for word in normalized.split())


def find_ingredient_match(raw_name, db, Ingredient, IngredientSynonym):
    """
    Deterministic ingredient matching:
    1. Normalize the name (strip adjectives, singularize)
    2. Check IngredientSynonym table for exact match
    3. Check Ingredient table for exact match
    4. Return (ingredient, match_type) or (None, None) if no match

    match_type is 'synonym', 'exact', or None
    """
    normalized = normalize_ingredient_name(raw_name)
    normalized_lower = normalized.lower()

    # Check synonyms first (case-insensitive)
    synonym = IngredientSynonym.query.filter(
        db.func.lower(IngredientSynonym.synonym) == normalized_lower
    ).first()
    if synonym:
        return synonym.ingredient, 'synonym'

    # Check ingredients directly (case-insensitive)
    ingredient = Ingredient.query.filter(
        db.func.lower(Ingredient.name) == normalized_lower
    ).first()
    if ingredient:
        return ingredient, 'exact'

    # Also check against raw name for exact match (in case normalization removed important info)
    raw_lower = raw_name.strip().lower()
    if raw_lower != normalized_lower:
        ingredient = Ingredient.query.filter(
            db.func.lower(Ingredient.name) == raw_lower
        ).first()
        if ingredient:
            return ingredient, 'exact'

    return None, None


def get_ingredient_suggestions(normalized_name, Ingredient, limit=5):
    """
    Get ranked suggestions for an ingredient name.
    Returns list of (ingredient, score, match_reason) tuples.
    """
    suggestions = []
    normalized_lower = normalized_name.lower()
    words = set(normalized_lower.split())

    all_ingredients = Ingredient.query.all()
    for ing in all_ingredients:
        ing_lower = ing.name.lower()
        ing_words = set(ing_lower.split())

        # Exact match = highest score
        if ing_lower == normalized_lower:
            suggestions.append((ing, 100, 'exact'))
            continue

        # Word overlap scoring
        common_words = words & ing_words
        if common_words:
            # Score based on % of words matched (weighted by specificity)
            score = (len(common_words) / max(len(words), len(ing_words))) * 80
            suggestions.append((ing, score, 'partial'))

    # Sort by score descending
    suggestions.sort(key=lambda x: x[1], reverse=True)
    return suggestions[:limit]
