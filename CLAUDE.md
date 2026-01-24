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

**Key function**: `convert_to_base_unit()` at line 490 handles all conversions.

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

### Utilities
| Function | Line | Purpose |
|----------|------|---------|
| `safe_float()` | 118 | Safe float parsing with bounds |
| `safe_int()` | 131 | Safe int parsing with bounds |
| `float_to_fraction()` | 27 | Converts 0.5 → "1/2" for display |
| `allowed_file()` | 114 | Validates image file extensions |

---

## Routes

### Recipes (lines 1049-1571)
| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/` | GET | `index()` | Home page with recipe list |
| `/recipes` | GET | `recipes_list()` | Recipe list with category filter |
| `/recipe/<id>` | GET | `recipe_view()` | Recipe detail with cost breakdown |
| `/recipe/add` | GET/POST | `recipe_add()` | Create new recipe |
| `/recipe/<id>/edit` | GET/POST | `recipe_edit()` | Edit recipe |
| `/recipe/<id>/delete` | POST | `recipe_delete()` | Delete recipe |
| `/recipe/<id>/upload-image` | POST | `recipe_upload_image()` | Upload recipe image |

### Recipe Import (lines 1252-1571)
| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/recipe/import` | GET/POST | `recipe_import()` | Fetch URL, extract JSON-LD |
| `/recipe/import/preview` | POST | `recipe_import_preview()` | Review ingredient matches |
| `/recipe/import/save` | POST | `recipe_import_save()` | Save with confirmed mappings |

### Shopping List (lines 1573-1764)
| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/shopping` | GET | `shopping_list()` | View shopping list |
| `/shopping/add` | POST | `shopping_add()` | Add manual item |
| `/shopping/check/<id>` | POST | `shopping_check()` | Toggle item checked |
| `/shopping/delete/<id>` | POST | `shopping_delete()` | Remove item |
| `/shopping/add-from-recipes` | POST | `shopping_add_from_recipes()` | Generate from recipes |
| `/shopping/generate` | POST | `shopping_generate()` | Generate with multipliers |

### Meal Plan (lines 1788-1880)
| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/mealplan` | GET | `meal_plan()` | View weekly meal plan |
| `/mealplan/randomize` | POST | `meal_plan_randomize()` | Randomize unlocked meals |
| `/mealplan/lock/<day>/<type>` | POST | `meal_plan_lock()` | Toggle meal lock |
| `/mealplan/shopping` | POST | `shopping_from_mealplan()` | Generate shopping from plan |

### Ingredients (lines 1882-2145)
| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/ingredients` | GET | `ingredients_list()` | List all ingredients |
| `/ingredient/add` | POST | `ingredient_add()` | Add new ingredient |
| `/ingredient/<id>/edit` | POST | `ingredient_edit()` | Edit ingredient (AJAX) |
| `/ingredient/<id>/delete` | POST | `ingredient_delete()` | Delete ingredient |
| `/ingredients/cleanup` | POST | `ingredients_cleanup()` | Merge duplicates, remove unused |

### Pantry (lines 2179-2284)
| Route | Method | Function | Purpose |
|-------|--------|----------|---------|
| `/pantry` | GET | `pantry_list()` | View pantry staples |
| `/pantry/add` | POST | `pantry_add()` | Add to pantry |
| `/pantry/<id>/toggle` | POST | `pantry_toggle()` | Toggle have_it status |
| `/pantry/<id>/delete` | POST | `pantry_delete()` | Remove from pantry |
| `/pantry/add-common` | POST | `pantry_add_common()` | Add common staples |

### Other
| Route | Method | Function | Line | Purpose |
|-------|--------|----------|------|---------|
| `/whatcanmake` | GET | `what_can_make()` | 2152 | Find recipes with pantry items |
| `/useup/add` | POST | `useup_add()` | 1772 | Add to use-up list |
| `/migrate/data` | GET | `migrate_data()` | 2291 | Legacy data migration |
| `/migrate/base-units` | GET | `migrate_base_units()` | 2346 | Migrate to base unit model |

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

### Unit Mappings (line 193)
```python
UNIT_MAPPINGS = {
    'pound': 'LB', 'cups': 'CUP', 'tablespoon': 'TBSP', 'teaspoon': 'TSP',
    'gram': 'G', 'kilogram': 'KG', 'ounce': 'OZ', 'milliliter': 'ML', ...
}
```

### Unit Conversions (line 217)
```python
VOLUME_TO_ML = {'ML': 1, 'L': 1000, 'CUP': 236.588, 'TBSP': 14.787, 'TSP': 4.929}
WEIGHT_TO_G = {'G': 1, 'KG': 1000, 'OZ': 28.3495, 'LB': 453.592}
```

### Ingredient Aliases (line 353)
Maps alternate names to canonical names (67 aliases):
```python
INGREDIENT_ALIASES = {
    'ground beef': 'Ground Beef', 'chicken breast': 'Chicken Breast',
    'green onion': 'Green Onion', 'scallion': 'Green Onion', ...
}
```

### Average Weights (line 233)
Default weights in grams for produce/proteins:
```python
AVERAGE_WEIGHTS = {
    'TOMATO': 150, 'ONION': 225, 'CHICKEN BREAST': 225, 'EGG': 50, ...
}
```

### Validation Whitelists (line 182)
```python
VALID_COST_FORMULAS = {'WEIGHT', 'VOLUME', 'PORTION', 'PACKAGE', 'COUNT'}
VALID_BASE_UNITS = {'EA', 'G', 'KG', 'LB', 'OZ', 'ML', 'L', 'CUP', 'TBSP', 'TSP', ...}
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
SQLite migrations are handled in `init_db()` (line 2446). New columns are added with:
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
