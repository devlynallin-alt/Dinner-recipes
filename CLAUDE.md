# CLAUDE.md

Instructions for Claude Code when working with this repository.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py                    # Direct run
# or
set FLASK_APP=app.py && flask run  # Windows
export FLASK_APP=app.py && flask run  # Linux/Mac

# App runs at http://localhost:5000
```

---

## Environment

**Python**: 3.10+ required (tested on 3.11)
**OS**: Windows, Linux, macOS

### Required Environment Variables

For production, set these (development has sensible defaults):

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SECRET_KEY` | Production | `dev-only-change-in-production` | Flask session signing |
| `FLASK_ENV` | No | `development` | `development` or `production` |
| `FLASK_DEBUG` | No | `1` in dev | Enable debug mode |

### .env.example

```bash
SECRET_KEY=your-secret-key-here-change-me
FLASK_ENV=production
FLASK_DEBUG=0
```

### Paths (auto-configured)

- **Database**: `instance/recipes.db` (SQLite, auto-created)
- **Uploads**: `static/uploads/` (auto-created)

---

## Change Policy

**Read this before making changes.**

### Golden Rules

1. **Keep behavior identical** unless the task explicitly asks for behavior changes
2. **No schema changes without migrations** - use `flask db migrate`, never raw ALTER TABLE
3. **Never bypass security utilities** - always use `safe_fetch()`, `validate_and_process_image()`, sanitizers
4. **Test your changes** - run the verification checklist below
5. **Don't grow app.py** - extract logic to `services/`, `utils/`, `models/` when touching related code

### When Modifying Critical Code

These areas require extra care:

| Area | Search for | Risk |
|------|------------|------|
| Unit conversions | `def convert_to_base_unit` | Wrong costs everywhere |
| Cost calculations | `def calculate_ingredient_cost` | Wrong totals |
| Ingredient parsing | `def parse_ingredient` | Import failures |
| Shopping aggregation | `def generate_shopping_list` | Wrong quantities |

**Rule**: If you change any of these, verify with the checklist below.

### Refactoring Guidance

When touching route handlers in `app.py`:
- Extract business logic to `services/`
- Extract parsing/formatting to `utils/`
- Keep routes thin: validate input → call service → return response

---

## Verification Checklist

Run these after any significant change:

```bash
# 1. Server starts without errors
python app.py

# 2. In browser, verify:
```

| Check | URL | What to verify |
|-------|-----|----------------|
| Home loads | `/` | Recipe grid displays |
| Import works | `/recipe/import` | Paste a recipe URL, preview shows ingredients |
| Shopping generates | `/shopping` | Add recipes, click generate, costs appear |
| Meal plan works | `/mealplan` | Randomize button fills meals |
| Migrations run | - | `flask db upgrade` completes |
| Image upload | Edit any recipe | Upload image, verify it saves |

### Security Spot Checks

| Test | Expected |
|------|----------|
| Import from `http://127.0.0.1/` | Should be **blocked** (SSRF) |
| Import from `http://192.168.1.1/` | Should be **blocked** (SSRF) |
| Upload `.svg` as image | Should be **rejected** |
| Recipe name with `<script>` | Should be **escaped** in display |

---

## Architecture

### Project Structure

```
webapp/
├── app.py                    # Routes + inline logic (~2500 lines, aim to shrink)
├── config.py                 # Dev/Prod/Test configuration classes
├── models/                   # SQLAlchemy models (use these for new code)
│   ├── ingredient.py        # Ingredient, IngredientSynonym
│   ├── recipe.py            # Recipe, RecipeIngredient
│   ├── shopping.py          # ShoppingItem, PantryStaple, UseUpItem
│   ├── mealplan.py          # MealPlan
│   └── settings.py          # Settings
├── constants/                # Application constants
│   ├── units.py             # UNIT_MAPPINGS, VOLUME_TO_ML, WEIGHT_TO_G
│   ├── ingredients.py       # INGREDIENT_ALIASES, AVERAGE_WEIGHTS
│   └── validation.py        # VALID_COST_FORMULAS, VALID_BASE_UNITS
├── services/                 # Business logic (use these for new code)
│   ├── parsing.py           # Ingredient text parsing
│   ├── cost.py              # Cost calculations
│   ├── matching.py          # Ingredient name matching
│   └── shopping.py          # Shopping list generation
├── utils/                    # Security utilities (ALWAYS use these)
│   ├── url_validator.py     # safe_fetch(), is_safe_url()
│   ├── image_handler.py     # validate_and_process_image()
│   └── sanitizer.py         # sanitize_text(), sanitize_url(), etc.
├── migrations/               # Alembic migrations (Flask-Migrate)
├── templates/                # Jinja2 templates (13 files)
├── static/uploads/           # Recipe images
└── instance/recipes.db       # SQLite database
```

