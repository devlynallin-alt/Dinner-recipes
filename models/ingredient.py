"""
Ingredient Models

Contains the Ingredient and IngredientSynonym models for managing
ingredient data and name mappings.
"""

from .base import db


class Ingredient(db.Model):
    """
    Ingredient with cost formula system for calculating recipe costs.

    Cost Formula Types:
    - WEIGHT: Meats, produce sold by weight. Converts G/OZ/LB/KG to base_unit
    - VOLUME: Liquids like broth, milk. Converts ML/L/CUP/TBSP/TSP to base_unit
    - PORTION: Items sold by portion (butter sticks). Uses portion_ml/portion_g
    - PACKAGE: Items in packages (eggs). Uses pkg_count for fraction calculation
    - COUNT: Items sold individually (lemons). No conversion needed
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    category = db.Column(db.String(50), default='Other', index=True)

    # Cost formula type - determines conversion method
    cost_formula = db.Column(db.String(20), default='COUNT')

    # Base unit for cost calculation (what you pay per)
    base_unit = db.Column(db.String(10), default='EA')

    # Cost per ONE base_unit
    cost = db.Column(db.Float, default=0.0)

    # Minimum purchase quantity in base_unit
    min_purchase = db.Column(db.Float, default=1.0)

    # Core ingredient - never deleted by cleanup even if unused
    is_core = db.Column(db.Boolean, default=False)

    # For PORTION formula: size of one portion in ML and/or grams
    portion_ml = db.Column(db.Float, nullable=True)
    portion_g = db.Column(db.Float, nullable=True)

    # For PACKAGE formula: number of units per package
    pkg_count = db.Column(db.Float, nullable=True)

    # For WEIGHT formula: average weight per piece in grams
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
