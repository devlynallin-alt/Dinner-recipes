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
flask db init      # First time setup
flask db migrate   # Generate migration
flask db upgrade   # Apply migrations
```

## Architecture Overview

This is a Flask recipe management and meal planning application with a modular architecture.

### Project Structure

```
webapp/
├── app.py                    # Flask routes and main application
├── config.py                 # Configuration classes (Dev/Prod/Test)
├── models/                   # SQLAlchemy database models
│   ├── __init__.py          # Exports all models + db instance
│   ├── base.py              # SQLAlchemy db instance
│   ├── ingredient.py        # Ingredient, IngredientSynonym
│   ├── recipe.py            # Recipe, RecipeIngredient
│   ├── shopping.py          # ShoppingItem, PantryStaple, UseUpItem
│   ├── mealplan.py          # MealPlan
│   └── settings.py          # Settings
├── constants/                # Application constants
│   ├── __init__.py          # Exports all constants
│   ├── units.py             # Unit conversions, mappings, fractions
│   ├── ingredients.py       # Aliases, average weights, minimums
│   └── validation.py        # Whitelists for security validation
├── services/                 # Business logic
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
├── templates/                # Jinja2 HTML templates
├── static/                   # CSS, JS, uploaded images
└── instance/                 # SQLite database
```

### Tech Stack
- **Backend**: Flask + SQLAlchemy ORM
- **Database**: SQLite (`instance/recipes.db`)
- **Frontend**: Bootstrap 5 + Jinja2 templates
- **Recipe Import**: BeautifulSoup + JSON-LD parsing
- **Security**: SSRF protection, XSS sanitization, image validation

### Database Models

| Model | File | Purpose |
|-------|------|---------|
| `Ingredient` | `models/ingredient.py` | Ingredients with cost formulas and pricing |
| `IngredientSynonym` | `models/ingredient.py` | Maps alternate names to canonical ingredients |
| `Recipe` | `models/recipe.py` | Recipe metadata (name, servings, instructions, image) |
| `RecipeIngredient` | `models/recipe.py` | Join table: recipe + ingredient + quantity/unit |
| `MealPlan` | `models/mealplan.py` | Weekly meal assignments (day 1-7, meal type, locked) |
| `PantryStaple` | `models/shopping.py` | Ingredients always in pantry (excluded from shopping) |
| `UseUpItem` | `models/shopping.py` | Ingredients to prioritize using |
| `ShoppingItem` | `models/shopping.py` | Manual + generated shopping list entries |

### Cost Formula System

The app uses 5 formula types to calculate ingredient costs:

| Formula | Field Used | Example |
|---------|------------|---------|
| `WEIGHT` | `piece_weight_g` | Chicken breast: 2 breasts × 250g = 500g → 0.5 KG × $10/KG |
| `VOLUME` | - | Milk: 2 cups → 0.47 L × $4/L |
| `PORTION` | `portion_ml`, `portion_g` | Butter: 4 TBSP → 0.5 sticks × $3.50/stick |
| `PACKAGE` | `pkg_count` | Eggs: 3 eggs ÷ 12/carton = 0.25 cartons × $4.20 |
| `COUNT` | - | Lemons: 2 × $0.99/EA |

### Key Services

| Service | File | Functions |
|---------|------|-----------|
| Parsing | `services/parsing.py` | `parse_ingredient()`, `parse_fraction()`, `float_to_fraction()` |
| Cost | `services/cost.py` | `convert_to_base_unit()`, `calculate_ingredient_cost()` |
| Matching | `services/matching.py` | `normalize_ingredient_name()`, `find_ingredient_match()` |
| Shopping | `services/shopping.py` | `generate_shopping_list()`, `format_shopping_qty()` |

### Security Utilities

| Utility | File | Purpose |
|---------|------|---------|
| `safe_fetch()` | `utils/url_validator.py` | SSRF-protected HTTP requests |
| `is_safe_url()` | `utils/url_validator.py` | Validates URLs (blocks localhost, private IPs) |
| `validate_and_process_image()` | `utils/image_handler.py` | PIL-based image validation |
| `sanitize_text()` | `utils/sanitizer.py` | HTML escape for XSS prevention |
| `sanitize_url()` | `utils/sanitizer.py` | Blocks dangerous URL schemes |

### Validation Constants

Located in `constants/validation.py`:
- `VALID_COST_FORMULAS` - Whitelist: WEIGHT, VOLUME, PORTION, PACKAGE, COUNT
- `VALID_BASE_UNITS` - Whitelist: EA, G, KG, LB, OZ, ML, L, CUP, TBSP, TSP, etc.
- `VALID_CATEGORIES` - Whitelist for ingredient categories

### Recipe Import Flow (3 steps)

1. **Fetch URL** (`/recipe/import`) - Extracts JSON-LD with SSRF protection
2. **Review & Match** (`/recipe/import/preview`) - Parses ingredients, matches to database
3. **Save** (`/recipe/import/save`) - Creates Recipe with validated/sanitized data

### Unit Conversion Tables

Located in `constants/units.py`:
```python
VOLUME_TO_ML = {'ML': 1, 'L': 1000, 'CUP': 236.588, 'TBSP': 14.787, 'TSP': 4.929}
WEIGHT_TO_G = {'G': 1, 'KG': 1000, 'OZ': 28.3495, 'LB': 453.592}
```

## Template Files

| Template | Purpose |
|----------|---------|
| `recipe_view.html` | Recipe display with cost breakdown, cook mode |
| `recipe_import_review.html` | Step 2 of import - ingredient matching UI |
| `shopping.html` | Shopping list with category grouping |
| `ingredients.html` | Ingredient database with inline editing |
| `mealplan.html` | 7-day meal plan with lock/randomize |
| `pantry.html` | Pantry staples management |

## Database Migrations

### Flask-Migrate (Recommended)
```bash
flask db migrate -m "Add new column"
flask db upgrade
```

### Legacy Manual Migrations
SQLite migrations are handled in `init_db()`. New columns are added with:
```python
try:
    conn.execute(db.text("SELECT new_column FROM table LIMIT 1"))
except Exception:
    conn.execute(db.text("ALTER TABLE table ADD COLUMN new_column TYPE"))
    conn.commit()
```

## Deployment

For PythonAnywhere, use `pythonanywhere_wsgi.py` as the WSGI configuration.

## Security Notes

- All external URLs are validated through `utils/url_validator.py`
- Images are re-encoded through PIL to strip malicious content
- User input is sanitized via `utils/sanitizer.py`
- Field values are validated against whitelists in `constants/validation.py`
- Shopping list regeneration preserves manual items (source tracking)