### Tech Stack

- **Backend**: Flask 3.0, SQLAlchemy ORM, Flask-Migrate
- **Database**: SQLite
- **Frontend**: Bootstrap 5, Jinja2
- **Security**: SSRF protection, XSS sanitization, PIL image validation

---

## Key Functions (search for these)

### Cost System (the heart of the app)

| Function | Search | Purpose |
|----------|--------|---------|
| `convert_to_base_unit` | `def convert_to_base_unit` | Converts recipe units to base units |
| `calculate_ingredient_cost` | `def calculate_ingredient_cost` | Calculates cost for a RecipeIngredient |
| `generate_shopping_list` | `def generate_shopping_list` | Aggregates, applies minimums, calculates totals |

### Parsing

| Function | Search | Purpose |
|----------|--------|---------|
| `parse_ingredient` | `def parse_ingredient` | "2 cups flour" → (qty=2, unit=CUP, name="flour") |
| `parse_fraction` | `def parse_fraction` | "1 1/2" → 1.5 |
| `normalize_fractions` | `def normalize_fractions` | Unicode fractions (½ → 0.5) |

### Matching

| Function | Search | Purpose |
|----------|--------|---------|
| `normalize_ingredient_name` | `def normalize_ingredient_name` | Removes adjectives, singularizes |
| `find_ingredient_match` | `def find_ingredient_match` | Matches via synonyms or exact |
| `get_ingredient_suggestions` | `def get_ingredient_suggestions` | Ranked suggestions for name |

### Security (always use these)

| Function | Import from | Purpose |
|----------|-------------|---------|
| `safe_fetch()` | `utils.url_validator` | SSRF-safe HTTP requests |
| `validate_and_process_image()` | `utils.image_handler` | Validates + re-encodes images |
| `sanitize_text()` | `utils.sanitizer` | HTML escapes user text |
| `sanitize_url()` | `utils.sanitizer` | Blocks javascript:, data: |

---

## Cost Formula System

5 formula types for calculating ingredient costs:

| Formula | Field | Example |
|---------|-------|---------|
| `WEIGHT` | `piece_weight_g` | 2 chicken breasts × 250g = 500g → 0.5 KG × $10/KG |
| `VOLUME` | - | 2 cups milk → 0.47 L × $4/L |
| `PORTION` | `portion_ml/g` | 4 TBSP butter → 0.5 sticks × $3.50/stick |
| `PACKAGE` | `pkg_count` | 3 eggs ÷ 12/carton = 0.25 cartons × $4.20 |
| `COUNT` | - | 2 lemons × $0.99/EA |

---

## Database Models

| Model | Purpose |
|-------|---------|
| `Ingredient` | Ingredients with cost formulas and pricing |
| `IngredientSynonym` | Maps alternate names to canonical ingredients |
| `Recipe` | Recipe metadata (name, servings, instructions, image) |
| `RecipeIngredient` | Join table: recipe + ingredient + quantity/unit |
| `PantryStaple` | Ingredients in pantry (excluded from shopping) |
| `MealPlan` | Weekly meal assignments (day 1-7, meal type, locked) |
| `ShoppingItem` | Shopping list entries (source: 'manual', 'recipe', 'mealplan') |
| `UseUpItem` | Ingredients to prioritize using |
| `Settings` | Key-value app settings |

---

## Routes Overview

| Section | Path prefix | Key routes |
|---------|-------------|------------|
| Recipes | `/recipe/` | view, add, edit, delete, import |
| Shopping | `/shopping/` | list, add, generate, check |
| Meal Plan | `/mealplan/` | view, randomize, lock, generate shopping |
| Ingredients | `/ingredient/` | list, add, edit, delete, cleanup |
| Pantry | `/pantry/` | list, add, toggle, delete |
| Other | `/` | home, `/whatcanmake` |

---

## Database Migrations

### Use Flask-Migrate (required for schema changes)

```bash
# Generate migration after model changes
flask db migrate -m "Add column_name to table"

# Apply migration
flask db upgrade

# Rollback if needed
flask db downgrade
```

