"""
anpr_pipeline.py

Runs the two-stage YOLO detection + OCR pipeline.
Stage 1: Detect vehicle (car/truck) in frame.
Stage 2: Detect and crop number plate within vehicle ROI.
Stage 3: OCR on cropped plate.

Runs as an async background task. Pushes results to a queue
that the WebSocket endpoint reads from.
"""

import asyncio
import logging
import time
import cv2
from ultralytics import YOLO

from stream_ingest import stream
from database import log_plate

logger = logging.getLogger(__name__)

# --- Config ---
VEHICLE_MODEL_PATH = "models/vehicle_detect.pt"
PLATE_MODEL_PATH = "models/plate_crop.pt"
VEHICLE_CONFIDENCE = 0.5
PLATE_CONFIDENCE = 0.5
DETECTION_INTERVAL = 0.5  # seconds between detection runs

# Shared result — latest detection result for WebSocket to read
latest_result = {
    "plate": None,
    "confidence": None,
    "bbox": None,
    "timestamp": None,
}

# Queue for pushing results to WebSocket clients
result_queue: asyncio.Queue = None


def init_queue(q: asyncio.Queue):
    global result_queue
    result_queue = q


async def run_pipeline():
    """
    Main async loop. Loads YOLO models once, then runs
    detection on the freshest frame every DETECTION_INTERVAL seconds.
    """
    logger.info("[ANPR] Loading YOLO models...")

    try:
        vehicle_model = YOLO(VEHICLE_MODEL_PATH)
        plate_model = YOLO(PLATE_MODEL_PATH)
        logger.info("[ANPR] Models loaded.")
    except Exception as e:
        logger.error(f"[ANPR] Failed to load models: {e}")
        logger.warning("[ANPR] Pipeline running in NO-MODEL mode (stream only).")
        vehicle_model = None
        plate_model = None

    while True:
        await asyncio.sleep(DETECTION_INTERVAL)

        if not stream.is_connected:
            continue

        frame = stream.get_frame()
        if frame is None:
            continue

        if vehicle_model is None or plate_model is None:
            # Models not loaded yet — skip detection, stream still works
            continue

        try:
            plate_text, confidence, bbox = await asyncio.get_event_loop().run_in_executor(
                None, detect_plate, frame, vehicle_model, plate_model
            )

            if plate_text:
                result = {
                    "plate": plate_text,
                    "confidence": round(confidence, 2),
                    "bbox": bbox,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                latest_result.update(result)
                await log_plate(plate_text, confidence)

                if result_queue:
                    await result_queue.put(result)
                    logger.info(f"[ANPR] Detected: {plate_text} ({confidence:.2f})")

        except Exception as e:
            logger.error(f"[ANPR] Detection error: {e}")


def detect_plate(frame, vehicle_model, plate_model):
    """
    Synchronous detection function (runs in thread executor).
    Returns (plate_text, confidence, bbox) or (None, None, None).
    """
    # Stage 1: Vehicle detection
    vehicle_results = vehicle_model(frame, conf=VEHICLE_CONFIDENCE, verbose=False)
    vehicles = [
        box for r in vehicle_results
        for box in r.boxes
        if int(box.cls[0]) in [2, 7]  # COCO: 2=car, 7=truck
    ]

    if not vehicles:
        return None, None, None

    # Use the highest-confidence vehicle detection
    best_vehicle = max(vehicles, key=lambda b: float(b.conf[0]))
    x1, y1, x2, y2 = map(int, best_vehicle.xyxy[0])
    vehicle_roi = frame[y1:y2, x1:x2]

    # Stage 2: Plate detection within vehicle ROI
    plate_results = plate_model(vehicle_roi, conf=PLATE_CONFIDENCE, verbose=False)
    plates = [
        box for r in plate_results for box in r.boxes
    ]

    if not plates:
        return None, None, None

    best_plate = max(plates, key=lambda b: float(b.conf[0]))
    px1, py1, px2, py2 = map(int, best_plate.xyxy[0])
    plate_crop = vehicle_roi[py1:py2, px1:px2]

    # Stage 3: OCR
    plate_text = run_ocr(plate_crop)
    confidence = float(best_plate.conf[0])

    # Absolute bbox in original frame coords (for overlay)
    abs_bbox = [x1 + px1, y1 + py1, x1 + px2, y1 + py2]

    return plate_text, confidence, abs_bbox


def run_ocr(plate_crop):
    """
    OCR on the cropped plate image.
    Uses easyocr if available, falls back to tesseract.
    Replace this with your existing OCR method.
    """
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        result = reader.readtext(plate_crop)
        if result:
            return result[0][1].upper().replace(" ", "")
    except ImportError:
        pass

    try:
        import pytesseract
        text = pytesseract.image_to_string(
            plate_crop,
            config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        )
        return text.strip().replace(" ", "").replace("\n", "")
    except Exception:
        pass

    return None
