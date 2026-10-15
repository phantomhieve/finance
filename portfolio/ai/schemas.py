"""Pydantic schemas and enums for portfolio AI insights."""
from __future__ import annotations

import enum
import re
from typing import Any

from pydantic import BaseModel, field_validator, model_validator


class InsightCategory(str, enum.Enum):
    RISK = 'risk'
    OPPORTUNITY = 'opportunity'
    REBALANCING = 'rebalancing'
    GOAL = 'goal'
    TAX = 'tax'
    MACRO = 'macro'
    CONSOLIDATION = 'consolidation'
    INTERNATIONAL = 'international'


class InsightSeverity(str, enum.Enum):
    INFO = 'info'
    WARNING = 'warning'
    POSITIVE = 'positive'
    CRITICAL = 'critical'


class Insight(BaseModel):
    category: InsightCategory
    severity: InsightSeverity
    title: str
    detail: str
    action: str | None = None

    @field_validator('category', mode='before')
    @classmethod
    def normalize_category(cls, v: Any):
        if isinstance(v, str):
            v_clean = v.strip().lower()
            valid = {c.value for c in InsightCategory}
            if v_clean in valid:
                return v_clean
            mapping = {
                'allocation': 'rebalancing',
                'asset_allocation': 'rebalancing',
                'diversification': 'rebalancing',
                'liquidity': 'risk',
                'concentration': 'risk',
                'debt': 'risk',
                'regulatory': 'tax',
                'compliance': 'tax',
            }
            if v_clean in mapping:
                return mapping[v_clean]
            if 'risk' in v_clean:
                return 'risk'
            if 'opp' in v_clean:
                return 'opportunity'
            if 'tax' in v_clean:
                return 'tax'
            return 'rebalancing'
        return v

    @field_validator('severity', mode='before')
    @classmethod
    def normalize_severity(cls, v: Any):
        if isinstance(v, str):
            v_clean = v.strip().lower()
            valid = {s.value for s in InsightSeverity}
            if v_clean in valid:
                return v_clean
            mapping = {
                'high': 'critical',
                'urgent': 'critical',
                'severe': 'critical',
                'medium': 'warning',
                'warn': 'warning',
                'moderate': 'warning',
                'low': 'info',
                'neutral': 'info',
                'informational': 'info',
                'good': 'positive',
                'success': 'positive',
                'opportunity': 'positive',
                'rebalancing': 'info',
                'goal': 'info',
                'tax': 'info',
            }
            if v_clean in mapping:
                return mapping[v_clean]
            return 'info'
        return v


class PortfolioInsightsResponse(BaseModel):
    summary: str
    score: int
    insights: list[Insight]
    market_context: str = ""
    outlook: str = ""

    @model_validator(mode='before')
    @classmethod
    def normalize_response_dict(cls, data: Any):
        if not isinstance(data, dict):
            return data

        # 1. Alias field names if LLM used common synonyms
        if 'summary' not in data:
            for alt in ('overview', 'executive_summary', 'portfolio_summary', 'analysis'):
                if alt in data and data[alt]:
                    data['summary'] = str(data[alt])
                    break
            else:
                data['summary'] = "Portfolio analysis completed successfully."

        if 'score' not in data:
            for alt in ('financial_health_score', 'health_score', 'rating'):
                if alt in data and data[alt] is not None:
                    data['score'] = data[alt]
                    break
            else:
                data['score'] = 65

        if 'insights' not in data:
            for alt in ('key_insights', 'recommendations', 'items', 'findings'):
                if alt in data and isinstance(data[alt], list):
                    data['insights'] = data[alt]
                    break
            else:
                data['insights'] = []

        if 'market_context' not in data:
            for alt in ('market_overview', 'macro', 'macro_context'):
                if alt in data and data[alt]:
                    data['market_context'] = str(data[alt])
                    break

        if 'outlook' not in data:
            for alt in ('next_steps', 'priorities', 'recommendations_summary', 'action_plan'):
                if alt in data and data[alt]:
                    data['outlook'] = str(data[alt])
                    break

        # 2. Heal individual insights list
        raw_insights = data.get('insights')
        if isinstance(raw_insights, list):
            cleaned_list = []
            for item in raw_insights:
                if isinstance(item, dict):
                    # Ensure title exists
                    if not item.get('title'):
                        item['title'] = str(item.get('headline') or item.get('name') or item.get('category') or 'Insight')[:100]
                    # Ensure detail exists
                    if not item.get('detail'):
                        item['detail'] = str(item.get('description') or item.get('text') or item.get('title') or '')
                    # Normalize empty action
                    if not item.get('action') or str(item.get('action')).strip().lower() in ('none', 'null', 'n/a', ''):
                        item['action'] = None
                    cleaned_list.append(item)
            data['insights'] = cleaned_list

        return data

    @field_validator('score', mode='before')
    @classmethod
    def normalize_score(cls, v: Any):
        if isinstance(v, (int, float)):
            return max(0, min(100, int(round(v))))
        if isinstance(v, str):
            m = re.search(r'\d+', v)
            if m:
                val = int(m.group(0))
                return max(0, min(100, val))
        return 65
