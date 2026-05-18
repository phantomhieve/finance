import logging

from django.core.management.base import BaseCommand

from portfolio.services import sync_zerodha_from_sheets

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync all Zerodha accounts from Google Sheets.'

    def handle(self, *args, **options):
        try:
            results = sync_zerodha_from_sheets()
        except Exception as e:
            logger.exception("Sheets sync failed")
            self.stderr.write(self.style.ERROR(str(e)))
            return

        for r in results:
            if 'error' in r:
                self.stderr.write(self.style.ERROR(
                    f"Failed: {r['account']} — {r['error']}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Synced {r['account']}: "
                    f"{r['stocks']} stocks, "
                    f"{r['index_mf']} index MFs, "
                    f"{r['other_mf']} other MFs"
                ))

        if not results:
            self.stdout.write(self.style.WARNING(
                "No accounts configured with sheet IDs. "
                "Add sheet_id via Django admin for your Zerodha accounts."
            ))
