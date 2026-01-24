"""
Smoke tests for the recipe app.
Run with: python tests/smoke.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_app_imports():
    """Verify app can be imported without errors."""
    from app import app, db
    assert app is not None
    assert db is not None
    print("OK: App imports successfully")

def test_models_import():
    """Verify models can be imported."""
    from app import Ingredient, Recipe, ShoppingItem, MealPlan
    assert Ingredient is not None
    assert Recipe is not None
    print("OK: Models import successfully")

def test_security_utils_import():
    """Verify security utilities can be imported."""
    from utils import safe_fetch, validate_and_process_image, sanitize_text
    assert callable(safe_fetch)
    assert callable(validate_and_process_image)
    assert callable(sanitize_text)
    print("OK: Security utils import successfully")

def test_constants_import():
    """Verify constants can be imported."""
    from app import UNIT_MAPPINGS, VOLUME_TO_ML, WEIGHT_TO_G, VALID_COST_FORMULAS
    assert 'CUP' in VOLUME_TO_ML
    assert 'LB' in WEIGHT_TO_G
    assert 'WEIGHT' in VALID_COST_FORMULAS
    print("OK: Constants import successfully")

def test_conversion_constants_unchanged():
    """Verify critical conversion constants have expected values."""
    from app import VOLUME_TO_ML, WEIGHT_TO_G

    # These values must not change
    assert VOLUME_TO_ML['ML'] == 1
    assert VOLUME_TO_ML['L'] == 1000
    assert VOLUME_TO_ML['CUP'] == 236.588
    assert WEIGHT_TO_G['G'] == 1
    assert WEIGHT_TO_G['KG'] == 1000
    assert WEIGHT_TO_G['LB'] == 453.592
    print("OK: Conversion constants unchanged")

def test_app_runs():
    """Verify app can create test client."""
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        response = client.get('/')
        assert response.status_code == 200
        print("OK: App serves home page")

if __name__ == '__main__':
    print("Running smoke tests...\n")

    tests = [
        test_app_imports,
        test_models_import,
        test_security_utils_import,
        test_constants_import,
        test_conversion_constants_unchanged,
        test_app_runs,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"FAIL: {test.__name__} - {e}")
            failed += 1

    print(f"\n{'='*40}")
    if failed:
        print(f"FAILED: {failed}/{len(tests)} tests")
        sys.exit(1)
    else:
        print(f"PASSED: {len(tests)}/{len(tests)} tests")
        sys.exit(0)
