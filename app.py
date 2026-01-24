from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.orm import joinedload
import math
import random
import os
import re
import json
import requests
from bs4 import BeautifulSoup

# Security utilities
from utils.url_validator import safe_fetch, SSRFError
from utils.image_handler import validate_and_process_image, ImageValidationError
from utils.sanitizer import (
    sanitize_text, sanitize_url, sanitize_recipe_name,
    sanitize_instructions, sanitize_ingredient_text
)

# Common fractions for display (using precise values)
COMMON_FRACTIONS = {
    0.125: '1/8', 0.25: '1/4', 1/3: '1/3', 0.375: '3/8',
    0.5: '1/2', 0.625: '5/8', 2/3: '2/3', 0.75: '3/4', 0.875: '7/8'
}

def float_to_fraction(value):
    """Convert float to fraction string for display"""
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

def format_shopping_qty(item):
    """Format quantity string for shopping list display"""
    qty = item['qty']
    unit = item['unit']

    # For LB, show as LB | KG
    if unit == 'LB':
        kg = qty * 0.453592
        return f"{qty:.2f} LB|{kg:.2f} KG"

    # For KG, show as KG | LB
    if unit == 'KG':
        lb = qty / 0.453592
        return f"{qty:.2f} KG|{lb:.2f} LB"

    # For L, show as L | cups
    if unit == 'L':
        cups = qty * 1000 / 236.588
        return f"{qty:.2f} L|{float_to_fraction(cups)} cups"

    # For ML, show as ML | cups or tbsp
    if unit == 'ML':
        if qty <= 30:
            tbsp = qty / 14.787
            return f"{qty:.0f} ML|{float_to_fraction(tbsp)} tbsp"
        else:
            cups = qty / 236.588
            return f"{qty:.0f} ML|{float_to_fraction(cups)} cups"

    # For EA and others, just show the number
    if unit == 'EA':
        return f"{int(qty) if qty == int(qty) else qty}"

    return f"{qty} {unit}"

def calculate_ingredient_cost(ri):
    """
    Calculate the cost of a recipe ingredient.
    Recipe stores original units, so convert to base_unit for cost calculation.
    Note: calls convert_to_base_unit() which is defined later but available at runtime.
    """
    ing = ri.ingredient
    if not ing or ing.cost <= 0:
        return 0.0

    # Convert recipe quantity (in original unit) to base unit for cost calculation
    base_qty = convert_to_base_unit(ri.quantity, ri.unit, ing)
    cost_per_unit = ing.cost

    return round(base_qty * cost_per_unit, 2)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Register Jinja filter for fraction display
app.jinja_env.filters['fraction'] = float_to_fraction

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def safe_float(value, default=0.0, min_val=None, max_val=None):
    """Safely parse a float value with optional bounds."""
    try:
        result = float(value) if value else default
        if min_val is not None:
            result = max(min_val, result)
        if max_val is not None:
            result = min(max_val, result)
        return result
    except (ValueError, TypeError):
        return default


def safe_int(value, default=1, min_val=None, max_val=None):
    """Safely parse an integer value with optional bounds."""
    try:
        result = int(value) if value else default
        if min_val is not None:
            result = max(min_val, result)
        if max_val is not None:
            result = min(max_val, result)
        return result
    except (ValueError, TypeError):
        return default


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


# Valid values for cost_formula field (whitelist for security)
VALID_COST_FORMULAS = {'WEIGHT', 'VOLUME', 'PORTION', 'PACKAGE', 'COUNT'}

# Valid values for base_unit field (whitelist for security)
VALID_BASE_UNITS = {'EA', 'G', 'KG', 'LB', 'OZ', 'ML', 'L', 'CUP', 'TBSP', 'TSP', 'CLOVE', 'HEAD', 'CAN'}

# Valid ingredient categories (whitelist for security)
VALID_CATEGORIES = {
    'Produce', 'Meat', 'Dairy', 'Bakery', 'Pantry', 'Frozen',
    'Beverages', 'Condiments', 'Spices', 'Canned', 'Other'
}

# Keywords indicating notes to remove from ingredient text (set for O(1) lookup)
NOTE_KEYWORDS = {
    'optional', 'divided', 'or more', 'or less', 'to taste',
    'for serving', 'for garnish', 'at room temp', 'softened',
    'melted', 'chopped', 'diced', 'minced', 'sliced', 'cubed',
    'sifted', 'packed', 'beaten', 'room temperature', 'thawed',
    'drained', 'rinsed', 'peeled', 'seeded', 'cored', 'trimmed',
    'cut into', 'plus more', 'as needed', 'torn', 'shredded'
}

# Unit mappings for ingredient parsing
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

# Unit conversion factors (to base unit)
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

# Average weight per EA (in grams) for common ingredients
# Used for cost calculation when recipe uses EA but price is per LB
AVERAGE_WEIGHTS = {
    # Produce - Vegetables
    'TOMATO': 150,          # 1 medium tomato = 150g (0.33 lb)
    'ONION': 225,           # 1 medium onion = 225g (0.5 lb)
    'RED ONION': 225,
    'YELLOW ONION': 225,
    'WHITE ONION': 225,
    'GREEN ONION': 30,      # 1 green onion = 30g
    'SCALLION': 30,
    'CARROT': 70,           # 1 medium carrot = 70g (0.15 lb)
    'CELERY': 45,           # 1 stalk = 45g (0.1 lb)
    'POTATO': 225,          # 1 medium potato = 225g (0.5 lb)
    'RUSSET POTATO': 225,
    'YELLOW POTATO': 170,
    'RED POTATO': 170,
    'SWEET POTATO': 200,
    'BELL PEPPER': 150,     # 1 medium = 150g (0.33 lb)
    'RED PEPPER': 150,
    'YELLOW PEPPER': 150,
    'GREEN PEPPER': 150,
    'JALAPENO': 15,         # 1 jalapeno = 15g
    'CUCUMBER': 300,        # 1 medium = 300g (0.66 lb)
    'ZUCCHINI': 200,        # 1 medium = 200g
    'MUSHROOM': 18,         # 1 medium = 18g
    'GARLIC': 5,            # 1 clove = 5g
    'GINGER': 30,           # 1 inch piece = 30g
    'BROCCOLI': 600,        # 1 head = 600g (1.3 lb)
    'CAULIFLOWER': 900,     # 1 head = 900g (2 lb)
    'CABBAGE': 900,         # 1 head = 900g (2 lb)
    'LETTUCE': 300,         # 1 head = 300g
    'ROMAINE': 300,
    'SPINACH': 30,          # 1 cup = 30g
    'KALE': 30,
    'AVOCADO': 200,         # 1 medium = 200g
    'CORN': 200,            # 1 ear = 200g

    # Produce - Fruits
    'LEMON': 85,            # 1 lemon = 85g (0.19 lb)
    'LIME': 65,             # 1 lime = 65g (0.14 lb)
    'ORANGE': 180,          # 1 medium = 180g
    'APPLE': 180,           # 1 medium = 180g
    'BANANA': 120,          # 1 medium = 120g

    # Proteins
    'EGG': 50,              # 1 large egg = 50g
    'CHICKEN BREAST': 225,  # 1 breast = 225g (0.5 lb)
    'CHICKEN THIGH': 115,   # 1 thigh = 115g (0.25 lb)
    'BACON': 30,            # 1 slice = 30g
    'SAUSAGE': 100,         # 1 link = 100g

    # Dairy
    'BUTTER': 14,           # 1 tbsp = 14g

    # Bakery
    'BREAD': 30,            # 1 slice = 30g
    'TORTILLA': 45,         # 1 tortilla = 45g
    'BUN': 60,              # 1 bun = 60g
}

# Items priced per EA (not per LB) - don't convert to weight for cost
COST_PER_EA = {
    'LEMON', 'LIME', 'GREEN ONION', 'SCALLION', 'AVOCADO',
    'LETTUCE', 'ROMAINE', 'CABBAGE', 'CAULIFLOWER', 'BROCCOLI',
    'CUCUMBER', 'CELERY', 'CORN', 'BANANA', 'ORANGE', 'APPLE',
    'TORTILLA', 'BREAD', 'BUN', 'EGG',
}

# Minimum purchase quantities (keyword -> (min_qty, unit))
MINIMUM_PURCHASE = {
    'BEEF': (1, 'LB'),           # Minimum 1 LB
    'CHICKEN': (1, 'LB'),        # Minimum 1 LB
    'PORK': (1, 'LB'),           # Minimum 1 LB
    'EGG': (6, 'EA'),            # Minimum 6 eggs
    'BROTH': (1, 'L'),           # Minimum 1 L
    'STOCK': (1, 'L'),           # Minimum 1 L
}

# Preferred units for specific ingredients (keyword -> preferred unit)
# Liquids should be in ML, meats in G, oils in TBSP
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

