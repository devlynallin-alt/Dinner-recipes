# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the development server
python app.py
# or
flask run

# The app runs at http://localhost:5000

# Database migrations (Flask-Migrate)
flask db init      # First time setup (already done)
flask db migrate -m "Description"  # Generate migration
flask db upgrade   # Apply migrations
```

## Architecture Overview

This is a Flask recipe management and meal planning application (~2550 lines in app.py) with a modular architecture.

### Project Structure

```
webapp/
├── app.py                    # Flask routes and main application (~2550 lines)
├── config.py                 # Configuration classes (Dev/Prod/Test)
├── models/                   # SQLAlchemy database models (modular)
│   ├── __init__.py          # Exports all models + db instance
│   ├── base.py              # SQLAlchemy db instance
│   ├── ingredient.py        # Ingredient, IngredientSynonym
│   ├── recipe.py            # Recipe, RecipeIngredient
│   ├── shopping.py          # ShoppingItem, PantryStaple, UseUpItem
│   ├── mealplan.py          # MealPlan
│   └── settings.py          # Settings
├── constants/                # Application constants (modular)
│   ├── __init__.py          # Exports all constants
│   ├── units.py             # Unit conversions, mappings, fractions
│   ├── ingredients.py       # Aliases, average weights, minimums
│   └── validation.py        # Whitelists for security validation
├── services/                 # Business logic (modular)
│   ├── __init__.py          # Exports all services
│   ├── parsing.py           # Ingredient text parsing, fractions
│   ├── cost.py              # Cost calculations, unit conversion
│   ├── matching.py          # Ingredient name matching
│   └── shopping.py          # Shopping list generation
├── utils/                    # Security utilities
│   ├── __init__.py          # Exports all utilities
│   ├── url_validator.py     # SSRF protection
│   ├── image_handler.py     # Image validation via PIL
│   └── sanitizer.py         # XSS prevention
├── migrations/               # Alembic database migrations
├── templates/                # Jinja2 HTML templates (13 files)
├── static/uploads/           # Uploaded recipe images
└── instance/recipes.db       # SQLite database
```

### Tech Stack
- **Backend**: Flask 3.0 + SQLAlchemy ORM + Flask-Migrate
- **Database**: SQLite (`instance/recipes.db`)
- **Frontend**: Bootstrap 5 + Jinja2 templates
- **Recipe Import**: BeautifulSoup + JSON-LD parsing
- **Security**: SSRF protection, XSS sanitization, PIL image validation
- **Dependencies**: Pillow, requests, beautifulsoup4, openpyxl

---

## Database Models (app.py lines 908-1038)

| Model | Line | Purpose |
|-------|------|---------|
| `Ingredient` | 908 | Ingredients with cost formulas and pricing |
| `IngredientSynonym` | 973 | Maps alternate names to canonical ingredients |
| `Recipe` | 980 | Recipe metadata (name, servings, instructions, image) |
| `RecipeIngredient` | 992 | Join table: recipe + ingredient + quantity/unit |
| `PantryStaple` | 1001 | Ingredients always in pantry (excluded from shopping) |
| `MealPlan` | 1007 | Weekly meal assignments (day 1-7, meal type, locked) |
| `Settings` | 1016 | Key-value storage for app settings |
| `UseUpItem` | 1021 | Ingredients to prioritize using |
| `ShoppingItem` | 1026 | Manual + generated shopping list entries (with source tracking) |

### Ingredient Fields
```python
class Ingredient:
    id, name, category
    cost_formula     # WEIGHT, VOLUME, PORTION, PACKAGE, COUNT
    base_unit        # EA, G, KG, LB, OZ, ML, L, CUP, TBSP, TSP
    cost             # Cost per base_unit
    min_purchase     # Minimum purchase quantity
    is_core          # Protected from cleanup
    portion_ml/g     # For PORTION formula
    pkg_count        # For PACKAGE formula (items per package)
    piece_weight_g   # For WEIGHT formula (grams per piece)
