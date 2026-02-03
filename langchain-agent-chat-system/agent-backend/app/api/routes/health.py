"""Health check and admin endpoints."""
from fastapi import APIRouter, Depends

from models import HealthCheckResponse
from infrastructure.database.mongodb import mongo_manager
from api.dependencies import get_current_user_id

router = APIRouter()


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint for monitoring

    Use Case:
    - Load balancer health checks
    - Kubernetes liveness/readiness probes
    - Monitoring systems
    """
    db_healthy = mongo_manager.health_check()
    db_stats = mongo_manager.get_connection_stats()

    return HealthCheckResponse(
        status="healthy" if db_healthy else "unhealthy",
        database=db_stats
    )


@router.get("/admin/connection-stats")
async def get_connection_stats(
    token_user_id: str = Depends(get_current_user_id)
):
    """
    Get MongoDB connection pool statistics

    Use Case: Debugging, monitoring
    Note: Should be protected with admin role in production
    """
    return mongo_manager.get_connection_stats()
