"""
Ingredient Constants

Contains ingredient aliases, average weights, and special handling rules.
"""

# Ingredient name aliases (normalized name -> canonical name)
INGREDIENT_ALIASES = {
    'sourdough': 'Sourdough Bread',
    'sourdough bread': 'Sourdough Bread',
    'bread sourdough': 'Sourdough Bread',
    'white bread': 'White Bread',
    'bread white': 'White Bread',
    'ground beef': 'Ground Beef',
    'beef ground': 'Ground Beef',
    'minced beef': 'Ground Beef',
    'chicken breast': 'Chicken Breast',
    'breast chicken': 'Chicken Breast',
    'boneless skinless chicken breast': 'Chicken Breast',
    'boneless skinless chicken breasts': 'Chicken Breast',
    'chicken thigh': 'Chicken Thigh',
    'chicken thighs': 'Chicken Thigh',
    'boneless skinless chicken thigh': 'Chicken Thigh',
    'boneless skinless chicken thighs': 'Chicken Thigh',
    'boneless chicken thigh': 'Chicken Thigh',
    'boneless chicken thighs': 'Chicken Thigh',
    'green onion': 'Green Onion',
    'green onions': 'Green Onion',
    'scallion': 'Green Onion',
    'scallions': 'Green Onion',
    'spring onion': 'Green Onion',
    'spring onions': 'Green Onion',
    'bell pepper': 'Bell Pepper',
    'bell peppers': 'Bell Pepper',
    'garlic clove': 'Garlic',
    'garlic cloves': 'Garlic',
    'minced garlic': 'Garlic',
    'olive oil': 'Olive Oil',
    'extra virgin olive oil': 'Olive Oil',
    'vegetable oil': 'Vegetable Oil',
    'canola oil': 'Vegetable Oil',
    'heavy cream': 'Heavy Cream',
    'whipping cream': 'Heavy Cream',
    'heavy whipping cream': 'Heavy Cream',
    'sour cream': 'Sour Cream',
    'cream cheese': 'Cream Cheese',
    'parmesan cheese': 'Parmesan',
    'parmigiano': 'Parmesan',
    'parmigiano reggiano': 'Parmesan',
    'cheddar cheese': 'Cheddar Cheese',
    'mozzarella cheese': 'Mozzarella',
    'kosher salt': 'Salt',
    'sea salt': 'Salt',
    'table salt': 'Salt',
    'black pepper': 'Pepper',
    'ground pepper': 'Pepper',
    'ground black pepper': 'Pepper',
    # Eggs
    'egg': 'Egg',
    'eggs': 'Egg',
    'large egg': 'Egg',
    'large eggs': 'Egg',
    # Common items
    'yellow onion': 'Onion',
    'white onion': 'Onion',
    'red onion': 'Red Onion',
    'clove garlic': 'Garlic',
    'all purpose flour': 'Flour',
    'all-purpose flour': 'Flour',
    'ap flour': 'Flour',
    'granulated sugar': 'Sugar',
    'white sugar': 'Sugar',
    'brown sugar': 'Brown Sugar',
    'light brown sugar': 'Brown Sugar',
    'dark brown sugar': 'Brown Sugar',
    'unsalted butter': 'Butter',
    'salted butter': 'Butter',
}

