import json
import time
from pathlib import Path
from statistics import mean


class CalibrationManager:
    """
    GestureOS gesture calibration manager.

    CalibrationWindow expects:
        start(gesture)
        add_sample(gesture, confidence, stability)
        stop()
        calibrate_gesture(gesture)
        calibrate_all()
        save_profile()
        reset()

    The manager learns per-gesture confidence thresholds from the
    samples collected by CalibrationWindow and persists them in JSON.
    """

    DEFAULT_PROFILE_PATH = Path("config") / "calibration_profile.json"

    def __init__(self, gesture_engine, profile_path=None):
        self.gesture_engine = gesture_engine
        self.profile_path = Path(
            profile_path or self.DEFAULT_PROFILE_PATH
        )

        self.active_gesture = None
        self.recording = False

        self.samples = {
            gesture: []
            for gesture in getattr(
                self.gesture_engine,
                "GESTURES",
                [],
            )
        }

        self.calibrated_thresholds = {}

        self._ensure_profile_dir()
        self.load_profile()

    # =========================================================
    # PROFILE
    # =========================================================

    def _ensure_profile_dir(self):
        self.profile_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load_profile(self):
        if not self.profile_path.exists():
            return False

        try:
            with self.profile_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                profile = json.load(file)

            thresholds = profile.get(
                "thresholds",
                {},
            )

            if isinstance(thresholds, dict):
                self.calibrated_thresholds = {
                    str(key): float(value)
                    for key, value in thresholds.items()
                }

            if self.calibrated_thresholds:
                self.gesture_engine.set_thresholds(
                    self.calibrated_thresholds
                )

            return True

        except Exception:
            return False

    def save_profile(self):
        self._ensure_profile_dir()

        thresholds = (
            self.gesture_engine.get_thresholds()
        )

        profile = {
            "version": 1,
            "saved_at": time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "thresholds": {
                key: round(float(value), 4)
                for key, value in thresholds.items()
            },
            "calibrated_gestures": list(
                self.calibrated_thresholds.keys()
            ),
        }

        temp_path = self.profile_path.with_suffix(
            ".tmp"
        )

        with temp_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                profile,
                file,
                indent=2,
            )

        temp_path.replace(
            self.profile_path
        )

        return True

    # =========================================================
    # RECORDING
    # =========================================================

    def start(self, gesture):
        if gesture not in self.samples:
            self.samples[gesture] = []

        self.active_gesture = gesture
        self.recording = True
        self.samples[gesture] = []

    def stop(self):
        self.recording = False
        self.active_gesture = None

    # =========================================================
    # SAMPLE COLLECTION
    # =========================================================

    def add_sample(
        self,
        gesture,
        confidence,
        stability,
    ):
        if not self.recording:
            return False

        if gesture != self.active_gesture:
            return False

        try:
            confidence = float(confidence)
            stability = float(stability)
        except (TypeError, ValueError):
            return False

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        stability = max(
            0.0,
            min(1.0, stability),
        )

        self.samples.setdefault(
            gesture,
            [],
        ).append(
            {
                "confidence": confidence,
                "stability": stability,
            }
        )

        return True

    # =========================================================
    # CALIBRATION
    # =========================================================

    def calibrate_gesture(self, gesture):
        values = self.samples.get(
            gesture,
            [],
        )

        if not values:
            return False

        confidence_values = [
            item["confidence"]
            for item in values
        ]

        stability_values = [
            item["stability"]
            for item in values
        ]

        avg_confidence = mean(
            confidence_values
        )

        avg_stability = mean(
            stability_values
        )

        # Use the observed confidence as the basis,
        # but keep the threshold in a safe operating range.
        #
        # Slightly below the average allows normal frame-to-frame
        # variation without making weak detections too permissive.
        threshold = (
            avg_confidence * 0.82
        )

        # Stability is also considered. Very unstable samples
        # should not produce an overly low threshold.
        stability_floor = (
            avg_stability * 0.55
        )

        threshold = max(
            threshold,
            stability_floor,
            0.30,
        )

        threshold = min(
            threshold,
            0.95,
        )

        self.gesture_engine.set_threshold(
            gesture,
            threshold,
        )

        self.calibrated_thresholds[
            gesture
        ] = threshold

        return True

    def calibrate_all(self):
        calibrated = 0

        for gesture in list(
            self.samples.keys()
        ):
            if self.samples.get(gesture):
                if self.calibrate_gesture(
                    gesture
                ):
                    calibrated += 1

        return calibrated

    # =========================================================
    # APPLY / RESET
    # =========================================================

    def apply(self):
        if self.calibrated_thresholds:
            self.gesture_engine.set_thresholds(
                self.calibrated_thresholds
            )

        return True

    def reset(self):
        self.recording = False
        self.active_gesture = None

        self.samples = {
            gesture: []
            for gesture in getattr(
                self.gesture_engine,
                "GESTURES",
                [],
            )
        }

        self.calibrated_thresholds = {}

        # Restore the engine's documented defaults.
        default_thresholds = getattr(
            self.gesture_engine,
            "DEFAULT_THRESHOLDS",
            {},
        )

        if default_thresholds:
            self.gesture_engine.set_thresholds(
                default_thresholds
            )

        try:
            if self.profile_path.exists():
                self.profile_path.unlink()
        except OSError:
            pass

        return True

    def get_profile(self):
        return {
            "thresholds": (
                self.gesture_engine.get_thresholds()
            ),
            "calibrated_gestures": list(
                self.calibrated_thresholds.keys()
            ),
            "recording": self.recording,
            "active_gesture": self.active_gesture,
        }