# Ingredient name aliases (normalized name -> canonical name)
INGREDIENT_ALIASES = {
    'sourdough': 'Sourdough Bread',
    'sourdough bread': 'Sourdough Bread',
    'bread sourdough': 'Sourdough Bread',
    'white bread': 'White Bread',
    'bread white': 'White Bread',
    'ground beef': 'Ground Beef',
    'beef ground': 'Ground Beef',
    'minced beef': 'Ground Beef',
    'chicken breast': 'Chicken Breast',
    'breast chicken': 'Chicken Breast',
    'boneless skinless chicken breast': 'Chicken Breast',
    'boneless skinless chicken breasts': 'Chicken Breast',
    'chicken thigh': 'Chicken Thigh',
    'chicken thighs': 'Chicken Thigh',
    'boneless skinless chicken thigh': 'Chicken Thigh',
    'boneless skinless chicken thighs': 'Chicken Thigh',
    'boneless chicken thigh': 'Chicken Thigh',
    'boneless chicken thighs': 'Chicken Thigh',
    'green onion': 'Green Onion',
    'green onions': 'Green Onion',
    'scallion': 'Green Onion',
    'scallions': 'Green Onion',
    'spring onion': 'Green Onion',
    'spring onions': 'Green Onion',
    'bell pepper': 'Bell Pepper',
    'bell peppers': 'Bell Pepper',
    'garlic clove': 'Garlic',
    'garlic cloves': 'Garlic',
    'minced garlic': 'Garlic',
    'olive oil': 'Olive Oil',
    'extra virgin olive oil': 'Olive Oil',
    'vegetable oil': 'Vegetable Oil',
    'canola oil': 'Vegetable Oil',
    'heavy cream': 'Heavy Cream',
    'whipping cream': 'Heavy Cream',
    'heavy whipping cream': 'Heavy Cream',
    'sour cream': 'Sour Cream',
    'cream cheese': 'Cream Cheese',
    'parmesan cheese': 'Parmesan',
    'parmigiano': 'Parmesan',
    'parmigiano reggiano': 'Parmesan',
    'cheddar cheese': 'Cheddar Cheese',
    'mozzarella cheese': 'Mozzarella',
    'kosher salt': 'Salt',
    'sea salt': 'Salt',
    'table salt': 'Salt',
    'black pepper': 'Pepper',
    'ground pepper': 'Pepper',
    'ground black pepper': 'Pepper',
    # Eggs
    'egg': 'Egg',
    'eggs': 'Egg',
    'large egg': 'Egg',
    'large eggs': 'Egg',
    # Common items
    'yellow onion': 'Onion',
    'white onion': 'Onion',
    'red onion': 'Red Onion',
    'clove garlic': 'Garlic',
    'all purpose flour': 'Flour',
    'all-purpose flour': 'Flour',
    'ap flour': 'Flour',
    'granulated sugar': 'Sugar',
    'white sugar': 'Sugar',
    'brown sugar': 'Brown Sugar',
    'light brown sugar': 'Brown Sugar',
    'dark brown sugar': 'Brown Sugar',
    'unsalted butter': 'Butter',
    'salted butter': 'Butter',
}

def convert_unit(quantity, from_unit, to_unit):
    """Convert quantity from one unit to another"""
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
    """Get the preferred unit for an ingredient based on keywords"""
    name_lower = ingredient_name.lower()
    for keyword, unit in INGREDIENT_PREFERRED_UNITS.items():
        if keyword in name_lower:
            return unit
    return None  # No preference

def standardize_unit(quantity, unit, ingredient_name):
    """Convert to preferred unit if one exists for this ingredient"""
    preferred = get_preferred_unit(ingredient_name)
    if preferred and preferred != unit.upper():
        new_qty, new_unit = convert_unit(quantity, unit, preferred)
        return new_qty, new_unit
    return quantity, unit


# Volume conversions to ML
VOLUME_TO_ML = {'ML': 1, 'L': 1000, 'CUP': 236.588, 'TBSP': 14.787, 'TSP': 4.929}

# Weight conversions to G
WEIGHT_TO_G = {'G': 1, 'KG': 1000, 'OZ': 28.3495, 'LB': 453.592}

# Valid units for each formula type
WEIGHT_UNITS = {'G', 'KG', 'OZ', 'LB'}
VOLUME_UNITS = {'ML', 'L', 'CUP', 'TBSP', 'TSP'}


def convert_to_base_unit(qty, from_unit, ingredient):
    """
    Convert recipe quantity to ingredient's base unit using formula-specific logic.

    Formula types:
    - WEIGHT:  Converts weight units (G, OZ, LB, KG) to base_unit
    - VOLUME:  Converts volume units (ML, L, CUP, TBSP, TSP) to base_unit
    - PORTION: Converts volume/weight to portion count using portion_ml/portion_g
    - PACKAGE: Converts unit count to package fraction using pkg_count
               e.g., 2 eggs with pkg_count=12 → 2/12 = 0.167 packages
    - COUNT:   No conversion, returns quantity as-is (for single items like lemons)

    Args:
        qty: The quantity to convert
        from_unit: The unit the quantity is in (CUP, TBSP, G, EA, etc.)
        ingredient: The Ingredient object with cost_formula and base_unit

    Returns:
        Converted quantity in the ingredient's base_unit
    """
    formula = (getattr(ingredient, 'cost_formula', None) or 'COUNT').upper()
    base_unit = (ingredient.base_unit or 'EA').upper()
    from_unit = (from_unit or 'EA').upper()

    # If units already match, no conversion needed
    # EXCEPT for PACKAGE formula where EA means different things:
    # - Recipe EA = individual items (cloves, eggs)
    # - Package EA = whole packages (heads, cartons)
    if from_unit == base_unit and formula != 'PACKAGE':
        return qty

    # =========== WEIGHT FORMULA ===========
    # For meats, produce by weight - convert any weight unit to base_unit (KG or LB)
    if formula == 'WEIGHT':
        # Direct weight-to-weight conversion
        if from_unit in WEIGHT_TO_G and base_unit in WEIGHT_UNITS:
            grams = qty * WEIGHT_TO_G[from_unit]
            if base_unit == 'G':
                return round(grams, 2)
            elif base_unit == 'KG':
                return round(grams / 1000, 4)
            elif base_unit == 'LB':
                return round(grams / 453.592, 4)
            elif base_unit == 'OZ':
                return round(grams / 28.3495, 2)

        # If recipe uses count units (EA, BREAST, etc.), convert via piece weight
        # This handles "2 chicken breasts" → 2 × 250g = 500g → 0.5 KG
        if from_unit not in WEIGHT_TO_G and from_unit not in VOLUME_TO_ML:
            # First try ingredient's piece_weight_g, then fall back to lookup table
            piece_weight = getattr(ingredient, 'piece_weight_g', None)
            if not piece_weight:
                piece_weight = _get_average_weight(ingredient.name)

            if piece_weight and base_unit in WEIGHT_UNITS:
                grams = qty * piece_weight
                if base_unit == 'G':
                    return round(grams, 2)
                elif base_unit == 'KG':
                    return round(grams / 1000, 4)
                elif base_unit == 'LB':
                    return round(grams / 453.592, 4)
                elif base_unit == 'OZ':
                    return round(grams / 28.3495, 2)

        return qty  # Can't convert

    # =========== VOLUME FORMULA ===========
    # For liquids - convert any volume unit to base_unit (L or ML)
    if formula == 'VOLUME':
        if from_unit in VOLUME_TO_ML and base_unit in VOLUME_UNITS:
            ml = qty * VOLUME_TO_ML[from_unit]
            if base_unit == 'ML':
                return round(ml, 2)
            elif base_unit == 'L':
                return round(ml / 1000, 4)
            elif base_unit == 'CUP':
                return round(ml / 236.588, 4)
            elif base_unit == 'TBSP':
                return round(ml / 14.787, 2)
            elif base_unit == 'TSP':
                return round(ml / 4.929, 2)
        return qty  # Can't convert

    # =========== PORTION FORMULA ===========
    # For items like butter sticks - convert volume/weight to portion count
    if formula == 'PORTION':
        # Convert from volume to portions using portion_ml
        if from_unit in VOLUME_TO_ML and ingredient.portion_ml:
            ml = qty * VOLUME_TO_ML[from_unit]
            portions = ml / ingredient.portion_ml
            return round(portions, 4)

        # Convert from weight to portions using portion_g
        if from_unit in WEIGHT_TO_G and ingredient.portion_g:
            grams = qty * WEIGHT_TO_G[from_unit]
            portions = grams / ingredient.portion_g
            return round(portions, 4)

        # Already in EA (portions), return as-is
        if from_unit == 'EA':
            return qty

        return qty  # Can't convert

    # =========== PACKAGE FORMULA ===========
    # For items sold in packages with multiple units (eggs, garlic)
    # Convert count to fraction of package
    if formula == 'PACKAGE':
        if ingredient.pkg_count and ingredient.pkg_count > 0:
            # Any count-based unit (EA, CLOVE, HEAD, etc.) should be converted
            # If it's NOT a weight or volume unit, treat it as a count unit
            if from_unit not in WEIGHT_UNITS and from_unit not in VOLUME_UNITS:
                # Recipe calls for X units, package has pkg_count units
                # Return fraction of packages needed
                packages = qty / ingredient.pkg_count
                return round(packages, 4)
        return qty  # Can't convert or already in packages

    # =========== COUNT FORMULA (default) ===========
    # No conversion for counted items (lemons, cans) - return quantity as-is
    # 1 EA = 1 EA, cost = qty × cost_per_EA
    return qty


def _get_average_weight(ingredient_name):
    """Look up average weight in grams for an ingredient by name."""
    if not ingredient_name:
        return None
    name_upper = ingredient_name.upper()
    # Check exact match first
    if name_upper in AVERAGE_WEIGHTS:
        return AVERAGE_WEIGHTS[name_upper]
    # Check if any key is contained in the name
    for key, weight in AVERAGE_WEIGHTS.items():
        if key in name_upper:
            return weight
    return None

def normalize_ingredient_name(name):
    """Normalize ingredient name for matching"""
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


def find_ingredient_match(raw_name):
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


def get_ingredient_suggestions(normalized_name, limit=5):
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


# Unicode fraction characters mapping (using escape sequences for reliability)
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

def normalize_fractions(text):
    """Replace Unicode fraction characters with decimal equivalents"""
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

