"""
Settings Model

Contains the Settings model for application-wide settings storage.
"""

from .base import db


class Settings(db.Model):
    """Key-value storage for application settings."""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200))
