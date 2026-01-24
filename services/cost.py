"""
Cost Calculation Service

Functions for calculating ingredient and recipe costs.
"""

from constants import VOLUME_TO_ML, WEIGHT_TO_G, WEIGHT_UNITS, VOLUME_UNITS, AVERAGE_WEIGHTS


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


def convert_to_base_unit(qty, from_unit, ingredient):
    """
    Convert recipe quantity to ingredient's base unit using formula-specific logic.

    Formula types:
    - WEIGHT:  Converts weight units (G, OZ, LB, KG) to base_unit
    - VOLUME:  Converts volume units (ML, L, CUP, TBSP, TSP) to base_unit
    - PORTION: Converts volume/weight to portion count using portion_ml/portion_g
    - PACKAGE: Converts unit count to package fraction using pkg_count
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
    # EXCEPT for PACKAGE formula where EA means different things
    if from_unit == base_unit and formula != 'PACKAGE':
        return qty

    # =========== WEIGHT FORMULA ===========
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
        if from_unit not in WEIGHT_TO_G and from_unit not in VOLUME_TO_ML:
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
    if formula == 'PACKAGE':
        if ingredient.pkg_count and ingredient.pkg_count > 0:
            # Any count-based unit (EA, CLOVE, HEAD, etc.) should be converted
            if from_unit not in WEIGHT_UNITS and from_unit not in VOLUME_UNITS:
                packages = qty / ingredient.pkg_count
                return round(packages, 4)
        return qty  # Can't convert or already in packages

    # =========== COUNT FORMULA (default) ===========
    return qty


def calculate_ingredient_cost(ri):
    """
    Calculate the cost of a recipe ingredient.
    Recipe stores original units, so convert to base_unit for cost calculation.
    """
    ing = ri.ingredient
    if not ing or ing.cost <= 0:
        return 0.0

    # Convert recipe quantity (in original unit) to base unit for cost calculation
    base_qty = convert_to_base_unit(ri.quantity, ri.unit, ing)
    cost_per_unit = ing.cost

    return round(base_qty * cost_per_unit, 2)
