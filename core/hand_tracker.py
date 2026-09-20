import cv2
import numpy as np
import mediapipe as mp

from mediapipe.tasks import python
from mediapipe.tasks.python import vision


class HandTracker:
    def __init__(
        self,
        num_hands=1,
        detection_confidence=0.5,
        tracking_confidence=0.5,
        model_path="models/hand_landmarker.task",
    ):
        self.num_hands = num_hands
        self.detection_confidence = detection_confidence
        self.tracking_confidence = tracking_confidence
        self.model_path = model_path

        base_options = python.BaseOptions(
            model_asset_path=self.model_path
        )

        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=self.num_hands,
            min_hand_detection_confidence=self.detection_confidence,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=self.tracking_confidence,
        )

        self.landmarker = vision.HandLandmarker.create_from_options(
            options
        )

        self.timestamp_ms = 0

    def process(self, frame):
        if frame is None:
            return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=np.asarray(rgb),
        )

        self.timestamp_ms += 33

        result = self.landmarker.detect_for_video(
            mp_image,
            self.timestamp_ms,
        )

        return result

    def get_landmarks(self, result):
        if result is None:
            return []

        if not hasattr(result, "hand_landmarks"):
            return []

        return result.hand_landmarks

    def get_first_hand(self, result):
        hands = self.get_landmarks(result)

        if not hands:
            return None

        return hands[0]

    def close(self):
        if self.landmarker is not None:
            try:
                self.landmarker.close()
            except Exception:
                pass

            self.landmarker = None