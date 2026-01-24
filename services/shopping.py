"""
Shopping List Service

Functions for generating and managing shopping lists.
"""

import math
from .cost import convert_to_base_unit
from .parsing import float_to_fraction


def format_shopping_qty(item):
    """Format quantity string for shopping list display."""
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


def generate_shopping_list(recipe_ids, multipliers, db, Recipe, Ingredient, PantryStaple, UseUpItem):
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
