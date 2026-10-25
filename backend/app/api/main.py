from fastapi import APIRouter
from app.api.rotes import tournaments, users, auth, messages

api_router = APIRouter()
api_router.include_router(tournaments.router)
api_router.include_router(users.router)
api_router.include_router(auth.router)
api_router.include_router(messages.router)
