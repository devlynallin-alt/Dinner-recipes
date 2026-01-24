"""
Recipe Models

Contains the Recipe and RecipeIngredient models for managing
recipes and their ingredient associations.
"""

from .base import db


class Recipe(db.Model):
    """Recipe with metadata and ingredient associations."""
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
    """Join table linking recipes to ingredients with quantity and unit."""
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id', ondelete='CASCADE'), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    size = db.Column(db.Float, nullable=True)  # Container size (e.g., 400 for 400ml can)
    unit = db.Column(db.String(20), nullable=False)
    ingredient = db.relationship('Ingredient')
