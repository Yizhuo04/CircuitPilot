"""Manual homography and uncertainty-aware overlays; no learned detection claims."""

import cv2
import numpy as np

from app.schemas.layout import AssemblyPlan
from app.schemas.product import CalibrationPoint
from app.services.breadboard import Breadboard


class CalibrationError(ValueError):
    pass


def calibrate(
    board: Breadboard,
    points: list[CalibrationPoint],
    width: int,
    height: int,
    plan: AssemblyPlan,
) -> dict[str, object]:
    source = np.array(
        [
            [board.get_hole(point.hole_id).position.x, board.get_hole(point.hole_id).position.y]
            for point in points
        ],
        dtype=np.float32,
    )
    target = np.array([[point.x, point.y] for point in points], dtype=np.float32)
    if (
        len(points) != 4
        or np.any(target < 0)
        or np.any(target[:, 0] >= width)
        or np.any(target[:, 1] >= height)
    ):
        raise CalibrationError("Four reference points must be inside the image.")
    if not cv2.isContourConvex(source) or not cv2.isContourConvex(target):
        raise CalibrationError(
            "Reference points must form matching convex quadrilaterals in perimeter order."
        )
    source_area = cv2.contourArea(source, oriented=True)
    target_area = cv2.contourArea(target, oriented=True)
    if abs(source_area) < 1 or abs(target_area) < 100 or source_area * target_area <= 0:
        raise CalibrationError("Calibration points are collinear, mirrored, or too close together.")
    lengths = np.linalg.norm(target - np.roll(target, -1, axis=0), axis=1)
    if (
        max(
            lengths[0] / lengths[2],
            lengths[2] / lengths[0],
            lengths[1] / lengths[3],
            lengths[3] / lengths[1],
        )
        > 10
    ):
        raise CalibrationError("Perspective is too extreme; use a near-top-down image.")
    matrix = cv2.getPerspectiveTransform(source, target)
    if not np.isfinite(matrix).all() or np.linalg.cond(matrix) > 1e8:
        raise CalibrationError(
            "Calibration is numerically unstable; choose better-separated points."
        )
    coordinates = np.array(
        [[hole.position.x, hole.position.y] for hole in board.model.holes], dtype=np.float32
    ).reshape(-1, 1, 2)
    mapped = cv2.perspectiveTransform(coordinates, matrix).reshape(-1, 2)
    if not np.isfinite(mapped).all():
        raise CalibrationError("Projection crosses a singularity; recheck reference points.")
    holes = {
        hole.id: {"x": round(float(mapped[index, 0]), 2), "y": round(float(mapped[index, 1]), 2)}
        for index, hole in enumerate(board.model.holes)
    }
    return {
        "status": "needs_confirmation",
        "electrically_verified": False,
        "method": "manual_homography",
        "model_version": "manual-homography-1",
        "homography": matrix.tolist(),
        "holes": holes,
        "observations": [],
        "component_detection_available": False,
        "overlay": {
            "components": [
                {
                    "component_id": component.component_id,
                    "pins": {pin: holes[hole] for pin, hole in component.pins.items()},
                }
                for component in plan.layout.components
            ],
            "jumpers": [
                {
                    "id": wire.id,
                    "start": holes[wire.start],
                    "end": holes[wire.end],
                    "color": wire.color,
                }
                for wire in plan.layout.jumpers
            ],
        },
        "uncertainties": [
            (
                "Calibration depends on the reference holes you selected; "
                "confirm the overlay alignment."
            ),
            (
                "No trained component detector is loaded. No physical "
                "placement has been observed or verified."
            ),
            (
                "Photos cannot establish electrical continuity, hidden "
                "connections, or safe operating current."
            ),
        ],
    }