```

---

## Cost Formula System

The app uses 5 formula types to calculate ingredient costs:

| Formula | Field Used | Example |
|---------|------------|---------|
| `WEIGHT` | `piece_weight_g` | Chicken breast: 2 breasts × 250g = 500g → 0.5 KG × $10/KG |
| `VOLUME` | - | Milk: 2 cups → 0.47 L × $4/L |
| `PORTION` | `portion_ml`, `portion_g` | Butter: 4 TBSP → 0.5 sticks × $3.50/stick |
| `PACKAGE` | `pkg_count` | Eggs: 3 eggs ÷ 12/carton = 0.25 cartons × $4.20 |
| `COUNT` | - | Lemons: 2 × $0.99/EA |

**Key function**: `convert_to_base_unit()` at line 490 handles all unit conversions.

---

## Key Functions in app.py

### Parsing & Conversion
| Function | Line | Purpose |
|----------|------|---------|
| `parse_ingredient(text)` | 837 | Parses "2 cups flour" → (qty=2, unit=CUP, name="flour") |
| `parse_fraction(value)` | 144 | Parses "1 1/2" → 1.5 |
| `normalize_fractions(text)` | 789 | Converts Unicode fractions (½ → 0.5) |
| `convert_to_base_unit()` | 490 | Converts recipe units to base units for cost |
| `convert_unit()` | 437 | Generic unit conversion |

### Ingredient Matching
| Function | Line | Purpose |
|----------|------|---------|
| `normalize_ingredient_name()` | 629 | Removes adjectives, singularizes plurals |
| `find_ingredient_match()` | 700 | Matches via synonyms or exact match |
| `get_ingredient_suggestions()` | 739 | Ranked suggestions for ingredient name |

### Cost & Shopping
| Function | Line | Purpose |
|----------|------|---------|
| `calculate_ingredient_cost(ri)` | 83 | Calculates cost for a RecipeIngredient |
| `generate_shopping_list()` | 1577 | Aggregates ingredients, applies minimums |
| `format_shopping_qty(item)` | 48 | Formats quantity with unit conversions |

### Database
| Function | Line | Purpose |
|----------|------|---------|
| `init_db()` | 2446 | Initialize database tables and run migrations |

### Utilities
| Function | Line | Purpose |
|----------|------|---------|
| `float_to_fraction()` | 27 | Converts 0.5 → "1/2" for display |
| `format_shopping_qty()` | 48 | Formats quantity with unit conversions |
| `allowed_file()` | 114 | Validates image file extensions |
| `safe_float()` | 118 | Safe float parsing with bounds |
| `safe_int()` | 131 | Safe int parsing with bounds |

---

## Routes

### Recipes (lines 1044-1250)
| Route | Method | Line | Purpose |
|-------|--------|------|---------|
| `/` | GET | 1044 | Home page with recipe list |
| `/recipes` | GET | 1053 | Recipe list with category filter |
| `/recipe/<id>` | GET | 1063 | Recipe detail with cost breakdown |
| `/recipe/add` | GET/POST | 1090 | Create new recipe |
| `/recipe/<id>/edit` | GET/POST | 1113 | Edit recipe |
| `/recipe/<id>/delete` | POST | 1141 | Delete recipe |
| `/recipe/<id>/ingredient/add` | POST | 1163 | Add ingredient to recipe |
| `/recipe/<id>/ingredient/<ri_id>/update` | POST | 1187 | Update recipe ingredient |
| `/recipe/<id>/ingredient/<ri_id>/delete` | POST | 1207 | Delete recipe ingredient |
| `/recipe/<id>/upload-image` | POST | 1214 | Upload recipe image |

### Recipe Import (lines 1251-1675)
| Route | Method | Line | Purpose |
|-------|--------|------|---------|
| `/recipe/import` | GET/POST | 1251 | Fetch URL, extract JSON-LD |
| `/recipe/import/preview` | POST | 1368 | Review ingredient matches |
| `/recipe/import/save` | POST | 1445 | Save with confirmed mappings |

### Shopping List (lines 1676-1790)
| Route | Method | Line | Purpose |
|-------|--------|------|---------|
| `/shopping` | GET | 1676 | View shopping list |
| `/shopping/add` | POST | 1698 | Add manual item (source='manual') |
| `/shopping/check/<id>` | POST | 1709 | Toggle item checked |
| `/shopping/delete/<id>` | POST | 1716 | Remove item |
| `/shopping/clear-checked` | POST | 1723 | Clear all checked items |
| `/shopping/add-from-recipes` | POST | 1730 | Generate from recipes |
| `/shopping/generate` | POST | 1755 | Generate with multipliers |
| `/useup/add` | POST | 1771 | Add to use-up list |
| `/useup/<id>/delete` | POST | 1781 | Remove from use-up list |

### Meal Plan (lines 1792-1885)
| Route | Method | Line | Purpose |
|-------|--------|------|---------|
| `/mealplan` | GET | 1792 | View weekly meal plan |
| `/mealplan/randomize` | POST | 1803 | Randomize unlocked meals |
| `/mealplan/lock/<day>/<type>` | POST | 1845 | Toggle meal lock |
| `/mealplan/shopping` | POST | 1853 | Generate shopping from plan |

### Ingredients (lines 1886-2150)
| Route | Method | Line | Purpose |
|-------|--------|------|---------|
| `/ingredients` | GET | 1886 | List all ingredients |
| `/ingredient/add` | POST | 1915 | Add new ingredient (with validation) |
| `/ingredient/<id>/edit` | POST | 1976 | Edit ingredient (AJAX, with validation) |
| `/ingredient/<id>/delete` | POST | 2057 | Delete ingredient |
| `/ingredients/cleanup` | POST | 2074 | Merge duplicates, remove unused |

### What Can I Make (line 2151)
| Route | Method | Line | Purpose |
|-------|--------|------|---------|
| `/whatcanmake` | GET | 2151 | Find recipes with pantry items |

### Pantry (lines 2181-2289)
| Route | Method | Line | Purpose |
|-------|--------|------|---------|
| `/pantry` | GET | 2181 | View pantry staples |
| `/pantry/add` | POST | 2192 | Add to pantry |
| `/pantry/<id>/toggle` | POST | 2214 | Toggle have_it status |
| `/pantry/<id>/delete` | POST | 2221 | Remove from pantry |
| `/pantry/add-from-ingredient/<id>` | POST | 2228 | Add ingredient to pantry |
| `/shopping/<id>/add-to-pantry` | POST | 2241 | Add shopping item to pantry |
| `/pantry/add-common` | POST | 2260 | Add common staples |

### Admin (lines 2290-2445)
| Route | Method | Line | Purpose |
|-------|--------|------|---------|
| `/admin/migrate` | POST | 2290 | Legacy data migration |
| `/admin/migrate-base-units` | POST | 2345 | Migrate to base unit model |

---

## Template Files (13 total)

| Template | Purpose |
|----------|---------|
| `base.html` | Base layout with navbar, Bootstrap CSS/JS |
| `index.html` | Home page with recipe grid |
| `recipes.html` | Recipe list with category filter |
| `recipe_view.html` | Recipe display with cost breakdown, cook mode |
| `recipe_form.html` | Add/edit recipe form |
| `recipe_import.html` | Step 1: Enter URL to import |
| `recipe_import_review.html` | Step 2: Review ingredient matches |
| `shopping.html` | Shopping list with category grouping |
| `shopping_result.html` | Generated shopping list preview |
| `ingredients.html` | Ingredient database with inline editing |
| `mealplan.html` | 7-day meal plan with lock/randomize |
| `pantry.html` | Pantry staples management |
| `whatcanmake.html` | Recipes makeable with current ingredients |

---

## Constants (in app.py and constants/)

### Validation Whitelists (line 183)
```python
VALID_COST_FORMULAS = {'WEIGHT', 'VOLUME', 'PORTION', 'PACKAGE', 'COUNT'}
VALID_BASE_UNITS = {'EA', 'G', 'KG', 'LB', 'OZ', 'ML', 'L', 'CUP', 'TBSP', 'TSP', 'CLOVE', 'HEAD', 'CAN'}
```

### Unit Mappings (line 205)
```python
UNIT_MAPPINGS = {
    'pound': 'LB', 'cups': 'CUP', 'tablespoon': 'TBSP', 'teaspoon': 'TSP',
    'gram': 'G', 'kilogram': 'KG', 'ounce': 'OZ', 'milliliter': 'ML', ...
}
```

### Average Weights (line 245)
Default weights in grams for produce/proteins:
```python
AVERAGE_WEIGHTS = {
    'TOMATO': 150, 'ONION': 225, 'CHICKEN BREAST': 225, 'EGG': 50, ...
}
```

### Ingredient Aliases (line 365)
Maps alternate names to canonical names (67+ aliases):
```python
INGREDIENT_ALIASES = {
    'ground beef': 'Ground Beef', 'chicken breast': 'Chicken Breast',
    'green onion': 'Green Onion', 'scallion': 'Green Onion', ...
}
```

### Unit Conversions (lines 480-483)
```python
VOLUME_TO_ML = {'ML': 1, 'L': 1000, 'CUP': 236.588, 'TBSP': 14.787, 'TSP': 4.929}
WEIGHT_TO_G = {'G': 1, 'KG': 1000, 'OZ': 28.3495, 'LB': 453.592}
```

---

## Security Utilities (utils/)

| Utility | File | Purpose |
|---------|------|---------|
| `safe_fetch()` | `url_validator.py` | SSRF-protected HTTP requests |
| `is_safe_url()` | `url_validator.py` | Validates URLs (blocks localhost, private IPs) |
| `SSRFError` | `url_validator.py` | Exception for blocked URLs |
| `validate_and_process_image()` | `image_handler.py` | PIL-based image validation, re-encodes to JPEG |
| `ImageValidationError` | `image_handler.py` | Exception for invalid images |
| `sanitize_text()` | `sanitizer.py` | HTML escape for XSS prevention |
| `sanitize_url()` | `sanitizer.py` | Blocks javascript:, data: schemes |
| `sanitize_recipe_name()` | `sanitizer.py` | Sanitizes recipe names |
| `sanitize_instructions()` | `sanitizer.py` | Sanitizes recipe instructions |
| `sanitize_ingredient_text()` | `sanitizer.py` | Sanitizes ingredient lines |

---

## Database Migrations

### Flask-Migrate (Recommended)
```bash
flask db migrate -m "Add new column"
flask db upgrade
```

### Legacy Manual Migrations
SQLite migrations are also handled in `init_db()` (line 2446) for backward compatibility. New columns can be added with:
```python
try:
    conn.execute(db.text("SELECT new_column FROM table LIMIT 1"))