def parse_ingredient(text):
    """Parse ingredient text like '2 cups flour' into (quantity, unit, name)"""
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

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ============================================
# DATABASE MODELS
# ============================================

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    category = db.Column(db.String(50), default='Other', index=True)

    # COST FORMULA SYSTEM:
    # Each ingredient has a formula type that determines how to convert recipe units to cost
    #
    # WEIGHT  - Meats, produce sold by weight. Converts G/OZ/LB/KG to base_unit (KG or LB)
    # VOLUME  - Liquids like broth, milk. Converts ML/L/CUP/TBSP/TSP to base_unit (L or ML)
    # PORTION - Items sold by portion (butter sticks, cheese blocks).
    #           Uses portion_ml/portion_g to convert recipe volume/weight to portion count
    # PACKAGE - Items sold in packages with multiple units (eggs, garlic heads).
    #           Uses pkg_count to calculate fraction of package used.
    #           e.g., eggs: 12 per carton, recipe needs 2 → 2/12 = 0.167 packages
    # COUNT   - Items sold individually (lemons, cans). No conversion, 1 EA = 1 EA.
    cost_formula = db.Column(db.String(20), default='COUNT')

    # Base unit for cost calculation (what you pay per)
    # WEIGHT: KG, LB, G, OZ
    # VOLUME: L, ML
    # PORTION: EA (each portion, e.g., 1 stick)
    # PACKAGE: EA (each package, e.g., 1 carton)
    # COUNT: EA (each individual item)
    base_unit = db.Column(db.String(10), default='EA')

    # Cost per ONE base_unit
    cost = db.Column(db.Float, default=0.0)

    # Minimum purchase quantity in base_unit (e.g., 0.5 for half pound minimum)
    min_purchase = db.Column(db.Float, default=1.0)

    # Core ingredient - never deleted by cleanup even if unused (pantry staples)
    is_core = db.Column(db.Boolean, default=False)

    # For PORTION formula: size of one portion in ML and/or grams
    # e.g., butter stick: portion_ml=118 (8 TBSP), portion_g=113
    # This allows converting "2 TBSP butter" → 2*14.787/118 = 0.25 sticks
    portion_ml = db.Column(db.Float, nullable=True)
    portion_g = db.Column(db.Float, nullable=True)

    # For PACKAGE formula: number of units per package
    # e.g., eggs: pkg_count=12 (12 eggs per carton)
    # e.g., garlic: pkg_count=10 (10 cloves per head)
    # Recipe "2 eggs" → 2/12 = 0.167 packages → cost = 0.167 × $4.20
    pkg_count = db.Column(db.Float, nullable=True)

    # For WEIGHT formula: average weight per piece in grams
    # e.g., chicken breast: piece_weight_g=250 (250g per breast)
    # Recipe "2 chicken breasts" → 2 × 250g = 500g → 0.5 KG → 0.5 × $price/KG
    # Only used when recipe specifies count (EA, BREAST, etc.) instead of weight
    piece_weight_g = db.Column(db.Float, nullable=True)

    # DEPRECATED - kept for migration compatibility
    unit_size = db.Column(db.Float, nullable=True)
    unit_size_unit = db.Column(db.String(10), nullable=True)
    default_unit = db.Column(db.String(20), default='EA')
    pack_size = db.Column(db.Integer, default=1)
    price_unit = db.Column(db.String(20), default='EA')
    weight = db.Column(db.Float, nullable=True)
    weight_unit = db.Column(db.String(10), default='G')
    pkg_volume = db.Column(db.Float, nullable=True)
    pkg_qty = db.Column(db.Float, nullable=True)


class IngredientSynonym(db.Model):
    """Maps alternate names to canonical ingredient (e.g., 'ground beef' -> 'Ground Beef')"""
    id = db.Column(db.Integer, primary_key=True)
    synonym = db.Column(db.String(100), unique=True, nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id', ondelete='CASCADE'), nullable=False)
    ingredient = db.relationship('Ingredient', backref='synonyms')

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    category = db.Column(db.String(50), default='Dinner', index=True)
    difficulty = db.Column(db.String(20), default='Easy')
    protein_type = db.Column(db.String(20), default='None', index=True)
    servings = db.Column(db.Integer, default=4)
    instructions = db.Column(db.Text, default='')
    image = db.Column(db.String(255), default='')
    source_url = db.Column(db.String(500), default='')
    ingredients = db.relationship('RecipeIngredient', backref='recipe', lazy=True, cascade='all, delete-orphan')

class RecipeIngredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id', ondelete='CASCADE'), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    size = db.Column(db.Float, nullable=True)  # Container size (e.g., 400 for 400ml can)
    unit = db.Column(db.String(20), nullable=False)
    ingredient = db.relationship('Ingredient')

class PantryStaple(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id', ondelete='CASCADE'), nullable=False, index=True)
    have_it = db.Column(db.Boolean, default=True)
    ingredient = db.relationship('Ingredient')

class MealPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week = db.Column(db.Integer, nullable=False, index=True)
    day = db.Column(db.Integer, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id', ondelete='SET NULL'), nullable=True, index=True)
    locked = db.Column(db.Boolean, default=False)
    recipe = db.relationship('Recipe')

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200))

class UseUpItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id', ondelete='CASCADE'), nullable=False)
    ingredient = db.relationship('Ingredient')

class ShoppingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.String(50), default='')
    checked = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50), default='Other')
    unit_cost = db.Column(db.String(20), default='')  # e.g., "$3.99/LB"
    cost = db.Column(db.Float, default=0.0)  # calculated total cost
    # FK to Ingredient for ID-based matching (nullable for manually-added items)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id', ondelete='SET NULL'), nullable=True, index=True)
    ingredient = db.relationship('Ingredient')
    # Source tracking: 'manual' (user added), 'recipe' (from recipe generation), 'mealplan' (from meal plan)
    source = db.Column(db.String(20), default='manual')

# ============================================
# ROUTES - HOME
# ============================================

@app.route('/')
def index():
    recipes = Recipe.query.filter(Recipe.category != 'Archive').order_by(Recipe.name).all()
    return render_template('index.html', recipes=recipes)

# ============================================
# ROUTES - RECIPES
# ============================================

@app.route('/recipes')
def recipes_list():
    category = request.args.get('category', 'all')
    if category == 'all':
        recipes = Recipe.query.order_by(Recipe.category, Recipe.name).all()
    else:
        recipes = Recipe.query.filter_by(category=category).order_by(Recipe.name).all()
    categories = db.session.query(Recipe.category).distinct().all()
    return render_template('recipes.html', recipes=recipes, categories=[c[0] for c in categories], selected_category=category)

@app.route('/recipe/<int:id>')
def recipe_view(id):
    recipe = Recipe.query.options(
        joinedload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient)
    ).get_or_404(id)

    # Filter out ingredients where the linked ingredient was deleted
    valid_ingredients = [ri for ri in recipe.ingredients if ri.ingredient]

    # Calculate costs for each ingredient
    ingredient_costs = {}
    subtotal = 0.0
    for ri in valid_ingredients:
        cost = calculate_ingredient_cost(ri)
        ingredient_costs[ri.id] = cost
        subtotal += cost

    tax = subtotal * 0.12
    total = subtotal + tax

    # Replace recipe.ingredients with filtered list for template
    recipe.ingredients = valid_ingredients

    return render_template('recipe_view.html', recipe=recipe,
                           ingredient_costs=ingredient_costs,
                           subtotal=subtotal, tax=tax, total=total)

@app.route('/recipe/add', methods=['GET', 'POST'])
def recipe_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Recipe name is required', 'danger')
            return render_template('recipe_form.html', recipe=None)

        recipe = Recipe(
            name=name,
            category=request.form.get('category', 'Dinner'),
            difficulty=request.form.get('difficulty', 'Easy'),
            protein_type=request.form.get('protein_type', 'None'),
            servings=safe_int(request.form.get('servings'), default=4, min_val=1, max_val=100),
            instructions=request.form.get('instructions', '')
        )
        db.session.add(recipe)
        db.session.commit()
        flash(f'Recipe "{recipe.name}" created!', 'success')
        return redirect(url_for('recipe_edit', id=recipe.id))

    return render_template('recipe_form.html', recipe=None)

@app.route('/recipe/<int:id>/edit', methods=['GET', 'POST'])
def recipe_edit(id):
    recipe = Recipe.query.options(
        joinedload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient)
    ).get_or_404(id)
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()

    # Filter out recipe ingredients where the linked ingredient was deleted
    recipe.ingredients = [ri for ri in recipe.ingredients if ri.ingredient]

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Recipe name is required', 'danger')
            return render_template('recipe_form.html', recipe=recipe, ingredients=ingredients)

        recipe.name = name
        recipe.category = request.form.get('category', 'Dinner')
        recipe.difficulty = request.form.get('difficulty', 'Easy')
        recipe.protein_type = request.form.get('protein_type', 'None')
        recipe.servings = safe_int(request.form.get('servings'), default=4, min_val=1, max_val=100)
        recipe.instructions = request.form.get('instructions', '')
        db.session.commit()
        flash(f'Recipe "{recipe.name}" updated!', 'success')
        return redirect(url_for('recipe_view', id=recipe.id))

    return render_template('recipe_form.html', recipe=recipe, ingredients=ingredients)

@app.route('/recipe/<int:id>/delete', methods=['POST'])
def recipe_delete(id):
    recipe = Recipe.query.get_or_404(id)
    name = recipe.name

    # Clear MealPlan references (set recipe_id to NULL for this recipe)
    MealPlan.query.filter_by(recipe_id=id).update({'recipe_id': None, 'locked': False})

    # Delete recipe image if exists
    if recipe.image:
        try:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], recipe.image)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception:
            pass  # Ignore image deletion errors

    db.session.delete(recipe)
    db.session.commit()
    flash(f'Recipe "{name}" deleted!', 'success')
    return redirect(url_for('recipes_list'))

@app.route('/recipe/<int:id>/ingredient/add', methods=['POST'])
def recipe_ingredient_add(id):
    recipe = Recipe.query.get_or_404(id)

    try:
        ingredient_id = int(request.form['ingredient_id'])
    except (ValueError, TypeError):
        flash('Invalid ingredient selected', 'danger')
        return redirect(url_for('recipe_edit', id=id))

    quantity = parse_fraction(request.form.get('quantity', '1'))
    quantity = max(0.001, min(9999, quantity))  # Clamp to reasonable range

    size_str = request.form.get('size', '').strip()
    size = safe_float(size_str, default=None, min_val=0.1, max_val=9999) if size_str else None

    unit = request.form.get('unit', 'EA')

    ri = RecipeIngredient(recipe_id=id, ingredient_id=ingredient_id, quantity=quantity, size=size, unit=unit)
    db.session.add(ri)
    db.session.commit()

    return redirect(url_for('recipe_edit', id=id))

