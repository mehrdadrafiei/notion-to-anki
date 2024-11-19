# middleware/caching.py
import asyncio

from aiocache import Cache, cached
from aiocache.serializers import PickleSerializer
from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

cache = Cache(Cache.MEMORY, serializer=PickleSerializer())


class CachingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Define a cache key based on the request
        cache_key = f"{request.method}:{request.url.path}"
        if request.query_params:
            cache_key += f"?{request.query_params}"

        if request.url.path.startswith("/generate-flashcards"):
            return await call_next(request)  # Don't cache generation endpoints

        # Check if the result is in the cache
        cached_response = await cache.get(cache_key)
        if cached_response:
            return Response(content=cached_response, status_code=200)

        # If not in cache, call the next middleware or route handler
        response = await call_next(request)

        # Check if response is streaming
        if isinstance(response, StreamingResponse):
            # Buffer the streaming response
            content = b''.join([part async for part in response.body_iterator])
            response = Response(content=content, status_code=response.status_code, headers=dict(response.headers))
        else:
            content = response.body

        if response.status_code == 200:
            await cache.set(cache_key, response.body, ttl=300)  # Cache for 5 minutes

        return response
