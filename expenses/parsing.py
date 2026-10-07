"""Parse Indian bank / card alert emails into structured transactions and statement summaries.

Deterministic regex first (fast, free, private); callers may fall back to the AI extractor in
``expenses.ai`` when an email looks transactional but these patterns can't read it.
"""
import datetime
import html
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_TAG_BREAKS = re.compile(r'<\s*(br|/p|/div|/tr|/li|/h\d)\b[^>]*>', re.I)
_TAG_CELLS = re.compile(r'<\s*/t[dh]\s*>', re.I)
_TAG_DROP = re.compile(r'<(script|style|head)\b.*?</\1\s*>', re.I | re.S)
_TAG_ANY = re.compile(r'<[^>]+>')


def html_to_text(markup):
    text = _TAG_DROP.sub(' ', markup or '')
    text = _TAG_BREAKS.sub('\n', text)
    text = _TAG_CELLS.sub(' ', text)
    text = _TAG_ANY.sub(' ', text)
    text = html.unescape(text).replace('\xa0', ' ')
    return clean_text(text)


def clean_text(text):
    lines = [re.sub(r'[ \t\r\f\v]+', ' ', ln).strip() for ln in (text or '').splitlines()]
    return '\n'.join(ln for ln in lines if ln)


def mask_sensitive(text):
    """Mask long digit runs (account / card / reference numbers) before sending text to an LLM."""
    return re.sub(r'\d{6,}', lambda m: 'X' * (len(m.group()) - 4) + m.group()[-4:], text or '')


def to_decimal(raw):
    try:
        return Decimal(str(raw).replace(',', '').strip())
    except (InvalidOperation, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Institutions
# ---------------------------------------------------------------------------

# (substring of sender address or body, display name). Order matters: more specific first.
_INSTITUTIONS = [
    ('sbicard', 'SBI Card'),
    ('onlinesbi', 'SBI'),
    ('sbi.co.in', 'SBI'),
    ('hdfcbank', 'HDFC Bank'),
    ('hdfc bank', 'HDFC Bank'),
    ('icicibank', 'ICICI Bank'),
    ('icici bank', 'ICICI Bank'),
    ('axisbank', 'Axis Bank'),
    ('axis.bank', 'Axis Bank'),
    ('axis bank', 'Axis Bank'),
    ('kotak', 'Kotak Bank'),
    ('americanexpress', 'American Express'),
    ('american express', 'American Express'),
    ('aexp', 'American Express'),
    ('amex', 'American Express'),
    ('yesbank', 'Yes Bank'),
    ('yes bank', 'Yes Bank'),
    ('indusind', 'IndusInd Bank'),
    ('idfcfirst', 'IDFC First Bank'),
    ('idfc first', 'IDFC First Bank'),
    ('aubank', 'AU Bank'),
    ('federalbank', 'Federal Bank'),
    ('rblbank', 'RBL Bank'),
    ('hsbc', 'HSBC'),
    ('sc.com', 'Standard Chartered'),
    ('standard chartered', 'Standard Chartered'),
    ('bobcard', 'BOB Card'),
    ('bankofbaroda', 'Bank of Baroda'),
    ('pnb', 'PNB'),
    ('canarabank', 'Canara Bank'),
    ('unionbank', 'Union Bank'),
    ('onecard', 'OneCard'),
    ('slice', 'Slice'),
    ('paytm', 'Paytm'),
    ('amazonpay', 'Amazon Pay'),
    ('jupiter', 'Jupiter'),
    ('fi.money', 'Fi'),
]


def detect_institution(sender, body):
    sender_l = (sender or '').lower()
    for needle, name in _INSTITUTIONS:
        if needle in sender_l:
            return name
    body_l = (body or '').lower()[:600]
    for needle, name in _INSTITUTIONS:
        if ' ' in needle and needle in body_l:
            return name
    return ''


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

_AMOUNT = r'(?:INR|Rs\.?|₹)\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)'
_AMOUNT_RE = re.compile(_AMOUNT, re.I)
_FOREIGN_AMOUNT_RE = re.compile(r'\b(USD|EUR|GBP|AED|SGD|AUD|CAD|JPY|CHF|THB)\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)', re.I)

_DEBIT_WORDS = re.compile(
    r'\b(debited|spent|used\s+for|been\s+used|for\s+using|withdrawn|deducted|charged|paid|sent|purchase'
    r'|transaction\s+of|txn\s+of)\b', re.I)
_CREDIT_WORDS = re.compile(r'\b(credited|received|refund(?:ed)?|reversal|reversed|deposited|cashback\s+of)\b', re.I)

_NOISE = re.compile(
    r'\b(otp|one[\s-]?time\s+password|verification\s+code|do\s+not\s+share\s+(?:this|the)\s+(?:otp|code)'
    r'|pre-?approved|limited\s+period|apply\s+now|avail\s+now|exclusive\s+offer|win\s+(?:up\s+to|a)'
    r'|will\s+be\s+debited|is\s+due\s+on|due\s+for\s+renewal|has\s+been\s+declined|was\s+declined'
    r'|transaction\s+(?:has\s+)?failed|could\s+not\s+be\s+processed|insufficient\s+(?:funds|balance)'
    r'|mandate\s+(?:has\s+been\s+)?(?:registered|created)|standing\s+instruction\s+registered)\b',
    re.I,
)

_STATEMENT_SUBJECT = re.compile(r'\b(e-?statement|statement)\b', re.I)
_STATEMENT_BODY = re.compile(r'(total\s+(?:amount\s+)?due|minimum\s+(?:amount\s+)?due|payment\s+due\s+date)', re.I)
_CARD_PAYMENT = re.compile(
    r'(payment\s+(?:of\s+)?' + _AMOUNT + r'.{0,80}?(?:received|credited|successful|has\s+been\s+received)'
    r'.{0,80}?credit\s+card'
    r'|(?:received|credited).{0,40}?payment.{0,80}?credit\s+card'
    r'|credit\s+card.{0,80}?payment\s+(?:of\s+)?' + _AMOUNT + r'.{0,40}?(?:received|credited|successful))',
    re.I | re.S,
)


def classify(sender, subject, body):
    """Return one of TXN, STATEMENT, CARD_PAYMENT, IGNORED for an email."""
    text = f'{subject}\n{body}'
    if _STATEMENT_SUBJECT.search(subject or '') and _STATEMENT_BODY.search(body or ''):
        return 'STATEMENT'
    if _CARD_PAYMENT.search(text):
        return 'CARD_PAYMENT'
    if not _AMOUNT_RE.search(text) and not _FOREIGN_AMOUNT_RE.search(text):
        return 'IGNORED'
    if _NOISE.search(text):
        return 'IGNORED'
    if _DEBIT_WORDS.search(text) or _CREDIT_WORDS.search(text):
        return 'TXN'
    return 'IGNORED'


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], start=1)}

