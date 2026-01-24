"""
Meal Plan Model

Contains the MealPlan model for weekly meal planning.
"""

from .base import db


class MealPlan(db.Model):
    """Weekly meal plan entry with lock support."""
    id = db.Column(db.Integer, primary_key=True)
    week = db.Column(db.Integer, nullable=False, index=True)
    day = db.Column(db.Integer, nullable=False)  # 1-7 for days of week
    meal_type = db.Column(db.String(20), nullable=False)  # 'Dinner', 'Dessert', etc.
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id', ondelete='SET NULL'), nullable=True, index=True)
    locked = db.Column(db.Boolean, default=False)  # Locked meals preserved during randomization
    recipe = db.relationship('Recipe')
