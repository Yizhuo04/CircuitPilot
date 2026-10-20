"""Authenticated product workflow, immutable versions, and bounded photo uploads."""

import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from importlib.resources import files
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.exc import IntegrityError

from app.models import (
    Annotation,
    CircuitVersion,
    ImageRecord,
    LoginSession,
    PilotSession,
    PlanRecord,
    Project,
    StepRecord,
    UploadTicket,
    User,
    VerificationRun,
    now,
)
from app.schemas.circuit import Circuit
from app.schemas.layout import AssemblyPlan
from app.schemas.product import (
    AnnotationRequest,
    AssistantRequest,
    AuthResponse,
    Credentials,
    ImagePublic,
    PilotFinish,
    PilotStart,
    PlanPublic,
    PlanRequest,
    ProjectCreate,
    ProjectPublic,
    UploadRequest,
    UserPublic,
    VerificationRequest,
)
from app.security import DB, CurrentUser, hash_password, new_session, token_hash, verify_password
from app.services.breadboard import Breadboard, reference_board
from app.services.circuit_engine import validate_circuit
from app.services.connectivity import circuit_digest, validate_layout
from app.services.placement_engine import PlanningError, generate_plan
from app.services.storage import InvalidImage, LocalObjectStore

router = APIRouter(prefix="/api/v1")
_dummy_password = hash_password("not-a-real-user-password")


class AuthLimiter:
    """Process-local guard; deployments must also enforce reverse-proxy rate limits."""

    def __init__(self) -> None:
        self.entries: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> None:
        current = time.monotonic()
        with self.lock:
            if len(self.entries) > 10000:
                self.entries = defaultdict(
                    deque, {k: v for k, v in self.entries.items() if v and current - v[-1] < 60}
                )
            queue = self.entries[key]
            while queue and current - queue[0] >= 60:
                queue.popleft()
            if len(queue) >= 10:
                raise HTTPException(429, "Too many authentication attempts. Try again in a minute.")
            queue.append(current)


def owned_project(db: DB, project_id: str, user_id: str) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == user_id)
    )
    if project is None:
        raise HTTPException(404, "Project not found.")
    return project


def owned_circuit(db: DB, circuit_id: str, user_id: str) -> CircuitVersion:
    circuit = db.scalar(
        select(CircuitVersion)
        .join(Project)
        .where(CircuitVersion.id == circuit_id, Project.owner_id == user_id)
    )
    if circuit is None:
        raise HTTPException(404, "Circuit version not found.")
    return circuit


def owned_plan(db: DB, plan_id: str, user_id: str) -> PlanRecord:
    plan = db.scalar(
        select(PlanRecord)
        .join(CircuitVersion)
        .join(Project)
        .where(PlanRecord.id == plan_id, Project.owner_id == user_id)
    )
    if plan is None:
        raise HTTPException(404, "Plan not found.")
    return plan


def owned_image(db: DB, image_id: str, user_id: str) -> ImageRecord:
    image = db.scalar(
        select(ImageRecord)
        .join(Project)
        .where(ImageRecord.id == image_id, Project.owner_id == user_id)
    )
    if image is None or image.expires_at <= now():
        raise HTTPException(404, "Image not found or retention period expired.")
    return image


def public_image(image: ImageRecord) -> ImagePublic:
    return ImagePublic(
        id=image.id,
        project_id=image.project_id,
        width=image.width,
        height=image.height,
        consent_for_training=image.consent_for_training,
        captured_at=image.captured_at,
        expires_at=image.expires_at,
    )


