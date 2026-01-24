"""
Models Package

Exports all database models and the db instance for use throughout the application.
"""

from .base import db

from .ingredient import Ingredient, IngredientSynonym
from .recipe import Recipe, RecipeIngredient
from .shopping import ShoppingItem, PantryStaple, UseUpItem
from .mealplan import MealPlan
from .settings import Settings

__all__ = [
    'db',
    'Ingredient',
    'IngredientSynonym',
    'Recipe',
    'RecipeIngredient',
    'ShoppingItem',
    'PantryStaple',
    'UseUpItem',
    'MealPlan',
    'Settings',
]
