import time
from pathlib import Path

import pyautogui


class GestureController:
    """
    GestureOS Controller
    --------------------
    Handles:
    - Cursor movement
    - Click
    - Scroll
    - Volume
    - Next / Previous
    - Screenshot
    - Pause / Play
    - Gesture mappings
    - Gesture transition intelligence
    - Action cooldown / protection
    - Controller enable / disable
    - Telemetry
    """

    SAFE_ACTIONS = {
        "No Action",
        "Cursor",
        "Click",
        "Scroll",
        "Volume Up",
        "Volume Down",
        "Next",
        "Previous",
        "Screenshot",
        "Pause",
    }

    DEFAULT_MAPPINGS = {
        "Point": "Cursor",
        "Pinch": "Click",
        "Peace": "Scroll",
        "Thumb Up": "Volume Up",
        "Thumb Down": "Volume Down",
        "Fist": "Screenshot",
        "Open Palm": "Pause",
        "Three Fingers": "No Action",
        "Rock Sign": "No Action",
    }

    def __init__(
        self,
        cooldown=0.8,
        sensitivity=25,
        mappings=None,
    ):
        self.cooldown = float(cooldown)
        self.sensitivity = float(sensitivity)

        self.enabled = True

        # ---------------------------------------------------------
        # ACTION MAPPINGS
        # ---------------------------------------------------------
        self.action_map = dict(self.DEFAULT_MAPPINGS)

        if isinstance(mappings, dict):
            self.set_mappings(mappings)

        # ---------------------------------------------------------
        # ACTION STATE
        # ---------------------------------------------------------
        self.last_action_time = 0.0
        self.last_action = "Ready"
        self.action_count = 0

        # ---------------------------------------------------------
        # GESTURE STATE
        # ---------------------------------------------------------
        self.previous_gesture = None
        self.previous_gesture_time = 0.0

        self.transition_gesture = None
        self.transition_since = 0.0

        self.transition_min_time = 0.075

        self.transition_lock_until = 0.0
        self.transition_lock_time = 0.12

        # ---------------------------------------------------------
        # ACTION CONFIRMATION
        # ---------------------------------------------------------
        self.gesture_confirmed = {}
        self.gesture_confirm_time = {}

        self.confirm_window = 0.16
        self.protected_actions = {
            "Click",
            "Screenshot",
            "Pause",
            "Next",
            "Previous",
            "Volume Up",
            "Volume Down",
        }

        # ---------------------------------------------------------
        # CURSOR INTELLIGENCE
        # ---------------------------------------------------------
        self.cursor_enabled = True

        self.cursor_x = None
        self.cursor_y = None

        self.cursor_smoothing = 0.35

        self.screen_width, self.screen_height = pyautogui.size()

        self.cursor_move_count = 0

        # ---------------------------------------------------------
        # SCROLL INTELLIGENCE
        # ---------------------------------------------------------
        self.last_scroll_y = None
        self.scroll_deadzone = 0.025
        self.scroll_scale = 14

        self.scroll_count = 0

        # ---------------------------------------------------------
        # PINCH STATE
        # ---------------------------------------------------------
        self.pinch_active = False

        # ---------------------------------------------------------
        # TELEMETRY
        # ---------------------------------------------------------
        self.last_execution_time = 0.0
        self.last_latency_ms = 0.0

        # ---------------------------------------------------------
        # SCREENSHOT
        # ---------------------------------------------------------
        self.screenshot_dir = Path.cwd() / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    # =============================================================
    # ENABLE / DISABLE
    # =============================================================

    def enable(self):
        self.enabled = True
        self.last_action = "Controller Enabled"
        return True

    def disable(self):
        self.enabled = False
        self.last_action = "Controller Disabled"
        return True

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

        if self.enabled:
            self.last_action = "Controller Enabled"
        else:
            self.last_action = "Controller Disabled"

        return self.enabled

    def is_enabled(self):
        return self.enabled

    # =============================================================
    # SENSITIVITY
    # =============================================================

    def set_sensitivity(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False

        self.sensitivity = max(1.0, min(100.0, value))

        # Higher sensitivity = slightly faster cursor response.
        self.cursor_smoothing = max(
            0.12,
            min(0.65, self.sensitivity / 100.0),
        )

        return True

    def get_sensitivity(self):
        return self.sensitivity

    # =============================================================
    # MAPPING
    # =============================================================

    def set_mapping(self, gesture, action):
        if not isinstance(gesture, str):
            return False

        if not isinstance(action, str):
            return False

        if action not in self.SAFE_ACTIONS:
            return False

        self.action_map[gesture] = action
        return True

    def set_mappings(self, mappings):
        if not isinstance(mappings, dict):
            return False

        for gesture, action in mappings.items():
            self.set_mapping(gesture, action)

        return True

    def get_mapping(self, gesture):
        return self.action_map.get(
            gesture,
            "No Action",
        )

    def get_mappings(self):
        return dict(self.action_map)

    def reset_mappings(self):
        self.action_map = dict(self.DEFAULT_MAPPINGS)
        return True

    # =============================================================
    # TRANSITION INTELLIGENCE
    # =============================================================

    def _update_transition(self, gesture):
        now = time.monotonic()

        if gesture is None:
            return

        if self.transition_gesture != gesture:
            self.transition_gesture = gesture
            self.transition_since = now
            self.transition_lock_until = (
                now + self.transition_lock_time
            )

    def _is_rapid_transition(self, gesture):
        now = time.monotonic()

        if self.previous_gesture is None:
            return False

        if gesture == self.previous_gesture:
            return False

        elapsed = now - self.previous_gesture_time

        return elapsed < self.transition_min_time

    def _register_gesture(self, gesture):
        now = time.monotonic()

        self.previous_gesture = gesture
        self.previous_gesture_time = now

    def _stable_transition(self, gesture):
        if self.transition_gesture != gesture:
            return False

        elapsed = time.monotonic() - self.transition_since

        return elapsed >= self.transition_min_time

    # =============================================================
    # ACTION CONFIRMATION
    # =============================================================

    def _gesture_confirmed(self, gesture):
        now = time.monotonic()

        previous = self.gesture_confirmed.get(
            gesture,
            False,
        )

        if not previous:
            self.gesture_confirmed[gesture] = True
            self.gesture_confirm_time[gesture] = now
            return False

        confirmed_at = self.gesture_confirm_time.get(
            gesture,
            now,
        )

        if now - confirmed_at <= self.confirm_window:
            return True

        self.gesture_confirmed[gesture] = False
        self.gesture_confirm_time[gesture] = now

        return False

    # =============================================================
    # COOLDOWN
    # =============================================================

    def _cooldown_ready(self):
        now = time.monotonic()

        return (
            now - self.last_action_time
            >= self.cooldown
        )

    # =============================================================
    # CURSOR
    # =============================================================

    def move_cursor(
        self,
        normalized_x,
        normalized_y,
    ):
        if not self.enabled:
            return False

        try:
            x = float(normalized_x)
            y = float(normalized_y)
        except (TypeError, ValueError):
            return False

        # Clamp normalized coordinates.
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))

        target_x = x * self.screen_width
        target_y = y * self.screen_height

        if self.cursor_x is None:
            self.cursor_x = target_x
            self.cursor_y = target_y
        else:
            alpha = self.cursor_smoothing

            self.cursor_x += (
                target_x - self.cursor_x
            ) * alpha

            self.cursor_y += (
                target_y - self.cursor_y
            ) * alpha

        try:
            pyautogui.moveTo(
                int(self.cursor_x),
                int(self.cursor_y),
                duration=0,
            )

            self.cursor_move_count += 1

            return True

        except Exception:
            return False

    def reset_cursor(self):
        self.cursor_x = None
        self.cursor_y = None

    # =============================================================
    # CLICK
    # =============================================================

    def click(self):
        if not self.enabled:
            return False

        if not self._cooldown_ready():
            return False

        try:
            pyautogui.click()

            self._record_action("Click")

            return True

        except Exception:
            return False

    # =============================================================
    # SCROLL
    # =============================================================

    def scroll(self, normalized_y=None):
        if not self.enabled:
            return False

        if normalized_y is None:
            return False

        try:
            current_y = float(normalized_y)
        except (TypeError, ValueError):
            return False

        current_y = max(
            0.0,
            min(1.0, current_y),
        )

        if self.last_scroll_y is None:
            self.last_scroll_y = current_y
            return False

        delta = current_y - self.last_scroll_y

        self.last_scroll_y = current_y

        if abs(delta) < self.scroll_deadzone:
            return False

        amount = int(
            -delta * self.scroll_scale * 100
        )

        amount = max(
            -12,
            min(12, amount),
        )

        if amount == 0:
            return False

        try:
            pyautogui.scroll(amount)

            self.scroll_count += 1

            return True

        except Exception:
            return False

    def reset_scroll(self):
        self.last_scroll_y = None

    # =============================================================
    # GENERIC ACTION
    # =============================================================

    def perform_action(self, action):
        if not self.enabled:
            return False

        if action not in self.SAFE_ACTIONS:
            return False

        if action == "No Action":
            return False

        if action == "Cursor":
            return False

        if action == "Scroll":
            return False

        if not self._cooldown_ready():
            return False

        start = time.perf_counter()

        try:

            if action == "Click":
                pyautogui.click()

            elif action == "Volume Up":
                pyautogui.press("volumeup")

            elif action == "Volume Down":
                pyautogui.press("volumedown")

            elif action == "Next":
                pyautogui.press("nexttrack")

            elif action == "Previous":
                pyautogui.press("prevtrack")

            elif action == "Screenshot":
                timestamp = time.strftime(
                    "%Y%m%d_%H%M%S"
                )

                path = (
                    self.screenshot_dir
                    / f"screenshot_{timestamp}.png"
                )

                image = pyautogui.screenshot()
                image.save(path)

            elif action == "Pause":
                pyautogui.press("playpause")

            else:
                return False

            elapsed = (
                time.perf_counter() - start
            )

            self.last_latency_ms = (
                elapsed * 1000.0
            )

            self._record_action(action)

            return True

        except Exception:
            return False

    # =============================================================
    # ACTION RECORDING
    # =============================================================

    def _record_action(self, action):
        now = time.monotonic()

        self.last_action_time = now
        self.last_action = action
        self.action_count += 1

    # =============================================================
    # MAIN GESTURE EXECUTION
    # =============================================================

    def execute(self, gesture):
        """
        Execute mapped gesture action.

        Continuous actions:
        - Cursor
        - Scroll

        Protected discrete actions:
        - Click
        - Screenshot
        - Pause
        - Next
        - Previous
        - Volume Up
        - Volume Down
        """

        if not self.enabled:
            return False

        if not gesture:
            return False

        self._update_transition(gesture)

        # Rapid transition protection.
        if self._is_rapid_transition(gesture):
            self._register_gesture(gesture)
            return False

        self._register_gesture(gesture)

        action = self.get_mapping(gesture)

        # ---------------------------------------------------------
        # CONTINUOUS ACTIONS
        # ---------------------------------------------------------

        if action == "Cursor":
            return True

        if action == "Scroll":
            return True

        # ---------------------------------------------------------
        # NO ACTION
        # ---------------------------------------------------------

        if action == "No Action":
            return False

        # ---------------------------------------------------------
        # TRANSITION LOCK
        # ---------------------------------------------------------

        now = time.monotonic()

        if now < self.transition_lock_until:
            return False

        # ---------------------------------------------------------
        # STABLE TRANSITION
        # ---------------------------------------------------------

        if not self._stable_transition(gesture):
            return False

        # ---------------------------------------------------------
        # PROTECTED ACTION
        # ---------------------------------------------------------

        if action in self.protected_actions:

            if not self._gesture_confirmed(gesture):
                return False

        # ---------------------------------------------------------
        # EXECUTE
        # ---------------------------------------------------------

        return self.perform_action(action)

    # =============================================================
    # MAPPED CONTINUOUS ACTION HELPERS
    # =============================================================

    def execute_cursor(
        self,
        normalized_x,
        normalized_y,
    ):
        if self.get_mapping("Point") != "Cursor":
            return False

        return self.move_cursor(
            normalized_x,
            normalized_y,
        )

    def execute_scroll(self, normalized_y):
        if self.get_mapping("Peace") != "Scroll":
            return False

        return self.scroll(normalized_y)

    # =============================================================
    # PINCH LATCH
    # =============================================================

    def reset_pinch(self):
        self.pinch_active = False

    def execute_pinch(self):
        """
        Pinch click with latch protection.
        """

        if not self.enabled:
            return False

        if self.get_mapping("Pinch") != "Click":
            return False

        if self.pinch_active:
            return False

        self.pinch_active = True

        return self.execute("Pinch")

    def release_pinch(self):
        self.pinch_active = False

    # =============================================================
    # TELEMETRY
    # =============================================================

    def get_last_action(self):
        return self.last_action

    def get_action_count(self):
        return self.action_count

    def get_cursor_move_count(self):
        return self.cursor_move_count

    def get_scroll_count(self):
        return self.scroll_count

    def get_last_latency_ms(self):
        return self.last_latency_ms

    def get_telemetry(self):
        return {
            "enabled": self.enabled,
            "sensitivity": self.sensitivity,
            "last_action": self.last_action,
            "action_count": self.action_count,
            "cursor_moves": self.cursor_move_count,
            "scroll_count": self.scroll_count,
            "last_latency_ms": self.last_latency_ms,
            "mappings": dict(self.action_map),
        }

    # =============================================================
    # RESET
    # =============================================================

    def reset(self):
        self.last_action_time = 0.0
        self.last_action = "Ready"
        self.action_count = 0

        self.previous_gesture = None
        self.previous_gesture_time = 0.0

        self.transition_gesture = None
        self.transition_since = 0.0
        self.transition_lock_until = 0.0

        self.gesture_confirmed.clear()
        self.gesture_confirm_time.clear()

        self.reset_cursor()
        self.reset_scroll()
        self.reset_pinch()

        self.last_execution_time = 0.0
        self.last_latency_ms = 0.0

        return True