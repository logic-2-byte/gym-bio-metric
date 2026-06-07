from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app import logger
from app.core.config import setup_logger
from app.core.manager import lifespan
from app.core.redis import RedisHelper
from app.core.settings import Settings
from app.router.base import router as base_router
from app.router.iclock import router as iclock_router

_settings = Settings()

app = FastAPI(lifespan=lifespan, debug=_settings.debug, docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_logger(_settings.debug)

app.include_router(base_router)
app.include_router(iclock_router)


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def catch_all(path: str, request: Request) -> str:
    body = await request.body()
    print("PATH:", path)
    print("QUERY:", request.query_params)
    print("BODY:", body.decode(errors="ignore"))
    return "OK"


client = TestClient(app)


def add_cache_layer(app: FastAPI) -> None:
    try:
        app.state.cache = RedisHelper()
    except Exception as e:
        logger.error(e)