except Exception:
    conn.execute(db.text("ALTER TABLE table ADD COLUMN new_column TYPE"))
    conn.commit()
```

---

## Deployment

For PythonAnywhere, use `pythonanywhere_wsgi.py` as the WSGI configuration.

---

## Security Notes

- **SSRF Protection**: All external URLs validated through `utils/url_validator.py`
  - Blocks localhost, 127.0.0.1, 192.168.x.x, 10.x.x.x, 172.16-31.x.x
  - Only allows http/https schemes
- **Image Validation**: Images re-encoded through PIL to strip malicious content
  - Validates format (JPEG, PNG, GIF, WEBP only)
  - Rejects SVG, detects decompression bombs
  - Always outputs as JPEG
- **XSS Prevention**: User input sanitized via `utils/sanitizer.py`
  - HTML escapes special characters
  - Blocks dangerous URL schemes (javascript:, data:)
- **Field Validation**: Whitelists for cost_formula, base_unit in `constants/validation.py`
- **Shopping Source Tracking**: Manual items preserved on regeneration (source column)

---

## Modular Imports (Alternative)

The codebase has parallel modular packages that can be used instead of inline definitions:

```python
# Instead of app.py inline code, you can import from:
from models import db, Ingredient, Recipe, ShoppingItem
from constants import UNIT_MAPPINGS, INGREDIENT_ALIASES, VALID_COST_FORMULAS
from services import parse_ingredient, convert_to_base_unit, normalize_ingredient_name
from utils import safe_fetch, validate_and_process_image, sanitize_text
```
