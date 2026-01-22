from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
import random
import os
import re
import json
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dinner-recipes-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    'can': 'EA', 'cans': 'EA',
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
    recipe = db.relationship('Recipe')

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200))

class UseUpItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    ingredient = db.relationship('Ingredient')

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
    quantity = float(request.form['quantity'])
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
    ri.quantity = float(request.form.get('quantity', ri.quantity))
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
            key = (ing_name_upper, size_key, ri.unit.upper())
            qty = ri.quantity * multiplier

            if key in consolidated:
                consolidated[key]['qty'] += qty
            else:
                consolidated[key] = {
                    'name': ri.ingredient.name,
                    'qty': qty,
                    'size': ri.size,
                    'unit': ri.unit,
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

        # For non-container items, auto-convert large quantities
        if not size:
            if unit == 'OZ' and qty >= 16:
                qty, unit = qty / 16, 'LB'
            elif unit == 'ML' and qty >= 1000:
                qty, unit = qty / 1000, 'L'
            elif unit == 'G' and qty >= 1000:
                qty, unit = qty / 1000, 'KG'

        qty = round(qty, 2)

        # Calculate leftover based on pack size
        pack_size = item['pack_size']
        leftover = 0
        if pack_size > 1:
            packs_needed = max(1, -(-int(qty) // pack_size))
            leftover = (packs_needed * pack_size) - qty

        shopping_items.append({
            'name': item['name'],
            'qty': qty,
            'size': size,
            'unit': unit,
            'category': item['category'],
            'pack_size': pack_size,
            'leftover': round(leftover, 2) if leftover > 0 else None,
            'cost': round(item['cost'] * qty, 2),
            'is_use_up': item['is_use_up']
        })

    shopping_items.sort(key=lambda x: (x['category'], x['name']))

    subtotal = sum(item['cost'] for item in shopping_items)
    tax = subtotal * 0.12
    total = subtotal + tax

    return shopping_items, round(subtotal, 2), round(tax, 2), round(total, 2)


@app.route('/shopping')
def shopping_list():
    recipes = Recipe.query.filter(Recipe.category != 'Archive').order_by(Recipe.name).all()
    use_up_items = UseUpItem.query.all()
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('shopping.html', recipes=recipes, use_up_items=use_up_items, ingredients=ingredients)

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
    # Get all dinner recipes and shuffle
    all_dinners = list(Recipe.query.filter_by(category='Dinner').all())
    random.shuffle(all_dinners)

    # Get all desserts and shuffle
    all_desserts = list(Recipe.query.filter_by(category='Dessert').all())
    random.shuffle(all_desserts)

    # Clear existing meal plan
    MealPlan.query.delete()

    # Assign 7 random dinners and desserts
    for day in range(1, 8):
        # Pick dinner
        if all_dinners:
            dinner_idx = (day - 1) % len(all_dinners)
            selected_dinner = all_dinners[dinner_idx]
            meal = MealPlan(week=1, day=day, meal_type='Dinner', recipe_id=selected_dinner.id)
            db.session.add(meal)

        # Pick dessert
        if all_desserts:
            dessert_idx = (day - 1) % len(all_desserts)
            selected_dessert = all_desserts[dessert_idx]
            meal = MealPlan(week=1, day=day, meal_type='Dessert', recipe_id=selected_dessert.id)
            db.session.add(meal)

    db.session.commit()
    flash('Week randomized!', 'success')
    return redirect(url_for('meal_plan'))

@app.route('/mealplan/shopping', methods=['POST'])
def shopping_from_mealplan():
    meals = MealPlan.query.filter_by(week=1).all()
    if not meals:
        flash('No meals in the plan. Randomize first!', 'warning')
        return redirect(url_for('meal_plan'))

    recipe_ids = {meal.recipe_id for meal in meals if meal.recipe_id}
    items, subtotal, tax, total = generate_shopping_list(recipe_ids)
    return render_template('shopping_result.html', items=items, subtotal=subtotal, tax=tax, total=total)

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

    # Add 'used_in_recipes' flag to each ingredient
    for ing in ingredients:
        ing.used_in_recipes = ing.id in used_ingredient_ids

    return render_template('ingredients.html', ingredients=ingredients)

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

@app.route('/pantry/add-common', methods=['POST'])
def pantry_add_common():
    common_staples = [
        'Salt', 'Pepper', 'Oil', 'Olive Oil', 'Butter', 'Garlic', 'Onion', 'Flour', 'Sugar',
        'Vanilla Extract', 'Vanilla', 'Baking Powder', 'Baking Soda',
        'Paprika', 'Cumin', 'Oregano', 'Basil', 'Thyme', 'Rosemary', 'Cinnamon',
        'Chili Powder', 'Cayenne', 'Italian Seasoning', 'Bay Leaves'
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