def public_project(project: Project) -> ProjectPublic:
    return ProjectPublic(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def public_plan(plan: PlanRecord) -> PlanPublic:
    return PlanPublic(
        id=plan.id,
        circuit_version_id=plan.circuit_version_id,
        created_at=plan.created_at,
        plan=AssemblyPlan.model_validate(plan.plan_json),
    )


def _auth_response(db: DB, user: User, request: Request, response: Response) -> AuthResponse:
    settings = request.app.state.settings
    token = new_session(db, user, settings.session_hours)
    db.commit()
    response.set_cookie(
        "circuitpilot_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(user=UserPublic(id=user.id, email=user.email), access_token=token)


@router.post("/auth/register", response_model=AuthResponse, status_code=201, tags=["accounts"])
def register(payload: Credentials, request: Request, response: Response, db: DB) -> AuthResponse:
    request.app.state.auth_limiter.check(request.client.host if request.client else "unknown")
    user = User(email=str(payload.email).casefold(), password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with that email already exists.") from None
    return _auth_response(db, user, request, response)


@router.post("/auth/login", response_model=AuthResponse, tags=["accounts"])
def login(payload: Credentials, request: Request, response: Response, db: DB) -> AuthResponse:
    request.app.state.auth_limiter.check(request.client.host if request.client else "unknown")
    user = db.scalar(select(User).where(User.email == str(payload.email).casefold()))
    if (
        not verify_password(payload.password, user.password_hash if user else _dummy_password)
        or user is None
    ):
        raise HTTPException(401, "Email or password is incorrect.")
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now()))
    return _auth_response(db, user, request, response)


@router.get("/auth/me", response_model=UserPublic, tags=["accounts"])
def me(user: CurrentUser) -> UserPublic:
    return UserPublic(id=user.id, email=user.email)


@router.post("/auth/logout", status_code=204, tags=["accounts"])
def logout(request: Request, response: Response, db: DB, user: CurrentUser) -> None:
    token = request.headers.get("authorization", "").removeprefix("Bearer ") or request.cookies.get(
        "circuitpilot_session", ""
    )
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(token)))
    db.commit()
    response.delete_cookie("circuitpilot_session", path="/")


@router.get("/board-models", tags=["boards"])
def board_models() -> list[dict[str, object]]:
    board = reference_board()
    return [
        {
            "model_id": board.model_id,
            "revision": board.revision,
            "verification_status": board.verification_status,
            "hole_count": len(board.holes),
        }
    ]


@router.get("/board-models/{model_id}", tags=["boards"])
def board_model(model_id: str, revision: str = "r1") -> dict[str, Any]:
    board = reference_board()
    if (model_id, revision) != (board.model_id, board.revision):
        raise HTTPException(404, "Board revision not found.")
    return board.model_dump(mode="json")


@router.get("/circuit-library", tags=["circuits"])
def circuit_library() -> list[dict[str, Any]]:
    directory = files("app").joinpath("data/circuits")
    return [
        Circuit.model_validate_json(file.read_text()).model_dump(mode="json")
        for file in sorted(directory.iterdir(), key=lambda p: p.name)
        if file.name.endswith(".json")
    ]


@router.post("/projects", response_model=ProjectPublic, status_code=201, tags=["projects"])
def create_project(payload: ProjectCreate, db: DB, user: CurrentUser) -> ProjectPublic:
    project = Project(owner_id=user.id, name=payload.name.strip())
    db.add(project)
    db.commit()
    return public_project(project)


@router.get("/projects", response_model=list[ProjectPublic], tags=["projects"])
def projects(db: DB, user: CurrentUser) -> list[ProjectPublic]:
    return [
        public_project(p)
        for p in db.scalars(
            select(Project)
            .where(Project.owner_id == user.id)
            .order_by(Project.updated_at.desc())
            .limit(200)
        )
    ]


@router.get("/projects/{project_id}", tags=["projects"])
def project_detail(project_id: str, db: DB, user: CurrentUser) -> dict[str, Any]:
    project = owned_project(db, project_id, user.id)
    circuits = list(
        db.scalars(
            select(CircuitVersion)
            .where(CircuitVersion.project_id == project.id)
            .order_by(CircuitVersion.created_at.desc())
        )
    )
    plans = list(
        db.scalars(
            select(PlanRecord)
            .join(CircuitVersion)
            .where(CircuitVersion.project_id == project.id)
            .order_by(PlanRecord.created_at.desc())
        )
    )
    images = db.scalars(
        select(ImageRecord).where(
            ImageRecord.project_id == project.id, ImageRecord.expires_at > now()
        )
    )
    return {
        **public_project(project).model_dump(mode="json"),
        "circuits": [
            {
                "id": c.id,
                "digest": c.digest,
                "circuit": c.netlist_json,
                "created_at": c.created_at.isoformat() + "Z",
            }
            for c in circuits
        ],
        "plans": [
            {
                "id": p.id,
                "circuit_version_id": p.circuit_version_id,
                "created_at": p.created_at.isoformat() + "Z",
            }
            for p in plans
        ],
        "images": [public_image(image).model_dump(mode="json") for image in images],
    }