@app.route('/recipe/<int:recipe_id>/ingredient/<int:ri_id>/update', methods=['POST'])
def recipe_ingredient_update(recipe_id, ri_id):
    ri = RecipeIngredient.query.get_or_404(ri_id)

    try:
        ri.ingredient_id = int(request.form.get('ingredient_id', ri.ingredient_id))
    except (ValueError, TypeError):
        pass  # Keep existing ingredient_id

    quantity_str = request.form.get('quantity')
    if quantity_str:
        ri.quantity = max(0.001, min(9999, parse_fraction(quantity_str)))

    size_str = request.form.get('size', '').strip()
    ri.size = safe_float(size_str, default=None, min_val=0.1, max_val=9999) if size_str else None

    ri.unit = request.form.get('unit', ri.unit)
    db.session.commit()
    return redirect(url_for('recipe_edit', id=recipe_id))

@app.route('/recipe/<int:recipe_id>/ingredient/<int:ri_id>/delete', methods=['POST'])
def recipe_ingredient_delete(recipe_id, ri_id):
    ri = RecipeIngredient.query.get_or_404(ri_id)
    db.session.delete(ri)
    db.session.commit()
    return redirect(url_for('recipe_edit', id=recipe_id))

@app.route('/recipe/<int:id>/upload-image', methods=['POST'])
def recipe_upload_image(id):
    recipe = Recipe.query.get_or_404(id)

    if 'image' not in request.files:
        flash('No image selected', 'warning')
        return redirect(url_for('recipe_edit', id=id))

    file = request.files['image']
    if file.filename == '':
        flash('No image selected', 'warning')
        return redirect(url_for('recipe_edit', id=id))

    if file and allowed_file(file.filename):
        try:
            # Delete old image if exists
            if recipe.image:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], recipe.image)
                if os.path.exists(old_path):
                    os.remove(old_path)

            # Validate and process image through PIL (strips malicious content, re-encodes as JPEG)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"recipe_{id}.tmp")
            final_path = validate_and_process_image(file, temp_path)

            # Extract final filename from path (always .jpg after processing)
            filename = os.path.basename(final_path)
            recipe.image = filename
            db.session.commit()
            flash('Image uploaded!', 'success')
        except ImageValidationError as e:
            flash(f'Invalid image: {str(e)}', 'danger')
    else:
        flash('Invalid file type. Use PNG, JPG, GIF, or WEBP.', 'danger')

    return redirect(url_for('recipe_edit', id=id))

@app.route('/recipe/import', methods=['GET', 'POST'])
def recipe_import():
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        if not url:
            flash('Please enter a URL', 'warning')
            return render_template('recipe_import.html')

        # Validate URL scheme
        safe_url = sanitize_url(url)
        if not safe_url:
            flash('Invalid URL. Only http and https URLs are allowed.', 'danger')
            return render_template('recipe_import.html')

        try:
            # Fetch the page with SSRF protection
            response = safe_fetch(url)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Try to find JSON-LD structured data (most recipe sites use this)
            recipe_data = None
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    # Handle both single recipe and array of items
                    if isinstance(data, list):
                        for item in data:
                            if item.get('@type') == 'Recipe' or (isinstance(item.get('@type'), list) and 'Recipe' in item.get('@type')):
                                recipe_data = item
                                break
                    elif data.get('@type') == 'Recipe' or (isinstance(data.get('@type'), list) and 'Recipe' in data.get('@type')):
                        recipe_data = data
                    elif '@graph' in data:
                        for item in data['@graph']:
                            if item.get('@type') == 'Recipe' or (isinstance(item.get('@type'), list) and 'Recipe' in item.get('@type')):
                                recipe_data = item
                                break
                    if recipe_data:
                        break
                except (json.JSONDecodeError, TypeError, AttributeError):
                    continue

            if recipe_data:
                # Extract and sanitize data from JSON-LD
                name = sanitize_recipe_name(recipe_data.get('name', 'Imported Recipe'))

                # Get and sanitize instructions
                instructions = ''
                inst_data = recipe_data.get('recipeInstructions', [])
                if isinstance(inst_data, str):
                    instructions = sanitize_instructions(inst_data)
                elif isinstance(inst_data, list):
                    steps = []
                    for i, inst in enumerate(inst_data, 1):
                        if isinstance(inst, str):
                            steps.append(f"{i}. {sanitize_text(inst)}")
                        elif isinstance(inst, dict):
                            text = inst.get('text', inst.get('name', ''))
                            if text:
                                steps.append(f"{i}. {sanitize_text(text)}")
                    instructions = '\n'.join(steps)

                # Get and sanitize ingredients list
                raw_ingredients = recipe_data.get('recipeIngredient', [])
                ingredients_list = [sanitize_ingredient_text(ing) for ing in raw_ingredients if ing]

                # Get servings
                servings = recipe_data.get('recipeYield', 4)
                if isinstance(servings, list):
                    servings = servings[0] if servings else 4
                if isinstance(servings, str):
                    match = re.search(r'\d+', servings)
                    servings = int(match.group()) if match else 4

                # Get and sanitize image URL
                image_url = recipe_data.get('image', '')
                if isinstance(image_url, list):
                    image_url = image_url[0] if image_url else ''
                if isinstance(image_url, dict):
                    image_url = image_url.get('url', '')
                image_url = sanitize_url(image_url)

                return render_template('recipe_import.html',
                    imported=True,
                    name=name,
                    instructions=instructions,
                    ingredients_text='\n'.join(ingredients_list),
                    servings=servings,
                    image_url=image_url,
                    source_url=sanitize_url(url)
                )
            else:
                # Fallback: try to scrape basic info
                title = soup.find('h1')
                name = sanitize_recipe_name(title.get_text().strip() if title else 'Imported Recipe')

                flash('Could not find structured recipe data. Please enter details manually.', 'warning')
                return render_template('recipe_import.html',
                    imported=True,
                    name=name,
                    instructions='',
                    ingredients_text='',
                    servings=4,
                    image_url='',
                    source_url=sanitize_url(url)
                )

        except SSRFError as e:
            flash(f'URL blocked for security: {str(e)}', 'danger')
            return render_template('recipe_import.html')
        except requests.RequestException as e:
            flash(f'Could not fetch URL: {str(e)}', 'danger')
            return render_template('recipe_import.html')

    return render_template('recipe_import.html')


@app.route('/recipe/import/preview', methods=['POST'])
def recipe_import_preview():
    """Parse ingredients and show review page for user to confirm matches."""
    name = request.form.get('name', 'Imported Recipe').strip()
    instructions = request.form.get('instructions', '')
    ingredients_text = request.form.get('ingredients_text', '')
    servings = safe_int(request.form.get('servings'), default=4, min_val=1)
    category = request.form.get('category', 'Dinner')
    difficulty = request.form.get('difficulty', 'Easy')
    protein_type = request.form.get('protein_type', 'None')
    source_url = request.form.get('source_url', '')
    image_url = request.form.get('image_url', '')

    # Check if recipe already exists
    existing = Recipe.query.filter_by(name=name).first()
    if existing:
        flash(f'Recipe "{name}" already exists!', 'warning')
        return redirect(url_for('recipe_import'))

    # Parse each ingredient line and find matches
    parsed_ingredients = []
    all_ingredients = Ingredient.query.order_by(Ingredient.name).all()

    for line in ingredients_text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        quantity, unit, ing_name = parse_ingredient(line)
        if not ing_name:
            continue

        normalized_name = normalize_ingredient_name(ing_name)
        quantity, unit = standardize_unit(quantity, unit, normalized_name)

        # Try to find a match
        match, match_type = find_ingredient_match(ing_name)

        # Get suggestions for dropdown
        suggestions = get_ingredient_suggestions(normalized_name, limit=5)
        suggestion_list = [s[0] for s in suggestions]
        suggestion_ids = {s.id for s in suggestion_list}

        # Calculate conversion preview if there's a match
        converted_qty = None
        base_unit = None
        if match and match.base_unit:
            base_unit = match.base_unit
            converted_qty = convert_to_base_unit(quantity, unit, match)

        parsed_ingredients.append({
            'raw_text': line,
            'normalized': normalized_name,
            'qty': quantity,
            'unit': unit,
            'match': match,
            'match_type': match_type,
            'suggestions': suggestion_list,
            'suggestion_ids': suggestion_ids,
            'converted_qty': converted_qty,
            'base_unit': base_unit
        })

    return render_template('recipe_import_review.html',
        recipe_name=name,
        category=category,
        difficulty=difficulty,
        protein_type=protein_type,
        servings=servings,
        instructions=instructions,
        source_url=source_url,
        image_url=image_url,
        parsed_ingredients=parsed_ingredients,
        all_ingredients=all_ingredients
    )


