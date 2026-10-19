"""Authenticated read-only monitoring of the frozen paper experiment."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.security import require_authenticated_user
from app.database import get_db
from app.services.sweet_spot import report
from app.config import settings

router = APIRouter(prefix='/sweet-spot', tags=['sweet-spot'], dependencies=[Depends(require_authenticated_user)])


@router.get('')
async def status(db: AsyncSession = Depends(get_db)):
    result = await report(db)
    result['enabled'] = settings.sweet_spot_tracking_enabled
    return result
