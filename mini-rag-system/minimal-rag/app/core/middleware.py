import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import logging 

logger = logging.getLogger(__name__)

class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        upstream_id = request.headers.get("X-Request-ID")
        request_id = upstream_id or f"gen-{uuid.uuid4().hex[:8]}"
        request.state.request_id = request_id

        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        return response