@app.route('/recipe/import/save', methods=['POST'])
def recipe_import_save():
    """Save recipe with user-confirmed ingredient mappings from review page."""
    name = request.form.get('name', 'Imported Recipe').strip()
    instructions = request.form.get('instructions', '')
    servings = safe_int(request.form.get('servings'), default=4, min_val=1)
    category = request.form.get('category', 'Dinner')
    difficulty = request.form.get('difficulty', 'Easy')
    protein_type = request.form.get('protein_type', 'None')
    source_url = request.form.get('source_url', '')
    image_url = request.form.get('image_url', '')

    # Check if recipe already exists
    existing = Recipe.query.filter_by(name=name).first()
    if existing:
        flash(f'Recipe "{name}" already exists!', 'warning')
        return redirect(url_for('recipe_import'))

    # Create recipe
    recipe = Recipe(
        name=name,
        category=category,
        difficulty=difficulty,
        protein_type=protein_type,
        servings=servings,
        instructions=instructions,
        source_url=source_url
    )
    db.session.add(recipe)
    db.session.flush()

    # Download and save image if URL provided (with SSRF protection and validation)
    if image_url:
        # Validate URL first
        safe_image_url = sanitize_url(image_url)
        if safe_image_url:
            try:
                # Fetch with SSRF protection
                img_response = safe_fetch(safe_image_url, max_size=10*1024*1024)

                # Validate and process image through PIL (strips malicious content)
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"recipe_{recipe.id}.tmp")
                final_path = validate_and_process_image(img_response.content, temp_path)

                # Extract final filename from path (always .jpg after processing)
                filename = os.path.basename(final_path)
                recipe.image = filename
            except SSRFError:
                pass  # URL blocked for security, continue without image
            except ImageValidationError:
                pass  # Invalid or malicious image, continue without it
            except (requests.RequestException, IOError, OSError):
                pass  # Image download failed, continue without it

    # Process ingredients from review form
    # Form fields: include_X, ingredient_X, qty_X, unit_X where X is 0-based index
    ingredients_added = 0
    index = 0

    while True:
        ingredient_value = request.form.get(f'ingredient_{index}')
        if ingredient_value is None:
            break  # No more ingredients

        # Skip if unchecked (not included)
        if not request.form.get(f'include_{index}'):
            index += 1
            continue

        qty = parse_fraction(request.form.get(f'qty_{index}'), default=1.0, min_val=0.01)
        unit = request.form.get(f'unit_{index}', 'EA')

        # Determine ingredient: new or existing
        if ingredient_value == 'new':
            # Create new ingredient with the user-provided name
            new_name = request.form.get(f'newname_{index}', '').strip()
            if not new_name:
                index += 1
                continue  # Skip if no name provided

            # Check if it already exists (user might have typed same name twice)
            ingredient = Ingredient.query.filter(
                db.func.lower(Ingredient.name) == new_name.lower()
            ).first()
            if not ingredient:
                # Determine base_unit from the recipe unit (common sense defaults)
                if unit in ['CUP', 'TBSP', 'TSP', 'ML', 'L']:
                    new_base_unit = 'L'  # Liquids default to L
                elif unit in ['LB', 'KG', 'OZ', 'G']:
                    new_base_unit = 'LB'  # Weights default to LB
                else:
                    new_base_unit = 'EA'  # Everything else is each

                ingredient = Ingredient(
                    name=new_name,
                    category='Other',
                    base_unit=new_base_unit,
                    default_unit=unit  # Keep for legacy compatibility
                )
                db.session.add(ingredient)
                db.session.flush()
        else:
            # Use existing ingredient by ID
            try:
                ingredient_id = int(ingredient_value)
                ingredient = Ingredient.query.get(ingredient_id)
            except (ValueError, TypeError):
                ingredient = None

        if ingredient:
            # Keep original recipe quantity and unit (don't convert to base unit)
            # Base unit conversion happens in shopping list generation
            ri = RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=qty,
                unit=unit
            )
            db.session.add(ri)
            ingredients_added += 1

        index += 1

    db.session.commit()

    flash(f'Recipe "{name}" imported with {ingredients_added} ingredients!', 'success')
    return redirect(url_for('recipe_view', id=recipe.id))

# ============================================
# ROUTES - SHOPPING LIST
# ============================================

def generate_shopping_list(recipe_ids, multipliers=None):
    """
    Generate a shopping list from recipe IDs.
    Converts recipe quantities to base units for aggregation and cost calculation.
    Returns (shopping_items, subtotal, tax, total)
    """
    if multipliers is None:
        multipliers = {}

    # Get pantry ingredient IDs to exclude
    pantry_ids = {ps.ingredient_id for ps in PantryStaple.query.filter_by(have_it=True).all()}

    # Also exclude "Water" by name as fallback
    water_ing = Ingredient.query.filter(db.func.lower(Ingredient.name) == 'water').first()
    if water_ing:
        pantry_ids.add(water_ing.id)

    # Get USE UP ingredient IDs for highlighting
    use_up_ids = {item.ingredient_id for item in UseUpItem.query.all()}

    # Consolidate ingredients from all recipes
    # Convert each recipe ingredient to base_unit before aggregating
    consolidated = {}
    for recipe_id in recipe_ids:
        recipe = Recipe.query.get(int(recipe_id))
        if not recipe:
            continue

        multiplier = multipliers.get(recipe.id, 1.0)

        for ri in recipe.ingredients:
            if not ri.ingredient:
                continue  # Skip if ingredient was deleted

            # Skip pantry items by ID
            if ri.ingredient_id in pantry_ids:
                continue

            ing = ri.ingredient
            recipe_qty = ri.quantity * multiplier
            recipe_unit = ri.unit

            # Convert recipe quantity to ingredient's base unit
            base_qty = convert_to_base_unit(recipe_qty, recipe_unit, ing)
            base_unit = ing.base_unit or 'EA'

            if ri.ingredient_id in consolidated:
                consolidated[ri.ingredient_id]['qty'] += base_qty
            else:
                consolidated[ri.ingredient_id] = {
                    'ingredient_id': ri.ingredient_id,
                    'name': ing.name,
                    'qty': base_qty,
                    'unit': base_unit,
                    'category': ing.category,
                    'cost_per_unit': ing.cost,
                    'min_purchase': ing.min_purchase or 1.0,
                    'is_use_up': ri.ingredient_id in use_up_ids
                }

    # Build shopping items with costs
    shopping_items = []
    for ing_id, item in consolidated.items():
        qty = item['qty']
        unit = item['unit']
        min_purchase = item['min_purchase']
        cost_per_unit = item['cost_per_unit']

        # Round up to minimum purchase if needed
        if qty < min_purchase:
            qty = min_purchase

        # Round up to whole units for EA
        if unit == 'EA':
            qty = math.ceil(qty)

        # Calculate cost: simple multiplication
        total_cost = round(qty * cost_per_unit, 2)

        shopping_items.append({
            'ingredient_id': item['ingredient_id'],
            'name': item['name'],
            'qty': round(qty, 2),
            'unit': unit,
            'category': item['category'],
            'unit_cost': f"${cost_per_unit:.2f}/{unit}" if cost_per_unit > 0 else '',
            'cost': total_cost,
            'is_use_up': item['is_use_up']
        })

    shopping_items.sort(key=lambda x: (x['category'], x['name']))

    subtotal = sum(item['cost'] for item in shopping_items)
    tax = subtotal * 0.12
    total = subtotal + tax

    return shopping_items, round(subtotal, 2), round(tax, 2), round(total, 2)


@app.route('/shopping')
def shopping_list():
    # Get pantry ingredient IDs (ID-based filtering)
    pantry_ids = {ps.ingredient_id for ps in PantryStaple.query.filter_by(have_it=True).all()}

    # Get all shopping items and filter out pantry items by ID
    all_items = ShoppingItem.query.order_by(ShoppingItem.checked, ShoppingItem.category, ShoppingItem.name).all()

    # Filter: keep items that either have no ingredient_id or ingredient_id is not in pantry
    items = [item for item in all_items
             if not item.ingredient_id or item.ingredient_id not in pantry_ids]

    # Delete pantry items from shopping list (cleanup) - by ID only
    for item in all_items:
        if item.ingredient_id and item.ingredient_id in pantry_ids:
            db.session.delete(item)
    db.session.commit()

    # Get categories from ingredients
    categories = sorted(set(ing.category for ing in Ingredient.query.with_entities(Ingredient.category).distinct() if ing.category))
    return render_template('shopping.html', items=items, pantry_ids=pantry_ids, categories=categories)

@app.route('/shopping/add', methods=['POST'])
def shopping_add():
    name = request.form.get('name', '').strip()
    quantity = request.form.get('quantity', '').strip()
    category = request.form.get('category', 'Other')
    if name:
        item = ShoppingItem(name=name, quantity=quantity, category=category)
        db.session.add(item)
        db.session.commit()
    return redirect(url_for('shopping_list'))

@app.route('/shopping/check/<int:id>', methods=['POST'])
def shopping_check(id):
    item = ShoppingItem.query.get_or_404(id)
    item.checked = not item.checked
    db.session.commit()
    return redirect(url_for('shopping_list'))

@app.route('/shopping/delete/<int:id>', methods=['POST'])
def shopping_delete(id):
    item = ShoppingItem.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('shopping_list'))

@app.route('/shopping/clear-checked', methods=['POST'])
def shopping_clear_checked():
    # Uncheck all checked items (move back to main list)
    ShoppingItem.query.filter_by(checked=True).update({'checked': False})
    db.session.commit()
    return redirect(url_for('shopping_list'))

@app.route('/shopping/add-from-recipes', methods=['POST'])
def shopping_add_from_recipes():
    """Add items from selected recipes to shopping list"""
    recipe_ids = request.form.getlist('recipes')
    if recipe_ids:
        # Clear only generated items, preserve manual entries
        ShoppingItem.query.filter(ShoppingItem.source != 'manual').delete()

        items, _, _, _ = generate_shopping_list(recipe_ids)
        for item in items:
            qty_str = format_shopping_qty(item)
            shopping_item = ShoppingItem(
                name=item['name'],
                quantity=qty_str,
                category=item['category'],
                unit_cost=item.get('unit_cost', ''),
                cost=item['cost'],
                ingredient_id=item.get('ingredient_id'),  # Link to ingredient for ID-based matching
                source='recipe'  # Track source for non-destructive regeneration
            )
            db.session.add(shopping_item)
        db.session.commit()
        flash(f"Added {len(items)} items from recipes (manual items preserved)", "success")
    return redirect(url_for('shopping_list'))

@app.route('/shopping/generate', methods=['POST'])
def shopping_generate():
    selected_recipe_ids = request.form.getlist('recipes')
    multipliers = {}
    for key, value in request.form.items():
        if key.startswith('multiplier_'):
            recipe_id = int(key.replace('multiplier_', ''))
            multipliers[recipe_id] = float(value) if value else 1.0

    items, subtotal, tax, total = generate_shopping_list(selected_recipe_ids, multipliers)
    return render_template('shopping_result.html', items=items, subtotal=subtotal, tax=tax, total=total)

# ============================================
# ROUTES - USE UP LIST
# ============================================

