"""
FarmLens Inference Engine
==========================
AI_MODE = "mock"   → random-walk Cv, no model file needed
AI_MODE = "tflite" → real TFLite inference on MODEL_PATH

To upgrade to real AI:
  1. Put your .tflite file in models/plant_disease.tflite
  2. Set AI_MODE=tflite in .env
  3. Restart: sudo systemctl restart farmlens

The rest of the system (fusion, API, app) requires ZERO changes.
"""
import random
import logging
import numpy as np

from config import AI_MODE, MODEL_PATH, CONFIDENCE_THRESHOLD, DISEASE_CLASSES, HEALTHY_CLASS

log = logging.getLogger("farmlens.inference")

# ── Try to import TFLite runtime ─────────────────────────────────────────────
_HAVE_TFLITE = False
if AI_MODE == "tflite":
    try:
        import tflite_runtime.interpreter as tflite
        _HAVE_TFLITE = True
        log.info("tflite_runtime available ✓")
    except ImportError:
        try:
            import tensorflow.lite as tflite
            _HAVE_TFLITE = True
            log.info("tensorflow.lite available ✓")
        except ImportError:
            log.warning("TFLite not installed — falling back to mock mode")


class InferenceEngine:
    """
    Unified inference interface.
    Returns: (detection_class: str, confidence: float, latency_ms: float)
    """

    def __init__(self):
        self._mode        = AI_MODE
        self._interpreter = None
        self._cv_state    = 0.35   # mock AI state
        self._cycle       = 0

        if self._mode == "tflite" and _HAVE_TFLITE:
            self._load_tflite()
        else:
            if self._mode == "tflite":
                log.warning("TFLite requested but not available — using mock mode")
            self._mode = "mock"
            log.info("Inference engine: MOCK MODE")

    def _load_tflite(self):
        import os
        if not os.path.isfile(MODEL_PATH):
            log.error("Model not found: %s — using mock mode", MODEL_PATH)
            self._mode = "mock"
            return
        try:
            self._interpreter = tflite.Interpreter(model_path=MODEL_PATH)
            self._interpreter.allocate_tensors()
            self._input_details  = self._interpreter.get_input_details()
            self._output_details = self._interpreter.get_output_details()
            self._mode = "tflite"
            log.info("TFLite model loaded: %s", MODEL_PATH)
        except Exception as e:
            log.error("Failed to load TFLite model: %s — using mock mode", e)
            self._mode = "mock"

    def run(self, frame_rgb: np.ndarray) -> tuple[str, float, float]:
        """
        Run inference on an RGB frame.
        Returns (detection_class, confidence, latency_ms).
        """
        if self._mode == "tflite" and self._interpreter:
            return self._run_tflite(frame_rgb)
        return self._run_mock()

    def mode(self) -> str:
        return self._mode

    # ── Mock AI ──────────────────────────────────────────────────────────────

    def _run_mock(self) -> tuple[str, float, float]:
        self._cycle += 1
        self._cv_state = max(0.10, min(0.95,
            self._cv_state + random.uniform(-0.07, 0.07)))
        cv = round(self._cv_state, 3)

        if cv > 0.60:
            cls = DISEASE_CLASSES[(self._cycle - 1) % len(DISEASE_CLASSES)]
        else:
            cls = HEALTHY_CLASS

        return cls, cv, 0.0   # 0ms latency for mock

    # ── TFLite inference ─────────────────────────────────────────────────────

    def _run_tflite(self, frame_rgb: np.ndarray) -> tuple[str, float, float]:
        import cv2, time
        from config import CAMERA_WIDTH, CAMERA_HEIGHT

        t0 = time.perf_counter()
        try:
            # Resize to model input size
            inp = self._input_details[0]
            h, w = inp["shape"][1], inp["shape"][2]
            img = cv2.resize(frame_rgb, (w, h))

            # Normalise (INT8 or FLOAT32)
            if inp["dtype"] == np.uint8:
                data = img.astype(np.uint8)
            else:
                data = (img.astype(np.float32) / 255.0)

            self._interpreter.set_tensor(inp["index"], data[np.newaxis])
            self._interpreter.invoke()

            # Read output — assumes classification output shape [1, N]
            out = self._interpreter.get_tensor(self._output_details[0]["index"])[0]
            best_idx  = int(np.argmax(out))
            confidence = float(out[best_idx])

            if confidence < CONFIDENCE_THRESHOLD or best_idx >= len(DISEASE_CLASSES):
                cls = HEALTHY_CLASS
                confidence = max(confidence, 0.1)
            else:
                cls = DISEASE_CLASSES[best_idx]

            latency_ms = (time.perf_counter() - t0) * 1000
            return cls, round(confidence, 3), round(latency_ms, 1)

        except Exception as e:
            log.error("TFLite inference error: %s", e)
            return HEALTHY_CLASS, 0.1, 0.0
