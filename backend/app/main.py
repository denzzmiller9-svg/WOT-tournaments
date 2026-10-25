import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path
import logging

from fastapi import FastAPI
from app.api.main import api_router
from app.core.config import get_settings
from app.services.background_service import BackgroundService
from fastapi.middleware.cors import CORSMiddleware


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    background_service = BackgroundService()

    background_services_tournament_statuses = asyncio.create_task(
        background_service.run_update_tournament_statuses(),
        name="background-service-tournament-status",
    )
    background_service_user_raiting = asyncio.create_task(
            background_service.run_update_user_raiting(),
            name="background-services-user-raiting",
        )
    try:
        yield
    finally:
        background_services_tournament_statuses.cancel()
        background_service_user_raiting.cancel()
        try:
            await background_services_tournament_statuses
            await background_service_user_raiting
        except asyncio.CancelledError:
            logger.info("background services stopped")


app = FastAPI(
    title=settings.project_name,
    openapi_url=f"{settings.api_v1_str}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_host],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(api_router, prefix=settings.api_v1_str)
app.frontend("/", directory=FRONTEND_DIST, fallback="auto")