@app.route('/useup/add', methods=['POST'])
def useup_add():
    ingredient_id = int(request.form['ingredient_id'])
    existing = UseUpItem.query.filter_by(ingredient_id=ingredient_id).first()
    if not existing:
        item = UseUpItem(ingredient_id=ingredient_id)
        db.session.add(item)
        db.session.commit()
    return redirect(url_for('shopping_list'))

@app.route('/useup/<int:id>/delete', methods=['POST'])
def useup_delete(id):
    item = UseUpItem.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('shopping_list'))

# ============================================
# ROUTES - MEAL PLAN
# ============================================

@app.route('/mealplan')
def meal_plan():
    # Get meal plan
    meals = MealPlan.query.order_by(MealPlan.week, MealPlan.day).all()
    meal_dict = {}
    for meal in meals:
        key = (meal.week, meal.day, meal.meal_type)
        meal_dict[key] = meal

    return render_template('mealplan.html', meal_dict=meal_dict)

@app.route('/mealplan/randomize', methods=['POST'])
def meal_plan_randomize():
    include_dessert = request.form.get('include_dessert') == 'on'

    # Get locked meals to preserve
    locked_meals = {(m.day, m.meal_type): m for m in MealPlan.query.filter_by(week=1, locked=True).all()}
    locked_recipe_ids = {m.recipe_id for m in locked_meals.values() if m.recipe_id}

    # Delete only unlocked meals
    MealPlan.query.filter_by(week=1, locked=False).delete()

    # Get all dinner recipes (excluding locked ones) and shuffle
    all_dinners = [r for r in Recipe.query.filter_by(category='Dinner').all() if r.id not in locked_recipe_ids]
    random.shuffle(all_dinners)

    # Assign random dinners to unlocked days
    dinner_idx = 0
    for day in range(1, 8):
        if (day, 'Dinner') not in locked_meals:
            if all_dinners:
                selected_dinner = all_dinners[dinner_idx % len(all_dinners)]
                meal = MealPlan(week=1, day=day, meal_type='Dinner', recipe_id=selected_dinner.id)
                db.session.add(meal)
                dinner_idx += 1

    # Add desserts only if checkbox is checked
    if include_dessert:
        all_desserts = [r for r in Recipe.query.filter_by(category='Dessert').all() if r.id not in locked_recipe_ids]
        random.shuffle(all_desserts)
        dessert_idx = 0
        for day in range(1, 8):
            if (day, 'Dessert') not in locked_meals:
                if all_desserts:
                    selected_dessert = all_desserts[dessert_idx % len(all_desserts)]
                    meal = MealPlan(week=1, day=day, meal_type='Dessert', recipe_id=selected_dessert.id)
                    db.session.add(meal)
                    dessert_idx += 1

    db.session.commit()
    flash('Week randomized! (Locked meals preserved)', 'success')
    return redirect(url_for('meal_plan'))

@app.route('/mealplan/lock/<int:day>/<meal_type>', methods=['POST'])
def meal_plan_lock(day, meal_type):
    meal = MealPlan.query.filter_by(week=1, day=day, meal_type=meal_type).first()
    if meal:
        meal.locked = not meal.locked
        db.session.commit()
    return redirect(url_for('meal_plan'))

@app.route('/mealplan/shopping', methods=['POST'])
def shopping_from_mealplan():
    meals = MealPlan.query.filter_by(week=1).all()
    if not meals:
        flash('No meals in the plan. Randomize first!', 'warning')
        return redirect(url_for('meal_plan'))

    recipe_ids = {meal.recipe_id for meal in meals if meal.recipe_id}

    # Clear only generated items, preserve manual entries
    ShoppingItem.query.filter(ShoppingItem.source != 'manual').delete()

    items, _, _, _ = generate_shopping_list(recipe_ids)
    for item in items:
        qty_str = format_shopping_qty(item)
        shopping_item = ShoppingItem(
            name=item['name'],
            quantity=qty_str,
            category=item['category'],
            unit_cost=item.get('unit_cost', ''),
            cost=item['cost'],
            ingredient_id=item.get('ingredient_id'),  # Link to ingredient for ID-based matching
            source='mealplan'  # Track source for non-destructive regeneration
        )
        db.session.add(shopping_item)
    db.session.commit()
    flash(f"Added {len(items)} items from meal plan (manual items preserved)", "success")
    return redirect(url_for('shopping_list'))

# ============================================
# ROUTES - INGREDIENTS
# ============================================

@app.route('/ingredients')
def ingredients_list():
    # Get IDs of ingredients used in recipes
    used_ingredient_ids = {r[0] for r in db.session.query(RecipeIngredient.ingredient_id).distinct().all()}

    # Get pantry ingredient IDs (ID-based filtering only)
    pantry_ingredient_ids = {r[0] for r in db.session.query(PantryStaple.ingredient_id).all()}

    # Show ingredients that are: used in recipes OR core (not in pantry)
    from sqlalchemy import or_
    all_shown = Ingredient.query.filter(
        or_(
            Ingredient.id.in_(used_ingredient_ids),
            Ingredient.is_core == True
        )
    ).order_by(Ingredient.category, Ingredient.name).all()

    # Filter out pantry items by ID only (no fuzzy name matching)
    ingredients = [ing for ing in all_shown if ing.id not in pantry_ingredient_ids]

    # Get all unique categories from ingredients shown
    categories = sorted(set(ing.category for ing in ingredients if ing.category))

    # Mark which ones are used in recipes
    for ing in ingredients:
        ing.used_in_recipes = ing.id in used_ingredient_ids

    return render_template('ingredients.html', ingredients=ingredients, pantry_ids=pantry_ingredient_ids, categories=categories)

@app.route('/ingredient/add', methods=['POST'])
def ingredient_add():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Ingredient name is required', 'danger')
        return redirect(url_for('ingredients_list'))

    # Sanitize name
    name = sanitize_text(name, max_length=200)

    # Check if ingredient already exists
    existing = Ingredient.query.filter(Ingredient.name.ilike(name)).first()
    if existing:
        # Check if it's in pantry
        in_pantry = PantryStaple.query.filter_by(ingredient_id=existing.id).first()
        if in_pantry:
            flash(f'"{name}" already exists in your Pantry', 'warning')
        else:
            flash(f'"{name}" already exists in Ingredients', 'warning')
        return redirect(url_for('ingredients_list'))

    # Validate cost_formula against whitelist
    cost_formula = request.form.get('cost_formula', 'COUNT').upper()
    if cost_formula not in VALID_COST_FORMULAS:
        flash(f'Invalid cost formula: {cost_formula}', 'danger')
        return redirect(url_for('ingredients_list'))

    # Validate base_unit against whitelist
    base_unit = request.form.get('base_unit', 'EA').upper()
    if base_unit not in VALID_BASE_UNITS:
        flash(f'Invalid base unit: {base_unit}', 'danger')
        return redirect(url_for('ingredients_list'))

    # Sanitize category
    category = sanitize_text(request.form.get('category', 'Other'), max_length=50)
    if not category:
        category = 'Other'

    portion_ml_str = request.form.get('portion_ml', '').strip()
    portion_g_str = request.form.get('portion_g', '').strip()
    pkg_count_str = request.form.get('pkg_count', '').strip()
    piece_weight_str = request.form.get('piece_weight_g', '').strip()

    ingredient = Ingredient(
        name=name,
        category=category,
        cost_formula=cost_formula,
        base_unit=base_unit,
        cost=safe_float(request.form.get('cost'), default=0.0, min_val=0.0, max_val=9999.99),
        min_purchase=safe_float(request.form.get('min_purchase'), default=1.0, min_val=0.1, max_val=9999),
        is_core=request.form.get('is_core') == '1',
        portion_ml=safe_float(portion_ml_str, default=None, min_val=0.1, max_val=99999) if portion_ml_str else None,
        portion_g=safe_float(portion_g_str, default=None, min_val=0.1, max_val=99999) if portion_g_str else None,
        pkg_count=safe_float(pkg_count_str, default=None, min_val=1, max_val=9999) if pkg_count_str else None,
        piece_weight_g=safe_float(piece_weight_str, default=None, min_val=1, max_val=99999) if piece_weight_str else None
    )
    db.session.add(ingredient)
    db.session.commit()
    flash(f'Ingredient "{ingredient.name}" added!', 'success')
    return redirect(url_for('ingredients_list'))

