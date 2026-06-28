from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers.lab import router as lab_router
from routers.projects import router as projects_router
from routers.schemes import router as schemes_router
from routers.knowledge import router as knowledge_router

app = FastAPI(title="FacadeGPT", version="1.0.0")

# 允许开发环境以及任意生产域名访问。没有登录态，无需 credentials。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(projects_router)
app.include_router(schemes_router)
app.include_router(knowledge_router)
app.include_router(lab_router)

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

RENDERS_DIR = Path(__file__).resolve().parent / "renders"
RENDERS_DIR.mkdir(exist_ok=True)
app.mount("/renders", StaticFiles(directory=RENDERS_DIR), name="renders")

DEMO_RENDERS_DIR = Path(__file__).resolve().parent / "demo_renders"
DEMO_RENDERS_DIR.mkdir(exist_ok=True)
app.mount("/demo-renders", StaticFiles(directory=DEMO_RENDERS_DIR), name="demo-renders")


@app.get("/")
def frontend_index():
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Frontend is not built. Run npm.cmd run build in frontend/."}


@app.get("/{full_path:path}")
def frontend_fallback(full_path: str):
    if full_path.startswith("api/"):
        return {"detail": "Not Found"}
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Frontend is not built. Run npm.cmd run build in frontend/."}
