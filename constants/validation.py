"""
Validation Constants

Contains whitelist values for validating user input to prevent
injection attacks and ensure data integrity.
"""

# Valid values for cost_formula field (whitelist for security)
VALID_COST_FORMULAS = {'WEIGHT', 'VOLUME', 'PORTION', 'PACKAGE', 'COUNT'}

# Valid values for base_unit field (whitelist for security)
VALID_BASE_UNITS = {'EA', 'G', 'KG', 'LB', 'OZ', 'ML', 'L', 'CUP', 'TBSP', 'TSP', 'CLOVE', 'HEAD', 'CAN'}

# Valid ingredient categories (whitelist for security)
VALID_CATEGORIES = {
    'Produce', 'Meat', 'Dairy', 'Bakery', 'Pantry', 'Frozen',
    'Beverages', 'Condiments', 'Spices', 'Canned', 'Other'
}

# Valid recipe categories
VALID_RECIPE_CATEGORIES = {
    'Dinner', 'Breakfast', 'Lunch', 'Dessert', 'Appetizer',
    'Side', 'Soup', 'Salad', 'Snack', 'Beverage', 'Archive'
}

# Valid difficulty levels
VALID_DIFFICULTIES = {'Easy', 'Medium', 'Hard'}

# Valid meal types for meal planning
VALID_MEAL_TYPES = {'Breakfast', 'Lunch', 'Dinner', 'Dessert', 'Snack'}

# Maximum field lengths for security
MAX_LENGTHS = {
    'ingredient_name': 200,
    'recipe_name': 200,
    'category': 50,
    'instructions': 50000,
    'source_url': 500,
    'ingredient_text': 500,
}

# Allowed image extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