@app.route('/ingredient/<int:id>/edit', methods=['POST'])
def ingredient_edit(id):
    ingredient = Ingredient.query.get_or_404(id)

    name = request.form.get('name', '').strip()
    if not name:
        return 'Ingredient name is required', 400

    # Check if new name conflicts with another ingredient
    if name.lower() != ingredient.name.lower():
        existing = Ingredient.query.filter(
            Ingredient.name.ilike(name),
            Ingredient.id != id
        ).first()
        if existing:
            return f'An ingredient named "{name}" already exists', 400

    # Validate cost_formula against whitelist
    cost_formula = request.form.get('cost_formula', 'COUNT').upper()
    if cost_formula not in VALID_COST_FORMULAS:
        return f'Invalid cost formula: {cost_formula}', 400

    # Validate base_unit against whitelist
    base_unit = request.form.get('base_unit', 'EA').upper()
    if base_unit not in VALID_BASE_UNITS:
        return f'Invalid base unit: {base_unit}', 400

    # Validate category (allow any for flexibility, but sanitize)
    category = sanitize_text(request.form.get('category', 'Other'), max_length=50)
    if not category:
        category = 'Other'

    ingredient.name = sanitize_text(name, max_length=200)
    ingredient.category = category
    ingredient.cost_formula = cost_formula
    ingredient.base_unit = base_unit
    ingredient.cost = safe_float(request.form.get('cost'), default=0.0, min_val=0.0, max_val=9999.99)
    ingredient.min_purchase = safe_float(request.form.get('min_purchase'), default=1.0, min_val=0.1, max_val=9999)

    # Handle portion_ml and portion_g for PORTION formula
    portion_ml_str = request.form.get('portion_ml', '').strip()
    if portion_ml_str:
        ingredient.portion_ml = safe_float(portion_ml_str, default=None, min_val=0.1, max_val=99999)
    elif 'portion_ml' in request.form:  # Explicitly cleared
        ingredient.portion_ml = None

    portion_g_str = request.form.get('portion_g', '').strip()
    if portion_g_str:
        ingredient.portion_g = safe_float(portion_g_str, default=None, min_val=0.1, max_val=99999)
    elif 'portion_g' in request.form:  # Explicitly cleared
        ingredient.portion_g = None

    # Handle pkg_count for PACKAGE formula
    pkg_count_str = request.form.get('pkg_count', '').strip()
    if pkg_count_str:
        ingredient.pkg_count = safe_float(pkg_count_str, default=None, min_val=1, max_val=9999)
    elif 'pkg_count' in request.form:  # Explicitly cleared
        ingredient.pkg_count = None

    # Handle piece_weight_g for WEIGHT formula (average weight per piece in grams)
    piece_weight_str = request.form.get('piece_weight_g', '').strip()
    if piece_weight_str:
        ingredient.piece_weight_g = safe_float(piece_weight_str, default=None, min_val=1, max_val=99999)
    elif 'piece_weight_g' in request.form:  # Explicitly cleared
        ingredient.piece_weight_g = None

    # Handle is_core - can be '1', 'true', or 'false'
    is_core_val = request.form.get('is_core', '')
    if is_core_val in ('1', 'true'):
        ingredient.is_core = True
    elif is_core_val in ('0', 'false'):
        ingredient.is_core = False
    # If not provided, don't change it

    try:
        db.session.commit()
        return '', 200  # Return success for AJAX
    except Exception as e:
        db.session.rollback()
        return 'Failed to save', 400

@app.route('/ingredient/<int:id>/delete', methods=['POST'])
def ingredient_delete(id):
    ingredient = Ingredient.query.get_or_404(id)
    name = ingredient.name

    # Manually delete related records (cascade doesn't work on existing SQLite tables)
    RecipeIngredient.query.filter_by(ingredient_id=id).delete()
    PantryStaple.query.filter_by(ingredient_id=id).delete()
    UseUpItem.query.filter_by(ingredient_id=id).delete()
    ShoppingItem.query.filter_by(ingredient_id=id).delete()
    IngredientSynonym.query.filter_by(ingredient_id=id).delete()

    db.session.delete(ingredient)
    db.session.commit()
    flash(f'Ingredient "{name}" deleted!', 'success')
    return redirect(url_for('ingredients_list'))

@app.route('/ingredients/cleanup', methods=['POST'])
def ingredients_cleanup():
    """Clean up database: merge duplicates, remove orphans, remove unused ingredients"""
    merged = 0
    removed_orphans = 0
    removed_unused = 0

    # 1. Find and merge duplicate ingredients (same name, case-insensitive)
    all_ingredients = Ingredient.query.all()
    name_to_ingredients = {}
    for ing in all_ingredients:
        key = ing.name.strip().lower()
        if key not in name_to_ingredients:
            name_to_ingredients[key] = []
        name_to_ingredients[key].append(ing)

    for name, duplicates in name_to_ingredients.items():
        if len(duplicates) > 1:
            # Keep the one with most data (has pricing info) or lowest ID
            duplicates.sort(key=lambda x: (x.cost > 0, x.weight is not None, -x.id), reverse=True)
            keeper = duplicates[0]

            for dup in duplicates[1:]:
                # Update all recipe ingredients to use the keeper
                RecipeIngredient.query.filter_by(ingredient_id=dup.id).update(
                    {'ingredient_id': keeper.id}
                )
                # Update pantry entries
                PantryStaple.query.filter_by(ingredient_id=dup.id).delete()
                # Delete the duplicate
                db.session.delete(dup)
                merged += 1

    # 2. Remove orphan pantry entries (ingredient was deleted)
    valid_ids = {ing.id for ing in Ingredient.query.all()}
    orphan_pantry = PantryStaple.query.filter(~PantryStaple.ingredient_id.in_(valid_ids)).all()
    for orphan in orphan_pantry:
        db.session.delete(orphan)
        removed_orphans += 1

    # 3. Remove orphan recipe ingredients
    orphan_ri = RecipeIngredient.query.filter(~RecipeIngredient.ingredient_id.in_(valid_ids)).all()
    for orphan in orphan_ri:
        db.session.delete(orphan)

    # 4. Remove ingredients not used in any recipe, not in pantry, and not core
    used_ids = {ri.ingredient_id for ri in RecipeIngredient.query.all()}
    pantry_ids = {ps.ingredient_id for ps in PantryStaple.query.all()}
    core_ids = {ing.id for ing in Ingredient.query.filter_by(is_core=True).all()}
    keep_ids = used_ids | pantry_ids | core_ids

    unused = Ingredient.query.filter(~Ingredient.id.in_(keep_ids)).all()
    for ing in unused:
        db.session.delete(ing)
        removed_unused += 1

    db.session.commit()

    messages = []
    if merged > 0:
        messages.append(f"Merged {merged} duplicate(s)")
    if removed_orphans > 0:
        messages.append(f"Removed {removed_orphans} orphan(s)")
    if removed_unused > 0:
        messages.append(f"Removed {removed_unused} unused ingredient(s)")

    if messages:
        flash(". ".join(messages), 'success')
    else:
        flash("Database is already clean!", 'info')

    return redirect(url_for('ingredients_list'))

# ============================================
# ROUTES - WHAT CAN I MAKE
# ============================================

@app.route('/whatcanmake')
def what_can_make():
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    recipes = Recipe.query.filter(Recipe.category != 'Archive').all()

    # Get pantry staple IDs (pre-checked)
    pantry_ids = {ps.ingredient_id for ps in PantryStaple.query.filter_by(have_it=True).all()}

    # Build recipes JSON for JavaScript
    recipes_json = []
    for r in recipes:
        valid_ris = [ri for ri in r.ingredients if ri.ingredient]
        recipes_json.append({
            'id': r.id,
            'name': r.name,
            'category': r.category,
            'image': r.image,
            'ingredients': [ri.ingredient_id for ri in valid_ris],
            'ingredient_names': [ri.ingredient.name for ri in valid_ris]
        })

    return render_template('whatcanmake.html',
                         ingredients=ingredients,
                         pantry_ids=pantry_ids,
                         recipes_json=json.dumps(recipes_json))

# ============================================
# ROUTES - PANTRY STAPLES
# ============================================

@app.route('/pantry')
def pantry_list():
    # Clean up orphan pantry staples in a single DELETE query (more efficient)
    valid_ingredient_ids = db.session.query(Ingredient.id)
    PantryStaple.query.filter(~PantryStaple.ingredient_id.in_(valid_ingredient_ids)).delete(synchronize_session=False)
    db.session.commit()

    staples = PantryStaple.query.options(joinedload(PantryStaple.ingredient)).join(Ingredient).order_by(Ingredient.name).all()
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('pantry.html', staples=staples, ingredients=ingredients)

@app.route('/pantry/add', methods=['POST'])
def pantry_add():
    ingredient_id = safe_int(request.form.get('ingredient_id'), default=0)
    if ingredient_id <= 0:
        flash('Invalid ingredient', 'danger')
        return redirect(url_for('pantry_list'))

    ingredient = Ingredient.query.get(ingredient_id)
    if not ingredient:
        flash('Ingredient not found', 'danger')
        return redirect(url_for('pantry_list'))

    existing = PantryStaple.query.filter_by(ingredient_id=ingredient_id).first()
    if not existing:
        staple = PantryStaple(ingredient_id=ingredient_id, have_it=True)
        db.session.add(staple)
        db.session.commit()
        flash('Added to pantry!', 'success')
    else:
        flash(f'"{ingredient.name}" is already in your Pantry', 'info')
    return redirect(url_for('pantry_list'))

@app.route('/pantry/<int:id>/toggle', methods=['POST'])
def pantry_toggle(id):
    staple = PantryStaple.query.get_or_404(id)
    staple.have_it = not staple.have_it
    db.session.commit()
    return redirect(url_for('pantry_list'))

@app.route('/pantry/<int:id>/delete', methods=['POST'])
def pantry_delete(id):
    staple = PantryStaple.query.get_or_404(id)
    db.session.delete(staple)
    db.session.commit()
    return redirect(url_for('pantry_list'))

@app.route('/pantry/add-from-ingredient/<int:id>', methods=['POST'])
def pantry_add_from_ingredient(id):
    """Add ingredient to pantry from ingredients page"""
    existing = PantryStaple.query.filter_by(ingredient_id=id).first()
    if not existing:
        staple = PantryStaple(ingredient_id=id, have_it=True)
        db.session.add(staple)
        db.session.commit()
        flash('Added to pantry!', 'success')
    else:
        flash('Already in pantry', 'info')
    return redirect(url_for('ingredients_list'))

@app.route('/shopping/<int:id>/add-to-pantry', methods=['POST'])
def shopping_add_to_pantry(id):
    """Add shopping list item to pantry"""
    item = ShoppingItem.query.get_or_404(id)
    # Find matching ingredient by name
    ingredient = Ingredient.query.filter(Ingredient.name.ilike(item.name)).first()
    if ingredient:
        existing = PantryStaple.query.filter_by(ingredient_id=ingredient.id).first()
        if not existing:
            staple = PantryStaple(ingredient_id=ingredient.id, have_it=True)
            db.session.add(staple)
            db.session.commit()
            flash(f'Added {item.name} to pantry!', 'success')
        else:
            flash(f'{item.name} already in pantry', 'info')
    else:
        flash(f'Ingredient "{item.name}" not found - add it to Ingredients first', 'warning')
    return redirect(url_for('shopping_list'))

