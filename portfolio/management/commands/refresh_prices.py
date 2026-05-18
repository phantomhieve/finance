import logging

from django.core.management.base import BaseCommand

from portfolio.services import refresh_commodity_prices, refresh_us_stock_prices

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Refresh commodity and US stock prices.'

    def handle(self, *args, **options):
        try:
            results = refresh_commodity_prices()
        except Exception as e:
            logger.exception("Commodity price refresh failed")
            self.stderr.write(self.style.ERROR(f"Commodity price refresh failed: {e}"))
            results = None

        if results:
            for commodity, rate in results.items():
                self.stdout.write(self.style.SUCCESS(
                    f"{commodity.title()}: \u20b9{rate:,.2f}/g"
                ))
        else:
            self.stderr.write(self.style.WARNING(
                "Could not fetch commodity prices."
            ))

        try:
            us_results = refresh_us_stock_prices()
            if us_results:
                for sym, price in us_results['prices'].items():
                    self.stdout.write(self.style.SUCCESS(
                        f"{sym}: ${price:.2f} (USD/INR: \u20b9{us_results['usd_inr']:,.2f})"
                    ))
            else:
                self.stdout.write(self.style.NOTICE("No US stock holdings to refresh."))
        except Exception as e:
            logger.exception("US stock price refresh failed")
            self.stderr.write(self.style.ERROR(f"US stock price refresh failed: {e}"))
