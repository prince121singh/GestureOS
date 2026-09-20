import math
from collections import deque


class GestureEngine:

    GESTURES = [
        "Pinch",
        "Thumb Up",
        "Thumb Down",
        "Three Fingers",
        "Rock Sign",
        "Peace",
        "Point",
        "Open Palm",
        "Fist",
    ]

    DEFAULT_THRESHOLDS = {
        "Pinch": 0.62,
        "Thumb Up": 0.60,
        "Thumb Down": 0.60,
        "Three Fingers": 0.60,
        "Rock Sign": 0.60,
        "Peace": 0.60,
        "Point": 0.60,
        "Open Palm": 0.60,
        "Fist": 0.60,
    }

    def __init__(
        self,
        history_size=7,
        confidence_threshold=0.60,
        smoothing=0.42,
        switch_margin=0.08,
    ):
        self.gesture = "No Hand"
        self.raw_gesture = "No Hand"

        self.history_size = max(5, int(history_size))
        self.history = deque(maxlen=self.history_size)
        self.confidence_history = deque(maxlen=self.history_size)
        self.raw_history = deque(maxlen=self.history_size)

        self.confidence_threshold = float(confidence_threshold)
        self.gesture_thresholds = self.DEFAULT_THRESHOLDS.copy()

        self.confidence = 0.0
        self.stability = 0.0
        self.last_detected_confidence = 0.0

        self.smoothing = self.clamp(smoothing, 0.15, 0.80)
        self.switch_margin = self.clamp(switch_margin, 0.02, 0.20)

        self.smoothed_confidence = 0.0
        self.candidate_gesture = "No Hand"
        self.candidate_frames = 0
        self.previous_stable_gesture = "No Hand"
        self.frames_since_change = 0

        self.gesture_confidences = {
            gesture: 0.0 for gesture in self.GESTURES
        }

    # =========================================================
    # BASIC GEOMETRY
    # =========================================================

    @staticmethod
    def distance(point1, point2):
        return math.sqrt(
            (point1.x - point2.x) ** 2
            + (point1.y - point2.y) ** 2
            + (point1.z - point2.z) ** 2
        )

    @staticmethod
    def finger_up(hand, tip, pip):
        return hand[tip].y < hand[pip].y

    @staticmethod
    def clamp(value, minimum=0.0, maximum=1.0):
        return max(minimum, min(maximum, float(value)))

    # =========================================================
    # CONFIDENCE
    # =========================================================

    def calculate_confidence(self, hand, gesture):
        if not hand or gesture == "No Hand":
            return 0.0

        index_up = self.finger_up(hand, 8, 6)
        middle_up = self.finger_up(hand, 12, 10)
        ring_up = self.finger_up(hand, 16, 14)
        pinky_up = self.finger_up(hand, 20, 18)

        wrist = hand[0]
        thumb_tip = hand[4]
        thumb_ip = hand[3]
        thumb_mcp = hand[2]

        if gesture == "Pinch":
            distance = self.distance(hand[4], hand[8])
            if distance >= 0.075:
                return 0.0
            return self.clamp(1.0 - distance / 0.075)

        if gesture == "Thumb Up":
            vertical = wrist.y - thumb_tip.y
            joint1 = thumb_ip.y - thumb_tip.y
            joint2 = thumb_mcp.y - thumb_ip.y
            confidence = 0.0
            if vertical > 0.055:
                confidence += 0.40
            if joint1 > 0:
                confidence += 0.25
            if joint2 > 0:
                confidence += 0.20
            if sum((index_up, middle_up, ring_up, pinky_up)) == 0:
                confidence += 0.15
            return self.clamp(confidence)

        if gesture == "Thumb Down":
            vertical = thumb_tip.y - wrist.y
            joint1 = thumb_tip.y - thumb_ip.y
            joint2 = thumb_ip.y - thumb_mcp.y
            confidence = 0.0
            if vertical > 0.055:
                confidence += 0.40
            if joint1 > 0:
                confidence += 0.25
            if joint2 > 0:
                confidence += 0.20
            if sum((index_up, middle_up, ring_up, pinky_up)) == 0:
                confidence += 0.15
            return self.clamp(confidence)

        if gesture == "Three Fingers":
            confidence = 0.0
            confidence += 0.25 if index_up else 0.0
            confidence += 0.25 if middle_up else 0.0
            confidence += 0.25 if ring_up else 0.0
            confidence += 0.15 if not pinky_up else 0.0
            confidence += 0.10 if not self.finger_up(hand, 4, 3) else 0.0
            return self.clamp(confidence)

        if gesture == "Rock Sign":
            confidence = 0.0
            confidence += 0.30 if index_up else 0.0
            confidence += 0.30 if pinky_up else 0.0
            confidence += 0.15 if not middle_up else 0.0
            confidence += 0.15 if not ring_up else 0.0
            confidence += 0.10 if not (middle_up or ring_up) else 0.0
            return self.clamp(confidence)

        if gesture == "Peace":
            confidence = 0.0
            confidence += 0.35 if index_up else 0.0
            confidence += 0.35 if middle_up else 0.0
            confidence += 0.15 if not ring_up else 0.0
            confidence += 0.15 if not pinky_up else 0.0
            return self.clamp(confidence)

        if gesture == "Point":
            confidence = 0.0
            confidence += 0.40 if index_up else 0.0
            confidence += 0.20 if not middle_up else 0.0
            confidence += 0.20 if not ring_up else 0.0
            confidence += 0.20 if not pinky_up else 0.0
            return self.clamp(confidence)

        if gesture == "Open Palm":
            confidence = 0.0
            confidence += 0.25 if index_up else 0.0
            confidence += 0.25 if middle_up else 0.0
            confidence += 0.25 if ring_up else 0.0
            confidence += 0.25 if pinky_up else 0.0
            return self.clamp(confidence)

        if gesture == "Fist":
            confidence = 0.0
            confidence += 0.25 if not index_up else 0.0
            confidence += 0.25 if not middle_up else 0.0
            confidence += 0.25 if not ring_up else 0.0
            confidence += 0.25 if not pinky_up else 0.0
            return self.clamp(confidence)

        return 0.0

    def _calculate_all_confidences(self, hand):
        values = {}
        if not hand:
            return values
        for gesture in self.GESTURES:
            values[gesture] = self.calculate_confidence(hand, gesture)
        return values

    # =========================================================
    # RAW DETECTION
    # =========================================================

    def detect_raw(self, hand):
        if not hand:
            return "No Hand"

        index_up = self.finger_up(hand, 8, 6)
        middle_up = self.finger_up(hand, 12, 10)
        ring_up = self.finger_up(hand, 16, 14)
        pinky_up = self.finger_up(hand, 20, 18)

        fingers_up = sum((index_up, middle_up, ring_up, pinky_up))

        wrist = hand[0]
        thumb_tip = hand[4]
        thumb_ip = hand[3]
        thumb_mcp = hand[2]

        thumb_vertical_length = wrist.y - thumb_tip.y
        thumb_down_length = thumb_tip.y - wrist.y
        thumb_index_distance = self.distance(hand[4], hand[8])

        if thumb_index_distance < 0.065:
            return "Pinch"

        if (
            fingers_up == 0
            and thumb_tip.y < thumb_ip.y
            and thumb_ip.y < thumb_mcp.y
            and thumb_vertical_length > 0.055
        ):
            return "Thumb Up"

        if (
            fingers_up == 0
            and thumb_tip.y > thumb_ip.y
            and thumb_ip.y > thumb_mcp.y
            and thumb_down_length > 0.055
        ):
            return "Thumb Down"

        if index_up and middle_up and ring_up and not pinky_up:
            return "Three Fingers"

        if index_up and pinky_up and not middle_up and not ring_up:
            return "Rock Sign"

        if index_up and middle_up and not ring_up and not pinky_up:
            return "Peace"

        if index_up and not middle_up and not ring_up and not pinky_up:
            return "Point"

        if fingers_up == 4:
            return "Open Palm"

        if fingers_up == 0:
            return "Fist"

        return "Unknown"

    # =========================================================
    # ADAPTIVE INTELLIGENCE
    # =========================================================

    def _update_stability(self, gesture):
        if not self.history:
            return 0.0

        same = sum(item == gesture for item in self.history)
        recent_window = list(self.history)[-min(5, len(self.history)):]
        recent_same = sum(item == gesture for item in recent_window)

        long_term = same / len(self.history)
        short_term = recent_same / len(recent_window)

        return self.clamp(long_term * 0.45 + short_term * 0.55)

    def _temporal_bonus(self, gesture):
        if not self.raw_history:
            return 0.0

        recent = list(self.raw_history)[-min(4, len(self.raw_history)):]
        same = sum(item == gesture for item in recent)
        return same / len(recent)

    def _required_frames(self, gesture):
        if gesture in ("Pinch", "Thumb Up", "Thumb Down"):
            return 3
        return 2

    def _accept_candidate(self, candidate, candidate_confidence):
        if candidate == "Unknown":
            return False

        threshold = self.gesture_thresholds.get(
            candidate,
            self.confidence_threshold,
        )

        temporal = self._temporal_bonus(candidate)
        adaptive_score = (
            candidate_confidence * 0.72
            + temporal * 0.28
        )

        if adaptive_score < threshold:
            return False

        if self.previous_stable_gesture == "No Hand":
            return True

        if candidate == self.previous_stable_gesture:
            return True

        old_confidence = self.gesture_confidences.get(
            self.previous_stable_gesture,
            0.0,
        )

        if candidate_confidence < old_confidence + self.switch_margin:
            return False

        return True

    # =========================================================
    # MAIN DETECTION
    # =========================================================

    def detect(self, hand):
        if not hand:
            self.history.clear()
            self.confidence_history.clear()
            self.raw_history.clear()

            self.gesture = "No Hand"
            self.raw_gesture = "No Hand"
            self.confidence = 0.0
            self.stability = 0.0
            self.last_detected_confidence = 0.0
            self.smoothed_confidence = 0.0
            self.candidate_gesture = "No Hand"
            self.candidate_frames = 0
            self.previous_stable_gesture = "No Hand"
            self.frames_since_change = 0
            self.gesture_confidences = {
                gesture: 0.0 for gesture in self.GESTURES
            }
            return self.gesture

        raw_gesture = self.detect_raw(hand)
        all_confidences = self._calculate_all_confidences(hand)

        self.raw_gesture = raw_gesture
        self.raw_history.append(raw_gesture)

        self.gesture_confidences = all_confidences

        raw_confidence = all_confidences.get(raw_gesture, 0.0)
        self.last_detected_confidence = raw_confidence

        self.confidence_history.append(raw_confidence)

        self.history.append(raw_gesture)

        if raw_gesture in self.GESTURES:
            if self.candidate_gesture == raw_gesture:
                self.candidate_frames += 1
            else:
                self.candidate_gesture = raw_gesture
                self.candidate_frames = 1
        else:
            self.candidate_gesture = "Unknown"
            self.candidate_frames = 0

        stable_gesture = max(
            self.history,
            key=lambda item: (
                sum(x == item for x in self.history),
                self._temporal_bonus(item),
            ),
        )

        self.stability = self._update_stability(stable_gesture)

        if self.confidence_history:
            average_confidence = sum(self.confidence_history) / len(
                self.confidence_history
            )
        else:
            average_confidence = 0.0

        temporal_bonus = self._temporal_bonus(stable_gesture)

        target_confidence = (
            average_confidence * 0.55
            + self.stability * 0.25
            + temporal_bonus * 0.20
        )

        self.smoothed_confidence = (
            self.smoothed_confidence * self.smoothing
            + target_confidence * (1.0 - self.smoothing)
        )

        self.confidence = self.clamp(self.smoothed_confidence)

        if (
            stable_gesture in self.GESTURES
            and self.candidate_gesture == stable_gesture
            and self.candidate_frames >= self._required_frames(stable_gesture)
            and self._accept_candidate(
                stable_gesture,
                all_confidences.get(stable_gesture, 0.0),
            )
        ):
            if stable_gesture != self.previous_stable_gesture:
                self.previous_stable_gesture = stable_gesture
                self.frames_since_change = 0

            self.gesture = stable_gesture
        else:
            self.frames_since_change += 1

            # Keep a valid gesture briefly during a noisy frame instead
            # of immediately switching to an unsafe/unknown action.
            if self.previous_stable_gesture in self.GESTURES:
                self.gesture = self.previous_stable_gesture
            elif self.confidence < self.confidence_threshold:
                self.gesture = "No Hand"

        return self.gesture

    # =========================================================
    # GETTERS
    # =========================================================

    def get_raw_gesture(self):
        return self.raw_gesture

    def get_confidence(self):
        return self.confidence

    def get_stability(self):
        return self.stability

    def get_last_confidence(self):
        return self.last_detected_confidence

    def get_gesture_confidences(self):
        return self.gesture_confidences.copy()

    def get_active_gesture_confidence(self):
        if self.gesture in self.gesture_confidences:
            return self.gesture_confidences[self.gesture]
        return 0.0

    # =========================================================
    # THRESHOLD MANAGEMENT
    # =========================================================

    def set_threshold(self, gesture, threshold):
        if gesture not in self.GESTURES:
            return False

        self.gesture_thresholds[gesture] = self.clamp(
            threshold,
            0.30,
            0.95,
        )
        return True

    def get_threshold(self, gesture):
        return self.gesture_thresholds.get(
            gesture,
            self.confidence_threshold,
        )

    def set_thresholds(self, thresholds):
        if not thresholds:
            return

        for gesture, threshold in thresholds.items():
            if gesture in self.GESTURES:
                self.set_threshold(gesture, threshold)

    def get_thresholds(self):
        return self.gesture_thresholds.copy()

    # =========================================================
    # ADAPTIVE SETTINGS
    # =========================================================

    def set_smoothing(self, value):
        self.smoothing = self.clamp(value, 0.15, 0.80)

    def get_smoothing(self):
        return self.smoothing

    def set_switch_margin(self, value):
        self.switch_margin = self.clamp(value, 0.02, 0.20)

    def get_switch_margin(self):
        return self.switch_margin

    def get_adaptive_state(self):
        return {
            "gesture": self.gesture,
            "raw_gesture": self.raw_gesture,
            "confidence": round(self.confidence, 4),
            "last_confidence": round(
                self.last_detected_confidence,
                4,
            ),
            "stability": round(self.stability, 4),
            "candidate": self.candidate_gesture,
            "candidate_frames": self.candidate_frames,
            "previous_gesture": self.previous_stable_gesture,
            "frames_since_change": self.frames_since_change,
            "smoothing": round(self.smoothing, 4),
            "switch_margin": round(self.switch_margin, 4),
        }

    # =========================================================
    # CALIBRATION SUPPORT
    # =========================================================

    def get_calibration_snapshot(self):
        return {
            "gesture": self.raw_gesture,
            "confidence": round(self.confidence, 4),
            "stability": round(self.stability, 4),
            "last_confidence": round(
                self.last_detected_confidence,
                4,
            ),
            "thresholds": self.get_thresholds(),
            "gesture_confidences": {
                key: round(value, 4)
                for key, value in self.gesture_confidences.items()
            },
        }

    # =========================================================
    # RESET
    # =========================================================

    def reset(self):
        self.history.clear()
        self.confidence_history.clear()
        self.raw_history.clear()

        self.gesture = "No Hand"
        self.raw_gesture = "No Hand"
        self.confidence = 0.0
        self.stability = 0.0
        self.last_detected_confidence = 0.0

        self.smoothed_confidence = 0.0
        self.candidate_gesture = "No Hand"
        self.candidate_frames = 0
        self.previous_stable_gesture = "No Hand"
        self.frames_since_change = 0

        self.gesture_confidences = {
            gesture: 0.0 for gesture in self.GESTURES
        }


def fingers_up_count(*fingers):
    return sum(bool(finger) for finger in fingers)
