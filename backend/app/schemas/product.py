"""Product API request contracts; all stored resource access is owner-scoped."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import EmailStr, Field, model_validator

from app.schemas.common import Contract
from app.schemas.layout import AssemblyPlan


class Credentials(Contract):
    email: EmailStr
    password: Annotated[str, Field(min_length=12, max_length=128)]


class UserPublic(Contract):
    id: str
    email: str


class AuthResponse(Contract):
    user: UserPublic
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class ProjectCreate(Contract):
    name: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]


class ProjectPublic(Contract):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class PlanRequest(Contract):
    circuit_version_id: str
    board_model_id: Literal["bb830-reference"] = "bb830-reference"
    board_revision: Literal["r1"] = "r1"
    seed: Annotated[int, Field(ge=0, le=2**31 - 1)] = 0


class PlanPublic(Contract):
    id: str
    circuit_version_id: str
    created_at: datetime
    plan: AssemblyPlan


class UploadRequest(Contract):
    project_id: str
    consent_for_training: bool = False


class TrainingConsent(Contract):
    consent_for_training: bool


class ImagePublic(Contract):
    id: str
    project_id: str
    width: int
    height: int
    consent_for_training: bool
    captured_at: datetime
    expires_at: datetime


class CalibrationPoint(Contract):
    hole_id: str
    x: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class VerificationRequest(Contract):
    plan_id: str
    image_id: str
    calibration_points: Annotated[list[CalibrationPoint], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def distinct_points(self) -> "VerificationRequest":
        if len({point.hole_id for point in self.calibration_points}) != 4:
            raise ValueError("Choose four distinct reference holes in matching order.")
        return self


class AnnotationBox(Contract):
    class_name: Literal["resistor", "led", "push_button", "wire_endpoint", "board_outline"]
    x: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    width: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    height: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class AnnotationRequest(Contract):
    setup_id: Annotated[str, Field(min_length=1, max_length=100)]
    capture_session_id: Annotated[str, Field(min_length=1, max_length=100)]
    boxes: Annotated[list[AnnotationBox], Field(max_length=100)]
    review_status: Literal["draft", "reviewed"] = "draft"


class PilotStart(Contract):
    project_id: str
    condition: Literal["control", "guided"]


class PilotFinish(Contract):
    error_count: Annotated[int, Field(ge=0, le=1000)]
    help_count: Annotated[int, Field(ge=0, le=1000)]
    notes: Annotated[str, Field(max_length=2000)] = ""


class AssistantRequest(Contract):
    plan_id: str
    step_sequence: Annotated[int, Field(ge=1)]
