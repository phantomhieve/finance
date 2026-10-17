"""Seed realistic local development expense data for UI testing and dashboard demonstration."""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from expenses.models import Expense, ExpenseCategory, PaymentSource
from expenses.parsing import normalize_merchant
from tracker.models import AccountGroup, User


class Command(BaseCommand):
    help = "Seed realistic local development expense transactions for Household"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true", help="Clear existing expenses before seeding"
        )

    def handle(self, *args, **options):
        group = AccountGroup.objects.filter(name="Household").first()
        if not group:
            group = AccountGroup.objects.first()
        if not group:
            self.stderr.write(self.style.ERROR("No AccountGroup found! Run migrations/create group first."))
            return

        user_primary = group.members.filter(user_type="PRIMARY").first() or User.objects.first()
        user_spouse = group.members.filter(user_type="ACCOUNT_HOLDER").first() or user_primary

        if options["clear"]:
            count, _ = Expense.objects.filter(group=group).delete()
            self.stdout.write(f"Cleared {count} existing expenses for {group.name}.")

        # 1. Ensure Payment Sources
        ps_hdfc_cc, _ = PaymentSource.objects.get_or_create(
            group=group, kind="CREDIT_CARD", institution="HDFC", last4="1001",
            defaults={"nickname": "Millennia", "owner": user_primary, "is_auto": False},
        )
        ps_icici_cc, _ = PaymentSource.objects.get_or_create(
            group=group, kind="CREDIT_CARD", institution="ICICI", last4="2002",
            defaults={"nickname": "Amazon Pay", "owner": user_primary, "is_auto": False},
        )
        ps_hdfc_dc, _ = PaymentSource.objects.get_or_create(
            group=group, kind="DEBIT_CARD", institution="HDFC", last4="3003",
            defaults={"nickname": "Salary A/C", "owner": user_primary, "is_auto": False},
        )
        ps_axis_dc, _ = PaymentSource.objects.get_or_create(
            group=group, kind="DEBIT_CARD", institution="AXIS", last4="4004",
            defaults={"nickname": "Spouse Card", "owner": user_spouse, "is_auto": False},
        )

        # 2. Category lookup map
        cats = {c.name.lower(): c for c in ExpenseCategory.objects.filter(group=group)}

        def get_cat(name):
            for k, c in cats.items():
                if name.lower() in k or k in name.lower():
                    return c
            return None

        cat_food = get_cat("Food") or get_cat("Dining")
        cat_groceries = get_cat("Groceries")
        cat_travel = get_cat("Travel") or get_cat("Commute")
        cat_bills = get_cat("Bills") or get_cat("Utilities")
        cat_shopping = get_cat("Shopping")
        cat_health = get_cat("Health") or get_cat("Medical")
        cat_transfers = get_cat("Transfer") or get_cat("Credit Card Payment")

        today = timezone.localdate()

        # 3. Seed dataset
        sample_txns = [
            # Today
            {"date": today, "time": "17:17", "merchant": "Googlecloud", "amount": "500.00", "cat": cat_bills, "ps": ps_hdfc_cc, "member": user_primary, "channel": "CARD", "source": "EMAIL", "cat_src": "AI", "flag": True, "reasons": ["Unusual off-peak recurring cloud charge"]},
            {"date": today, "time": "12:30", "merchant": "Chai Point", "amount": "140.00", "cat": cat_food, "ps": ps_hdfc_dc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "KEYWORD"},
            # Yesterday
            {"date": today - datetime.timedelta(days=1), "time": "20:45", "merchant": "Swiggy Instamart", "raw": "Swiggy Instamart payment", "amount": "46.00", "cat": cat_groceries, "ps": ps_icici_cc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "AI"},
            {"date": today - datetime.timedelta(days=1), "time": "19:10", "merchant": "Every Step", "amount": "52.00", "cat": cat_food, "ps": ps_hdfc_dc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today - datetime.timedelta(days=1), "time": "13:20", "merchant": "Zepto", "amount": "389.00", "cat": cat_groceries, "ps": ps_icici_cc, "member": user_spouse, "channel": "UPI", "source": "EMAIL", "cat_src": "KEYWORD"},
            # 2 days ago
            {"date": today - datetime.timedelta(days=2), "time": "20:35", "merchant": "Ct Flight", "raw": "Cleartrip Flights Indigo", "amount": "20092.00", "cat": cat_travel, "ps": ps_hdfc_cc, "member": user_primary, "channel": "CARD", "source": "EMAIL", "cat_src": "AI", "flag": True, "reasons": ["Large ticket purchase — 8× your usual travel spend"]},
            {"date": today - datetime.timedelta(days=2), "time": "20:21", "merchant": "Goibibo", "amount": "3846.00", "cat": cat_travel, "ps": ps_hdfc_cc, "member": user_primary, "channel": "CARD", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today - datetime.timedelta(days=2), "time": "10:15", "merchant": "Uber", "amount": "340.00", "cat": cat_travel, "ps": ps_icici_cc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "RULE"},
            # 3 days ago
            {"date": today - datetime.timedelta(days=3), "time": "18:05", "merchant": "Vendor UPI payment", "amount": "170.00", "cat": cat_transfers, "ps": ps_icici_cc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "AI"},
            {"date": today - datetime.timedelta(days=3), "time": "15:20", "merchant": "Vyapar", "amount": "10.00", "cat": cat_groceries, "ps": ps_hdfc_dc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today - datetime.timedelta(days=3), "time": "11:40", "merchant": "Shop UPI transfer", "amount": "163.00", "cat": cat_transfers, "ps": ps_icici_cc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "AI"},
            {"date": today - datetime.timedelta(days=3), "time": "09:12", "merchant": "Market UPI pay", "amount": "33.00", "cat": cat_groceries, "ps": ps_icici_cc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "AI"},
            # 5 days ago
            {"date": today - datetime.timedelta(days=5), "time": "19:40", "merchant": "Swiggy", "amount": "640.00", "cat": cat_food, "ps": ps_icici_cc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today - datetime.timedelta(days=5), "time": "14:22", "merchant": "Blinkit", "amount": "780.00", "cat": cat_groceries, "ps": ps_axis_dc, "member": user_spouse, "channel": "UPI", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today - datetime.timedelta(days=5), "time": "11:05", "merchant": "Amazon", "amount": "1499.00", "cat": cat_shopping, "ps": ps_icici_cc, "member": user_primary, "channel": "CARD", "source": "EMAIL", "cat_src": "KEYWORD"},
            # 7 days ago
            {"date": today - datetime.timedelta(days=7), "time": "16:30", "merchant": "Apollo Pharmacy", "amount": "450.00", "cat": cat_health, "ps": ps_hdfc_cc, "member": user_spouse, "channel": "CARD", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today - datetime.timedelta(days=7), "time": "10:00", "merchant": "Airtel Broadband", "amount": "1179.00", "cat": cat_bills, "ps": ps_hdfc_cc, "member": user_primary, "channel": "CARD", "source": "EMAIL", "cat_src": "KEYWORD"},
            # 10 days ago
            {"date": today - datetime.timedelta(days=10), "time": "18:00", "merchant": "CRED", "raw": "CRED CC Payment HDFC", "amount": "25000.00", "cat": cat_transfers, "ps": ps_hdfc_dc, "member": user_primary, "channel": "NETBANKING", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today - datetime.timedelta(days=10), "time": "14:15", "merchant": "Zara", "amount": "4990.00", "cat": cat_shopping, "ps": ps_axis_dc, "member": user_spouse, "channel": "CARD", "source": "EMAIL", "cat_src": "KEYWORD"},
            # 12 days ago
            {"date": today - datetime.timedelta(days=12), "time": "13:45", "merchant": "Starbucks", "amount": "580.00", "cat": cat_food, "ps": ps_hdfc_cc, "member": user_primary, "channel": "CARD", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today - datetime.timedelta(days=12), "time": "09:30", "merchant": "Bescom", "raw": "Bescom Electricity Bill", "amount": "2180.00", "cat": cat_bills, "ps": ps_hdfc_dc, "member": user_primary, "channel": "NETBANKING", "source": "EMAIL", "cat_src": "KEYWORD"},
            # Previous month (September 2026) for trend chart & comparisons
            {"date": today.replace(day=28) - datetime.timedelta(days=30), "time": "19:00", "merchant": "Croma", "amount": "8999.00", "cat": cat_shopping, "ps": ps_hdfc_cc, "member": user_primary, "channel": "CARD", "source": "STATEMENT", "cat_src": "KEYWORD"},
            {"date": today.replace(day=20) - datetime.timedelta(days=30), "time": "12:00", "merchant": "Swiggy", "amount": "520.00", "cat": cat_food, "ps": ps_icici_cc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today.replace(day=15) - datetime.timedelta(days=30), "time": "18:30", "merchant": "Zepto", "amount": "650.00", "cat": cat_groceries, "ps": ps_icici_cc, "member": user_spouse, "channel": "UPI", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today.replace(day=10) - datetime.timedelta(days=30), "time": "14:00", "merchant": "Airtel Broadband", "amount": "1179.00", "cat": cat_bills, "ps": ps_hdfc_cc, "member": user_primary, "channel": "CARD", "source": "EMAIL", "cat_src": "KEYWORD"},
            {"date": today.replace(day=5) - datetime.timedelta(days=30), "time": "11:20", "merchant": "Uber", "amount": "280.00", "cat": cat_travel, "ps": ps_icici_cc, "member": user_primary, "channel": "UPI", "source": "EMAIL", "cat_src": "RULE"},
            {"date": today.replace(day=2) - datetime.timedelta(days=30), "time": "10:00", "merchant": "Salary Credit", "amount": "125000.00", "direction": "CREDIT", "cat": get_cat("Income"), "ps": ps_hdfc_dc, "member": user_primary, "channel": "NETBANKING", "source": "EMAIL", "cat_src": "KEYWORD"},
        ]

        created_count = 0
        for item in sample_txns:
            display, key = normalize_merchant(item["merchant"])
            t_time = datetime.datetime.strptime(item.get("time", "12:00"), "%H:%M").time()
            exp = Expense(
                group=group,
                amount=Decimal(item["amount"]),
                direction=item.get("direction", "DEBIT"),
                currency="INR",
                txn_date=item["date"],
                txn_time=t_time,
                merchant=display,
                merchant_raw=item.get("raw", display),
                merchant_key=key,
                category=item.get("cat"),
                category_source=item.get("cat_src", "KEYWORD"),
                category_confidence=0.85 if item.get("cat_src") == "AI" else 1.0,
                payment_source=item.get("ps"),
                channel=item.get("channel", "UPI"),
                source=item.get("source", "EMAIL"),
                member=item.get("member", user_primary),
                is_flagged=item.get("flag", False),
                flag_reasons=item.get("reasons", []),
                flag_reviewed=False,
            )
            exp.save()
            created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {created_count} realistic expenses for '{group.name}'."))
