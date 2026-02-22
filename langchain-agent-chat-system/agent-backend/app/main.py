from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import logging

from app.infrastructure.database.mongodb import mongo_manager
from app.api.middleware import setup_cors
from app.api.routes import chat_router, sessions_router, health_router
from starlette.exceptions import HTTPException as StarletteException
from fastapi.responses import JSONResponse
from app.clients.mcp_client import get_mcp_tools

logger = logging.getLogger("LangChain-Agent")

# ===== APPLICATION LIFECYCLE =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management

    STARTUP:
    - Initialize MongoDB connection pool
    - Verify connections

    SHUTDOWN:
    - Close MongoDB connections gracefully
    - Clean up resources
    """
    logger.info("Starting LangChain-Agent Chat Backend...")
    try:
        # Initialize MongoDB
        mongo_manager.initialize()
        logger.info("Mongo connected")

        logger.info("Application startup complete")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    yield

    logger.info("Shutting down LangChain-Agent Chat Backend...")
    try:
        mongo_manager.close()
        logger.info("Graceful shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# --- FastAPI App Setup ---
app = FastAPI(
    title="Langchain Chat Inference Service",
    version="2.1.5",
    description="Production-ready chat API with cursor pagination and connection pooling",
    lifespan=lifespan
)

# --- Middleware ---
setup_cors(app)

# --- Include Routers
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(sessions_router)

@app.exception_handler(StarletteException)
async def http_exception_handler(request: Request, exc: StarletteException):
    """Global HTTP Exception Handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(Exception)
async def universal_exception_handler(request: Request, exc:Exception):
    """Global universal fallback handler"""
    logger.error(f"Global Crash: {str(exc)}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "msg": str(exc)}
    )