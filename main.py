import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from tachyon.core.worker import TachyonVerificationWorker

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = TachyonVerificationWorker(interval_seconds=3600)
    task = asyncio.create_task(worker.start())
    yield
    worker.stop()
    task.cancel()

app = FastAPI(
    title="VIT Tachyon Fabric",
    description="Decentralised swarm storage coordination — EEC erasure coding, multi-cloud burst transfer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from tachyon.api.router import router as api_router
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return RedirectResponse(url="/health")

@app.get("/health")
async def health():
    from tachyon.core.scheduler import TachyonScheduler
    return {
        "status": "quantum_stable",
        "version": "1.0.0",
        "plane": "coordination",
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
