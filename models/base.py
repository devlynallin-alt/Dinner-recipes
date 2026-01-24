"""
Database Base Module

Creates the SQLAlchemy database instance that all models inherit from.
This is separate to avoid circular imports.
"""

from flask_sqlalchemy import SQLAlchemy

# Create the SQLAlchemy instance
# This will be initialized with the Flask app in app.py
db = SQLAlchemy()
