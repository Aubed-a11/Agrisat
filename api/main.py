"""API AGRISAT. Lancement: uvicorn api.main:app --reload --port 8000"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .db import Base, engine, SessionLocal
from .store import get_store
from .routers import core, operations, admin
from .seed import seed

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


@asynccontextmanager
async def lifespan(app):
    get_store()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="AGRISAT API", version="1.0.0", lifespan=lifespan,
              description="Assurance agricole indicielle par satellite pour le Nord Bénin")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(core.router)
app.include_router(operations.router)
app.include_router(admin.router)

if WEB_DIST.exists():  # en production, l'API sert aussi l'application web compilee
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB_DIST / path
        return FileResponse(f if path and f.is_file() else WEB_DIST / "index.html")
