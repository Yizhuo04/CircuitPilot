"""Versioned API routes."""

from fastapi import APIRouter, Response

from app import __version__
from app.schemas.circuit import Circuit
from app.schemas.common import Contract
from app.schemas.validation import ValidationResult
from app.services.circuit_engine import validate_circuit

router = APIRouter(prefix="/api/v1")


class Health(Contract):
    status: str
    version: str


@router.get("/health", response_model=Health, tags=["system"])
def health() -> Health:
    return Health(status="ok", version=__version__)


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