@router.post("/projects/{project_id}/circuits", status_code=201, tags=["circuits"])
def import_circuit(project_id: str, circuit: Circuit, db: DB, user: CurrentUser) -> Any:
    project = owned_project(db, project_id, user.id)
    report = validate_circuit(circuit)
    if not report.valid:
        return JSONResponse(status_code=422, content=report.model_dump(mode="json"))
    version = CircuitVersion(
        project_id=project.id,
        digest=circuit_digest(circuit),
        schema_version=circuit.schema_version,
        netlist_json=circuit.model_dump(mode="json"),
    )
    project.updated_at = now()
    db.add(version)
    db.commit()
    return {
        "id": version.id,
        "project_id": project.id,
        "digest": version.digest,
        "circuit": version.netlist_json,
        "validation": report.model_dump(mode="json"),
    }


@router.post("/plans", response_model=PlanPublic, status_code=201, tags=["plans"])
def create_plan(payload: PlanRequest, db: DB, user: CurrentUser) -> PlanPublic:
    version = owned_circuit(db, payload.circuit_version_id, user.id)
    circuit = Circuit.model_validate(version.netlist_json)
    try:
        plan = generate_plan(circuit, Breadboard(reference_board()), payload.seed)
    except PlanningError as exc:
        raise HTTPException(422, {"code": exc.code, "message": str(exc)}) from exc
    record = PlanRecord(
        circuit_version_id=version.id,
        board_model_id=plan.layout.board_model_id,
        board_revision=plan.layout.board_revision,
        planner_version=plan.layout.planner_version,
        plan_json=plan.model_dump(mode="json"),
    )
    db.add(record)
    db.flush()
    db.add_all(
        [
            StepRecord(
                plan_id=record.id,
                sequence=step.sequence,
                instruction_json=step.model_dump(mode="json"),
            )
            for step in plan.steps
        ]
    )
    db.commit()
    return public_plan(record)


@router.get("/plans/{plan_id}", response_model=PlanPublic, tags=["plans"])
def plan_detail(plan_id: str, db: DB, user: CurrentUser) -> PlanPublic:
    return public_plan(owned_plan(db, plan_id, user.id))


