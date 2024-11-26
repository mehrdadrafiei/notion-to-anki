from fastapi import APIRouter, Request

from monitoring.health import HealthCheck

router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    """
    Perform system health check.

    Args:
        request (Request): Incoming HTTP request

    Returns:
        Dict: Health check results
    """
    async with HealthCheck() as health_check:
        return await health_check.get_health(request)