# Average weight per EA (in grams) for common ingredients
# Used for cost calculation when recipe uses EA but price is per LB
AVERAGE_WEIGHTS = {
    # Produce - Vegetables
    'TOMATO': 150,          # 1 medium tomato = 150g (0.33 lb)
    'ONION': 225,           # 1 medium onion = 225g (0.5 lb)
    'RED ONION': 225,
    'YELLOW ONION': 225,
    'WHITE ONION': 225,
    'GREEN ONION': 30,      # 1 green onion = 30g
    'SCALLION': 30,
    'CARROT': 70,           # 1 medium carrot = 70g (0.15 lb)
    'CELERY': 45,           # 1 stalk = 45g (0.1 lb)
    'POTATO': 225,          # 1 medium potato = 225g (0.5 lb)
    'RUSSET POTATO': 225,
    'YELLOW POTATO': 170,
    'RED POTATO': 170,
    'SWEET POTATO': 200,
    'BELL PEPPER': 150,     # 1 medium = 150g (0.33 lb)
    'RED PEPPER': 150,
    'YELLOW PEPPER': 150,
    'GREEN PEPPER': 150,
    'JALAPENO': 15,         # 1 jalapeno = 15g
    'CUCUMBER': 300,        # 1 medium = 300g (0.66 lb)
    'ZUCCHINI': 200,        # 1 medium = 200g
    'MUSHROOM': 18,         # 1 medium = 18g
    'GARLIC': 5,            # 1 clove = 5g
    'GINGER': 30,           # 1 inch piece = 30g
    'BROCCOLI': 600,        # 1 head = 600g (1.3 lb)
    'CAULIFLOWER': 900,     # 1 head = 900g (2 lb)
    'CABBAGE': 900,         # 1 head = 900g (2 lb)
    'LETTUCE': 300,         # 1 head = 300g
    'ROMAINE': 300,
    'SPINACH': 30,          # 1 cup = 30g
    'KALE': 30,
    'AVOCADO': 200,         # 1 medium = 200g
    'CORN': 200,            # 1 ear = 200g

    # Produce - Fruits
    'LEMON': 85,            # 1 lemon = 85g (0.19 lb)
    'LIME': 65,             # 1 lime = 65g (0.14 lb)
    'ORANGE': 180,          # 1 medium = 180g
    'APPLE': 180,           # 1 medium = 180g
    'BANANA': 120,          # 1 medium = 120g

    # Proteins
    'EGG': 50,              # 1 large egg = 50g
    'CHICKEN BREAST': 225,  # 1 breast = 225g (0.5 lb)
    'CHICKEN THIGH': 115,   # 1 thigh = 115g (0.25 lb)
    'BACON': 30,            # 1 slice = 30g
    'SAUSAGE': 100,         # 1 link = 100g

    # Dairy
    'BUTTER': 14,           # 1 tbsp = 14g

    # Bakery
    'BREAD': 30,            # 1 slice = 30g
    'TORTILLA': 45,         # 1 tortilla = 45g
    'BUN': 60,              # 1 bun = 60g
}

# Items priced per EA (not per LB) - don't convert to weight for cost
COST_PER_EA = {
    'LEMON', 'LIME', 'GREEN ONION', 'SCALLION', 'AVOCADO',
    'LETTUCE', 'ROMAINE', 'CABBAGE', 'CAULIFLOWER', 'BROCCOLI',
    'CUCUMBER', 'CELERY', 'CORN', 'BANANA', 'ORANGE', 'APPLE',
    'TORTILLA', 'BREAD', 'BUN', 'EGG',
}

# Minimum purchase quantities (keyword -> (min_qty, unit))
MINIMUM_PURCHASE = {
    'BEEF': (1, 'LB'),           # Minimum 1 LB
    'CHICKEN': (1, 'LB'),        # Minimum 1 LB
    'PORK': (1, 'LB'),           # Minimum 1 LB
    'EGG': (6, 'EA'),            # Minimum 6 eggs
    'BROTH': (1, 'L'),           # Minimum 1 L
    'STOCK': (1, 'L'),           # Minimum 1 L
}

# Keywords indicating notes to remove from ingredient text (set for O(1) lookup)
NOTE_KEYWORDS = {
    'optional', 'divided', 'or more', 'or less', 'to taste',
    'for serving', 'for garnish', 'at room temp', 'softened',
    'melted', 'chopped', 'diced', 'minced', 'sliced', 'cubed',
    'sifted', 'packed', 'beaten', 'room temperature', 'thawed',
    'drained', 'rinsed', 'peeled', 'seeded', 'cored', 'trimmed',
    'cut into', 'plus more', 'as needed', 'torn', 'shredded'
}
