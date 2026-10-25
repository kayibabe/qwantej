"""Read-only market catalogue endpoint."""

from fastapi import APIRouter

from app.services.market_catalog import market_catalog_payload


router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/catalog")
def get_market_catalog() -> dict:
    return {
        "catalog_version": "1.0.0",
        "markets": market_catalog_payload(),
    }
