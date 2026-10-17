"""Data migration: seed CategoryTemplate, BrandKnowledge, and KeywordKnowledge into the database."""
from django.db import migrations

# (name, kind, icon, hue, sort_order)
DEFAULT_CATEGORIES = [
    ('Food & Dining', 'SPEND', 'restaurant', 20, 10),
    ('Groceries', 'SPEND', 'shopping_basket', 120, 20),
    ('Shopping', 'SPEND', 'shopping_bag', 300, 30),
    ('Transport', 'SPEND', 'local_taxi', 200, 40),
    ('Fuel', 'SPEND', 'local_gas_station', 30, 50),
    ('Bills & Utilities', 'SPEND', 'receipt_long', 45, 60),
    ('Rent & Housing', 'SPEND', 'home', 260, 70),
    ('Household & Services', 'SPEND', 'cleaning_services', 170, 80),
    ('Health', 'SPEND', 'medication', 0, 90),
    ('Personal Care', 'SPEND', 'spa', 320, 100),
    ('Entertainment', 'SPEND', 'movie', 335, 110),
    ('Subscriptions', 'SPEND', 'subscriptions', 280, 120),
    ('Travel', 'SPEND', 'flight', 190, 130),
    ('Education', 'SPEND', 'school', 230, 140),
    ('Kids', 'SPEND', 'child_care', 50, 150),
    ('Insurance', 'SPEND', 'shield', 210, 160),
    ('EMI & Loans', 'SPEND', 'account_balance', 15, 170),
    ('Gifts & Donations', 'SPEND', 'redeem', 345, 180),
    ('Fees & Charges', 'SPEND', 'request_quote', 5, 190),
    ('Cash Withdrawal', 'SPEND', 'local_atm', 100, 200),
    ('Other', 'SPEND', 'category', 230, 210),
    ('Investments', 'TRANSFER', 'trending_up', 150, 220),
    ('Transfers', 'TRANSFER', 'swap_horiz', 215, 230),
    ('Credit Card Payment', 'TRANSFER', 'credit_score', 250, 240),
    ('Income & Refunds', 'INCOME', 'savings', 140, 250),
]

