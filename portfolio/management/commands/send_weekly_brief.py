import os
import json
from google import genai
from pydantic import BaseModel
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone as _tz
from django.db.models import Sum
from django.conf import settings

from tracker.models import AccountGroup
from portfolio.models import StockHolding, CashPosition, FixedDeposit
from portfolio.ai import _load_investor_profile, _get_model

class AIContextItem(BaseModel):
    symbol: str
    context: str

class WeeklyAnalysisResponse(BaseModel):
    safety_floor_inr: float
    items: list[AIContextItem]

class Command(BaseCommand):
    help = 'Sends the weekly equity intelligence brief.'

    def handle(self, *args, **options):
        target_email = 'khetanatulz@gmail.com'
        group = AccountGroup.objects.first()
        if not group:
            self.stdout.write(self.style.ERROR('No household group found.'))
            return

        # 1. Cash & FDs
        cash_qs = CashPosition.objects.filter(group=group)
        fd_qs = FixedDeposit.objects.filter(group=group, is_active=True)
        total_cash = float(cash_qs.aggregate(t=Sum('amount'))['t'] or 0)
        total_fd = sum(float(fd.current_value) for fd in fd_qs)
        total_liquid = total_cash + total_fd

        # 2. Consolidated Stock Holdings
        stocks_qs = StockHolding.objects.filter(account__group=group)
        
        symbols_dict = {}
        for s in stocks_qs:
            if s.symbol not in symbols_dict:
                symbols_dict[s.symbol] = {
                    'symbol': s.symbol,
                    'invested': 0.0,
                    'current': 0.0,
                    'accounts': []
                }
            
            acc_invested = float(s.purchase_value)
            acc_current = float(s.current_value)
            symbols_dict[s.symbol]['invested'] += acc_invested
            symbols_dict[s.symbol]['current'] += acc_current
            symbols_dict[s.symbol]['accounts'].append({
                'name': s.account.name,
                'qty': s.quantity,
                'invested': acc_invested,
                'current': acc_current
            })
            
        stock_list = []
        for s in symbols_dict.values():
            s['pnl'] = s['current'] - s['invested']
            s['pnl_pct'] = (s['pnl'] / s['invested'] * 100) if s['invested'] else 0
            stock_list.append(s)
            
        # Sort by worst performing first to highlight drawdowns
        stock_list.sort(key=lambda x: x['pnl_pct'])

        # Find drawdowns (>10% below cost basis) and outperformers
        notable_stocks = [s for s in stock_list if s['pnl_pct'] <= -10 or s['pnl_pct'] >= 15]

        # 3. Call Gemini to calculate the floor dynamically and provide context
        api_key = os.environ.get('GEMINI_API_KEY', '')
        floor = 600000.0
        ai_context = []
        
        if api_key:
            try:
                client = genai.Client(api_key=api_key)
                model = _get_model()
                profile = _load_investor_profile(group)
                stocks_json = json.dumps([{
                    'symbol': s['symbol'], 
                    'pnl_pct': round(s['pnl_pct'], 2)
                } for s in notable_stocks])
                
                prompt = (
                    "You are a financial analyst generating a weekly equity brief.\n\n"
                    "TASK 1: Extract the safety floor (emergency fund target) in INR from the investor profile below. Return it as a float.\n"
                    f"Profile: {profile}\n\n"
                    "TASK 2: Provide fundamental valuation context (P/E, yield, moat durability) for these notable stock positions based on their net performance. Be concise.\n"
                    f"Stocks: {stocks_json}\n"
                )
                
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": WeeklyAnalysisResponse
                    }
                )
                
                if response.parsed:
                    floor = response.parsed.safety_floor_inr
                    ai_context = response.parsed.items
                    
                self.stdout.write(self.style.SUCCESS('Successfully generated AI context and dynamic floor.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to generate AI context: {e}'))

        deficit = max(0.0, floor - total_liquid)
        deployable = 0.0 if deficit > 0 else max(0.0, total_liquid - floor)

        context = {
            'date': _tz.now().strftime('%d %B %Y'),
            'total_cash': total_cash,
            'total_fd': total_fd,
            'total_liquid': total_liquid,
            'floor': floor,
            'deficit': deficit,
            'deployable': deployable,
            'stocks': stock_list,
            'ai_context': ai_context,
        }

        html_content = render_to_string('emails/weekly_brief.html', context)
        text_content = f"Weekly Equity Intelligence Brief\nLiquid Reserves: {total_liquid}\nFloor: {floor}\nDeficit: {deficit}\nDeployable: {deployable}"
        
        subject = "Weekly Long-Term Equity Intelligence & Allocation Brief"
        from_email = getattr(settings, 'EMAIL_HOST_USER', 'vault@example.com') or 'vault@example.com'
        
        msg = EmailMultiAlternatives(subject, text_content, from_email, [target_email])
        msg.attach_alternative(html_content, "text/html")
        
        try:
            msg.send()
            self.stdout.write(self.style.SUCCESS(f'Successfully sent weekly brief to {target_email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to send email: {e}'))
