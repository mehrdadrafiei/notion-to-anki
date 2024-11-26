from fastapi import APIRouter, Request

from src.core.error_handling import handle_exceptions
from src.core.exceptions.base import ExternalServiceError

from ..monitoring.health import HealthCheck

router = APIRouter()


@router.get("/health")
@handle_exceptions({ExternalServiceError: (503, "Service health check failed")})
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