@router.get("/plans/{plan_id}/steps", tags=["plans"])
def plan_steps(plan_id: str, db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    plan = owned_plan(db, plan_id, user.id)
    return [
        step.instruction_json
        for step in db.scalars(
            select(StepRecord).where(StepRecord.plan_id == plan.id).order_by(StepRecord.sequence)
        )
    ]


@router.post("/images/uploads", status_code=201, tags=["photos"])
def upload_ticket(
    payload: UploadRequest, request: Request, db: DB, user: CurrentUser
) -> dict[str, Any]:
    project = owned_project(db, payload.project_id, user.id)
    token = secrets.token_urlsafe(32)
    db.add(
        UploadTicket(
            token_hash=token_hash(token),
            project_id=project.id,
            consent_for_training=payload.consent_for_training,
            expires_at=now() + timedelta(minutes=10),
        )
    )
    db.commit()
    return {
        "upload_url": f"/api/v1/images/uploads/{token}",
        "method": "PUT",
        "expires_in_seconds": 600,
        "max_bytes": request.app.state.settings.max_upload_bytes,
    }


@router.put("/images/uploads/{token}", response_model=ImagePublic, status_code=201, tags=["photos"])
async def upload_image(token: str, request: Request, db: DB, user: CurrentUser) -> ImagePublic:
    ticket = db.get(UploadTicket, token_hash(token))
    if ticket is None or ticket.expires_at <= now() or ticket.consumed:
        raise HTTPException(404, "Upload ticket not found, expired, or already used.")
    owned_project(db, ticket.project_id, user.id)
    claimed = cast(
        CursorResult[Any],
        db.execute(
            update(UploadTicket)
            .where(UploadTicket.token_hash == ticket.token_hash, UploadTicket.consumed.is_(False))
            .values(consumed=True)
        ),
    )
    if claimed.rowcount != 1:
        raise HTTPException(409, "Upload ticket was already consumed.")
    data = await request.body()
    store: LocalObjectStore = request.app.state.store
    key = uuid4().hex + ".png"
    try:
        digest, width, height = store.save_image(
            key, data, request.app.state.settings.max_upload_bytes
        )
    except InvalidImage as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    image = ImageRecord(
        project_id=ticket.project_id,
        storage_key=key,
        sha256=digest,
        width=width,
        height=height,
        consent_for_training=ticket.consent_for_training,
        expires_at=now() + timedelta(days=request.app.state.settings.photo_retention_days),
    )
    db.add(image)
    try:
        db.commit()
    except Exception:
        db.rollback()
        store.delete(key)
        raise
    return public_image(image)


@router.get("/images/{image_id}/content", tags=["photos"])
def image_content(image_id: str, request: Request, db: DB, user: CurrentUser) -> FileResponse:
    image = owned_image(db, image_id, user.id)
    return FileResponse(
        request.app.state.store.path(image.storage_key),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/images/{image_id}", status_code=204, tags=["photos"])
def delete_image(image_id: str, request: Request, db: DB, user: CurrentUser) -> None:
    image = owned_image(db, image_id, user.id)
    key = image.storage_key
    db.delete(image)
    db.commit()
    request.app.state.store.delete(key)


@router.post("/verification-runs", status_code=202, tags=["verification"])
def verification(
    payload: VerificationRequest,
    request: Request,
    background: BackgroundTasks,
    db: DB,
    user: CurrentUser,
) -> dict[str, str]:
    plan = owned_plan(db, payload.plan_id, user.id)
    version = owned_circuit(db, plan.circuit_version_id, user.id)
    image = owned_image(db, payload.image_id, user.id)
    if image.project_id != version.project_id:
        raise HTTPException(409, "Image and plan belong to different projects.")
    run = VerificationRun(
        plan_id=plan.id, image_id=image.id, request_json=payload.model_dump(mode="json")
    )
    db.add(run)
    db.commit()
    from app.worker import process_job

    background.add_task(
        process_job,
        run.id,
        request.app.state.sessions,
        request.app.state.store,
        request.app.state.detector,
    )
    return {"id": run.id, "status": "pending"}


@router.get("/verification-runs/{run_id}", tags=["verification"])
def verification_detail(run_id: str, db: DB, user: CurrentUser) -> dict[str, Any]:
    run = db.get(VerificationRun, run_id)
    if run is None:
        raise HTTPException(404, "Verification run not found.")
    owned_plan(db, run.plan_id, user.id)
    owned_image(db, run.image_id, user.id)
    return {
        "id": run.id,
        "status": run.status,
        "electrically_verified": False,
        "model_version": run.model_version,
        "results": run.results_json,
    }


@router.post("/images/{image_id}/annotations", status_code=201, tags=["datasets"])
def annotate(
    image_id: str, payload: AnnotationRequest, db: DB, user: CurrentUser
) -> dict[str, str]:
    image = owned_image(db, image_id, user.id)
    if any(
        box.x + box.width > image.width or box.y + box.height > image.height
        for box in payload.boxes
    ):
        raise HTTPException(422, "Annotation boxes must be contained in the image.")
    annotation = Annotation(
        image_id=image.id,
        labels_json=payload.model_dump(mode="json"),
        review_status=payload.review_status,
    )
    db.add(annotation)
    db.commit()
    return {"id": annotation.id, "review_status": annotation.review_status}


@router.get("/datasets/export", tags=["datasets"])
def dataset_export(db: DB, user: CurrentUser) -> dict[str, Any]:
    rows = db.execute(
        select(Annotation, ImageRecord)
        .join(ImageRecord)
        .join(Project)
        .where(
            Project.owner_id == user.id,
            ImageRecord.consent_for_training.is_(True),
            ImageRecord.expires_at > now(),
            Annotation.review_status == "reviewed",
        )
        .order_by(Annotation.created_at.desc())
    ).all()
    seen: set[str] = set()
    images = []
    for annotation, image in rows:
        if image.id in seen:
            continue
        seen.add(image.id)
        images.append(
            {
                "image_id": image.id,
                "sha256": image.sha256,
                "width": image.width,
                "height": image.height,
                "consent_for_training": True,
                "content_url": f"/api/v1/images/{image.id}/content",
                **annotation.labels_json,
            }
        )
    return {
        "schema_version": "1.0",
        "images": images,
        "note": (
            "Only your consented, reviewed, unexpired photos are "
            "included. Download each content_url using your "
            "authenticated session."
        ),
    }


@router.post("/assistant/messages", tags=["assistant"])
def explain_step(payload: AssistantRequest, db: DB, user: CurrentUser) -> dict[str, Any]:
    record = owned_plan(db, payload.plan_id, user.id)
    version = owned_circuit(db, record.circuit_version_id, user.id)
    plan = AssemblyPlan.model_validate(record.plan_json)
    report = validate_layout(
        Circuit.model_validate(version.netlist_json), plan.layout, Breadboard(reference_board())
    )
    if not report.valid:
        raise HTTPException(409, "Stored layout no longer passes validation.")
    step = next((s for s in plan.steps if s.sequence == payload.step_sequence), None)
    if step is None:
        raise HTTPException(404, "Assembly step not found.")
    return {
        "mode": "deterministic_validated_explanation",
        "llm_used": False,
        "message": step.instruction,
        "holes": step.holes,
        "validation": report.model_dump(mode="json"),
    }


@router.post("/pilot-sessions", status_code=201, tags=["pilot"])
def start_pilot(payload: PilotStart, db: DB, user: CurrentUser) -> dict[str, str]:
    project = owned_project(db, payload.project_id, user.id)
    pilot = PilotSession(project_id=project.id, condition=payload.condition)
    db.add(pilot)
    db.commit()
    return {
        "id": pilot.id,
        "started_at": pilot.started_at.isoformat() + "Z",
        "condition": pilot.condition,
    }


@router.post("/pilot-sessions/{pilot_id}/complete", tags=["pilot"])
def finish_pilot(pilot_id: str, payload: PilotFinish, db: DB, user: CurrentUser) -> dict[str, Any]:
    pilot = db.get(PilotSession, pilot_id)
    if pilot is None:
        raise HTTPException(404, "Pilot session not found.")
    owned_project(db, pilot.project_id, user.id)
    if pilot.completed_at is not None:
        raise HTTPException(409, "Pilot session is already complete.")
    pilot.completed_at = now()
    pilot.error_count, pilot.help_count, pilot.notes = (
        payload.error_count,
        payload.help_count,
        payload.notes,
    )
    db.commit()
    return {
        "id": pilot.id,
        "duration_seconds": (pilot.completed_at - pilot.started_at).total_seconds(),
        "error_count": pilot.error_count,
        "help_count": pilot.help_count,
    }


@router.get("/pilot-sessions", tags=["pilot"])
def pilot_results(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "condition": p.condition,
            "project_id": p.project_id,
            "duration_seconds": (p.completed_at - p.started_at).total_seconds()
            if p.completed_at
            else None,
            "error_count": p.error_count,
            "help_count": p.help_count,
            "notes": p.notes,
        }
        for p in db.scalars(select(PilotSession).join(Project).where(Project.owner_id == user.id))
    ]


@router.get("/projects/{project_id}/export", tags=["privacy"])
def export_project(project_id: str, db: DB, user: CurrentUser) -> dict[str, Any]:
    detail = project_detail(project_id, db, user)
    detail["plan_contents"] = [
        public_plan(p).model_dump(mode="json")
        for p in db.scalars(
            select(PlanRecord).join(CircuitVersion).where(CircuitVersion.project_id == project_id)
        )
    ]
    detail["photo_downloads"] = [
        f"/api/v1/images/{image['id']}/content" for image in detail["images"]
    ]
    return detail


@router.delete("/projects/{project_id}", status_code=204, tags=["privacy"])
def delete_project(project_id: str, request: Request, db: DB, user: CurrentUser) -> None:
    project = owned_project(db, project_id, user.id)
    keys = list(
        db.scalars(select(ImageRecord.storage_key).where(ImageRecord.project_id == project.id))
    )
    db.delete(project)
    db.commit()
    for key in keys:
        request.app.state.store.delete(key)


@router.delete("/auth/account", status_code=204, tags=["privacy"])
def delete_account(request: Request, response: Response, db: DB, user: CurrentUser) -> None:
    keys = list(
        db.scalars(select(ImageRecord.storage_key).join(Project).where(Project.owner_id == user.id))
    )
    db.delete(user)
    db.commit()
    for key in keys:
        request.app.state.store.delete(key)
    response.delete_cookie("circuitpilot_session", path="/")
