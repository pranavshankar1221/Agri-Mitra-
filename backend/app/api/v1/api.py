from fastapi import APIRouter
from app.api.v1.endpoints import agent, market

api_router = APIRouter()
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(market.router, prefix="/markets", tags=["market prices"])
