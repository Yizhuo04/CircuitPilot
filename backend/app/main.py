"""FastAPI composition root; no database or AI key required for M1."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.schemas.validation import ValidationIssue, ValidationResult


def create_app() -> FastAPI:
    application = FastAPI(
        title="CircuitPilot",
        version=__version__,
        description=(
            "M1 structural netlist validation. No physical assembly or safety verification."
        ),
    )

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

    application.include_router(router)
    return application


app = create_app()
