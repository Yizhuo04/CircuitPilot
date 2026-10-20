"""Versioned API routes."""

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.schemas.circuit import Circuit
from app.schemas.common import Contract
from app.schemas.validation import ValidationResult
from app.services.circuit_engine import validate_circuit
from app.worker import worker_healthy

router = APIRouter(prefix="/api/v1")


class Health(Contract):
    status: str
    version: str


@router.get("/health", response_model=Health, tags=["system"])
def health() -> Health:
    return Health(status="ok", version=__version__)


@router.get("/health/ready", response_model=Health, tags=["system"])
def ready(request: Request, response: Response) -> Health:
    """Readiness covers persistence and, for hosted deployments, the worker loop."""
    settings = request.app.state.settings
    try:
        with request.app.state.sessions() as db:
            db.execute(text("SELECT 1"))
        available = not settings.require_worker_health or worker_healthy(settings.storage_dir)
    except SQLAlchemyError:
        available = False
    if not available:
        response.status_code = 503
    return Health(status="ok" if available else "unavailable", version=__version__)


@router.post(
    "/circuits/validate",
    response_model=ValidationResult,
    responses={422: {"model": ValidationResult, "description": "Invalid schema or netlist"}},
    tags=["circuits"],
)
def validate(circuit: Circuit, response: Response) -> ValidationResult:
    result = validate_circuit(circuit)
    if not result.valid:
        response.status_code = 422
    return result
