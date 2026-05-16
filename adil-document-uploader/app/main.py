import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.judgments import router as judgments_router
from health_bot import notify as msentry_notify  # MSentry health-bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    msentry_notify(
        "info", "deploy", "adil-document-uploader started", commit=os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown")
    )  # MSentry startup ping
    yield


app = FastAPI(
    title="AskAdil Document Uploader",
    description="Fetches UK case law from TNA and uploads to Gemini FST store",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "adil-document-uploader"}


app.include_router(judgments_router)
app.include_router(admin_router)
