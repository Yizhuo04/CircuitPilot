"""FastAPI composition root; no database or AI key required for M1."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException

from app import __version__
from app.api.product import AuthLimiter
from app.api.product import router as product_router
from app.api.routes import router
from app.config import Settings
from app.database import Base, make_engine
from app.middleware import BodyLimitMiddleware
from app.models import BoardRecord
from app.schemas.validation import ValidationIssue, ValidationResult
from app.services.breadboard import reference_board
from app.services.detection import LocalYOLODetector
from app.services.storage import LocalObjectStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        if settings.auto_create_schema:
            Base.metadata.create_all(engine)
        application.state.settings = settings
        application.state.sessions = sessionmaker(engine, expire_on_commit=False)
        application.state.store = LocalObjectStore(settings.storage_dir)
        application.state.auth_limiter = AuthLimiter()
        application.state.detector = (
            LocalYOLODetector(settings.detector_model_dir) if settings.detector_model_dir else None
        )
        with application.state.sessions() as db:
            board = reference_board()
            identity = f"{board.model_id}:{board.revision}"
            existing = db.get(BoardRecord, identity)
            if existing is None:
                db.add(
                    BoardRecord(
                        id=identity,
                        model_id=board.model_id,
                        revision=board.revision,
                        geometry_json=board.model_dump(mode="json"),
                    )
                )
                db.commit()
            elif existing.geometry_json != board.model_dump(mode="json"):
                raise RuntimeError("Board model changed without a revision increment.")
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="CircuitPilot",
        version=__version__,
        description="Circuit planning, guided reference assembly, and uncertain photo overlays.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.add_middleware(BodyLimitMiddleware, upload_limit=settings.max_upload_bytes)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo circuit inputs or arbitrary Pydantic exception context.
        result = ValidationResult(
            valid=False,
            errors=[
                ValidationIssue(
                    code=f"schema.{error['type']}",
                    message=error["msg"],
                    path=list(error["loc"]),
                )
                for error in exc.errors()
            ],
        )
        return JSONResponse(status_code=422, content=result.model_dump(mode="json"))

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {
                "code": {
                    401: "unauthorized",
                    403: "forbidden",
                    404: "not_found",
                    409: "conflict",
                    422: "invalid_request",
                    429: "rate_limited",
                }.get(exc.status_code, "request_error"),
                "message": str(exc.detail),
            }
        )
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    application.include_router(router)
    application.include_router(product_router)
    return application


app = create_app()
