import cv2
import time
import logging
import threading

from core.hand_tracker import HandTracker
from core.gesture_engine import GestureEngine
from core.calibration_manager import CalibrationManager


class CameraEngine:
    def __init__(
        self,
        camera_index=0,
        width=1280,
        height=720,
        fps=30,
    ):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.target_fps = fps

        self.cap = None
        self.tracker = None

        # Gesture intelligence + calibration services.
        self.gesture_engine = GestureEngine()
        self.calibration_manager = CalibrationManager(
            self.gesture_engine
        )

        self.running = False
        self.thread = None

        self.latest_frame = None
        self.latest_result = None
        self.latest_hand = None
        self.latest_gesture = "No Hand"
        self.latest_confidence = 0.0
        self.latest_stability = 0.0

        self.lock = threading.Lock()

        self.actual_fps = 0.0
        self.processing_time = 0.0
        self.frame_count = 0

        self.logger = logging.getLogger(
            "GestureOS.CameraEngine"
        )

    def start(self):
        if self.running:
            return True

        self.logger.info(
            "Starting camera engine..."
        )

        try:
            self.cap = cv2.VideoCapture(
                self.camera_index,
                cv2.CAP_DSHOW,
            )

            if not self.cap.isOpened():
                self.logger.warning(
                    "DirectShow failed, trying default camera backend..."
                )

                self.cap.release()
                self.cap = cv2.VideoCapture(
                    self.camera_index
                )

            if not self.cap.isOpened():
                raise RuntimeError(
                    f"Unable to open camera index "
                    f"{self.camera_index}"
                )

            self.cap.set(
                cv2.CAP_PROP_FRAME_WIDTH,
                self.width,
            )
            self.cap.set(
                cv2.CAP_PROP_FRAME_HEIGHT,
                self.height,
            )
            self.cap.set(
                cv2.CAP_PROP_FPS,
                self.target_fps,
            )
            self.cap.set(
                cv2.CAP_PROP_BUFFERSIZE,
                1,
            )

            self.tracker = HandTracker(
                num_hands=1,
                detection_confidence=0.5,
                tracking_confidence=0.5,
            )

            # Load the saved calibration profile if one exists.
            self.calibration_manager.load_profile()

            self.gesture_engine.reset()

            self.running = True

            self.thread = threading.Thread(
                target=self._capture_loop,
                daemon=True,
                name="GestureOS-Camera",
            )

            self.thread.start()

            self.logger.info(
                "Camera engine started successfully."
            )

            return True

        except Exception:
            self.logger.exception(
                "Camera start failed."
            )

            self.running = False

            if self.cap is not None:
                self.cap.release()
                self.cap = None

            if self.tracker is not None:
                try:
                    self.tracker.close()
                except Exception:
                    pass

            self.tracker = None

            raise

    def stop(self):
        if not self.running:
            return

        self.logger.info(
            "Stopping camera engine..."
        )

        self.running = False

        if self.thread is not None:
            self.thread.join(
                timeout=2.0
            )
            self.thread = None

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        if self.tracker is not None:
            try:
                self.tracker.close()
            except Exception:
                pass

            self.tracker = None

        with self.lock:
            self.latest_frame = None
            self.latest_result = None
            self.latest_hand = None
            self.latest_gesture = "No Hand"
            self.latest_confidence = 0.0
            self.latest_stability = 0.0

        self.logger.info(
            "Camera engine stopped."
        )

    def _capture_loop(self):
        fps_counter = 0
        fps_timer = time.perf_counter()

        while self.running:

            if self.cap is None:
                break

            loop_start = time.perf_counter()

            success, frame = self.cap.read()

            if not success or frame is None:
                self.logger.warning(
                    "Camera frame read failed."
                )
                time.sleep(0.02)
                continue

            frame = cv2.flip(
                frame,
                1,
            )

            result = None
            hand = None
            gesture = "No Hand"
            confidence = 0.0
            stability = 0.0

            processing_start = (
                time.perf_counter()
            )

            try:
                if self.tracker is not None:
                    result = self.tracker.process(
                        frame
                    )

                    hand = (
                        self.tracker.get_first_hand(
                            result
                        )
                    )

                gesture = (
                    self.gesture_engine.detect(
                        hand
                    )
                )

                confidence = float(
                    self.gesture_engine.get_confidence()
                )

                stability = float(
                    self.gesture_engine.get_stability()
                )

            except Exception:
                self.logger.exception(
                    "Hand tracking / gesture engine error."
                )

                gesture = "No Hand"
                confidence = 0.0
                stability = 0.0

            self.processing_time = (
                time.perf_counter()
                - processing_start
            ) * 1000.0

            with self.lock:
                self.latest_frame = frame
                self.latest_result = result
                self.latest_hand = hand
                self.latest_gesture = gesture
                self.latest_confidence = confidence
                self.latest_stability = stability

            self.frame_count += 1
            fps_counter += 1

            now = time.perf_counter()

            if now - fps_timer >= 1.0:
                self.actual_fps = (
                    fps_counter
                    / (now - fps_timer)
                )

                fps_counter = 0
                fps_timer = now

            elapsed = (
                time.perf_counter()
                - loop_start
            )

            target_time = (
                1.0
                / max(
                    self.target_fps,
                    1,
                )
            )

            remaining = (
                target_time - elapsed
            )

            if remaining > 0:
                time.sleep(remaining)

    # =========================================================
    # APP-COMPATIBLE READ
    # =========================================================

    def read(self):
        with self.lock:
            if self.latest_frame is None:
                return None

            return {
                "frame": self.latest_frame.copy(),
                "results": self.latest_result,
                "gesture": self.latest_gesture,
                "hand": self.latest_hand,
                "confidence": self.latest_confidence,
                "stability": self.latest_stability,
                "fps": self.actual_fps,
            }

    def get_frame(self):
        with self.lock:
            if self.latest_frame is None:
                return None

            return self.latest_frame.copy()

    def get_result(self):
        with self.lock:
            return self.latest_result

    def get_stats(self):
        return {
            "fps": round(
                self.actual_fps,
                1,
            ),
            "processing_ms": round(
                self.processing_time,
                1,
            ),
            "frames": self.frame_count,
            "running": self.running,
            "gesture": self.latest_gesture,
            "confidence": round(
                self.latest_confidence,
                3,
            ),
            "stability": round(
                self.latest_stability,
                3,
            ),
        }

    def apply_calibration(self):
        return self.calibration_manager.apply()

    def is_running(self):
        return self.running

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass
