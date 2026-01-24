"""
Unit Constants and Conversion Tables

Contains all unit mappings, conversion factors, and related constants
for ingredient parsing and cost calculations.
"""

# Unit mappings for ingredient parsing (lowercase input -> standard unit)
UNIT_MAPPINGS = {
    'pound': 'LB', 'pounds': 'LB', 'lb': 'LB', 'lbs': 'LB',
    'ounce': 'OZ', 'ounces': 'OZ', 'oz': 'OZ',
    'cup': 'CUP', 'cups': 'CUP', 'c': 'CUP',
    'tablespoon': 'TBSP', 'tablespoons': 'TBSP', 'tbsp': 'TBSP', 'tbs': 'TBSP', 'tb': 'TBSP',
    'teaspoon': 'TSP', 'teaspoons': 'TSP', 'tsp': 'TSP', 'ts': 'TSP',
    'gram': 'G', 'grams': 'G', 'g': 'G',
    'kilogram': 'KG', 'kilograms': 'KG', 'kg': 'KG',
    'milliliter': 'ML', 'milliliters': 'ML', 'ml': 'ML',
    'liter': 'L', 'liters': 'L', 'l': 'L',
    'clove': 'CLOVE', 'cloves': 'CLOVE',
    'head': 'HEAD', 'heads': 'HEAD',
    'slice': 'EA', 'slices': 'EA',
    'piece': 'EA', 'pieces': 'EA',
    'can': 'CAN', 'cans': 'CAN',
    'package': 'EA', 'packages': 'EA', 'pkg': 'EA',
    'bunch': 'EA', 'bunches': 'EA',
    'stalk': 'EA', 'stalks': 'EA',
    'sprig': 'EA', 'sprigs': 'EA',
    'pinch': 'EA', 'pinches': 'EA',
    'dash': 'EA', 'dashes': 'EA',
}

# Unit conversion factors (unit -> (base_unit, factor))
UNIT_CONVERSIONS = {
    # Volume: base = ML
    'CUP': ('ML', 236.588),
    'TBSP': ('ML', 14.787),
    'TSP': ('ML', 4.929),
    'L': ('ML', 1000),
    'ML': ('ML', 1),
    # Weight: base = G
    'LB': ('G', 453.592),
    'OZ': ('G', 28.3495),
    'KG': ('G', 1000),
    'G': ('G', 1),
}

# Volume conversions to ML
VOLUME_TO_ML = {'ML': 1, 'L': 1000, 'CUP': 236.588, 'TBSP': 14.787, 'TSP': 4.929}

# Weight conversions to G
WEIGHT_TO_G = {'G': 1, 'KG': 1000, 'OZ': 28.3495, 'LB': 453.592}

# Valid units for each formula type
WEIGHT_UNITS = {'G', 'KG', 'OZ', 'LB'}
VOLUME_UNITS = {'ML', 'L', 'CUP', 'TBSP', 'TSP'}

# Preferred units for specific ingredients (keyword -> preferred unit)
INGREDIENT_PREFERRED_UNITS = {
    # Liquids -> ML
    'milk': 'ML',
    'cream': 'ML',
    'water': 'ML',
    'broth': 'ML',
    'stock': 'ML',
    'juice': 'ML',
    'vinegar': 'ML',
    'wine': 'ML',
    'sauce': 'ML',
    'honey': 'ML',
    'syrup': 'ML',
    'yogurt': 'ML',
    # Oils -> TBSP (small amounts are easier to measure)
    'oil': 'TBSP',
    # Meats -> G
    'chicken': 'G',
    'beef': 'G',
    'pork': 'G',
    'turkey': 'G',
    'bacon': 'G',
    'sausage': 'G',
    'fish': 'G',
    'salmon': 'G',
    'shrimp': 'G',
    'ground': 'G',
    # Cheese -> G
    'cheese': 'G',
    'parmesan': 'G',
    'mozzarella': 'G',
    'cheddar': 'G',
    # Flour/Sugar -> G
    'flour': 'G',
    'sugar': 'G',
    'rice': 'G',
    'pasta': 'G',
    'oats': 'G',
}

# Common fractions for display (using precise values)
COMMON_FRACTIONS = {
    0.125: '1/8', 0.25: '1/4', 1/3: '1/3', 0.375: '3/8',
    0.5: '1/2', 0.625: '5/8', 2/3: '2/3', 0.75: '3/4', 0.875: '7/8'
}

# Unicode fraction characters mapping
UNICODE_FRACTIONS = {
    '\u00bd': 0.5,    # ½
    '\u2153': 1/3,    # ⅓
    '\u2154': 2/3,    # ⅔
    '\u00bc': 0.25,   # ¼
    '\u00be': 0.75,   # ¾
    '\u2155': 0.2,    # ⅕
    '\u2156': 0.4,    # ⅖
    '\u2157': 0.6,    # ⅗
    '\u2158': 0.8,    # ⅘
    '\u2159': 1/6,    # ⅙
    '\u215a': 5/6,    # ⅚
    '\u215b': 0.125,  # ⅛
    '\u215c': 0.375,  # ⅜
    '\u215d': 0.625,  # ⅝
    '\u215e': 0.875,  # ⅞
}
