"""Authenticated read-only monitoring of the frozen paper rules."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.security import require_authenticated_user
from app.database import get_db
from app.services.paper_rules import RULES, list_summaries, rule_report
from app.config import settings

router = APIRouter(prefix='/paper-rules', tags=['paper-rules'], dependencies=[Depends(require_authenticated_user)])


@router.get('')
async def index(db: AsyncSession = Depends(get_db)):
    return {
        'enabled': settings.paper_rules_tracking_enabled,
        'rules': await list_summaries(db),
    }


@router.get('/{rule_key}')
async def report(rule_key: str, db: AsyncSession = Depends(get_db)):
    if rule_key not in RULES:
        raise HTTPException(status_code=404, detail=f'Unknown paper rule: {rule_key}')
    result = await rule_report(db, rule_key)
    result['enabled'] = settings.paper_rules_tracking_enabled
    return result