# (merchant_key, display_name, category_name, icon)
DEFAULT_BRANDS = [
    ('SWIGGYINSTAMART', 'Swiggy Instamart', 'Groceries', 'shopping_basket'),
    ('INSTAMART', 'Swiggy Instamart', 'Groceries', 'shopping_basket'),
    ('SWIGGY', 'Swiggy', 'Food & Dining', 'delivery_dining'),
    ('ZOMATO', 'Zomato', 'Food & Dining', 'lunch_dining'),
    ('BLINKIT', 'Blinkit', 'Groceries', 'shopping_basket'),
    ('GROFERS', 'Blinkit', 'Groceries', 'shopping_basket'),
    ('ZEPTO', 'Zepto', 'Groceries', 'shopping_bag'),
    ('BIGBASKET', 'BigBasket', 'Groceries', 'storefront'),
    ('BBNOW', 'BigBasket', 'Groceries', 'shopping_basket'),
    ('DMART', 'DMart', 'Groceries', 'storefront'),
    ('AVENUESUPERMART', 'DMart', 'Groceries', 'storefront'),
    ('JIOMART', 'JioMart', 'Groceries', 'shopping_cart'),
    ('AMAZONPRIME', 'Amazon Prime', 'Subscriptions', 'video_camera_front'),
    ('AMAZONPAY', 'Amazon', 'Shopping', 'package_2'),
    ('AMAZON', 'Amazon', 'Shopping', 'package_2'),
    ('FLIPKART', 'Flipkart', 'Shopping', 'shopping_cart'),
    ('MYNTRA', 'Myntra', 'Shopping', 'apparel'),
    ('AJIO', 'Ajio', 'Shopping', 'checkroom'),
    ('NYKAA', 'Nykaa', 'Personal Care', 'spa'),
    ('MEESHO', 'Meesho', 'Shopping', 'shopping_bag'),
    ('TATACLIQ', 'Tata CLiQ', 'Shopping', 'shopping_bag'),
    ('CROMA', 'Croma', 'Shopping', 'devices'),
    ('RELIANCEDIGITAL', 'Reliance Digital', 'Shopping', 'devices'),
    ('IKEA', 'IKEA', 'Household & Services', 'chair'),
    ('UBER', 'Uber', 'Transport', 'local_taxi'),
    ('OLACABS', 'Ola', 'Transport', 'directions_car'),
    ('ANITECHNOLOGIES', 'Ola', 'Transport', 'directions_car'),
    ('RAPIDO', 'Rapido', 'Transport', 'two_wheeler'),
    ('NAMMAYATRI', 'Namma Yatri', 'Transport', 'directions_car'),
    ('METRO', 'Metro', 'Transport', 'subway'),
    ('FASTAG', 'FASTag', 'Transport', 'toll'),
    ('IRCTC', 'IRCTC', 'Travel', 'train'),
    ('MAKEMYTRIP', 'MakeMyTrip', 'Travel', 'travel_explore'),
    ('GOIBIBO', 'Goibibo', 'Travel', 'travel_explore'),
    ('CLEARTRIP', 'Cleartrip', 'Travel', 'flight_takeoff'),
    ('INDIGO', 'IndiGo', 'Travel', 'flight'),
    ('INTERGLOBE', 'IndiGo', 'Travel', 'flight'),
    ('AIRINDIA', 'Air India', 'Travel', 'flight'),
    ('AKASA', 'Akasa Air', 'Travel', 'flight'),
    ('AIRBNB', 'Airbnb', 'Travel', 'hotel'),
    ('OYO', 'OYO', 'Travel', 'hotel'),
    ('REDBUS', 'redBus', 'Travel', 'directions_bus'),
    ('NETFLIX', 'Netflix', 'Subscriptions', 'tv'),
    ('SPOTIFY', 'Spotify', 'Subscriptions', 'headphones'),
    ('HOTSTAR', 'Disney+ Hotstar', 'Subscriptions', 'tv'),
    ('JIOHOTSTAR', 'JioHotstar', 'Subscriptions', 'tv'),
    ('YOUTUBE', 'YouTube Premium', 'Subscriptions', 'smart_display'),
    ('GOOGLEPLAY', 'Google Play', 'Subscriptions', 'play_arrow'),
    ('APPLECOM', 'Apple', 'Subscriptions', 'phone_iphone'),
    ('ITUNES', 'Apple', 'Subscriptions', 'music_note'),
    ('OPENAI', 'OpenAI', 'Subscriptions', 'smart_toy'),
    ('CHATGPT', 'OpenAI', 'Subscriptions', 'smart_toy'),
    ('BOOKMYSHOW', 'BookMyShow', 'Entertainment', 'confirmation_number'),
    ('PVR', 'PVR INOX', 'Entertainment', 'movie'),
    ('INOX', 'PVR INOX', 'Entertainment', 'movie'),
    ('DISTRICT', 'District', 'Entertainment', 'theater_comedy'),
    ('STARBUCKS', 'Starbucks', 'Food & Dining', 'coffee'),
    ('MCDONALD', "McDonald's", 'Food & Dining', 'fastfood'),
    ('DOMINOS', "Domino's", 'Food & Dining', 'local_pizza'),
    ('KFC', 'KFC', 'Food & Dining', 'lunch_dining'),
    ('BURGERKING', 'Burger King', 'Food & Dining', 'fastfood'),
    ('EATCLUB', 'EatClub', 'Food & Dining', 'restaurant'),
    ('HALDIRAM', "Haldiram's", 'Food & Dining', 'bakery_dining'),
    ('APOLLO', 'Apollo', 'Health', 'medication'),
    ('PHARMEASY', 'PharmEasy', 'Health', 'prescriptions'),
    ('NETMEDS', 'Netmeds', 'Health', 'prescriptions'),
    ('TATA1MG', 'Tata 1mg', 'Health', 'medication'),
    ('PRACTO', 'Practo', 'Health', 'stethoscope'),
    ('CULTFIT', 'cult.fit', 'Health', 'fitness_center'),
    ('CUREFIT', 'cult.fit', 'Health', 'fitness_center'),
    ('URBANCOMPANY', 'Urban Company', 'Household & Services', 'cleaning_services'),
    ('URBANCLAP', 'Urban Company', 'Household & Services', 'cleaning_services'),
    ('JIO', 'Jio', 'Bills & Utilities', 'wifi'),
    ('AIRTEL', 'Airtel', 'Bills & Utilities', 'cell_tower'),
    ('VODAFONE', 'Vi', 'Bills & Utilities', 'cell_tower'),
    ('BSNL', 'BSNL', 'Bills & Utilities', 'cell_tower'),
    ('ACTFIBERNET', 'ACT Fibernet', 'Bills & Utilities', 'router'),
    ('TATAPOWER', 'Tata Power', 'Bills & Utilities', 'bolt'),
    ('BESCOM', 'BESCOM', 'Bills & Utilities', 'bolt'),
    ('ADANIELECTRIC', 'Adani Electricity', 'Bills & Utilities', 'bolt'),
    ('BSES', 'BSES', 'Bills & Utilities', 'bolt'),
    ('MAHANAGARGAS', 'Mahanagar Gas', 'Bills & Utilities', 'propane_tank'),
    ('INDRAPRASTHAGAS', 'IGL', 'Bills & Utilities', 'propane_tank'),
    ('BBPS', 'Bill payment', 'Bills & Utilities', 'receipt_long'),
    ('INDIANOIL', 'Indian Oil', 'Fuel', 'local_gas_station'),
    ('IOCL', 'Indian Oil', 'Fuel', 'local_gas_station'),
    ('HPCL', 'HP Petrol', 'Fuel', 'local_gas_station'),
    ('BPCL', 'Bharat Petroleum', 'Fuel', 'local_gas_station'),
    ('BHARATPETROLEUM', 'Bharat Petroleum', 'Fuel', 'local_gas_station'),
    ('SHELL', 'Shell', 'Fuel', 'local_gas_station'),
    ('NAYARA', 'Nayara', 'Fuel', 'local_gas_station'),
    ('LIC', 'LIC', 'Insurance', 'shield'),
    ('ACKO', 'Acko', 'Insurance', 'shield'),
    ('POLICYBAZAAR', 'PolicyBazaar', 'Insurance', 'shield'),
    ('HDFCERGO', 'HDFC Ergo', 'Insurance', 'shield'),
    ('ICICILOMBARD', 'ICICI Lombard', 'Insurance', 'shield'),
    ('STARHEALTH', 'Star Health', 'Insurance', 'shield'),
    ('ZERODHA', 'Zerodha', 'Investments', 'show_chart'),
    ('GROWW', 'Groww', 'Investments', 'trending_up'),
    ('KUVERA', 'Kuvera', 'Investments', 'trending_up'),
    ('COIN', 'Zerodha Coin', 'Investments', 'monetization_on'),
    ('NPSTRUST', 'NPS', 'Investments', 'account_balance'),
    ('INDIANCLEARINGCORP', 'Mutual fund SIP', 'Investments', 'currency_rupee'),
    ('BSESTARMF', 'Mutual fund SIP', 'Investments', 'currency_rupee'),
    ('CRED', 'CRED', 'Credit Card Payment', 'credit_card'),
    ('CREDITCARDPAYMENT', 'Credit card bill', 'Credit Card Payment', 'credit_card'),
    ('CREDITCARD', 'Credit card bill', 'Credit Card Payment', 'credit_card'),
    ('CCPAYMENT', 'Credit card bill', 'Credit Card Payment', 'credit_card'),
    ('CCPMT', 'Credit card bill', 'Credit Card Payment', 'credit_card'),
]