_DATE_PATTERNS = [
    # 2025-10-05
    (re.compile(r'\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b'), 'ymd'),
    # 05-10-2025, 05/10/25, 05.10.25
    (re.compile(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b'), 'dmy'),
    # 05-Oct-25, 05 Oct 2025, 05Oct25, 5-OCT-2025
    (re.compile(r'\b(\d{1,2})[-\s]?([A-Za-z]{3})[a-z]*[-\s,]*(\d{2,4})\b'), 'dMy'),
    # Oct 05, 2025
    (re.compile(r'\b([A-Za-z]{3})[a-z]*\s+(\d{1,2}),?\s+(\d{4})\b'), 'Mdy'),
]


def _year(y):
    y = int(y)
    return y + 2000 if y < 100 else y


def parse_date(text, reference=None):
    """First plausible date in text. With a reference date, reject dates more than 60 days away."""
    for rx, kind in _DATE_PATTERNS:
        for m in rx.finditer(text or ''):
            try:
                if kind == 'ymd':
                    d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif kind == 'dmy':
                    d = datetime.date(_year(m.group(3)), int(m.group(2)), int(m.group(1)))
                elif kind == 'dMy':
                    mon = _MONTHS.get(m.group(2).lower()[:3])
                    if not mon:
                        continue
                    d = datetime.date(_year(m.group(3)), mon, int(m.group(1)))
                else:
                    mon = _MONTHS.get(m.group(1).lower()[:3])
                    if not mon:
                        continue
                    d = datetime.date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                continue
            if reference and abs((d - reference).days) > 60:
                continue
            return d
    return None


_TIME_RE = re.compile(r'\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\s*([AaPp][Mm])?\b')


def parse_time(text):
    m = _TIME_RE.search(text or '')
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    meridiem = (m.group(4) or '').lower()
    if meridiem == 'pm' and hour < 12:
        hour += 12
    elif meridiem == 'am' and hour == 12:
        hour = 0
    return datetime.time(hour, minute, int(m.group(3) or 0))


_LAST4_PATTERNS = [
    re.compile(r'ending\s*(?:with|in)?\s*(?:[xX*•.]+\s?)?(\d{4})(?!\d)', re.I),
    re.compile(r'(?:[xX*•]{2,}|\.{3,})\s?(\d{4})(?!\d)'),
    re.compile(r'\b(?:a/c|ac|acct|account|card)\s*(?:no\.?|number)?\s*[:\-]?\s*[xX*•]*\s?(\d{4})(?!\d)', re.I),
]


def parse_last4(text):
    for rx in _LAST4_PATTERNS:
        m = rx.search(text or '')
        if m:
            return m.group(1)
    return ''


def parse_instrument(text):
    t = (text or '').lower()
    if 'credit card' in t or re.search(r'av(?:ai)?l(?:able|\.)?\s*(?:credit\s*)?l(?:imi)?t|avl\s*lmt', t):
        return 'CREDIT_CARD'
    if 'debit card' in t:
        return 'DEBIT_CARD'
    if re.search(r'(\ba/c\b|\bac\b|\bacct\b|\baccount\b|\bsavings\b)', t):
        return 'BANK_ACCOUNT'
    if re.search(r'\bcard\b', t):
        return 'CREDIT_CARD'
    if re.search(r'\b(upi|vpa|wallet)\b', t):
        return 'UPI'
    return 'OTHER'


def parse_channel(text, instrument):
    t = (text or '').lower()
    if re.search(r'\b(upi|vpa)\b|@[a-z]{2,}\b', t):
        return 'UPI'
    if re.search(r'\b(atm|cash\s+wdl|cash\s+withdrawal|nfs\*cash)\b', t):
        return 'ATM'
    if re.search(r'\b(imps|neft|rtgs)\b', t):
        return 'IMPS'
    if re.search(r'\b(nach|ecs|auto[\s-]?debit|si\s+debit|standing\s+instruction|mandate)\b', t):
        return 'AUTO_DEBIT'
    if re.search(r'net\s*banking|netbanking|billdesk|payu', t):
        return 'NETBANKING'
    if instrument in ('CREDIT_CARD', 'DEBIT_CARD'):
        return 'CARD'
    return 'OTHER'


_REF_RE = re.compile(
    r'(?:upi\s*ref(?:erence)?|ref(?:erence)?|rrn|txn\s*id|transaction\s*id|utr)\.?\s*(?:no\.?|number|#|id)?'
    r'\s*(?:is)?\s*[:\-]?\s*([A-Za-z0-9]{6,24})',
    re.I,
)


def parse_reference(text):
    m = _REF_RE.search(text or '')
    return m.group(1) if m else ''


_STOP = r'(?=\s+on\s+\d|\s+on\s+[A-Za-z]{3}\s+\d|\s+on\s+your\b|\s+using\b|\s*\.\s|\s*\.$|\s+avl|\s+avbl|\s+available|\s+ref\b|\s+upi\b|\s+via\b|\s+for\s+inr|\s*\(|\s*,\s*(?:avl|ref)|\s+total\s+avbl|\n|$)'
_MERCHANT_PATTERNS = [
    # HDFC UPI: "to VPA abc@okicici MERCHANT NAME on 05-10-25" / credits "by VPA x@okhdfc NAME on"
    re.compile(r'\b(?:to|by|from)\s+vpa\s+(\S+@\S+?)\s+(.{2,60}?)' + _STOP, re.I),
    re.compile(r'\b(?:to|by|from)\s+vpa\s+(\S+@[a-z]{2,})', re.I),
    # "to abc@ybl on" / "to paytm.s1h22ek@pty SUBXTR RUZZ on"
    re.compile(r'\bto\s+([a-z0-9._\-]+@[a-z]{2,})\s+([A-Z][A-Za-z0-9 &.\'\-]{1,60}?)' + _STOP, re.I),
    re.compile(r'\bto\s+([a-z0-9._\-]+@[a-z]{2,})\b', re.I),
    # Axis summary: "Merchant Name: AMAZON"
    re.compile(r'merchant\s*(?:name)?\s*[:\-]\s*(.{2,60}?)' + _STOP, re.I),
    # ICICI: "on 05-Oct-25 on AMAZON. Avl Limit"; "on 05-Oct-25 at AMAZON"
    re.compile(r'\bon\s+\d{1,2}[-/\s][A-Za-z0-9]{2,3}[-/\s]\d{2,4}(?:[\s,:]+\d{1,2}:\d{2}(?::\d{2})?)?\s+(?:on|at)\s+(.{2,60}?)' + _STOP, re.I),
    # HDFC / SBI card: "at AMAZON on 05-10-25"
    re.compile(r'\bat\s+(.{2,60}?)' + _STOP, re.I),
    # HDFC: "towards MERCHANT"
    re.compile(r'\btowards\s+(.{2,60}?)' + _STOP, re.I),
    # ICICI / Axis: "Info: UPI-12345-MERCHANT" / "Info: AMAZON"
    re.compile(r'\binfo\s*[:\-]\s*(.{2,80}?)' + _STOP, re.I),
    # Axis: "UPI/P2M/123456/MERCHANT"
    re.compile(r'\b(?:UPI|IMPS|NEFT)/(?:P2[AM]/)?\d+/([^/\s]{2,40})', re.I),
    # SBI: "transfer to MERCHANT Ref No"
    re.compile(r'\btransfer(?:red)?\s+to\s+(.{2,60}?)' + _STOP, re.I),
    # Kotak: "Sent Rs.500 from Kotak Bank AC X1234 to MERCHANT on"
    re.compile(r'\bto\s+([A-Z][A-Za-z0-9 &.\'\-]{2,60}?)' + _STOP),
    # Credits: "received from NAME", "credited by NAME"
    re.compile(r'\b(?:from|by)\s+([A-Za-z][A-Za-z0-9 &.\'\-]{2,60}?)' + _STOP, re.I),
]

_BAD_MERCHANT = re.compile(
    r'^(your\b|the\b|a/c|ac\b|account|card\b|credit\b|debit\b|bank\b|hdfc|icici|sbi\b|axis|kotak|customer'
    r'|xx|on\s|rs\b|inr\b|\d)',
    re.I,
)


def parse_merchant(text):
    for rx in _MERCHANT_PATTERNS:
        for m in rx.finditer(text or ''):
            groups = [g for g in m.groups() if g]
            if not groups:
                continue
            # VPA + name: prefer the human name, keep VPA as raw context
            candidate = groups[-1].strip(' .,:-')
            if len(groups) == 2 and len(candidate) < 3:
                candidate = groups[0]
            if len(candidate) < 2 or _BAD_MERCHANT.match(candidate):
                continue
            return candidate[:120], ' '.join(groups)[:255]
    return '', ''


# ---------------------------------------------------------------------------
# Merchant normalisation
# ---------------------------------------------------------------------------

# token in the alnum key → (display name, default category name)
KNOWN_BRANDS = {
    'SWIGGYINSTAMART': ('Swiggy Instamart', 'Groceries'),
    'INSTAMART': ('Swiggy Instamart', 'Groceries'),
    'SWIGGY': ('Swiggy', 'Food & Dining'),
    'ZOMATO': ('Zomato', 'Food & Dining'),
    'BLINKIT': ('Blinkit', 'Groceries'),
    'GROFERS': ('Blinkit', 'Groceries'),
    'ZEPTO': ('Zepto', 'Groceries'),
    'BIGBASKET': ('BigBasket', 'Groceries'),
    'BBNOW': ('BigBasket', 'Groceries'),
    'DMART': ('DMart', 'Groceries'),
    'AVENUESUPERMART': ('DMart', 'Groceries'),
    'JIOMART': ('JioMart', 'Groceries'),
    'AMAZONPRIME': ('Amazon Prime', 'Subscriptions'),
    'AMAZONPAY': ('Amazon', 'Shopping'),
    'AMAZON': ('Amazon', 'Shopping'),
    'FLIPKART': ('Flipkart', 'Shopping'),
    'MYNTRA': ('Myntra', 'Shopping'),
    'AJIO': ('Ajio', 'Shopping'),
    'NYKAA': ('Nykaa', 'Personal Care'),
    'MEESHO': ('Meesho', 'Shopping'),
    'TATACLIQ': ('Tata CLiQ', 'Shopping'),
    'CROMA': ('Croma', 'Shopping'),
    'RELIANCEDIGITAL': ('Reliance Digital', 'Shopping'),
    'IKEA': ('IKEA', 'Household & Services'),
    'UBER': ('Uber', 'Transport'),
    'OLACABS': ('Ola', 'Transport'),
    'ANITECHNOLOGIES': ('Ola', 'Transport'),
    'RAPIDO': ('Rapido', 'Transport'),
    'NAMMAYATRI': ('Namma Yatri', 'Transport'),
    'METRO': ('Metro', 'Transport'),
    'FASTAG': ('FASTag', 'Transport'),
    'IRCTC': ('IRCTC', 'Travel'),
    'MAKEMYTRIP': ('MakeMyTrip', 'Travel'),
    'GOIBIBO': ('Goibibo', 'Travel'),
    'CLEARTRIP': ('Cleartrip', 'Travel'),
    'INDIGO': ('IndiGo', 'Travel'),
    'INTERGLOBE': ('IndiGo', 'Travel'),
    'AIRINDIA': ('Air India', 'Travel'),
    'AKASA': ('Akasa Air', 'Travel'),
    'AIRBNB': ('Airbnb', 'Travel'),
    'OYO': ('OYO', 'Travel'),
    'REDBUS': ('redBus', 'Travel'),
    'NETFLIX': ('Netflix', 'Subscriptions'),
    'SPOTIFY': ('Spotify', 'Subscriptions'),
    'HOTSTAR': ('Disney+ Hotstar', 'Subscriptions'),
    'JIOHOTSTAR': ('JioHotstar', 'Subscriptions'),
    'YOUTUBE': ('YouTube Premium', 'Subscriptions'),
    'GOOGLEPLAY': ('Google Play', 'Subscriptions'),
    'APPLECOM': ('Apple', 'Subscriptions'),
    'ITUNES': ('Apple', 'Subscriptions'),
    'OPENAI': ('OpenAI', 'Subscriptions'),
    'CHATGPT': ('OpenAI', 'Subscriptions'),
    'BOOKMYSHOW': ('BookMyShow', 'Entertainment'),
    'PVR': ('PVR INOX', 'Entertainment'),
    'INOX': ('PVR INOX', 'Entertainment'),
    'DISTRICT': ('District', 'Entertainment'),
    'STARBUCKS': ('Starbucks', 'Food & Dining'),
    'MCDONALD': ("McDonald's", 'Food & Dining'),
    'DOMINOS': ("Domino's", 'Food & Dining'),
    'KFC': ('KFC', 'Food & Dining'),
    'BURGERKING': ('Burger King', 'Food & Dining'),
    'EATCLUB': ('EatClub', 'Food & Dining'),
    'HALDIRAM': ("Haldiram's", 'Food & Dining'),
    'APOLLO': ('Apollo', 'Health'),
    'PHARMEASY': ('PharmEasy', 'Health'),
    'NETMEDS': ('Netmeds', 'Health'),
    'TATA1MG': ('Tata 1mg', 'Health'),
    'PRACTO': ('Practo', 'Health'),
    'CULTFIT': ('cult.fit', 'Health'),
    'CUREFIT': ('cult.fit', 'Health'),
    'URBANCOMPANY': ('Urban Company', 'Household & Services'),
    'URBANCLAP': ('Urban Company', 'Household & Services'),
    'JIO': ('Jio', 'Bills & Utilities'),
    'AIRTEL': ('Airtel', 'Bills & Utilities'),
    'VODAFONE': ('Vi', 'Bills & Utilities'),
    'BSNL': ('BSNL', 'Bills & Utilities'),
    'ACTFIBERNET': ('ACT Fibernet', 'Bills & Utilities'),
    'TATAPOWER': ('Tata Power', 'Bills & Utilities'),
    'BESCOM': ('BESCOM', 'Bills & Utilities'),
    'ADANIELECTRIC': ('Adani Electricity', 'Bills & Utilities'),
    'BSES': ('BSES', 'Bills & Utilities'),
    'MAHANAGARGAS': ('Mahanagar Gas', 'Bills & Utilities'),
    'INDRAPRASTHAGAS': ('IGL', 'Bills & Utilities'),
    'BBPS': ('Bill payment', 'Bills & Utilities'),
    'INDIANOIL': ('Indian Oil', 'Fuel'),
    'IOCL': ('Indian Oil', 'Fuel'),
    'HPCL': ('HP Petrol', 'Fuel'),
    'BPCL': ('Bharat Petroleum', 'Fuel'),
    'BHARATPETROLEUM': ('Bharat Petroleum', 'Fuel'),
    'SHELL': ('Shell', 'Fuel'),
    'NAYARA': ('Nayara', 'Fuel'),
    'LIC': ('LIC', 'Insurance'),
    'ACKO': ('Acko', 'Insurance'),
    'POLICYBAZAAR': ('PolicyBazaar', 'Insurance'),
    'HDFCERGO': ('HDFC Ergo', 'Insurance'),
    'ICICILOMBARD': ('ICICI Lombard', 'Insurance'),
    'STARHEALTH': ('Star Health', 'Insurance'),
    'ZERODHA': ('Zerodha', 'Investments'),
    'GROWW': ('Groww', 'Investments'),
    'KUVERA': ('Kuvera', 'Investments'),
    'COIN': ('Zerodha Coin', 'Investments'),
    'NPSTRUST': ('NPS', 'Investments'),
    'INDIANCLEARINGCORP': ('Mutual fund SIP', 'Investments'),
    'BSESTARMF': ('Mutual fund SIP', 'Investments'),
    'CRED': ('CRED', 'Credit Card Payment'),
    'CREDITCARDPAYMENT': ('Credit card bill', 'Credit Card Payment'),
    'CREDITCARD': ('Credit card bill', 'Credit Card Payment'),
    'CCPAYMENT': ('Credit card bill', 'Credit Card Payment'),
    'CCPMT': ('Credit card bill', 'Credit Card Payment'),
}

# Keyword fallbacks for unknown merchants: substring in the alnum key → category name.
CATEGORY_KEYWORDS = [
    ('CASHWDL', 'Cash Withdrawal'), ('ATMWDL', 'Cash Withdrawal'), ('ATM', 'Cash Withdrawal'),
    ('RESTAURANT', 'Food & Dining'), ('CAFE', 'Food & Dining'), ('BAKERY', 'Food & Dining'),
    ('FOODS', 'Food & Dining'), ('KITCHEN', 'Food & Dining'), ('DHABA', 'Food & Dining'), ('BIRYANI', 'Food & Dining'),
    ('SUPERMARKET', 'Groceries'), ('HYPERMARKET', 'Groceries'), ('SUPERMART', 'Groceries'), ('KIRANA', 'Groceries'), ('MART', 'Groceries'), ('FRESH', 'Groceries'),
    ('DAIRY', 'Groceries'), ('VEGETABLE', 'Groceries'),
    ('PETROL', 'Fuel'), ('FUEL', 'Fuel'), ('FILLING', 'Fuel'),
    ('PHARMA', 'Health'), ('MEDICAL', 'Health'), ('CHEMIST', 'Health'), ('HOSPITAL', 'Health'),
    ('CLINIC', 'Health'), ('DIAGNOSTIC', 'Health'), ('DENTAL', 'Health'), ('LAB', 'Health'),
    ('SALON', 'Personal Care'), ('SPA', 'Personal Care'),
    ('SCHOOL', 'Education'), ('COLLEGE', 'Education'), ('ACADEMY', 'Education'), ('TUITION', 'Education'),
    ('ELECTRICITY', 'Bills & Utilities'), ('BROADBAND', 'Bills & Utilities'), ('RECHARGE', 'Bills & Utilities'),
    ('WATER', 'Bills & Utilities'), ('GAS', 'Bills & Utilities'), ('DTH', 'Bills & Utilities'),
    ('INSURANCE', 'Insurance'), ('PREMIUM', 'Insurance'),
    ('EMI', 'EMI & Loans'), ('LOAN', 'EMI & Loans'), ('NACH', 'EMI & Loans'),
    ('RENT', 'Rent & Housing'), ('MAINTENANCE', 'Rent & Housing'), ('SOCIETY', 'Rent & Housing'),
    ('HOTEL', 'Travel'), ('AIRLINE', 'Travel'), ('AIRWAYS', 'Travel'), ('TRAVEL', 'Travel'), ('RAILWAY', 'Travel'),
    ('CAB', 'Transport'), ('TAXI', 'Transport'), ('PARKING', 'Transport'), ('TOLL', 'Transport'),
    ('MUTUALFUND', 'Investments'), ('SIP', 'Investments'), ('SECURITIES', 'Investments'),
    ('DONATION', 'Gifts & Donations'), ('TEMPLE', 'Gifts & Donations'), ('TRUST', 'Gifts & Donations'),
    ('CHARGES', 'Fees & Charges'), ('FEE', 'Fees & Charges'), ('GST', 'Fees & Charges'), ('PENALTY', 'Fees & Charges'),
    ('FASHION', 'Shopping'), ('APPAREL', 'Shopping'), ('ELECTRONICS', 'Shopping'), ('STORE', 'Shopping'),
    ('RETAIL', 'Shopping'), ('JEWELLER', 'Shopping'),
    ('MOVIE', 'Entertainment'), ('CINEMA', 'Entertainment'), ('GAMING', 'Entertainment'),
]

_VPA_NOISE = re.compile(r'^(paytmqr|paytm|bharatpe|q\d+|gpay|phonepe|mab|ombk|upi|pay|bhim)[._\-]*', re.I)
_MERCHANT_NOISE = re.compile(
    r'\b(upi|pos|ecom|imps|neft|rtgs|p2m|p2a|pvt|private|ltd|limited|llp|india|in|inc|co|corp|the|www|com|payments?)\b',
    re.I,
)


def normalize_merchant(raw):
    """Return (display_name, merchant_key). The key is stable across alert formats for learning."""
    s = (raw or '').strip()
    if not s:
        return '', ''
    if '@' in s and ' ' not in s.strip():
        s = _VPA_NOISE.sub('', s.split('@')[0])
        s = re.sub(r'[._\-]+', ' ', s)
    s = re.sub(r'\b\d{3,}\b', ' ', s)
    s = re.sub(r'[*#/|_]+', ' ', s)
    cleaned = re.sub(r'\s+', ' ', _MERCHANT_NOISE.sub(' ', s)).strip(' .,-')
    cleaned = re.sub(r'^(?:from|to|by|at)\s+', '', cleaned, flags=re.I)
    key = re.sub(r'[^A-Z0-9]', '', (cleaned or s).upper())[:60]
    words = _words(cleaned or s)
    for token in _BRAND_TOKENS:
        if _token_hit(token, key, words):
            return KNOWN_BRANDS[token][0], token
    display = (cleaned or s).strip()
    if display.isupper() or display.islower():
        display = display.title()
    return display[:120], key


# Longest first so e.g. CREDITCARDPAYMENT wins over CRED.
_BRAND_TOKENS = sorted(KNOWN_BRANDS, key=len, reverse=True)
# Tokens this short must be a whole word, or LIC would match SLICE and FEE would match COFFEE.
_SHORT_TOKEN = 4


def _words(text):
    return set(re.findall(r'[A-Z0-9]+', (text or '').upper()))


def _token_hit(token, key, words):
    if len(token) <= _SHORT_TOKEN:
        return token in words or key == token
    return token in key


def brand_category(merchant_key, text=''):
    brand = KNOWN_BRANDS.get(merchant_key)
    if brand:
        return brand[1]
    words = _words(text)
    for token, category in CATEGORY_KEYWORDS:
        if _token_hit(token, merchant_key, words):
            return category
    return None


# ---------------------------------------------------------------------------
# Public parse results
# ---------------------------------------------------------------------------

@dataclass
class ParsedTransaction:
    amount: Decimal
    direction: str
    txn_date: datetime.date
    txn_time: datetime.time | None = None
    merchant: str = ''
    merchant_raw: str = ''
    merchant_key: str = ''
    currency: str = 'INR'
    instrument: str = 'OTHER'
    channel: str = 'OTHER'
    last4: str = ''
    institution: str = ''
    reference: str = ''


@dataclass
class ParsedStatement:
    institution: str = ''
    last4: str = ''
    statement_date: datetime.date | None = None
    due_date: datetime.date | None = None
    total_due: Decimal | None = None
    min_due: Decimal | None = None
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    lines: list = field(default_factory=list)


@dataclass
class ParsedLine:
    txn_date: datetime.date
    description: str
    amount: Decimal
    is_credit: bool = False


def _direction(text):
    debit, credit = _DEBIT_WORDS.search(text), _CREDIT_WORDS.search(text)
    if debit and credit:
        return 'DEBIT' if debit.start() < credit.start() else 'CREDIT'
    return 'CREDIT' if credit and not debit else 'DEBIT'


def parse_transaction(sender, subject, body, received=None):
    """Parse a single transaction alert. Returns ParsedTransaction or None."""
    text = clean_text(f'{body}')
    full = f'{subject}\n{text}'
    received_date = received.date() if isinstance(received, datetime.datetime) else received

    currency = 'INR'
    m = _AMOUNT_RE.search(full)
    fm = _FOREIGN_AMOUNT_RE.search(full)
    if fm and (not m or fm.start() < m.start()):
        currency, amount = fm.group(1).upper(), to_decimal(fm.group(2))
    else:
        amount = to_decimal(m.group(1)) if m else None
    if not amount or amount <= 0:
        return None

    merchant_text, merchant_raw = parse_merchant(text)
    if not merchant_text:
        merchant_text, merchant_raw = parse_merchant(subject or '')
    display, key = normalize_merchant(merchant_text)
    instrument = parse_instrument(full)

    return ParsedTransaction(
        amount=amount,
        direction=_direction(full),
        txn_date=parse_date(text, received_date) or received_date or datetime.date.today(),
        txn_time=parse_time(text),
        merchant=display,
        merchant_raw=merchant_raw,
        merchant_key=key,
        currency=currency,
        instrument=instrument,
        channel=parse_channel(full, instrument),
        last4=parse_last4(full),
        institution=detect_institution(sender, full),
        reference=parse_reference(text),
    )


def _labelled_amount(text, label):
    m = re.search(label + r'[^0-9₹\n]{0,40}?(?:' + _AMOUNT + r'|([0-9][0-9,]*\.[0-9]{2}))', text, re.I)
    if not m:
        return None
    return to_decimal(m.group(1) or m.group(2))


def _labelled_date(text, label):
    m = re.search(label + r'[^0-9A-Za-z\n]{0,15}(.{6,25})', text, re.I)
    return parse_date(m.group(1)) if m else None


def parse_statement_summary(sender, subject, text):
    """Totals, due date and period from a statement email body or PDF text."""
    full = f'{subject}\n{text}'
    st = ParsedStatement(
        institution=detect_institution(sender, full),
        last4=parse_last4(full),
        total_due=_labelled_amount(full, r'total\s+(?:amount\s+)?due'),
        min_due=_labelled_amount(full, r'min(?:imum)?\.?\s+(?:amount\s+)?due'),
        due_date=_labelled_date(full, r'(?:payment\s+)?due\s+(?:date|by|on)'),
        statement_date=_labelled_date(full, r'statement\s+(?:date|generated\s+on)'),
    )
    period = re.search(
        r'(?:statement\s+period|billing\s+(?:period|cycle))[^0-9A-Za-z]{0,10}(.{6,20}?)\s*(?:to|-|–)\s*(.{6,20})',
        full, re.I,
    )
    if period:
        st.period_start, st.period_end = parse_date(period.group(1)), parse_date(period.group(2))
    if not st.statement_date and st.period_end:
        st.statement_date = st.period_end
    return st


_LINE_RE = re.compile(
    r'^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s?[A-Za-z]{3}\s?\d{2,4})'
    r'(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?'
    r'\s+(.+?)\s+'
    r'(?:[A-Z]{3}\s+[0-9,]+\.\d{2}\s+)?'
    r'(?:₹\s?|Rs\.?\s?|INR\s?)?([0-9][0-9,]*\.\d{2})\s*(Cr|CR|C|Dr|DR|D)?\s*$'
)
_SKIP_LINE = re.compile(
    r'(opening\s+balance|closing\s+balance|total\s+(?:amount\s+)?due|minimum\s+(?:amount\s+)?due|'
    r'credit\s+limit|available\s+limit|previous\s+balance|reward\s+points)', re.I)


def parse_statement_lines(text):
    """Line items from statement PDF text. Payment-received lines are marked credit."""
    lines = []
    for raw in (text or '').splitlines():
        if _SKIP_LINE.search(raw):
            continue
        m = _LINE_RE.match(raw)
        if not m:
            continue
        d = parse_date(m.group(1))
        amount = to_decimal(m.group(3))
        if not d or not amount:
            continue
        desc = re.sub(r'\s+', ' ', m.group(2)).strip()
        is_credit = (m.group(4) or '').upper().startswith('C') or bool(
            re.search(r'payment\s+received|thank\s+you\s+for\s+(?:the\s+)?payment|refund|reversal', desc, re.I))
        lines.append(ParsedLine(txn_date=d, description=desc[:255], amount=amount, is_credit=is_credit))
    return lines


def parse_card_payment(sender, subject, body):
    """(amount, last4, institution) for a 'payment received on your credit card' email."""
    full = f'{subject}\n{clean_text(body)}'
    m = _AMOUNT_RE.search(full)
    return (to_decimal(m.group(1)) if m else None), parse_last4(full), detect_institution(sender, full)
