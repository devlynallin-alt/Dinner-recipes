"""
Services Package

Business logic modules for the recipe application.
"""

from .parsing import (
    float_to_fraction,
    normalize_fractions,
    parse_fraction,
    parse_ingredient,
)

from .cost import (
    convert_to_base_unit,
    calculate_ingredient_cost,
)

from .matching import (
    convert_unit,
    get_preferred_unit,
    standardize_unit,
    normalize_ingredient_name,
    find_ingredient_match,
    get_ingredient_suggestions,
)

from .shopping import (
    format_shopping_qty,
    generate_shopping_list,
)

__all__ = [
    # Parsing
    'float_to_fraction',
    'normalize_fractions',
    'parse_fraction',
    'parse_ingredient',
    # Cost
    'convert_to_base_unit',
    'calculate_ingredient_cost',
    # Matching
    'convert_unit',
    'get_preferred_unit',
    'standardize_unit',
    'normalize_ingredient_name',
    'find_ingredient_match',
    'get_ingredient_suggestions',
    # Shopping
    'format_shopping_qty',
    'generate_shopping_list',
]