### Legacy `init_db()` (read-only, don't add new migrations here)

There's a legacy migration path in `init_db()` for backwards compatibility. **Don't use it for new changes** - it exists only for old deployments that haven't switched to Flask-Migrate.

---

## Security Rules

### SSRF Protection

- **Always use `safe_fetch()`** for external URLs, never raw `requests.get()`
- Blocks: localhost, 127.x.x.x, 10.x.x.x, 172.16-31.x.x, 192.168.x.x, ::1
- Blocks: non-http(s) schemes
- Blocks: redirects to private IPs

### Image Uploads

- **Always use `validate_and_process_image()`**, never save raw uploads
- Re-encodes all images to JPEG (strips malicious content)
- Rejects: SVG (XSS vector), non-image files
- Detects: decompression bombs
- **Never trust filename** - generate new filename (recipe_N.jpg)

### XSS Prevention

- **Always sanitize external data** before storing/displaying
- Use `sanitize_text()`, `sanitize_recipe_name()`, `sanitize_instructions()`
- `sanitize_url()` blocks javascript:, data: schemes

### Field Validation

- `cost_formula` must be in `VALID_COST_FORMULAS`
- `base_unit` must be in `VALID_BASE_UNITS`
- Reject unknown values with 400 error

### CSRF

**Known gap**: Forms are not currently CSRF-protected. Don't add sensitive state-changing operations without addressing this.

---

## Deployment (PythonAnywhere)

### Setup

1. Upload code to PythonAnywhere
2. Create virtualenv: `mkvirtualenv --python=python3.11 myenv`
3. Install deps: `pip install -r requirements.txt`
4. Set WSGI file to `pythonanywhere_wsgi.py`

### Production Config

```python
# In pythonanywhere_wsgi.py or set env vars:
import os
os.environ['SECRET_KEY'] = 'your-production-secret-key'
os.environ['FLASK_ENV'] = 'production'
```

### Checklist

| Task | Notes |
|------|-------|
| Set `SECRET_KEY` | Generate secure random key |
| Run migrations | `flask db upgrade` in console |
| Create uploads folder | `mkdir -p static/uploads` |
| Set static files | Configure in Web tab |
| Check ALLOWED_HOSTS | If using ProxyFix, configure trusted proxies |

### Database in Production

- SQLite works fine for single-user/low-traffic
- Database file: `instance/recipes.db`
- **Backup regularly** - it's just a file

---

## Templates (13 files)

| Template | Purpose |
|----------|---------|
| `base.html` | Base layout, navbar, Bootstrap |
| `index.html` | Home page recipe grid |
| `recipes.html` | Recipe list with category filter |
| `recipe_view.html` | Recipe detail with cost breakdown |
| `recipe_form.html` | Add/edit recipe form |
| `recipe_import.html` | Import step 1: enter URL |
| `recipe_import_review.html` | Import step 2: match ingredients |
| `shopping.html` | Shopping list with categories |
| `shopping_result.html` | Generated shopping preview |
| `ingredients.html` | Ingredient database, inline editing |
| `mealplan.html` | 7-day meal plan |
| `pantry.html` | Pantry staples |
| `whatcanmake.html` | Recipes makeable with pantry |

---

## Constants Reference

Search for these when you need to modify them:

| Constant | Search | Purpose |
|----------|--------|---------|
| `UNIT_MAPPINGS` | `UNIT_MAPPINGS = {` | Unit name variations → standard |
| `VOLUME_TO_ML` | `VOLUME_TO_ML = {` | Volume unit → milliliters |
| `WEIGHT_TO_G` | `WEIGHT_TO_G = {` | Weight unit → grams |
| `INGREDIENT_ALIASES` | `INGREDIENT_ALIASES = {` | Alternate names → canonical |
| `AVERAGE_WEIGHTS` | `AVERAGE_WEIGHTS = {` | Default weights for produce |
| `VALID_COST_FORMULAS` | `VALID_COST_FORMULAS = {` | Allowed cost formula values |
| `VALID_BASE_UNITS` | `VALID_BASE_UNITS = {` | Allowed base unit values |

---

## Importing from Modular Packages

Prefer imports from packages for new code:

```python
from models import db, Ingredient, Recipe, ShoppingItem
from constants import UNIT_MAPPINGS, INGREDIENT_ALIASES, VALID_COST_FORMULAS
from services import parse_ingredient, normalize_ingredient_name
from utils import safe_fetch, validate_and_process_image, sanitize_text
```
