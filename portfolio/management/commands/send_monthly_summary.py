import datetime
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone as _tz
from django.conf import settings

from tracker.models import AccountGroup
from portfolio.models import PortfolioInsight, InsightGenerationSettings
from portfolio.services import get_portfolio_summary, get_growth_data
from portfolio.ai import build_prompt_data, call_gemini

class Command(BaseCommand):
    help = 'Sends the monthly AI portfolio summary to the household head.'

    def handle(self, *args, **options):
        # We want to send it to the household head only for now
        target_email = 'khetanatulz@gmail.com'
        
        # Get the household group (assuming first one for now)
        group = AccountGroup.objects.first()
        if not group:
            self.stdout.write(self.style.ERROR('No household group found.'))
            return
            
        # 1. Sync AI service if not in cooldown
        qs = PortfolioInsight.objects.filter(group=group).order_by('-generated_at')
        latest = qs.first()
        
        # Get cooldown settings
        cooldown_days = InsightGenerationSettings.get_solo().cooldown_days
        cooldown = datetime.timedelta(days=cooldown_days)
        
        can_generate = True
        if latest:
            can_generate = (_tz.now() - latest.generated_at) >= cooldown
            
        if can_generate:
            self.stdout.write('AI insight cooldown has passed. Generating new insights...')
            try:
                summary = get_portfolio_summary(group)
                growth = get_growth_data(group=group)
                prompt_data = build_prompt_data(summary, growth, group)
                result = call_gemini(prompt_data, group=group)
                latest = PortfolioInsight.objects.create(
                    group=group,
                    model_used=result.model,
                    prompt_data=prompt_data,
                    insights=result.insights_dict,
                )
                self.stdout.write(self.style.SUCCESS('Successfully generated new AI insights.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to generate AI insights: {e}'))
        else:
            self.stdout.write('AI insight generation is on cooldown. Using the latest available insights.')
            
        # 2. Prepare and send the email
        if not latest:
            self.stdout.write(self.style.WARNING('No AI insights available to send.'))
            return
            
        context = {
            'month': _tz.now().strftime('%B %Y'),
            'insights': latest.insights,
        }
        
        html_content = render_to_string('emails/monthly_summary.html', context)
        
        # Fallback text content just in case
        text_content = f"Monthly Portfolio AI Summary for {_tz.now().strftime('%B %Y')}\n\n"
        if latest.insights:
            text_content += f"Score: {latest.insights.get('score')}/100\n\n"
            text_content += f"Summary: {latest.insights.get('summary')}\n"
            
        subject = f"Your Vault Monthly AI Summary - {_tz.now().strftime('%b %Y')}"
        from_email = getattr(settings, 'EMAIL_HOST_USER', 'vault@example.com') or 'vault@example.com'
        
        msg = EmailMultiAlternatives(subject, text_content, from_email, [target_email])
        msg.attach_alternative(html_content, "text/html")
        
        try:
            msg.send()
            self.stdout.write(self.style.SUCCESS(f'Successfully sent monthly summary to {target_email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to send email: {e}'))
