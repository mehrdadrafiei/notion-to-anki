from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.core.config import settings
from src.core.container import cleanup_dependencies, init_dependencies
from src.domain.chatbot.factory import ChatBotFactory

from ..core.config import settings
from .middleware.rate_limiting import RateLimitMiddleware
from .routes import flashcard_routes, health_routes, websocket_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_dependencies()
    yield
    # Shutdown
    await cleanup_dependencies()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured application instance
    """
    app = FastAPI(
        title="Flashcard Generator API",
        description="API for generating flashcards from Notion pages",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    # Add middleware
    app.add_middleware(RateLimitMiddleware, calls=settings.rate_limit_calls, period=settings.rate_limit_period)

    # Mount static files and templates
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Include routers
    app.include_router(flashcard_routes.router, prefix="")
    app.include_router(health_routes.router)
    app.include_router(websocket_routes.router)

    return app


app = create_app()
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def home(request: Request):
    """
    Home route rendering the index page.

    Args:
        request (Request): Incoming HTTP request

    Returns:
        TemplateResponse: Rendered index page
    """
    return templates.TemplateResponse(
        "index.html", {"request": request, "chatbot_types": ChatBotFactory.get_available_chatbots()}
    )


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True, ws="websockets", log_level="info")
