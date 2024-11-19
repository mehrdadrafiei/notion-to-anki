import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int, period: int):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.requests = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        current_time = time.time()

        # Remove outdated requests
        self.requests[client_ip] = [t for t in self.requests[client_ip] if t > current_time - self.period]

        if len(self.requests[client_ip]) >= self.calls:
            return Response(status_code=429, content="Rate limit exceeded")

        self.requests[client_ip].append(current_time)
        response = await call_next(request)
        return response