# (keyword, category_name, icon, sort_order)
DEFAULT_KEYWORDS = [
    ('CASHWDL', 'Cash Withdrawal', 'local_atm', 10),
    ('ATMWDL', 'Cash Withdrawal', 'local_atm', 20),
    ('ATM', 'Cash Withdrawal', 'local_atm', 30),
    ('RESTAURANT', 'Food & Dining', 'restaurant', 40),
    ('CAFE', 'Food & Dining', 'local_cafe', 50),
    ('BAKERY', 'Food & Dining', 'bakery_dining', 60),
    ('FOODS', 'Food & Dining', 'fastfood', 70),
    ('KITCHEN', 'Food & Dining', 'kitchen', 80),
    ('DHABA', 'Food & Dining', 'restaurant', 90),
    ('BIRYANI', 'Food & Dining', 'lunch_dining', 100),
    ('SUPERMARKET', 'Groceries', 'storefront', 110),
    ('HYPERMARKET', 'Groceries', 'storefront', 120),
    ('SUPERMART', 'Groceries', 'storefront', 130),
    ('KIRANA', 'Groceries', 'storefront', 140),
    ('MART', 'Groceries', 'storefront', 150),
    ('FRESH', 'Groceries', 'shopping_basket', 160),
    ('DAIRY', 'Groceries', 'egg', 170),
    ('VEGETABLE', 'Groceries', 'nutrition', 180),
    ('PETROL', 'Fuel', 'local_gas_station', 190),
    ('FUEL', 'Fuel', 'local_gas_station', 200),
    ('FILLING', 'Fuel', 'local_gas_station', 210),
    ('PHARMA', 'Health', 'medication', 220),
    ('MEDICAL', 'Health', 'medical_services', 230),
    ('CHEMIST', 'Health', 'medication', 240),
    ('HOSPITAL', 'Health', 'local_hospital', 250),
    ('CLINIC', 'Health', 'health_and_safety', 260),
    ('DIAGNOSTIC', 'Health', 'biotechnology', 270),
    ('DENTAL', 'Health', 'dentistry', 280),
    ('LAB', 'Health', 'science', 290),
    ('SALON', 'Personal Care', 'content_cut', 300),
    ('SPA', 'Personal Care', 'spa', 310),
    ('SCHOOL', 'Education', 'school', 320),
    ('COLLEGE', 'Education', 'school', 330),
    ('ACADEMY', 'Education', 'school', 340),
    ('TUITION', 'Education', 'menu_book', 350),
    ('ELECTRICITY', 'Bills & Utilities', 'bolt', 360),
    ('BROADBAND', 'Bills & Utilities', 'router', 370),
    ('RECHARGE', 'Bills & Utilities', 'phone_android', 380),
    ('WATER', 'Bills & Utilities', 'water_drop', 390),
    ('GAS', 'Bills & Utilities', 'propane_tank', 400),
    ('DTH', 'Bills & Utilities', 'tv', 410),
    ('INSURANCE', 'Insurance', 'shield', 420),
    ('PREMIUM', 'Insurance', 'shield', 430),
    ('EMI', 'EMI & Loans', 'account_balance', 440),
    ('LOAN', 'EMI & Loans', 'account_balance', 450),
    ('NACH', 'EMI & Loans', 'account_balance', 460),
    ('RENT', 'Rent & Housing', 'home', 470),
    ('MAINTENANCE', 'Rent & Housing', 'home_repair_service', 480),
    ('SOCIETY', 'Rent & Housing', 'apartment', 490),
    ('HOTEL', 'Travel', 'hotel', 500),
    ('AIRLINE', 'Travel', 'flight', 510),
    ('AIRWAYS', 'Travel', 'flight', 520),
    ('TRAVEL', 'Travel', 'travel_explore', 530),
    ('RAILWAY', 'Travel', 'train', 540),
    ('CAB', 'Transport', 'local_taxi', 550),
    ('TAXI', 'Transport', 'local_taxi', 560),
    ('PARKING', 'Transport', 'local_parking', 570),
    ('TOLL', 'Transport', 'toll', 580),
    ('MUTUALFUND', 'Investments', 'show_chart', 590),
    ('SIP', 'Investments', 'trending_up', 600),
    ('SECURITIES', 'Investments', 'monitoring', 610),
    ('DONATION', 'Gifts & Donations', 'volunteer_activism', 620),
    ('TEMPLE', 'Gifts & Donations', 'temple_hindu', 630),
    ('TRUST', 'Gifts & Donations', 'handshake', 640),
    ('CHARGES', 'Fees & Charges', 'request_quote', 650),
    ('FEE', 'Fees & Charges', 'request_quote', 660),
    ('GST', 'Fees & Charges', 'percent', 670),
    ('PENALTY', 'Fees & Charges', 'warning', 680),
    ('FASHION', 'Shopping', 'apparel', 690),
    ('APPAREL', 'Shopping', 'apparel', 700),
    ('ELECTRONICS', 'Shopping', 'devices', 710),
    ('STORE', 'Shopping', 'store', 720),
    ('RETAIL', 'Shopping', 'shopping_bag', 730),
    ('JEWELLER', 'Shopping', 'diamond', 740),
    ('MOVIE', 'Entertainment', 'movie', 750),
    ('CINEMA', 'Entertainment', 'theaters', 760),
    ('GAMING', 'Entertainment', 'sports_esports', 770),
]


