"""Durable verification jobs with atomic claims and recoverable leases.

FastAPI schedules jobs after responding; a separate `python -m app.worker` process
recovers pending/interrupted work. No electrical claims or trained detections.
"""

import argparse
import logging
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import make_engine
from app.models import ImageRecord, PlanRecord, UploadTicket, VerificationRun, now
from app.schemas.layout import AssemblyPlan
from app.schemas.product import VerificationRequest
from app.services.breadboard import Breadboard, reference_board
from app.services.calibration import CalibrationError, calibrate
from app.services.detection import Detector, LocalYOLODetector, compare_observations
from app.services.storage import LocalObjectStore

logger = logging.getLogger(__name__)


def worker_healthy(directory: Path) -> bool:
    try:
        age = time.time() - (directory / ".worker-heartbeat").stat().st_mtime
        return 0 <= age < 120
    except FileNotFoundError:
        return False


def process_job(
    run_id: str,
    sessions: sessionmaker[Session],
    store: LocalObjectStore | None = None,
    detector: Detector | None = None,
) -> None:
    with sessions() as db:
        claimed = cast(
            CursorResult[Any],
            db.execute(
                update(VerificationRun)
                .where(VerificationRun.id == run_id, VerificationRun.status == "pending")
                .values(status="running", started_at=now())
            ),
        )
        db.commit()
        if claimed.rowcount != 1:
            return
        run = db.get(VerificationRun, run_id)
        if run is None:
            return
        try:
            image = db.get(ImageRecord, run.image_id)
            plan = db.get(PlanRecord, run.plan_id)
            if image is None or plan is None or image.expires_at <= now():
                raise CalibrationError("Source image or plan is unavailable or expired.")
            payload = VerificationRequest.model_validate(run.request_json)
            result = calibrate(
                Breadboard(reference_board()),
                payload.calibration_points,
                image.width,
                image.height,
                AssemblyPlan.model_validate(plan.plan_json),
            )
            if detector is not None and store is not None:
                observations = compare_observations(
                    AssemblyPlan.model_validate(plan.plan_json),
                    result,
                    detector.predict(store.path(image.storage_key)),
                )
                result["observations"] = observations
                result["component_detection_available"] = True
                result["model_version"] = detector.version
                run.model_version = detector.version
                result["uncertainties"] = [
                    (
                        "Detector scores are not calibrated probabilities; absence "
                        "may mean occlusion or a missed detection."
                    ),
                    "Calibration and terminal localization require your confirmation.",
                    "Photos cannot establish electrical continuity or safe current.",
                ]
            run.results_json = result
            run.status = "needs_confirmation"
        except (ValueError, KeyError) as exc:
            run.status = "failed"
            run.results_json = {"error": str(exc), "electrically_verified": False}
        except Exception:
            logger.exception("Verification job failed: %s", run_id)
            run.status = "failed"
            run.results_json = {
                "error": "Image analysis failed. Please retry or recalibrate.",
                "electrically_verified": False,
            }
        db.commit()


def maintenance(sessions: sessionmaker[Session], store: LocalObjectStore) -> list[str]:
    with sessions() as db:
        # Jobs interrupted for more than 30 minutes are eligible for another worker.
        db.execute(
            update(VerificationRun)
            .where(
                VerificationRun.status == "running",
                VerificationRun.started_at < now() - timedelta(minutes=30),
            )
            .values(status="pending", started_at=None)
        )
        expired = list(db.scalars(select(ImageRecord).where(ImageRecord.expires_at <= now())))
        keys = [image.storage_key for image in expired]
        for image in expired:
            db.delete(image)
        db.execute(delete(UploadTicket).where(UploadTicket.expires_at <= now()))
        db.commit()
        for key in keys:
            store.delete(key)
        return list(
            db.scalars(
                select(VerificationRun.id)
                .where(VerificationRun.status == "pending")
                .order_by(VerificationRun.created_at)
                .limit(100)
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument(
        "--healthcheck", action="store_true", help="Check the worker loop heartbeat"
    )
    args = parser.parse_args()
    settings = Settings()
    if args.healthcheck:
        parser.exit(0 if worker_healthy(settings.storage_dir) else 1)
    engine = make_engine(settings.database_url)
    sessions = sessionmaker(engine, expire_on_commit=False)
    store = LocalObjectStore(settings.storage_dir)
    detector = (
        LocalYOLODetector(settings.detector_model_dir) if settings.detector_model_dir else None
    )
    try:
        while True:
            pending = maintenance(sessions, store)
            (store.root / ".worker-heartbeat").touch()
            for run_id in pending:
                (store.root / ".worker-heartbeat").touch()
                process_job(run_id, sessions, store, detector)
            if args.once:
                break
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
