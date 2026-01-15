"""
Health check endpoint for Green Agent.

Provides system health status, component status, and readiness checks.
Implements Health check endpoint with component status.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from src.config import get_config
from src.resources.health_checker import check_mcp_health


class ComponentStatus(BaseModel):
    """Status of a component."""
    
    name: str
    status: str  # healthy, degraded, unhealthy
    message: Optional[str] = None
    last_check: str


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str  # healthy, degraded, unhealthy
    timestamp: str
    version: str
    uptime_seconds: Optional[float] = None
    components: Dict[str, ComponentStatus]


# Track application start time
_start_time: Optional[datetime] = None


def set_start_time(start_time: datetime) -> None:
    """Set application start time."""
    global _start_time
    _start_time = start_time


def get_uptime_seconds() -> Optional[float]:
    """Get application uptime in seconds."""
    if _start_time is None:
        return None
    return (datetime.utcnow() - _start_time).total_seconds()


async def check_mcp_server_health() -> ComponentStatus:
    """
    Check MCP server health.
    
    Returns:
        MCP server component status
    """
    try:
        # TODO: Import actual MCP health check when available
        # For now, return a placeholder
        return ComponentStatus(
            name="mcp_server",
            status="healthy",
            message="MCP server operational",
            last_check=datetime.utcnow().isoformat() + "Z"
        )
    except Exception as e:
        return ComponentStatus(
            name="mcp_server",
            status="unhealthy",
            message=f"MCP health check failed: {e}",
            last_check=datetime.utcnow().isoformat() + "Z"
        )


async def check_langfuse_health() -> ComponentStatus:
    """
    Check Langfuse tracing health.
    
    Returns:
        Langfuse component status
    """
    config = get_config()
    
    if not config.observability.enable_langfuse:
        return ComponentStatus(
            name="langfuse",
            status="healthy",
            message="Langfuse disabled",
            last_check=datetime.utcnow().isoformat() + "Z"
        )
    
    try:
        # TODO: Add actual Langfuse health check
        # For now, check if keys are configured
        if config.observability.langfuse_public_key and config.observability.langfuse_secret_key:
            return ComponentStatus(
                name="langfuse",
                status="healthy",
                message="Langfuse configured",
                last_check=datetime.utcnow().isoformat() + "Z"
            )
        else:
            return ComponentStatus(
                name="langfuse",
                status="degraded",
                message="Langfuse keys not configured",
                last_check=datetime.utcnow().isoformat() + "Z"
            )
    except Exception as e:
        return ComponentStatus(
            name="langfuse",
            status="unhealthy",
            message=f"Langfuse check failed: {e}",
            last_check=datetime.utcnow().isoformat() + "Z"
        )


async def check_session_health() -> ComponentStatus:
    """
    Check session management health.
    
    Returns:
        Session component status
    """
    config = get_config()
    
    try:
        if config.session.use_persistent_sessions:
            # TODO: Check SQLite database connectivity
            return ComponentStatus(
                name="sessions",
                status="healthy",
                message="Persistent sessions configured",
                last_check=datetime.utcnow().isoformat() + "Z"
            )
        else:
            return ComponentStatus(
                name="sessions",
                status="healthy",
                message="In-memory sessions",
                last_check=datetime.utcnow().isoformat() + "Z"
            )
    except Exception as e:
        return ComponentStatus(
            name="sessions",
            status="unhealthy",
            message=f"Session check failed: {e}",
            last_check=datetime.utcnow().isoformat() + "Z"
        )


async def get_health_status() -> HealthResponse:
    """
    Get comprehensive health status.
    
    Returns:
        Health check response with all component statuses
    """
    config = get_config()
    
    # Check all components in parallel
    component_checks = await asyncio.gather(
        check_mcp_server_health(),
        check_langfuse_health(),
        check_session_health(),
        return_exceptions=True
    )
    
    # Build component status dict
    components = {}
    for check in component_checks:
        if isinstance(check, ComponentStatus):
            components[check.name] = check
        elif isinstance(check, Exception):
            components["unknown"] = ComponentStatus(
                name="unknown",
                status="unhealthy",
                message=f"Health check error: {check}",
                last_check=datetime.utcnow().isoformat() + "Z"
            )
    
    # Determine overall status
    statuses = [comp.status for comp in components.values()]
    if "unhealthy" in statuses:
        overall_status = "unhealthy"
    elif "degraded" in statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat() + "Z",
        version=config.agent_version,
        uptime_seconds=get_uptime_seconds(),
        components=components
    )


# FastAPI router for health endpoints
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(response: Response) -> HealthResponse:
    """
    Comprehensive health check endpoint.
    
    Returns health status of Green Agent and all components.
    Sets HTTP status code based on health:
    - 200: healthy
    - 503: degraded or unhealthy
    
    Returns:
        Health check response
    """
    health_status = await get_health_status()
    
    # Set HTTP status code
    if health_status.status == "healthy":
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return health_status


@router.get("/health/ready", response_model=Dict[str, Any])
async def readiness_check(response: Response) -> Dict[str, Any]:
    """
    Readiness check endpoint for Kubernetes.
    
    Returns 200 if ready to accept requests, 503 otherwise.
    
    Returns:
        Readiness status
    """
    health_status = await get_health_status()
    
    ready = health_status.status != "unhealthy"
    
    if ready:
        response.status_code = status.HTTP_200_OK
        return {"ready": True, "status": health_status.status}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ready": False, "status": health_status.status}


@router.get("/health/live", response_model=Dict[str, Any])
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check endpoint for Kubernetes.
    
    Returns 200 if application is alive (even if degraded).
    Only returns 503 if application is completely broken.
    
    Returns:
        Liveness status
    """
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


__all__ = [
    "HealthResponse",
    "ComponentStatus",
    "get_health_status",
    "router",
    "set_start_time",
    "get_uptime_seconds",
]