def seed_all_defaults(apps, schema_editor):
    CategoryTemplate = apps.get_model('expenses', 'CategoryTemplate')
    BrandKnowledge = apps.get_model('expenses', 'BrandKnowledge')
    KeywordKnowledge = apps.get_model('expenses', 'KeywordKnowledge')
    ExpenseCategory = apps.get_model('expenses', 'ExpenseCategory')
    AccountGroup = apps.get_model('tracker', 'AccountGroup')

    # 1. Seed CategoryTemplate
    cat_templates = []
    existing_cats = set(CategoryTemplate.objects.values_list('name', flat=True))
    for name, kind, icon, hue, sort_order in DEFAULT_CATEGORIES:
        if name not in existing_cats:
            cat_templates.append(
                CategoryTemplate(
                    name=name,
                    kind=kind,
                    icon=icon,
                    hue=hue,
                    sort_order=sort_order,
                )
            )
    if cat_templates:
        CategoryTemplate.objects.bulk_create(cat_templates, ignore_conflicts=True)

    # 2. Seed BrandKnowledge
    brand_entries = []
    existing_brands = set(BrandKnowledge.objects.values_list('merchant_key', flat=True))
    for key, display, category, icon in DEFAULT_BRANDS:
        if key not in existing_brands:
            brand_entries.append(
                BrandKnowledge(
                    merchant_key=key,
                    display_name=display,
                    category_name=category,
                    icon=icon,
                    source='SEED',
                    confidence=1.0,
                )
            )
    if brand_entries:
        BrandKnowledge.objects.bulk_create(brand_entries, ignore_conflicts=True)

    # 3. Seed KeywordKnowledge
    keyword_entries = []
    existing_keywords = set(KeywordKnowledge.objects.values_list('keyword', flat=True))
    for kw, cat, icon, sort_order in DEFAULT_KEYWORDS:
        if kw not in existing_keywords:
            keyword_entries.append(
                KeywordKnowledge(
                    keyword=kw,
                    category_name=cat,
                    icon=icon,
                    sort_order=sort_order,
                )
            )
    if keyword_entries:
        KeywordKnowledge.objects.bulk_create(keyword_entries, ignore_conflicts=True)

    # 4. Seed ExpenseCategory for any existing AccountGroups
    all_templates = list(CategoryTemplate.objects.all())
    for group in AccountGroup.objects.all():
        existing_group_cats = set(ExpenseCategory.objects.filter(group=group).values_list('name', flat=True))
        to_create = [
            ExpenseCategory(
                group=group,
                name=t.name,
                kind=t.kind,
                icon=t.icon,
                hue=t.hue,
                sort_order=t.sort_order,
            )
            for t in all_templates
            if t.name not in existing_group_cats
        ]
        if to_create:
            ExpenseCategory.objects.bulk_create(to_create, ignore_conflicts=True)


def unseed_defaults(apps, schema_editor):
    CategoryTemplate = apps.get_model('expenses', 'CategoryTemplate')
    BrandKnowledge = apps.get_model('expenses', 'BrandKnowledge')
    KeywordKnowledge = apps.get_model('expenses', 'KeywordKnowledge')
    CategoryTemplate.objects.all().delete()
    BrandKnowledge.objects.filter(source='SEED').delete()
    KeywordKnowledge.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0005_categorytemplate_keywordknowledge'),
        ('tracker', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_all_defaults, reverse_code=unseed_defaults),
    ]
