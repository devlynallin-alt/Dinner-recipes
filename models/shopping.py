"""
Shopping Models

Contains the ShoppingItem, PantryStaple, and UseUpItem models
for managing shopping lists and pantry tracking.
"""

from .base import db


class ShoppingItem(db.Model):
    """Shopping list item with cost tracking and source information."""
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


class PantryStaple(db.Model):
    """Ingredients always in pantry (excluded from shopping lists)."""
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id', ondelete='CASCADE'), nullable=False, index=True)
    have_it = db.Column(db.Boolean, default=True)
    ingredient = db.relationship('Ingredient')


class UseUpItem(db.Model):
    """Ingredients to prioritize using in meal planning."""
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id', ondelete='CASCADE'), nullable=False)
    ingredient = db.relationship('Ingredient')
