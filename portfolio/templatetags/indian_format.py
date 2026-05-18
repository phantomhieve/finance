"""
Custom template filter for Indian number formatting.
Indian system: last 3 digits, then groups of 2.
  12079850  → 1,20,79,850
  1365800   → 13,65,800
  270558    → 2,70,558
"""
from django import template

register = template.Library()


def _format_indian(number_str):
    """Apply Indian grouping to an integer string (no sign, no decimals)."""
    if len(number_str) <= 3:
        return number_str
    last3 = number_str[-3:]
    rest = number_str[:-3]
    groups = []
    while rest:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    return ','.join(groups) + ',' + last3


@register.filter(name='indian_number')
def indian_number(value):
    """
    Format a number with Indian comma grouping.
    Works with int, float, Decimal, and pre-formatted strings.
    """
    if value is None or value == '':
        return '0'

    text = str(value).replace(',', '').strip()

    negative = text.startswith('-')
    if negative:
        text = text[1:]

    if '.' in text:
        integer_part, decimal_part = text.split('.', 1)
    else:
        integer_part = text
        decimal_part = None

    integer_part = integer_part.lstrip('0') or '0'
    formatted = _format_indian(integer_part)

    if decimal_part is not None:
        formatted += '.' + decimal_part

    if negative:
        formatted = '-' + formatted

    return formatted