@app.route('/pantry/add-common', methods=['POST'])
def pantry_add_common():
    common_staples = [
        'Salt', 'Pepper', 'Oil', 'Olive Oil', 'Cooking Oil', 'Vegetable Oil',
        'Butter', 'Garlic', 'Onion', 'Flour', 'Sugar',
        'Vanilla Extract', 'Vanilla', 'Baking Powder', 'Baking Soda',
        'Paprika', 'Cumin', 'Oregano', 'Basil', 'Thyme', 'Rosemary', 'Cinnamon', 'Ground Cinnamon',
        'Chili Powder', 'Cayenne', 'Italian Seasoning', 'Bay Leaves',
        'Hot Sauce', 'Worcestershire Sauce', 'Panko Breadcrumbs', 'Panko'
    ]
    added = 0
    for name in common_staples:
        ingredient = Ingredient.query.filter(Ingredient.name.ilike(name)).first()
        if ingredient:
            existing = PantryStaple.query.filter_by(ingredient_id=ingredient.id).first()
            if not existing:
                staple = PantryStaple(ingredient_id=ingredient.id, have_it=True)
                db.session.add(staple)
                added += 1
    db.session.commit()
    if added > 0:
        flash(f'Added {added} common staples to pantry!', 'success')
    else:
        flash('Common staples already in pantry or ingredients not found.', 'info')
    return redirect(url_for('pantry_list'))

# ============================================
# DATA MIGRATION
# ============================================

@app.route('/admin/migrate', methods=['POST'])
def migrate_data():
    """
    Run data migration:
    1. Populate IngredientSynonym from INGREDIENT_ALIASES
    2. Link existing ShoppingItems to Ingredients
    3. Merge duplicate ingredients
    """
    synonyms_added = 0
    shopping_linked = 0

    # 1. Populate IngredientSynonym from INGREDIENT_ALIASES
    for alias, canonical in INGREDIENT_ALIASES.items():
        # Check if synonym already exists
        existing = IngredientSynonym.query.filter(
            db.func.lower(IngredientSynonym.synonym) == alias.lower()
        ).first()
        if existing:
            continue

        # Find the canonical ingredient
        ing = Ingredient.query.filter(
            db.func.lower(Ingredient.name) == canonical.lower()
        ).first()
        if ing:
            syn = IngredientSynonym(synonym=alias, ingredient_id=ing.id)
            db.session.add(syn)
            synonyms_added += 1

    # 2. Link existing ShoppingItems to Ingredients
    for item in ShoppingItem.query.filter(ShoppingItem.ingredient_id.is_(None)).all():
        # Try exact match first
        ing = Ingredient.query.filter(
            db.func.lower(Ingredient.name) == item.name.lower()
        ).first()
        if ing:
            item.ingredient_id = ing.id
            shopping_linked += 1

    db.session.commit()

    messages = []
    if synonyms_added > 0:
        messages.append(f"Added {synonyms_added} synonyms")
    if shopping_linked > 0:
        messages.append(f"Linked {shopping_linked} shopping items")

    if messages:
        flash(". ".join(messages), 'success')
    else:
        flash("No migration needed - data is up to date!", 'info')

    return redirect(url_for('ingredients_list'))


@app.route('/admin/migrate-base-units', methods=['POST'])
def migrate_base_units():
    """
    Migrate ingredients to the new simplified base_unit model:
    - Copy price_unit to base_unit
    - Set min_purchase defaults based on ingredient type
    """
    migrated = 0

    for ing in Ingredient.query.all():
        # Only migrate if base_unit is not set or is the default 'EA'
        if not ing.base_unit or ing.base_unit == 'EA':
            # Use price_unit as the new base_unit
            old_price_unit = ing.price_unit or 'EA'

            # Convert CAN and PKG to more useful base units
            if old_price_unit == 'CAN':
                ing.base_unit = 'EA'  # CANs are counted
            elif old_price_unit == 'PKG':
                # For PKG items, try to determine a better base unit
                if ing.pkg_volume:  # Liquid packages (like broth)
                    ing.base_unit = 'L'
                    # Convert cost: if pkg_volume is in ML and cost is per pkg
                    # cost per L = cost / (pkg_volume / 1000)
                    if ing.cost > 0 and ing.pkg_volume > 0:
                        ing.cost = round(ing.cost / (ing.pkg_volume / 1000), 2)
                else:
                    ing.base_unit = 'EA'
            else:
                ing.base_unit = old_price_unit

        # Set min_purchase if not already set or is default
        if not ing.min_purchase or ing.min_purchase == 1.0:
            base = ing.base_unit.upper() if ing.base_unit else 'EA'
            name_upper = ing.name.upper()

            # Set reasonable minimums based on ingredient type
            if base in ['LB', 'KG']:
                # Meats typically have 1 lb/0.5 kg minimum
                if any(x in name_upper for x in ['CHICKEN', 'BEEF', 'PORK', 'FISH', 'SALMON', 'SHRIMP']):
                    ing.min_purchase = 1.0 if base == 'LB' else 0.5
                else:
                    ing.min_purchase = 0.5  # Half pound/kg for produce, cheese, etc.
            elif base == 'L':
                # Liquids: 1 L minimum for broth/stock, otherwise 0.5 L
                if any(x in name_upper for x in ['BROTH', 'STOCK']):
                    ing.min_purchase = 1.0
                else:
                    ing.min_purchase = 0.5
            elif base == 'EA':
                # Count items: depends on type
                if 'EGG' in name_upper:
                    ing.min_purchase = 6  # Eggs come in 6+
                else:
                    ing.min_purchase = 1
            else:
                ing.min_purchase = 1.0

        # Set cost_formula based on category and base_unit
        if not ing.cost_formula or ing.cost_formula == 'COUNT':
            base = (ing.base_unit or 'EA').upper()
            cat = (ing.category or '').lower()
            name_lower = ing.name.lower()

            # WEIGHT formula for meats and produce by weight
            if base in ['LB', 'KG', 'G', 'OZ']:
                ing.cost_formula = 'WEIGHT'
            # VOLUME formula for liquids
            elif base in ['L', 'ML'] or cat == 'liquids':
                ing.cost_formula = 'VOLUME'
            # PORTION formula for butter, cheese blocks, etc.
            elif any(x in name_lower for x in ['butter', 'cream cheese', 'margarine']):
                ing.cost_formula = 'PORTION'
                # Set default portion sizes for butter sticks if not set
                if 'butter' in name_lower and not ing.portion_ml:
                    ing.portion_ml = 118  # 8 TBSP
                    ing.portion_g = 113   # 113g per stick
            # PACKAGE formula for eggs, garlic (multi-unit packages)
            elif any(x in name_lower for x in ['egg', 'garlic']):
                ing.cost_formula = 'PACKAGE'
                # Set default pkg_count if not set
                if 'egg' in name_lower and not ing.pkg_count:
                    ing.pkg_count = 12  # 12 eggs per carton
                elif 'garlic' in name_lower and not ing.pkg_count:
                    ing.pkg_count = 10  # ~10 cloves per head
            # COUNT formula for single items (lemons, cans, etc.)
            else:
                ing.cost_formula = 'COUNT'

        migrated += 1

    db.session.commit()

    flash(f"Migrated {migrated} ingredients to base unit model with cost formulas!", 'success')
    return redirect(url_for('ingredients_list'))


# ============================================
# INITIALIZE DATABASE
# ============================================

def init_db():
    with app.app_context():
        # Enable SQLite foreign key enforcement
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        import sqlite3

        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if isinstance(dbapi_connection, sqlite3.Connection):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        db.create_all()

        # Add new columns if they don't exist (for existing databases)
        with db.engine.connect() as conn:
            # Check and add ingredient_id to shopping_item
            try:
                conn.execute(db.text("SELECT ingredient_id FROM shopping_item LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE shopping_item ADD COLUMN ingredient_id INTEGER REFERENCES ingredient(id)"))
                conn.commit()

            # Check and add base_unit to ingredient
            try:
                conn.execute(db.text("SELECT base_unit FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN base_unit VARCHAR(10) DEFAULT 'EA'"))
                conn.commit()

            # Check and add min_purchase to ingredient
            try:
                conn.execute(db.text("SELECT min_purchase FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN min_purchase FLOAT DEFAULT 1.0"))
                conn.commit()

            # Check and add is_core to ingredient
            try:
                conn.execute(db.text("SELECT is_core FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN is_core BOOLEAN DEFAULT 0"))
                conn.commit()

            # Check and add unit_size to ingredient
            try:
                conn.execute(db.text("SELECT unit_size FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN unit_size FLOAT"))
                conn.commit()

            # Check and add unit_size_unit to ingredient
            try:
                conn.execute(db.text("SELECT unit_size_unit FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN unit_size_unit VARCHAR(10)"))
                conn.commit()

            # Check and add cost_formula to ingredient
            try:
                conn.execute(db.text("SELECT cost_formula FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN cost_formula VARCHAR(20) DEFAULT 'COUNT'"))
                conn.commit()

            # Check and add portion_ml to ingredient
            try:
                conn.execute(db.text("SELECT portion_ml FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN portion_ml FLOAT"))
                conn.commit()

            # Check and add portion_g to ingredient
            try:
                conn.execute(db.text("SELECT portion_g FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN portion_g FLOAT"))
                conn.commit()

            # Check and add pkg_count to ingredient
            try:
                conn.execute(db.text("SELECT pkg_count FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN pkg_count FLOAT"))
                conn.commit()

            # Check and add piece_weight_g to ingredient (for WEIGHT formula - avg weight per piece)
            try:
                conn.execute(db.text("SELECT piece_weight_g FROM ingredient LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE ingredient ADD COLUMN piece_weight_g FLOAT"))
                conn.commit()

            # Check and add source to shopping_item (for non-destructive regeneration)
            try:
                conn.execute(db.text("SELECT source FROM shopping_item LIMIT 1"))
            except Exception:
                conn.execute(db.text("ALTER TABLE shopping_item ADD COLUMN source VARCHAR(20) DEFAULT 'manual'"))
                conn.commit()


if __name__ == '__main__':
    init_db()
    # host='0.0.0.0' allows access from other devices on the network
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
