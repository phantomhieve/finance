from decimal import Decimal

from django.core.management.base import BaseCommand

from portfolio.services import apply_annual_land_appreciation


class Command(BaseCommand):
    help = 'FY-end markup of plot/agricultural land valuations (run on 1 April, before the March snapshot).'

    def add_arguments(self, parser):
        parser.add_argument('--pct', type=Decimal, default=Decimal('6'), help='Annual appreciation %% (default 6).')
        parser.add_argument('--dry-run', action='store_true', help='Show changes without saving.')

    def handle(self, *args, **options):
        fy, results = apply_annual_land_appreciation(pct=options['pct'], dry_run=options['dry_run'])
        prefix = '[dry-run] ' if options['dry_run'] else ''
        if not results:
            self.stdout.write(f'{prefix}No land holdings pending appreciation for {fy}.')
            return
        for r in results:
            h = r['holding']
            if r['skipped']:
                self.stdout.write(f"{prefix}{h.name}: revalued manually on {h.last_valuation_date}, kept ₹{r['old']:,.0f}")
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"{prefix}{h.name}: ₹{r['old']:,.0f} → ₹{r['new']:,.0f} (+{options['pct']}% for {fy})"
                ))
