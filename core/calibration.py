import json
import os
from datetime import datetime


class CalibrationManager:

    VERSION = "1.0"

    def __init__(
        self,
        file_path="calibration_profile.json"
    ):

        self.file_path = file_path

        self.samples = {}

        self.thresholds = {}

        self.active = False

        self.current_gesture = None

        self.load()

    # =========================================================
    # START / STOP
    # =========================================================

    def start(self, gesture):

        self.active = True

        self.current_gesture = gesture

        if gesture not in self.samples:
            self.samples[gesture] = []

    def stop(self):

        self.active = False

        self.current_gesture = None

    # =========================================================
    # SAMPLE COLLECTION
    # =========================================================

    def add_sample(
        self,
        gesture,
        confidence,
        stability
    ):

        if not gesture:
            return False

        if gesture == "No Hand":
            return False

        if gesture == "Unknown":
            return False

        sample = {
            "confidence": round(
                float(confidence),
                4
            ),
            "stability": round(
                float(stability),
                4
            ),
            "timestamp": datetime.now().isoformat()
        }

        if gesture not in self.samples:
            self.samples[gesture] = []

        self.samples[gesture].append(
            sample
        )

        return True

    # =========================================================
    # SAMPLE COUNT
    # =========================================================

    def sample_count(
        self,
        gesture
    ):

        return len(
            self.samples.get(
                gesture,
                []
            )
        )

    def total_samples(self):

        return sum(
            len(samples)
            for samples in self.samples.values()
        )

    # =========================================================
    # CALCULATE THRESHOLD
    # =========================================================

    def calculate_threshold(
        self,
        gesture
    ):

        samples = self.samples.get(
            gesture,
            []
        )

        if not samples:
            return None

        confidences = [
            sample["confidence"]
            for sample in samples
        ]

        confidences.sort()

        count = len(confidences)

        average = (
            sum(confidences)
            / count
        )

        # Remove the weakest samples when
        # enough calibration data exists.
        if count >= 5:

            strong_samples = (
                confidences[
                    max(
                        0,
                        int(count * 0.20)
                    ):
                ]
            )

            if strong_samples:

                average = (
                    sum(
                        strong_samples
                    )
                    / len(
                        strong_samples
                    )
                )

        # Keep threshold slightly below
        # observed average so normal
        # hand movement does not get rejected.
        threshold = (
            average * 0.82
        )

        threshold = max(
            0.45,
            min(
                0.90,
                threshold
            )
        )

        self.thresholds[
            gesture
        ] = round(
            threshold,
            3
        )

        return self.thresholds[
            gesture
        ]

    # =========================================================
    # CALIBRATE ONE GESTURE
    # =========================================================

    def calibrate_gesture(
        self,
        gesture
    ):

        return self.calculate_threshold(
            gesture
        )

    # =========================================================
    # CALIBRATE ALL
    # =========================================================

    def calibrate_all(self):

        results = {}

        for gesture in self.samples:

            threshold = (
                self.calculate_threshold(
                    gesture
                )
            )

            if threshold is not None:

                results[
                    gesture
                ] = threshold

        return results

    # =========================================================
    # GET THRESHOLD
    # =========================================================

    def get_threshold(
        self,
        gesture,
        default=None
    ):

        return self.thresholds.get(
            gesture,
            default
        )

    def get_thresholds(self):

        return self.thresholds.copy()

    # =========================================================
    # PROFILE DATA
    # =========================================================

    def profile(self):

        return {
            "version": self.VERSION,
            "updated_at": datetime.now().isoformat(),
            "thresholds": self.thresholds,
            "samples": self.samples
        }

    # =========================================================
    # SAVE
    # =========================================================

    def save(self):

        try:

            directory = os.path.dirname(
                os.path.abspath(
                    self.file_path
                )
            )

            os.makedirs(
                directory,
                exist_ok=True
            )

            with open(
                self.file_path,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    self.profile(),
                    file,
                    indent=4
                )

            return True

        except Exception:

            return False

    # =========================================================
    # LOAD
    # =========================================================

    def load(self):

        if not os.path.exists(
            self.file_path
        ):

            return False

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            self.thresholds = (
                data.get(
                    "thresholds",
                    {}
                )
            )

            self.samples = (
                data.get(
                    "samples",
                    {}
                )
            )

            return True

        except Exception:

            self.thresholds = {}
            self.samples = {}

            return False

    # =========================================================
    # RESET
    # =========================================================

    def reset(self):

        self.samples = {}

        self.thresholds = {}

        self.active = False

        self.current_gesture = None

        if os.path.exists(
            self.file_path
        ):

            try:

                os.remove(
                    self.file_path
                )

            except OSError:

                pass

    # =========================================================
    # EXPORT / IMPORT
    # =========================================================

    def export_profile(self):

        return self.profile()

    def import_profile(
        self,
        profile
    ):

        if not isinstance(
            profile,
            dict
        ):

            return False

        self.thresholds = (
            profile.get(
                "thresholds",
                {}
            )
        )

        self.samples = (
            profile.get(
                "samples",
                {}
            )
        )

        return True

    # =========================================================
    # STATUS
    # =========================================================

    def status(self):

        return {
            "active": self.active,
            "current_gesture": (
                self.current_gesture
            ),
            "total_samples": (
                self.total_samples()
            ),
            "calibrated_gestures": len(
                self.thresholds
            ),
            "thresholds": (
                self.get_thresholds()
            )
        }