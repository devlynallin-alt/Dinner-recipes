from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from fractions import Fraction
import math
import random
import os
import re
import json
import requests
from bs4 import BeautifulSoup

# Common fractions for display
COMMON_FRACTIONS = {
    0.125: '1/8', 0.25: '1/4', 0.333: '1/3', 0.375: '3/8',
    0.5: '1/2', 0.625: '5/8', 0.667: '2/3', 0.75: '3/4', 0.875: '7/8'
}

def parse_fraction(text):
    """Parse fraction string like '2/3' or '1 1/2' to float"""
    if not text:
        return 0.0
    text = str(text).strip()
    # Already a number
    try:
        return float(text)
    except ValueError:
        pass
    # Handle mixed fractions like "1 1/2"
    parts = text.split()
    total = 0.0
    for part in parts:
        if '/' in part:
            try:
                num, denom = part.split('/')
                total += float(num) / float(denom)
            except (ValueError, ZeroDivisionError):
                pass
        else:
            try:
                total += float(part)
            except ValueError:
                pass
    return total if total > 0 else 0.0

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
    """Format quantity string for shopping list, with unit conversions"""
    qty = item['qty']
    unit = item['unit']
    size = item.get('size')

    if size:
        return f"{int(qty)} x {int(size)}{unit.lower()}"

    # For LB, show as KG | LB
    if unit == 'LB':
        kg = qty * 0.453592
        return f"{kg:.2f} KG|{qty:.2f} LB"

    # For KG, show as KG | LB
    if unit == 'KG':
        lb = qty / 0.453592
        return f"{qty:.2f} KG|{lb:.2f} LB"

    # For ML, convert based on amount
    if unit == 'ML':
        # Small amounts: use TSP or TBSP
        if qty <= 5:
            tsp = qty / 4.929
            return f"{float_to_fraction(tsp)} tsp|{qty:.0f} ML"
        elif qty <= 30:
            tbsp = qty / 14.787
            return f"{float_to_fraction(tbsp)} tbsp|{qty:.0f} ML"
        else:
            # Larger amounts: cups | ML
            cups = qty / 236.588
            return f"{float_to_fraction(cups)} cups|{qty:.0f} ML"

    # For CUP, show cups | ML
    if unit == 'CUP':
        ml = qty * 236.588
        return f"{float_to_fraction(qty)} cups|{ml:.0f} ML"

    return f"{qty} {unit}"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dinner-recipes-secret-key'
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

# Keywords indicating notes to remove from ingredient text
NOTE_KEYWORDS = [
    'optional', 'divided', 'or more', 'or less', 'to taste',
    'for serving', 'for garnish', 'at room temp', 'softened',
    'melted', 'chopped', 'diced', 'minced', 'sliced', 'cubed',
    'sifted', 'packed', 'beaten', 'room temperature', 'thawed',
    'drained', 'rinsed', 'peeled', 'seeded', 'cored', 'trimmed',
    'cut into', 'plus more', 'as needed', 'torn', 'shredded'
]

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
    'garlic clove': 'Garlic',
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

    # Remove common descriptors
    remove_words = ['fresh', 'dried', 'chopped', 'diced', 'sliced', 'minced',
                    'large', 'small', 'medium', 'whole', 'raw', 'cooked',
                    'boneless', 'skinless', 'organic', 'frozen', 'canned',
                    'a', 'an', 'the', 'of']
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

    # Also handle generic -s plural if not in map
    words = [w[:-1] if w.endswith('s') and len(w) > 3 and w not in ['cheese', 'rice', 'grass', 'molasses', 'hummus'] else w for w in words]

    normalized = ' '.join(words)

    # Check exact aliases first
    if normalized in INGREDIENT_ALIASES:
        return INGREDIENT_ALIASES[normalized]

    # Try partial alias matches (only if alias is contained in normalized, not the other way)
    # Sort by longest alias first to match more specific aliases first
    for alias, canonical in sorted(INGREDIENT_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias == normalized:
            return canonical

    # Capitalize each word for display
    return ' '.join(word.capitalize() for word in normalized.split())


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

def parse_fraction(s):
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
    except:
        return 1.0

def parse_ingredient(text):
    """Parse ingredient text like '2 cups flour' into (quantity, unit, name)"""
    original = text
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
        quantity = parse_fraction(qty_str)

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

# ============================================
# DATABASE MODELS
# ============================================

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    category = db.Column(db.String(50), default='Other', index=True)
    default_unit = db.Column(db.String(20), default='EA')
    cost = db.Column(db.Float, default=0.0)
    pack_size = db.Column(db.Integer, default=1)

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
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    size = db.Column(db.Float, nullable=True)  # Container size (e.g., 400 for 400ml can)
    unit = db.Column(db.String(20), nullable=False)
    ingredient = db.relationship('Ingredient')

class PantryStaple(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False, index=True)
    have_it = db.Column(db.Boolean, default=True)
    ingredient = db.relationship('Ingredient')

class MealPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week = db.Column(db.Integer, nullable=False, index=True)
    day = db.Column(db.Integer, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=True, index=True)
    locked = db.Column(db.Boolean, default=False)
    recipe = db.relationship('Recipe')

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200))

class UseUpItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    ingredient = db.relationship('Ingredient')

class ShoppingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.String(50), default='')
    checked = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50), default='Other')
    unit_cost = db.Column(db.String(20), default='')  # e.g., "$3.99/LB"
    cost = db.Column(db.Float, default=0.0)  # calculated total cost

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
    return render_template('recipe_view.html', recipe=recipe)

@app.route('/recipe/add', methods=['GET', 'POST'])
def recipe_add():
    if request.method == 'POST':
        recipe = Recipe(
            name=request.form['name'],
            category=request.form['category'],
            difficulty=request.form['difficulty'],
            protein_type=request.form['protein_type'],
            servings=int(request.form['servings']),
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

    if request.method == 'POST':
        recipe.name = request.form['name']
        recipe.category = request.form['category']
        recipe.difficulty = request.form['difficulty']
        recipe.protein_type = request.form['protein_type']
        recipe.servings = int(request.form['servings'])
        recipe.instructions = request.form.get('instructions', '')
        db.session.commit()
        flash(f'Recipe "{recipe.name}" updated!', 'success')
        return redirect(url_for('recipe_view', id=recipe.id))

    return render_template('recipe_form.html', recipe=recipe, ingredients=ingredients)

@app.route('/recipe/<int:id>/delete', methods=['POST'])
def recipe_delete(id):
    recipe = Recipe.query.get_or_404(id)
    name = recipe.name
    db.session.delete(recipe)
    db.session.commit()
    flash(f'Recipe "{name}" deleted!', 'success')
    return redirect(url_for('recipes_list'))

@app.route('/recipe/<int:id>/ingredient/add', methods=['POST'])
def recipe_ingredient_add(id):
    recipe = Recipe.query.get_or_404(id)
    ingredient_id = int(request.form['ingredient_id'])
    quantity = parse_fraction(request.form['quantity'])
    size = float(request.form['size']) if request.form.get('size') else None
    unit = request.form['unit']

    ri = RecipeIngredient(recipe_id=id, ingredient_id=ingredient_id, quantity=quantity, size=size, unit=unit)
    db.session.add(ri)
    db.session.commit()

    return redirect(url_for('recipe_edit', id=id))

@app.route('/recipe/<int:recipe_id>/ingredient/<int:ri_id>/update', methods=['POST'])
def recipe_ingredient_update(recipe_id, ri_id):
    ri = RecipeIngredient.query.get_or_404(ri_id)
    ri.ingredient_id = int(request.form.get('ingredient_id', ri.ingredient_id))
    ri.quantity = parse_fraction(request.form.get('quantity', ri.quantity))
    ri.size = float(request.form['size']) if request.form.get('size') else None
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
        # Delete old image if exists
        if recipe.image:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], recipe.image)
            if os.path.exists(old_path):
                os.remove(old_path)

        # Save new image
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"recipe_{id}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        recipe.image = filename
        db.session.commit()
        flash('Image uploaded!', 'success')
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

        try:
            # Fetch the page
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
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
                except:
                    continue

            if recipe_data:
                # Extract data from JSON-LD
                name = recipe_data.get('name', 'Imported Recipe')

                # Get instructions
                instructions = ''
                inst_data = recipe_data.get('recipeInstructions', [])
                if isinstance(inst_data, str):
                    instructions = inst_data
                elif isinstance(inst_data, list):
                    steps = []
                    for i, inst in enumerate(inst_data, 1):
                        if isinstance(inst, str):
                            steps.append(f"{i}. {inst}")
                        elif isinstance(inst, dict):
                            text = inst.get('text', inst.get('name', ''))
                            if text:
                                steps.append(f"{i}. {text}")
                    instructions = '\n'.join(steps)

                # Get ingredients list
                ingredients_list = recipe_data.get('recipeIngredient', [])

                # Get servings
                servings = recipe_data.get('recipeYield', 4)
                if isinstance(servings, list):
                    servings = servings[0] if servings else 4
                if isinstance(servings, str):
                    match = re.search(r'\d+', servings)
                    servings = int(match.group()) if match else 4

                # Get image
                image_url = recipe_data.get('image', '')
                if isinstance(image_url, list):
                    image_url = image_url[0] if image_url else ''
                if isinstance(image_url, dict):
                    image_url = image_url.get('url', '')

                return render_template('recipe_import.html',
                    imported=True,
                    name=name,
                    instructions=instructions,
                    ingredients_text='\n'.join(ingredients_list),
                    servings=servings,
                    image_url=image_url,
                    source_url=url
                )
            else:
                # Fallback: try to scrape basic info
                title = soup.find('h1')
                name = title.get_text().strip() if title else 'Imported Recipe'

                flash('Could not find structured recipe data. Please enter details manually.', 'warning')
                return render_template('recipe_import.html',
                    imported=True,
                    name=name,
                    instructions='',
                    ingredients_text='',
                    servings=4,
                    image_url='',
                    source_url=url
                )

        except requests.RequestException as e:
            flash(f'Could not fetch URL: {str(e)}', 'danger')
            return render_template('recipe_import.html')

    return render_template('recipe_import.html')

@app.route('/recipe/import/save', methods=['POST'])
def recipe_import_save():
    name = request.form.get('name', 'Imported Recipe').strip()
    instructions = request.form.get('instructions', '')
    ingredients_text = request.form.get('ingredients_text', '')
    servings = int(request.form.get('servings', 4))
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

    # Download and save image if URL provided
    if image_url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            img_response = requests.get(image_url, headers=headers, timeout=10)
            img_response.raise_for_status()

            # Determine extension from content type or URL
            content_type = img_response.headers.get('content-type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = 'jpg'
            elif 'png' in content_type:
                ext = 'png'
            elif 'webp' in content_type:
                ext = 'webp'
            elif 'gif' in content_type:
                ext = 'gif'
            else:
                ext = 'jpg'

            filename = f"recipe_{recipe.id}.{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(img_response.content)
            recipe.image = filename
        except:
            pass  # Image download failed, continue without it

    # Parse and add ingredients
    ingredients_added = 0
    if ingredients_text:
        for line in ingredients_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue

            quantity, unit, ing_name = parse_ingredient(line)
            if not ing_name:
                continue

            # Normalize the ingredient name for matching
            normalized_name = normalize_ingredient_name(ing_name)

            # Standardize unit based on ingredient type
            quantity, unit = standardize_unit(quantity, unit, normalized_name)

            # Try to find existing ingredient
            # First try exact match on normalized name
            ingredient = Ingredient.query.filter(Ingredient.name.ilike(normalized_name)).first()

            # If not found, try the original parsed name
            if not ingredient:
                ingredient = Ingredient.query.filter(Ingredient.name.ilike(ing_name)).first()

            # If still not found, create new ingredient with normalized name
            if not ingredient:
                ingredient = Ingredient(
                    name=normalized_name,
                    category='Other',
                    default_unit=unit
                )
                db.session.add(ingredient)
                db.session.flush()

            # Add to recipe
            ri = RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=quantity,
                unit=unit
            )
            db.session.add(ri)
            ingredients_added += 1

    db.session.commit()

    flash(f'Recipe "{name}" imported with {ingredients_added} ingredients!', 'success')
    return redirect(url_for('recipe_view', id=recipe.id))

# ============================================
# ROUTES - SHOPPING LIST
# ============================================

