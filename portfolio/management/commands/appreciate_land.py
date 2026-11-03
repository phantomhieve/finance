from decimal import Decimal

from django.core.management.base import BaseCommand

from portfolio.services import apply_annual_land_appreciation


class Command(BaseCommand):
    help = (
        'FY-end markup of plot/agricultural land valuations (run on 1 April, before the March snapshot). '
        'Uses an AI multi-stage consensus DAG (Gemini Search Grounding + DeepSeek auditor) unless overridden.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--pct',
            type=Decimal,
            default=None,
            help='Manual appreciation %% override (e.g. 6.0). If omitted, multi-stage AI appraisal is executed.',
        )
        parser.add_argument(
            '--no-ai',
            action='store_true',
            help='Disable multi-stage AI appraisal and use conservative fallback (6%%).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show changes without saving to database.',
        )
        parser.add_argument(
            '--send-email',
            action='store_true',
            help='Dispatch valuation report email even when running in --dry-run mode.',
        )
        parser.add_argument(
            '--no-email',
            action='store_true',
            help='Suppress sending valuation report email.',
        )

    def handle(self, *args, **options):
        pct = options.get('pct')
        no_ai = options.get('no_ai')
        use_ai = not no_ai if pct is None else False
        dry_run = options.get('dry_run', False)

        fy, results = apply_annual_land_appreciation(
            pct=pct,
            dry_run=dry_run,
            use_ai=use_ai,
        )
        prefix = '[dry-run] ' if dry_run else ''
        if not results:
            self.stdout.write(f'{prefix}No land holdings pending appreciation for {fy}.')
            return

        for r in results:
            h = r['holding']
            if r['skipped']:
                self.stdout.write(f"{prefix}{h.name}: revalued manually on {h.last_valuation_date}, kept ₹{r['old']:,.0f}")
            else:
                pct_str = f"+{r['pct']:.2f}%" if isinstance(r['pct'], Decimal) else f"+{r['pct']}%"
                mode_label = "AI Appraisal" if r.get('appraisal') else "Manual/Rule"
                self.stdout.write(self.style.SUCCESS(
                    f"{prefix}{h.name}: ₹{r['old']:,.0f} → ₹{r['new']:,.0f} ({pct_str} for {fy}) [{mode_label}]"
                ))
                appraisal = r.get('appraisal')
                if appraisal:
                    self.stdout.write(f"  • Models: {appraisal.model_chain_used}")
                    if appraisal.implied_rate_per_sq_yd_inr > 0:
                        unit = h.area_unit or 'unit'
                        self.stdout.write(f"  • Implied rate: ₹{appraisal.implied_rate_per_sq_yd_inr:,.0f} / {unit}")
                    if appraisal.key_drivers:
                        self.stdout.write(f"  • Growth catalysts: {', '.join(appraisal.key_drivers[:3])}")
                    if appraisal.risk_haircuts_applied:
                        self.stdout.write(f"  • Skeptical haircuts: {', '.join(appraisal.risk_haircuts_applied[:3])}")
                    self.stdout.write(f"  • Methodology: {appraisal.methodology_summary}")

        should_send = (not dry_run and not options.get('no_email')) or options.get('send_email')
        if should_send:
            from portfolio.emails import send_land_appraisal_email
            ok, msg = send_land_appraisal_email(results, fy)
            if ok:
                self.stdout.write(self.style.SUCCESS(f"{prefix}{msg}"))
            else:
                self.stdout.write(self.style.WARNING(f"{prefix}{msg}"))