def generate_shopping_list(recipe_ids, multipliers=None):
    """
    Generate a shopping list from recipe IDs.
    Returns (shopping_items, subtotal, tax, total)
    """
    if multipliers is None:
        multipliers = {}

    # Get pantry staples to exclude (filter out any with deleted ingredients)
    pantry_staples = {ps.ingredient.name.upper() for ps in PantryStaple.query.filter_by(have_it=True).all() if ps.ingredient}
    pantry_staples.add('WATER')  # Always exclude water

    # Get USE UP items for highlighting
    use_up_names = {item.ingredient.name.upper() for item in UseUpItem.query.all() if item.ingredient}

    # Consolidate ingredients
    consolidated = {}

    for recipe_id in recipe_ids:
        recipe = Recipe.query.get(int(recipe_id))
        if not recipe:
            continue

        multiplier = multipliers.get(recipe.id, 1.0)

        for ri in recipe.ingredients:
            ing_name_upper = ri.ingredient.name.upper()
            if ing_name_upper in pantry_staples:
                continue

            # Use size in key if present (for containers like cans)
            size_key = ri.size if ri.size else None
            unit = ri.unit.upper()
            qty = ri.quantity * multiplier

            # Convert garlic heads to cloves (1 head = 9 cloves)
            if 'GARLIC' in ing_name_upper and unit == 'HEAD':
                qty = qty * 9
                unit = 'CLOVE'

            # Convert chicken thighs EA to weight (6 thighs = 1 lb = 453.592g)
            if 'CHICKEN' in ing_name_upper and 'THIGH' in ing_name_upper and unit == 'EA':
                qty = qty * 75.6  # ~75.6g per thigh
                unit = 'G'

            # Convert cheese from cups to weight (1 LB = 4 cups shredded)
            # 1 cup shredded cheese = 0.25 LB = 113.4g
            if 'CHEESE' in ing_name_upper and unit in ('CUP', 'CUPS'):
                qty = qty * 113.4  # Convert cups to grams
                unit = 'G'

            # Normalize to base units for consolidation (ML for volume, G for weight)
            if unit in UNIT_CONVERSIONS:
                base_unit, factor = UNIT_CONVERSIONS[unit]
                qty = qty * factor
                unit = base_unit

            key = (ing_name_upper, size_key, unit)

            if key in consolidated:
                consolidated[key]['qty'] += qty
            else:
                consolidated[key] = {
                    'name': ri.ingredient.name,
                    'qty': qty,
                    'size': ri.size,
                    'unit': unit,
                    'category': ri.ingredient.category,
                    'pack_size': ri.ingredient.pack_size,
                    'cost': ri.ingredient.cost,
                    'is_use_up': ing_name_upper in use_up_names
                }

    # Convert units and build shopping items
    shopping_items = []
    for key, item in consolidated.items():
        qty = item['qty']
        unit = item['unit']
        size = item.get('size')

        # For non-container items, auto-convert to user-friendly units
        if not size:
            # Volume: ML -> L if large, or -> CUP for medium amounts
            if unit == 'ML':
                if qty >= 1000:
                    qty, unit = qty / 1000, 'L'
                elif qty >= 237:  # About 1 cup
                    qty, unit = qty / 236.588, 'CUP'
            # Weight: G -> KG if large, or -> LB for medium amounts
            elif unit == 'G':
                ing_name_upper = key[0]
                # Cheese always converts to LB (we buy by the pound)
                if 'CHEESE' in ing_name_upper:
                    qty, unit = qty / 453.592, 'LB'
                elif qty >= 1000:
                    qty, unit = qty / 1000, 'KG'
                elif qty >= 454:  # About 1 lb
                    qty, unit = qty / 453.592, 'LB'

        qty = round(qty, 2)

        # Calculate leftover based on pack size
        pack_size = item['pack_size']
        leftover = 0
        if pack_size > 1:
            packs_needed = max(1, -(-int(qty) // pack_size))
            leftover = (packs_needed * pack_size) - qty

        # Calculate cost - item['cost'] is the per-unit cost
        unit_cost = item['cost']
        ing_upper = key[0]

        # Check for minimum purchase quantity
        min_qty_for_cost = None
        for min_key, (min_val, min_unit) in MINIMUM_PURCHASE.items():
            if min_key in ing_upper:
                min_qty_for_cost = (min_val, min_unit)
                break

        # Handle canned/container items - cost is per CAN
        # Must buy whole cans, round up (e.g., 1.5 cans = 2 cans)
        if size:
            cost_unit = 'CAN'
            cans_needed = max(1, math.ceil(qty))  # Round up, minimum 1 can
            total_cost = round(unit_cost * cans_needed, 2)
        # Weight-based items - cost is per LB
        elif unit in ('LB', 'KG', 'G'):
            cost_unit = 'LB'
            if unit == 'KG':
                qty_in_lb = qty * 2.20462
            elif unit == 'G':
                qty_in_lb = qty / 453.592
            else:
                qty_in_lb = qty
            # Apply minimum (e.g., 1 LB for beef)
            if min_qty_for_cost and min_qty_for_cost[1] == 'LB':
                qty_in_lb = max(min_qty_for_cost[0], qty_in_lb)
            total_cost = round(unit_cost * qty_in_lb, 2)
        elif unit == 'EA':
            # Check if this item is priced per EA (not per LB)
            is_per_ea = any(ea_item in ing_upper for ea_item in COST_PER_EA)
            if is_per_ea:
                # Cost is per EA - apply minimum
                cost_unit = 'EA'
                if min_qty_for_cost and min_qty_for_cost[1] == 'EA':
                    cost_qty = max(min_qty_for_cost[0], qty)
                else:
                    cost_qty = max(1, qty)  # Minimum 1 EA
                total_cost = round(unit_cost * cost_qty, 2)
            else:
                # Check if we have average weight for this item
                avg_weight = None
                for name_key, weight in AVERAGE_WEIGHTS.items():
                    if name_key in ing_upper:
                        avg_weight = weight
                        break
                if avg_weight:
                    # Convert EA to LB using average weight
                    cost_unit = 'LB'
                    qty_in_lb = (qty * avg_weight) / 453.592
                    # Apply minimum (e.g., 1 LB for beef)
                    if min_qty_for_cost and min_qty_for_cost[1] == 'LB':
                        qty_in_lb = max(min_qty_for_cost[0], qty_in_lb)
                    total_cost = round(unit_cost * qty_in_lb, 2)
                else:
                    # No average weight, assume cost is per EA
                    cost_unit = 'EA'
                    cost_qty = max(1, qty)  # Minimum 1 EA
                    total_cost = round(unit_cost * cost_qty, 2)
        else:
            # For volume units - cost is per L (liter)
            cost_unit = 'L'
            if unit == 'ML':
                qty_in_l = qty / 1000
            elif unit == 'CUP':
                qty_in_l = (qty * 236.588) / 1000
            elif unit == 'L':
                qty_in_l = qty
            else:
                # TSP, TBSP - convert to L
                qty_in_l = qty / 1000 if unit in ('TSP', 'TBSP') else qty
                cost_unit = unit
            # Apply minimum (e.g., 1 L for broth)
            if min_qty_for_cost and min_qty_for_cost[1] == 'L':
                qty_in_l = max(min_qty_for_cost[0], qty_in_l)
            total_cost = round(unit_cost * qty_in_l, 2)

        shopping_items.append({
            'name': item['name'],
            'qty': qty,
            'size': size,
            'unit': unit,
            'category': item['category'],
            'pack_size': pack_size,
            'leftover': round(leftover, 2) if leftover > 0 else None,
            'unit_cost': f"${unit_cost:.2f}/{cost_unit}" if unit_cost > 0 else '',
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
    items = ShoppingItem.query.order_by(ShoppingItem.checked, ShoppingItem.category, ShoppingItem.name).all()
    # Get names of ingredients in pantry for highlighting
    pantry_names = set(
        ps.ingredient.name.lower() for ps in PantryStaple.query.options(joinedload(PantryStaple.ingredient)).all()
    )
    return render_template('shopping.html', items=items, pantry_names=pantry_names)

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
        # Clear existing items first
        ShoppingItem.query.delete()

        items, _, _, _ = generate_shopping_list(recipe_ids)
        for item in items:
            qty_str = format_shopping_qty(item)
            shopping_item = ShoppingItem(
                name=item['name'],
                quantity=qty_str,
                category=item['category'],
                unit_cost=item.get('unit_cost', ''),
                cost=item['cost']
            )
            db.session.add(shopping_item)
        db.session.commit()
        flash(f"Added {len(items)} items from recipes", "success")
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

    # Clear existing shopping list and add items from meal plan
    ShoppingItem.query.delete()

    items, _, _, _ = generate_shopping_list(recipe_ids)
    for item in items:
        qty_str = format_shopping_qty(item)
        shopping_item = ShoppingItem(
            name=item['name'],
            quantity=qty_str,
            category=item['category'],
            unit_cost=item.get('unit_cost', ''),
            cost=item['cost']
        )
        db.session.add(shopping_item)
    db.session.commit()
    flash(f"Added {len(items)} items from meal plan", "success")
    return redirect(url_for('shopping_list'))

# ============================================
# ROUTES - INGREDIENTS
# ============================================

@app.route('/ingredients')
def ingredients_list():
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()

    # Get IDs of ingredients used in recipes
    used_ingredient_ids = set(
        ri.ingredient_id for ri in RecipeIngredient.query.with_entities(RecipeIngredient.ingredient_id).distinct()
    )

    # Get IDs of ingredients in pantry
    pantry_ids = set(
        ps.ingredient_id for ps in PantryStaple.query.with_entities(PantryStaple.ingredient_id).all()
    )

    # Add 'used_in_recipes' flag to each ingredient
    for ing in ingredients:
        ing.used_in_recipes = ing.id in used_ingredient_ids

    return render_template('ingredients.html', ingredients=ingredients, pantry_ids=pantry_ids)

@app.route('/ingredient/add', methods=['POST'])
def ingredient_add():
    ingredient = Ingredient(
        name=request.form['name'],
        category=request.form['category'],
        default_unit=request.form['default_unit'],
        cost=float(request.form['cost']) if request.form['cost'] else 0.0,
        pack_size=int(request.form['pack_size']) if request.form['pack_size'] else 1
    )
    db.session.add(ingredient)
    db.session.commit()
    flash(f'Ingredient "{ingredient.name}" added!', 'success')
    return redirect(url_for('ingredients_list'))

@app.route('/ingredient/<int:id>/edit', methods=['POST'])
def ingredient_edit(id):
    ingredient = Ingredient.query.get_or_404(id)
    ingredient.name = request.form['name']
    ingredient.category = request.form['category']
    ingredient.default_unit = request.form['default_unit']
    ingredient.cost = float(request.form['cost']) if request.form['cost'] else 0.0
    ingredient.pack_size = int(request.form['pack_size']) if request.form['pack_size'] else 1
    db.session.commit()
    flash(f'Ingredient "{ingredient.name}" updated!', 'success')
    return redirect(url_for('ingredients_list'))

@app.route('/ingredient/<int:id>/delete', methods=['POST'])
def ingredient_delete(id):
    ingredient = Ingredient.query.get_or_404(id)
    name = ingredient.name
    db.session.delete(ingredient)
    db.session.commit()
    flash(f'Ingredient "{name}" deleted!', 'success')
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
        recipes_json.append({
            'id': r.id,
            'name': r.name,
            'category': r.category,
            'image': r.image,
            'ingredients': [ri.ingredient_id for ri in r.ingredients],
            'ingredient_names': [ri.ingredient.name for ri in r.ingredients]
        })

    import json
    return render_template('whatcanmake.html',
                         ingredients=ingredients,
                         pantry_ids=pantry_ids,
                         recipes_json=json.dumps(recipes_json))

# ============================================
# ROUTES - PANTRY STAPLES
# ============================================

@app.route('/pantry')
def pantry_list():
    staples = PantryStaple.query.options(joinedload(PantryStaple.ingredient)).order_by(Ingredient.name).join(Ingredient).all()
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('pantry.html', staples=staples, ingredients=ingredients)

@app.route('/pantry/add', methods=['POST'])
def pantry_add():
    ingredient_id = int(request.form['ingredient_id'])
    existing = PantryStaple.query.filter_by(ingredient_id=ingredient_id).first()
    if not existing:
        staple = PantryStaple(ingredient_id=ingredient_id, have_it=True)
        db.session.add(staple)
        db.session.commit()
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
# HELPER FUNCTIONS
# ============================================

def get_setting(key, default=''):
    setting = Settings.query.filter_by(key=key).first()
    return setting.value if setting else default

def set_setting(key, value):
    setting = Settings.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        setting = Settings(key=key, value=value)
        db.session.add(setting)
    db.session.commit()

# ============================================
# INITIALIZE DATABASE
# ============================================

def init_db():
    with app.app_context():
        db.create_all()

if __name__ == '__main__':
    init_db()
    # host='0.0.0.0' allows access from other devices on the network
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
