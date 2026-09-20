import sys
import os
import time
import logging
from collections import deque

import cv2

from PySide6.QtCore import (
    Qt,
    QTimer,
    Signal,
    QObject,
    QPropertyAnimation,
    QEasingCurve,
    QSettings,
    QPoint,
    QRect,
)
from PySide6.QtGui import QImage, QPixmap, QIcon, QAction, QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
    QSystemTrayIcon,
    QMenu,
    QDialog,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QCheckBox,
    QSplashScreen,
)

from core.camera_engine import CameraEngine
from core.controller import GestureController


# ============================================================
# LOGGING — writes to gestureos.log next to the script instead
# of bare print() calls, so issues are diagnosable after the
# window has been closed.
# ============================================================

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

try:
    os.makedirs(_LOG_DIR, exist_ok=True)
except Exception:
    _LOG_DIR = None

_log_handlers = [logging.StreamHandler()]

if _LOG_DIR:
    try:
        _log_handlers.append(
            logging.FileHandler(
                os.path.join(_LOG_DIR, "gestureos.log"),
                encoding="utf-8",
            )
        )
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=_log_handlers,
)

logger = logging.getLogger("GestureOS")

APP_VERSION = "v7.0 Premium"

# Actions the four "simple" gestures can be remapped between.
REMAPPABLE_GESTURES = ["Thumb Up", "Thumb Down", "Fist", "Open Palm"]

REMAPPABLE_ACTIONS = ["Volume Up", "Volume Down", "Screenshot", "Pause"]

ACTION_DISPLAY_TEXT = {
    "Volume Up": "VOLUME UP",
    "Volume Down": "VOLUME DOWN",
    "Screenshot": "SCREENSHOT",
    "Pause": "PAUSE / PLAY",
}

DEFAULT_ACTION_MAP = {
    "Thumb Up": "Volume Up",
    "Thumb Down": "Volume Down",
    "Fist": "Screenshot",
    "Open Palm": "Pause",
}


# ============================================================
# CAMERA WORKER
# ============================================================

class CameraWorker(QObject):
    """Qt-side bridge between CameraEngine and the premium UI.

    CameraEngine owns the real capture thread.  This worker only polls
    the engine from a QTimer and forwards fresh frames/state to Qt.
    """

    frame_ready = Signal(object)
    state_ready = Signal(dict)
    error = Signal(str)

    def __init__(self):
        super().__init__()

        self.engine = CameraEngine()

        self.controller = GestureController(
            cooldown=0.8,
            sensitivity=30,
        )

        self.running = False
        self.controller_enabled = False

        self.last_gesture = None
        self.last_action_time = 0.0
        self.pinch_latched = False

        self.gesture_history = deque(maxlen=10)

        self.timer = None

        self.action_map = dict(DEFAULT_ACTION_MAP)

        self.last_success_time = 0.0
        self.reconnecting = False
        self.reconnect_cooldown = 3.0

        self.last_frame_count = 0
        self.last_engine_error = ""

    def set_action_map(self, mapping):
        cleaned = {}

        for gesture in REMAPPABLE_GESTURES:
            action = mapping.get(gesture)
            if action in REMAPPABLE_ACTIONS:
                cleaned[gesture] = action

        for gesture, action in DEFAULT_ACTION_MAP.items():
            cleaned.setdefault(gesture, action)

        self.action_map = cleaned

    def get_action_map(self):
        return dict(self.action_map)

    def start(self):
        if self.running:
            return

        try:
            logger.info("Starting GestureOS camera worker...")

            self.engine.start()

            if not self.engine.is_running():
                raise RuntimeError("Camera engine did not enter running state.")

            self.running = True
            self.controller.enable()
            self.controller_enabled = True

            self.gesture_history.clear()
            self.last_gesture = None
            self.last_action_time = 0.0
            self.pinch_latched = False
            self.last_frame_count = 0
            self.last_engine_error = ""

            self.last_success_time = time.perf_counter()
            self.reconnecting = False

            if self.timer is None:
                self.timer = QTimer(self)
                self.timer.setInterval(15)
                self.timer.timeout.connect(self.process_frame)

            if not self.timer.isActive():
                self.timer.start()

            logger.info("GestureOS camera worker started.")

        except Exception as error:
            self.running = False
            self.controller_enabled = False

            try:
                self.controller.disable()
            except Exception:
                pass

            logger.exception("Camera worker start failed.")
            self.error.emit(f"Camera start failed: {error}")

    def calculate_stability(self, gesture):
        if gesture == "No Hand":
            self.gesture_history.clear()
            return 0

        self.gesture_history.append(gesture)

        if not self.gesture_history:
            return 0

        matching = sum(
            1 for item in self.gesture_history if item == gesture
        )

        return int((matching / len(self.gesture_history)) * 100)

    def process_frame(self):
        if not self.running:
            return

        start_time = time.perf_counter()

        try:
            data = self.engine.read()

            # CameraEngine may need a few milliseconds after start before
            # its capture thread publishes the first frame.
            if data is None:
                stats = self.engine.get_stats()
                if stats.get("running") and stats.get("frames", 0) == 0:
                    self._show_waiting_state()
                return

            frame = data.get("frame")
            results = data.get("results")
            gesture = data.get("gesture", "No Hand")
            hand = data.get("hand")
            confidence = data.get("confidence", 0.0)
            fps = data.get("fps", 0.0)

            if frame is None:
                return

            # MediaPipe result can be None when tracking is unavailable.
            has_landmarks = bool(
                results is not None
                and getattr(results, "hand_landmarks", None)
            )

            action = "NO ACTION"

            stability = self.calculate_stability(gesture)

            # ==================================================
            # POINT → CURSOR
            # ==================================================
            if (
                gesture == "Point"
                and has_landmarks
                and self.controller_enabled
            ):
                landmarks = results.hand_landmarks[0]
                index_tip = landmarks[8]

                # GestureController.move_cursor expects normalized
                # coordinates. Keep this call exactly in the working
                # form so UI changes cannot affect cursor control.
                nx = max(0.0, min(1.0, float(index_tip.x)))
                ny = max(0.0, min(1.0, float(index_tip.y)))

                if self.controller.move_cursor(nx, ny):
                    action = "CURSOR MOVING"

            # ==================================================
            # PINCH → CLICK
            # ==================================================
            if gesture == "Pinch":
                if not self.pinch_latched:
                    if (
                        self.controller_enabled
                        and self.controller.click()
                    ):
                        action = "LEFT CLICK"
                        self.pinch_latched = True
                else:
                    action = "PINCH READY"
            else:
                self.pinch_latched = False

            # ==================================================
            # PEACE → SCROLL
            # ==================================================
            if (
                gesture == "Peace"
                and has_landmarks
                and self.controller_enabled
            ):
                wrist_y = results.hand_landmarks[0][0].y

                scroll_amount = self.controller.scroll(wrist_y)

                if scroll_amount > 0:
                    action = "SCROLL UP"
                elif scroll_amount < 0:
                    action = "SCROLL DOWN"
                else:
                    action = "SCROLL READY"
            else:
                self.controller.last_scroll_y = None

            # ==================================================
            # ACTION COOLDOWN
            # ==================================================
            now = time.perf_counter()

            gesture_changed = gesture != self.last_gesture
            cooldown_passed = now - self.last_action_time >= 0.9
            can_action = gesture_changed or cooldown_passed

            # ==================================================
            # REMAPPABLE GESTURES
            # ==================================================
            if (
                gesture in self.action_map
                and self.controller_enabled
                and can_action
            ):
                mapped_action = self.action_map[gesture]

                if self.controller.perform_action(mapped_action):
                    action = ACTION_DISPLAY_TEXT.get(
                        mapped_action,
                        mapped_action.upper(),
                    )
                    self.last_action_time = now
                    self.total_action_marker()

            self.last_gesture = gesture
            self.last_success_time = now
            self.reconnecting = False

            latency = (time.perf_counter() - start_time) * 1000.0

            stats = self.engine.get_stats()
            capture_fps = float(stats.get("fps", fps) or 0.0)
            processing_time_ms = float(
                stats.get("processing_ms", 0.0) or 0.0
            )
            processing_fps = (
                1000.0 / processing_time_ms
                if processing_time_ms > 0.1
                else capture_fps
            )
            processed_frames = int(stats.get("frames", 0) or 0)

            state = {
                "gesture": gesture,
                "hand": hand,
                "confidence": confidence,
                "fps": capture_fps,
                "action": action,
                "enabled": self.controller_enabled,
                "stability": stability,
                "latency": latency,
                "frames": processed_frames,
                "capture_fps": capture_fps,
                "processing_fps": processing_fps,
                "processing_time_ms": processing_time_ms,
                "processed_frames": processed_frames,
                "skipped_frames": 0,
            }

            self.frame_ready.emit(frame)
            self.state_ready.emit(state)

        except Exception as error:
            message = f"{type(error).__name__}: {error}"

            if message != self.last_engine_error:
                logger.exception("Frame processing error")
                self.last_engine_error = message
                self.error.emit(message)

            self._maybe_reconnect()

    def total_action_marker(self):
        """Keeps action counting in the main dashboard as before.
        The UI increments its own counter from the emitted action/state."""
        return None

    def _show_waiting_state(self):
        # Do not emit an error while the camera thread is simply waiting
        # for its first frame. This prevents the UI from flashing red at
        # every startup.
        return

    def _maybe_reconnect(self):
        if self.reconnecting or not self.running:
            return

        now = time.perf_counter()

        if now - self.last_success_time < self.reconnect_cooldown:
            return

        self.reconnecting = True
        logger.info("Attempting camera auto-reconnect...")

        try:
            self.engine.stop()
            time.sleep(0.1)
            self.engine.start()
            self.last_success_time = time.perf_counter()
            self.last_engine_error = ""
            logger.info("Camera auto-reconnect succeeded.")

        except Exception as reconnect_error:
            logger.error(
                "Camera auto-reconnect failed: %s",
                reconnect_error,
            )
            self.error.emit(
                f"Camera reconnect failed: {reconnect_error}"
            )

        finally:
            self.reconnecting = False

    def set_enabled(self, enabled):
        self.controller_enabled = bool(enabled)

        if self.controller_enabled:
            self.controller.enable()
        else:
            self.controller.disable()

    def set_sensitivity(self, value):
        self.controller.set_sensitivity(value)

    def stop(self):
        self.running = False
        self.gesture_history.clear()
        self.last_gesture = None
        self.pinch_latched = False

        if self.timer is not None:
            self.timer.stop()

        try:
            self.controller.disable()
        except Exception:
            pass

        try:
            self.engine.stop()
        except Exception:
            logger.exception("Camera engine stop failed")

        self.controller_enabled = False
        self.reconnecting = False

        logger.info("GestureOS camera worker stopped.")


# ============================================================
# PULSING DOT — small premium widget used for "live" indicators
# ============================================================

class PulsingDot(QLabel):
    """A glowing dot that gently pulses opacity. Purely cosmetic."""

    def __init__(self, color="#52e5bf", size=8, parent=None):
        super().__init__(parent)

        self._color = color
        self._size = size

        self.setFixedSize(size, size)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)

        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(1100)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.35)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setLoopCount(-1)

        self.set_color(color)

    def set_color(self, color):
        self._color = color
        self.setStyleSheet(
            f"background: {color};"
            f"border-radius: {self._size // 2}px;"
        )

    def start_pulse(self):
        if self._anim.state() != QPropertyAnimation.Running:
            self._anim.start()

    def stop_pulse(self):
        self._anim.stop()
        self._effect.setOpacity(1.0)


# ============================================================
# FPS SPARKLINE — tiny live trend graph, no extra dependencies
# ============================================================

class FpsSparkline(QWidget):
    """Lightweight rolling line-graph. Feed it values with push();
    it repaints itself using plain QPainter, no charting library."""

    def __init__(self, max_points=60, parent=None):
        super().__init__(parent)

        self.max_points = max_points
        self.values = deque(maxlen=max_points)

        self.setMinimumHeight(28)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def push(self, value):
        try:
            self.values.append(float(value))
        except (TypeError, ValueError):
            return

        self.update()

    def clear_data(self):
        self.values.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(4, 4, -4, -4)

        if len(self.values) < 2:
            painter.setPen(QPen(QColor("#33454f")))
            painter.drawText(
                rect, Qt.AlignCenter, "collecting data..."
            )
            painter.end()
            return

        values = list(self.values)
        v_min = min(values)
        v_max = max(values)

        if v_max - v_min < 1e-6:
            v_max = v_min + 1.0

        step_x = rect.width() / max(1, (len(values) - 1))

        points = []

        for index, value in enumerate(values):
            x = rect.left() + index * step_x
            ratio = (value - v_min) / (v_max - v_min)
            y = rect.bottom() - ratio * rect.height()
            points.append(QPoint(int(x), int(y)))

        pen = QPen(QColor("#6dffcf"))
        pen.setWidthF(1.8)
        painter.setPen(pen)

        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

        # Soft fill under the line for a premium "area chart" feel.
        fill_color = QColor("#6dffcf")
        fill_color.setAlpha(28)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill_color)

        polygon_points = points + [
            QPoint(points[-1].x(), rect.bottom()),
            QPoint(points[0].x(), rect.bottom()),
        ]
        painter.drawPolygon(polygon_points)

        painter.end()


# ============================================================
# TOAST NOTIFICATION — brief floating confirmation for actions
# ============================================================

class ToastNotification(QFrame):
    """A small floating pill that fades in top-right of the given
    parent widget, shows a message, then fades back out."""

    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)

        self.label = QLabel("")
        self.label.setObjectName("ToastLabel")
        layout.addWidget(self.label)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

        self._fade_out = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_out.setDuration(320)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self.hide)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out.start)

        self.hide()

    def show_message(self, text, duration_ms=1800):
        self.label.setText(text)
        self.adjustSize()
        self._reposition()

        self._fade_out.stop()
        self._hide_timer.stop()

        self.show()
        self.raise_()

        self._fade_in.stop()
        self._fade_in.start()

        self._hide_timer.start(duration_ms)

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return

        margin = 22
        x = parent.width() - self.width() - margin
        y = margin + 64
        self.move(max(0, x), y)


# ============================================================
# REMAP GESTURES DIALOG
# ============================================================

class RemapDialog(QDialog):
    """Lets the user decide which of the four simple gestures
    (Thumb Up/Down, Fist, Open Palm) triggers which action."""

    def __init__(self, current_map, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Remap Gestures")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        heading = QLabel("GESTURE → ACTION")
        heading.setObjectName("Tiny")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)

        self.combos = {}

        for gesture in REMAPPABLE_GESTURES:
            combo = QComboBox()
            combo.addItems(REMAPPABLE_ACTIONS)

            current_action = current_map.get(
                gesture, DEFAULT_ACTION_MAP[gesture]
            )

            if current_action in REMAPPABLE_ACTIONS:
                combo.setCurrentText(current_action)

            form.addRow(f"{gesture}:", combo)
            self.combos[gesture] = combo

        layout.addLayout(form)

        hint = QLabel(
            "Each action can only be assigned once — picking a\n"
            "duplicate will be sorted out automatically."
        )
        hint.setObjectName("DockInfo")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def resulting_map(self):
        """Returns a gesture->action dict with no duplicate actions.
        If the user assigned the same action twice, later entries
        fall back to their default so nothing is silently lost."""

        chosen = {}
        used_actions = set()

        for gesture in REMAPPABLE_GESTURES:
            wanted = self.combos[gesture].currentText()

            if wanted in used_actions:
                # Preferred choice is taken — fall back to this
                # gesture's default, then to whatever action is
                # still free, so no two gestures ever collide.
                fallback = DEFAULT_ACTION_MAP[gesture]

                if fallback not in used_actions:
                    wanted = fallback
                else:
                    wanted = next(
                        a for a in REMAPPABLE_ACTIONS if a not in used_actions
                    )

            used_actions.add(wanted)
            chosen[gesture] = wanted

        return chosen


# ============================================================
# ABOUT DIALOG
# ============================================================

class AboutDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("About GestureOS")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(6)

        logo = QLabel("✦ GESTUREOS")
        logo.setStyleSheet(
            "font-size: 18px; font-weight: 900; letter-spacing: 2px;"
            "color: #7dffd6;"
        )
        layout.addWidget(logo)

        version = QLabel(APP_VERSION)
        version.setObjectName("Tiny")
        layout.addWidget(version)

        layout.addSpacing(10)

        body = QLabel(
            "AI-powered hand gesture control for your desktop.\n"
            "Built with MediaPipe, OpenCV, PySide6 and PyAutoGUI.\n\n"
            "7 gestures map to cursor, click, scroll, volume,\n"
            "screenshot and media pause/play — fully remappable."
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        layout.addSpacing(12)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


# ============================================================
# DRAGGABLE TOP BAR — custom title bar for the frameless window
# ============================================================

class TopBar(QFrame):
    """The header frame doubles as the window's title bar: it can
    be dragged to move the window and double-clicked to toggle
    maximize, since the native OS title bar has been removed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.window()
            self._drag_offset = (
                event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            window = self.window()
            if window.isMaximized():
                return
            window.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        window = self.window()
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()
        super().mouseDoubleClickEvent(event)


# ============================================================
# MAIN WINDOW
# ============================================================

class GestureOS(QMainWindow):

    def __init__(self):

        super().__init__()

        self.worker = CameraWorker()

        self.history = deque(maxlen=8)
        self.calibration_window = None
        self.tray = None
        self.tray_menu = None

        # V6 Advanced Performance Dashboard
        self.session_start = time.perf_counter()
        self.total_frames = 0
        self.total_processed_frames = 0
        self.total_skipped_frames = 0
        self.total_actions = 0
        self.last_dashboard_update = 0.0
        self.tray_start_action = None
        self.tray_pause_action = None

        self._pulse_dots = []

        # Persisted settings (sensitivity, geometry, remap table,
        # launch-at-startup) survive between sessions via QSettings —
        # no extra config files to manage.
        self.settings = QSettings("GestureOS", "GestureOS")

        # Set True only by the tray "Exit" action / real quit path,
        # so the window's own close button just hides to tray.
        self._force_quit = False

        self.toast = None

        self.setup_window()
        self.build_ui()
        self.connect_worker()
        self.setup_tray()
        self.apply_elevation()
        self.load_settings()

        self.toast = ToastNotification(self.centralWidget())

    # ========================================================
    # WINDOW
    # ========================================================

    def setup_window(self):

        self.setWindowTitle(
            "GestureOS — AI Hand Gesture Controller"
        )

        # Frameless window: we draw our own title bar (drag to move,
        # minimize / more-options / close) instead of the OS chrome.
        self.setWindowFlag(Qt.FramelessWindowHint, True)

        self.resize(1600, 960)

        # This must be >= the central widget's real minimumSizeHint
        # (computed from all the panels' content), otherwise Qt lets
        # the window shrink smaller than the layout actually needs —
        # which is exactly what causes panels to overlap/clip.
        self.setMinimumSize(
            1100,
            1000
        )

        self.setStyleSheet(load_stylesheet())

    # ========================================================
    # SHADOW / ELEVATION HELPERS
    # ========================================================

    def make_shadow(self, blur=36, color="#000000", alpha=160, dx=0, dy=10):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        c = QColor(color)
        c.setAlpha(alpha)
        shadow.setColor(c)
        shadow.setOffset(dx, dy)
        return shadow

    def make_glow(self, blur=40, color="#35f0c0", alpha=120):
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(blur)
        c = QColor(color)
        c.setAlpha(alpha)
        glow.setColor(c)
        glow.setOffset(0, 0)
        return glow

    def apply_elevation(self):
        """Apply premium drop-shadows / accent glows to key panels once
        the widget tree has been fully constructed."""

        for widget in [
            self.top_bar,
            self.camera_card,
            self.detection_card,
            self.dashboard_card,
            self.control_dock,
        ]:
            widget.setGraphicsEffect(
                self.make_shadow(blur=42, alpha=150, dy=14)
            )

        # Accent glow on the camera panel — the hero element.
        self.camera_card.setGraphicsEffect(
            self.make_glow(blur=55, color="#35f0c0", alpha=45)
        )

        for card, _gesture, _action_label in self.mapping_cards:
            card.setGraphicsEffect(
                self.make_shadow(blur=18, alpha=110, dy=6)
            )

        for dot in self._pulse_dots:
            dot.start_pulse()

    # ========================================================
    # BUILD UI
    # ========================================================

    def build_ui(self):

        central = QWidget()

        self.setCentralWidget(central)

        root = QVBoxLayout(central)

        root.setContentsMargins(
            22,
            20,
            22,
            20
        )

        root.setSpacing(16)

        # ====================================================
        # TOP HEADER
        # ====================================================

        header = TopBar()

        header.setObjectName("TopBar")
        self.top_bar = header

        header_layout = QHBoxLayout(header)

        header_layout.setContentsMargins(
            22,
            16,
            22,
            16
        )

        logo = QLabel("✦")

        logo.setObjectName("Logo")
        logo.setAlignment(Qt.AlignCenter)

        header_layout.addWidget(logo)

        brand_box = QVBoxLayout()
        brand_box.setSpacing(3)

        title = QLabel("GESTUREOS")

        title.setObjectName("MainTitle")

        subtitle = QLabel(
            "AI HAND INTERFACE  ·  COMPUTER VISION SYSTEM"
        )

        subtitle.setObjectName("SubTitle")

        brand_box.addWidget(title)
        brand_box.addWidget(subtitle)

        header_layout.addLayout(brand_box)

        header_layout.addStretch()

        ai_pill_wrap = QHBoxLayout()
        ai_pill_wrap.setSpacing(8)
        ai_dot = PulsingDot(color="#65ffd0", size=8)
        self._pulse_dots.append(ai_dot)

        self.ai_pill = QLabel(
            "AI CORE READY"
        )

        self.ai_pill.setObjectName("AIPill")

        ai_pill_frame = QFrame()
        ai_pill_frame.setObjectName("AIPillFrame")
        ai_pill_layout = QHBoxLayout(ai_pill_frame)
        ai_pill_layout.setContentsMargins(12, 7, 14, 7)
        ai_pill_layout.setSpacing(8)
        ai_pill_layout.addWidget(ai_dot)
        ai_pill_layout.addWidget(self.ai_pill)
        self.ai_dot = ai_dot

        header_layout.addWidget(ai_pill_frame)

        self.system_status = QLabel(
            "SYSTEM STANDBY"
        )

        self.system_status.setObjectName(
            "SystemPill"
        )

        header_layout.addWidget(
            self.system_status
        )

        # Window controls: since the window is frameless, these
        # replace the OS-native minimize / menu / close buttons.

        window_controls = QHBoxLayout()
        window_controls.setSpacing(6)
        window_controls.setContentsMargins(14, 0, 0, 0)

        self.more_button = QPushButton("⋮")
        self.more_button.setObjectName("WindowButton")
        self.more_button.setFixedSize(32, 32)
        self.more_button.setCursor(Qt.PointingHandCursor)
        self.more_button.clicked.connect(self.open_more_menu)
        window_controls.addWidget(self.more_button)

        self.minimize_button = QPushButton("—")
        self.minimize_button.setObjectName("WindowButton")
        self.minimize_button.setFixedSize(32, 32)
        self.minimize_button.setCursor(Qt.PointingHandCursor)
        self.minimize_button.clicked.connect(self.showMinimized)
        window_controls.addWidget(self.minimize_button)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("CloseButton")
        self.close_button.setFixedSize(32, 32)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.close)
        window_controls.addWidget(self.close_button)

        header_layout.addLayout(window_controls)

        root.addWidget(header)

        # ====================================================
        # MAIN GRID
        # ====================================================

        main_grid = QGridLayout()

        main_grid.setSpacing(16)

        # ====================================================
        # CAMERA PANEL
        # ====================================================

        camera_card = QFrame()

        camera_card.setObjectName(
            "CameraPanel"
        )
        self.camera_card = camera_card

        camera_layout = QVBoxLayout(
            camera_card
        )

        camera_layout.setContentsMargins(
            16,
            16,
            16,
            16
        )

        # Camera top

        cam_top = QHBoxLayout()

        cam_title = QLabel(
            "LIVE VISION"
        )

        cam_title.setObjectName(
            "PanelTitle"
        )

        cam_top.addWidget(cam_title)

        cam_top.addStretch()

        live_wrap = QHBoxLayout()
        live_wrap.setSpacing(6)
        self.live_dot = PulsingDot(color="#54606b", size=7)
        self._pulse_dots.append(self.live_dot)
        live_wrap.addWidget(self.live_dot)

        self.live_badge = QLabel(
            "OFFLINE"
        )

        self.live_badge.setObjectName(
            "LiveBadge"
        )

        live_wrap.addWidget(
            self.live_badge
        )

        cam_top.addLayout(live_wrap)

        camera_layout.addLayout(
            cam_top
        )

        # Camera

        self.camera_label = QLabel()

        self.camera_label.setObjectName(
            "CameraView"
        )

        self.camera_label.setAlignment(
            Qt.AlignCenter
        )

        self.camera_label.setMinimumSize(
            480,
            340
        )

        self.camera_label.setText(
            "✦\n\n"
            "GESTUREOS VISION SYSTEM\n\n"
            "CAMERA OFFLINE\n\n"
            "Press  START CONTROLLER"
        )

        camera_layout.addWidget(
            self.camera_label,
            1
        )

        # Camera HUD

        hud = QHBoxLayout()
        hud.setSpacing(18)

        self.hud_hand = QLabel(
            "HAND  —"
        )

        self.hud_fps = QLabel(
            "FPS  —"
        )

        self.hud_latency = QLabel(
            "LATENCY  —"
        )

        for label in [
            self.hud_hand,
            self.hud_fps,
            self.hud_latency,
        ]:

            label.setObjectName(
                "HUD"
            )

            hud.addWidget(label)

        hud.addStretch()

        camera_layout.addLayout(hud)

        main_grid.addWidget(
            camera_card,
            0,
            0,
            2,
            7
        )

        # ====================================================
        # DETECTION PANEL
        # ====================================================

        detection_card = QFrame()

        detection_card.setObjectName(
            "DetectionPanel"
        )
        self.detection_card = detection_card

        detection_layout = QVBoxLayout(
            detection_card
        )

        detection_layout.setContentsMargins(
            16,
            13,
            16,
            13
        )
        detection_layout.setSpacing(4)

        small = QLabel(
            "CURRENT DETECTION"
        )

        small.setObjectName(
            "Tiny"
        )

        detection_layout.addWidget(small)

        self.gesture_label = QLabel(
            "No Hand"
        )

        self.gesture_label.setObjectName(
            "BigGesture"
        )

        detection_layout.addWidget(
            self.gesture_label
        )

        self.action_label = QLabel(
            "NO ACTION"
        )

        self.action_label.setObjectName(
            "CurrentAction"
        )

        detection_layout.addWidget(
            self.action_label
        )

        detection_layout.addSpacing(6)

        # Confidence

        conf_row = QHBoxLayout()

        conf_name = QLabel(
            "CONFIDENCE"
        )

        conf_name.setObjectName("Tiny")

        self.conf_value = QLabel(
            "0%"
        )

        self.conf_value.setObjectName(
            "Percent"
        )

        conf_row.addWidget(conf_name)
        conf_row.addStretch()
        conf_row.addWidget(self.conf_value)

        detection_layout.addLayout(conf_row)

        self.conf_bar = QProgressBar()

        self.conf_bar.setRange(
            0,
            100
        )

        self.conf_bar.setValue(0)

        self.conf_bar.setTextVisible(False)

        self.conf_bar.setObjectName(
            "Confidence"
        )

        detection_layout.addWidget(
            self.conf_bar
        )

        detection_layout.addSpacing(6)

        # Stability

        stab_row = QHBoxLayout()

        stab_name = QLabel(
            "STABILITY"
        )

        stab_name.setObjectName("Tiny")

        self.stab_value = QLabel(
            "0%"
        )

        self.stab_value.setObjectName(
            "Percent"
        )

        stab_row.addWidget(stab_name)
        stab_row.addStretch()
        stab_row.addWidget(self.stab_value)

        detection_layout.addLayout(stab_row)

        self.stab_bar = QProgressBar()

        self.stab_bar.setRange(
            0,
            100
        )

        self.stab_bar.setValue(0)

        self.stab_bar.setTextVisible(False)

        self.stab_bar.setObjectName(
            "Stability"
        )

        detection_layout.addWidget(
            self.stab_bar
        )

        detection_layout.addStretch()

        # AI status

        self.detection_status = QLabel(
            "WAITING FOR HAND..."
        )

        self.detection_status.setObjectName(
            "DetectionStatus"
        )

        detection_layout.addWidget(
            self.detection_status
        )

        main_grid.addWidget(
            detection_card,
            0,
            7,
            1,
            3
        )

        # (Standalone "System Telemetry" panel was merged into the
        # unified "Performance Intelligence" sidebar card below —
        # see the dash_grid section — to save a full card's worth
        # of margins/title height and keep the sidebar compact.)

        # ====================================================
        # V6 ADVANCED PERFORMANCE DASHBOARD
        # (lives in the right sidebar now, stacked under Telemetry,
        # so the camera panel can take the full vertical height)
        # ====================================================

        dashboard_card = QFrame()
        dashboard_card.setObjectName("Panel")
        self.dashboard_card = dashboard_card

        dashboard_layout = QVBoxLayout(dashboard_card)
        dashboard_layout.setContentsMargins(16, 12, 16, 12)
        dashboard_layout.setSpacing(6)

        dashboard_top = QHBoxLayout()

        dashboard_title = QLabel("PERFORMANCE INTELLIGENCE")
        dashboard_title.setObjectName("PanelTitle")
        dashboard_top.addWidget(dashboard_title)
        dashboard_top.addStretch()

        self.session_uptime = QLabel("UPTIME 00:00:00")
        self.session_uptime.setObjectName("DashboardTiny")
        dashboard_top.addWidget(self.session_uptime)

        dashboard_layout.addLayout(dashboard_top)

        # 2 columns x 4 rows fits a narrow sidebar much better than
        # the old 4 columns x 2 rows, which used to force this panel
        # to be very wide (hence living in a separate full-width strip).

        dash_grid = QGridLayout()
        dash_grid.setSpacing(6)

        # 3 columns x 4 rows fits the same 12 metrics in noticeably
        # less vertical space than the old 2 x 6 arrangement.

        self.fps_metric = self.dashboard_metric(
            dash_grid, 0, 0, "FPS", "0.0"
        )
        self.latency_metric = self.dashboard_metric(
            dash_grid, 0, 1, "LATENCY", "—"
        )
        self.hand_metric = self.dashboard_metric(
            dash_grid, 0, 2, "HAND", "None"
        )

        self.state_metric = self.dashboard_metric(
            dash_grid, 1, 0, "CONTROL", "OFF"
        )
        self.capture_metric = self.dashboard_metric(
            dash_grid, 1, 1, "CAPTURE FPS", "0.0"
        )
        self.process_metric = self.dashboard_metric(
            dash_grid, 1, 2, "AI FPS", "0.0"
        )

        self.process_time_metric = self.dashboard_metric(
            dash_grid, 2, 0, "AI PROCESS", "—"
        )
        self.skip_metric = self.dashboard_metric(
            dash_grid, 2, 1, "SKIP RATE", "0%"
        )
        self.frame_metric = self.dashboard_metric(
            dash_grid, 2, 2, "FRAMES", "0"
        )

        self.action_metric = self.dashboard_metric(
            dash_grid, 3, 0, "ACTIONS", "0"
        )
        self.confidence_metric = self.dashboard_metric(
            dash_grid, 3, 1, "CONFIDENCE", "0%"
        )
        self.stability_metric = self.dashboard_metric(
            dash_grid, 3, 2, "STABILITY", "0%"
        )

        dashboard_layout.addLayout(dash_grid)

        sparkline_title = QLabel("FPS TREND")
        sparkline_title.setObjectName("Tiny")
        dashboard_layout.addWidget(sparkline_title)

        self.fps_sparkline = FpsSparkline(max_points=60)
        self.fps_sparkline.setObjectName("Sparkline")
        dashboard_layout.addWidget(self.fps_sparkline)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.dashboard_dot = PulsingDot(color="#5fcdb4", size=7)
        self._pulse_dots.append(self.dashboard_dot)
        status_row.addWidget(self.dashboard_dot)

        self.dashboard_status = QLabel(
            "PERFORMANCE MONITOR READY"
        )
        self.dashboard_status.setObjectName("DashboardStatus")
        status_row.addWidget(self.dashboard_status)
        status_row.addStretch()

        dashboard_layout.addLayout(status_row)

        main_grid.addWidget(
            dashboard_card,
            1,
            7,
            1,
            3
        )

        root.addLayout(
            main_grid,
            1
        )

        # ====================================================
        # CONTROL DOCK
        # ====================================================

        control_dock = QFrame()

        control_dock.setObjectName(
            "ControlDock"
        )
        self.control_dock = control_dock

        control_layout = QHBoxLayout(
            control_dock
        )

        control_layout.setContentsMargins(
            18,
            13,
            18,
            13
        )
        control_layout.setSpacing(12)

        self.start_button = QPushButton(
            "▶   START CONTROLLER"
        )

        self.start_button.setObjectName(
            "StartButton"
        )
        self.start_button.setCursor(Qt.PointingHandCursor)

        self.start_button.clicked.connect(
            self.toggle_controller
        )

        control_layout.addWidget(
            self.start_button
        )

        self.calibration_button = QPushButton(
            "⚙   CALIBRATE"
        )

        self.calibration_button.setObjectName(
            "CalibrationButton"
        )
        self.calibration_button.setCursor(Qt.PointingHandCursor)

        self.calibration_button.clicked.connect(
            self.open_calibration
        )

        control_layout.addWidget(
            self.calibration_button
        )

        self.enable_button = QPushButton(
            "●   ACTIVE"
        )

        self.enable_button.setObjectName(
            "ControlButton"
        )

        self.enable_button.setEnabled(
            False
        )
        self.enable_button.setCursor(Qt.PointingHandCursor)

        self.enable_button.clicked.connect(
            self.toggle_enabled
        )

        control_layout.addWidget(
            self.enable_button
        )

        divider = QFrame()

        divider.setObjectName(
            "Divider"
        )

        divider.setFixedWidth(1)

        control_layout.addWidget(
            divider
        )

        sens_title = QLabel(
            "CURSOR SENSITIVITY"
        )

        sens_title.setObjectName(
            "Tiny"
        )

        control_layout.addWidget(
            sens_title
        )

        self.sensitivity_slider = QSlider(
            Qt.Horizontal
        )

        self.sensitivity_slider.setMinimum(10)
        self.sensitivity_slider.setMaximum(60)
        self.sensitivity_slider.setValue(30)

        self.sensitivity_slider.setMinimumWidth(
            210
        )
        self.sensitivity_slider.setCursor(Qt.PointingHandCursor)

        self.sensitivity_slider.valueChanged.connect(
            self.change_sensitivity
        )

        control_layout.addWidget(
            self.sensitivity_slider
        )

        self.sensitivity_value = QLabel(
            "30"
        )

        self.sensitivity_value.setObjectName(
            "SliderValue"
        )

        control_layout.addWidget(
            self.sensitivity_value
        )

        control_layout.addStretch()

        self.control_info = QLabel(
            "7 GESTURES  ·  REAL-TIME AI"
        )

        self.control_info.setObjectName(
            "DockInfo"
        )

        control_layout.addWidget(
            self.control_info
        )

        root.addWidget(
            control_dock
        )

        # ====================================================
        # GESTURE STRIP
        # ====================================================

        gesture_header = QHBoxLayout()

        gesture_title = QLabel(
            "GESTURE COMMAND MATRIX"
        )

        gesture_title.setObjectName(
            "PanelTitle"
        )

        gesture_header.addWidget(
            gesture_title
        )

        gesture_header.addStretch()

        gesture_hint = QLabel(
            "7 ACTIVE COMMANDS"
        )

        gesture_hint.setObjectName(
            "Tiny"
        )

        gesture_header.addWidget(
            gesture_hint
        )

        root.addLayout(
            gesture_header
        )

        gesture_grid = QGridLayout()

        gesture_grid.setSpacing(10)

        mappings = [
            ("☝", "POINT", "CURSOR"),
            ("🤏", "PINCH", "LEFT CLICK"),
            ("✌", "PEACE", "SCROLL"),
            ("👍", "THUMB UP", "VOLUME +"),
            ("👎", "THUMB DOWN", "VOLUME −"),
            ("✊", "FIST", "SCREENSHOT"),
            ("✋", "OPEN PALM", "PAUSE / PLAY"),
        ]

        self.mapping_cards = []

        for index, (
            icon,
            gesture,
            action
        ) in enumerate(mappings):

            card = QFrame()

            card.setObjectName(
                "GestureTile"
            )

            tile_layout = QHBoxLayout(card)

            tile_layout.setContentsMargins(
                12,
                10,
                12,
                10
            )
            tile_layout.setSpacing(10)

            icon_wrap = QFrame()
            icon_wrap.setObjectName("TileIconWrap")
            icon_wrap_layout = QVBoxLayout(icon_wrap)
            icon_wrap_layout.setContentsMargins(0, 0, 0, 0)

            icon_label = QLabel(icon)

            icon_label.setObjectName(
                "TileIcon"
            )
            icon_label.setAlignment(Qt.AlignCenter)
            icon_wrap_layout.addWidget(icon_label)

            tile_layout.addWidget(
                icon_wrap
            )

            text = QVBoxLayout()
            text.setSpacing(2)

            gesture_name = QLabel(
                gesture
            )

            gesture_name.setObjectName(
                "TileGesture"
            )

            action_name = QLabel(
                action
            )

            action_name.setObjectName(
                "TileAction"
            )

            text.addWidget(
                gesture_name
            )

            text.addWidget(
                action_name
            )

            tile_layout.addLayout(text)
            tile_layout.addStretch()

            row = index // 4
            column = index % 4

            gesture_grid.addWidget(
                card,
                row,
                column
            )

            self.mapping_cards.append(
                (card, gesture, action_name)
            )

        root.addLayout(
            gesture_grid
        )

        # ====================================================
        # HISTORY
        # ====================================================

        bottom = QHBoxLayout()

        history_title = QLabel(
            "RECENT ACTIVITY"
        )

        history_title.setObjectName(
            "PanelTitle"
        )

        bottom.addWidget(
            history_title
        )

        bottom.addStretch()

        self.history_label = QLabel(
            "No actions recorded yet."
        )

        self.history_label.setObjectName(
            "HistoryLine"
        )

        bottom.addWidget(
            self.history_label
        )

        root.addLayout(bottom)

        # ====================================================
        # FOOTER
        # ====================================================

        footer = QLabel(
            "GESTUREOS  ·  COMPUTER VISION  ·  "
            "MEDIAPIPE  ·  PYAUTOGUI  ·  REAL-TIME CONTROL"
        )

        footer.setObjectName(
            "Footer"
        )

        footer.setAlignment(
            Qt.AlignCenter
        )

        root.addWidget(footer)

    # ========================================================
    # V6 DASHBOARD METRIC
    # ========================================================

    def dashboard_metric(
        self,
        grid,
        row,
        column,
        title,
        value
    ):
        box = QFrame()
        box.setObjectName("DashboardBox")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(9, 6, 9, 6)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("DashboardTiny")

        value_label = QLabel(value)
        value_label.setObjectName("DashboardValue")

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        grid.addWidget(box, row, column)

        return value_label

    # ========================================================
    # METRIC BOX
    # ========================================================

    def metric_box(
        self,
        grid,
        row,
        column,
        title,
        value
    ):

        box = QFrame()

        box.setObjectName(
            "TelemetryBox"
        )

        layout = QVBoxLayout(box)

        layout.setContentsMargins(
            10,
            8,
            10,
            8
        )
        layout.setSpacing(2)

        title_label = QLabel(title)

        title_label.setObjectName(
            "Tiny"
        )

        value_label = QLabel(value)

        value_label.setObjectName(
            "TelemetryValue"
        )

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        grid.addWidget(
            box,
            row,
            column
        )

        return value_label

    # ========================================================
    # SIGNALS
    # ========================================================

    def connect_worker(self):

        self.worker.frame_ready.connect(
            self.update_frame
        )

        self.worker.state_ready.connect(
            self.update_state
        )

        self.worker.error.connect(
            self.show_error
        )

    # ========================================================
    # SYSTEM TRAY
    # ========================================================

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.windowIcon())
        self.tray.setToolTip("GestureOS — AI Hand Gesture Controller")

        self.tray_menu = QMenu(self)

        open_action = QAction("Open GestureOS", self)
        open_action.triggered.connect(self.show_from_tray)
        self.tray_menu.addAction(open_action)

        self.tray_start_action = QAction("▶ Start Controller", self)
        self.tray_start_action.triggered.connect(self.tray_toggle_controller)
        self.tray_menu.addAction(self.tray_start_action)

        self.tray_pause_action = QAction("○ Disable Controls", self)
        self.tray_pause_action.setEnabled(False)
        self.tray_pause_action.triggered.connect(self.toggle_enabled)
        self.tray_menu.addAction(self.tray_pause_action)

        self.tray_menu.addSeparator()

        calibration_action = QAction("⚙ Calibration", self)
        calibration_action.triggered.connect(self.open_calibration)
        self.tray_menu.addAction(calibration_action)

        self.tray_menu.addSeparator()

        exit_action = QAction("✕ Exit GestureOS", self)
        exit_action.triggered.connect(self.exit_application)
        self.tray_menu.addAction(exit_action)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_from_tray()

    def show_from_tray(self):
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_toggle_controller(self):
        if self.worker.running:
            self.stop_controller()
        else:
            self.start_controller()
        self.update_tray_actions()

    def update_tray_actions(self):
        if self.tray_start_action is None:
            return
        if self.worker.running:
            self.tray_start_action.setText("■ Stop Controller")
            self.tray_pause_action.setEnabled(True)
            self.tray_pause_action.setText(
                "○ Enable Controls" if not self.worker.controller_enabled
                else "○ Disable Controls"
            )
        else:
            self.tray_start_action.setText("▶ Start Controller")
            self.tray_pause_action.setEnabled(False)
            self.tray_pause_action.setText("○ Disable Controls")

    def exit_application(self):
        self._force_quit = True
        self.save_settings()
        if self.tray is not None:
            self.tray.hide()
        try:
            self.worker.stop()
        except Exception:
            pass
        QApplication.quit()

    # ========================================================
    # MORE MENU (⋮) — remap gestures, launch at startup, about
    # ========================================================

    def open_more_menu(self):

        menu = QMenu(self)

        remap_action = QAction("🎛  Remap Gestures", self)
        remap_action.triggered.connect(self.open_remap_dialog)
        menu.addAction(remap_action)

        menu.addSeparator()

        startup_action = QAction("🚀  Launch at Windows Startup", self)
        startup_action.setCheckable(True)
        startup_action.setChecked(self.is_launch_at_startup_enabled())
        startup_action.triggered.connect(self.toggle_launch_at_startup)
        menu.addAction(startup_action)

        menu.addSeparator()

        about_action = QAction("ⓘ  About GestureOS", self)
        about_action.triggered.connect(self.open_about_dialog)
        menu.addAction(about_action)

        menu.exec(
            self.more_button.mapToGlobal(
                self.more_button.rect().bottomRight()
            )
        )

    def open_remap_dialog(self):

        dialog = RemapDialog(self.worker.get_action_map(), self)

        if dialog.exec() == QDialog.Accepted:
            new_map = dialog.resulting_map()
            self.worker.set_action_map(new_map)
            self.save_settings()
            self.refresh_gesture_matrix_labels()

            if self.toast is not None:
                self.toast.show_message("GESTURES REMAPPED")

            logger.info("Gesture map updated: %s", new_map)

    def refresh_gesture_matrix_labels(self):
        """After a remap, update the 'GESTURE COMMAND MATRIX' tiles
        so their action labels reflect the new mapping."""

        current_map = self.worker.get_action_map()

        for card, gesture, action_label in self.mapping_cards:
            if gesture in current_map:
                mapped = current_map[gesture]
                action_label.setText(
                    ACTION_DISPLAY_TEXT.get(mapped, mapped.upper())
                )

    def open_about_dialog(self):
        AboutDialog(self).exec()

    def is_launch_at_startup_enabled(self):
        if sys.platform != "win32":
            return False

        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            )
            try:
                winreg.QueryValueEx(key, "GestureOS")
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)

        except Exception:
            return False

    def toggle_launch_at_startup(self, checked):

        if sys.platform != "win32":
            if self.toast is not None:
                self.toast.show_message(
                    "STARTUP LAUNCH IS WINDOWS-ONLY"
                )
            return

        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )

            if checked:
                exe_path = os.path.abspath(sys.argv[0])
                winreg.SetValueEx(
                    key, "GestureOS", 0, winreg.REG_SZ, f'"{sys.executable}" "{exe_path}"'
                )
                message = "WILL LAUNCH AT STARTUP"
            else:
                try:
                    winreg.DeleteValue(key, "GestureOS")
                except FileNotFoundError:
                    pass
                message = "STARTUP LAUNCH DISABLED"

            winreg.CloseKey(key)

            if self.toast is not None:
                self.toast.show_message(message)

        except Exception as error:
            logger.error("Could not update startup registry entry: %s", error)
            if self.toast is not None:
                self.toast.show_message("COULD NOT UPDATE STARTUP SETTING")

    # ========================================================
    # SETTINGS PERSISTENCE
    # ========================================================

    def load_settings(self):

        try:
            sensitivity = int(self.settings.value("sensitivity", 30))
            sensitivity = max(10, min(60, sensitivity))
            self.sensitivity_slider.setValue(sensitivity)
        except Exception:
            pass

        try:
            action_map = {}
            for gesture in REMAPPABLE_GESTURES:
                key = f"action_map/{gesture}"
                stored = self.settings.value(key, None)
                if stored in REMAPPABLE_ACTIONS:
                    action_map[gesture] = stored

            if action_map:
                self.worker.set_action_map(action_map)
                self.refresh_gesture_matrix_labels()
        except Exception:
            pass

        try:
            geometry = self.settings.value("window_geometry", None)
            if geometry is not None:
                self.restoreGeometry(geometry)
        except Exception:
            pass

    def save_settings(self):

        try:
            self.settings.setValue(
                "sensitivity", self.sensitivity_slider.value()
            )

            current_map = self.worker.get_action_map()
            for gesture, action in current_map.items():
                self.settings.setValue(f"action_map/{gesture}", action)

            self.settings.setValue("window_geometry", self.saveGeometry())

            self.settings.sync()

        except Exception as error:
            logger.warning("Could not save settings: %s", error)

    # ========================================================
    # CONTROLLER
    # ========================================================

    def toggle_controller(self):

        if self.worker.running:
            self.stop_controller()
        else:
            self.start_controller()

    def open_calibration(self):

        if self.calibration_window is not None:
            try:
                if self.calibration_window.isVisible():
                    self.calibration_window.raise_()
                    self.calibration_window.activateWindow()
                    return
            except RuntimeError:
                self.calibration_window = None

        try:
            if not self.worker.running:
                self.start_controller()

            if not self.worker.running:
                self.show_error(
                    "Calibration could not start: camera engine is not running."
                )
                return

            # Lazy import: calibration problems cannot stop the main app.
            from core.calibration_ui import CalibrationWindow

            gesture_engine = getattr(
                self.worker.engine,
                "gesture_engine",
                None,
            )
            calibration_manager = getattr(
                self.worker.engine,
                "calibration_manager",
                None,
            )

            if gesture_engine is None or calibration_manager is None:
                raise RuntimeError(
                    "Calibration services are not initialized. Restart the controller first."
                )

            self.worker.set_enabled(False)

            self.enable_button.setText(
                "○   DISABLED"
            )
            self.system_status.setText(
                "CALIBRATION MODE"
            )
            self.engine_status_text(
                "● CALIBRATION ENGINE READY"
            )

            self.calibration_window = CalibrationWindow(
                self.worker.engine,
                gesture_engine,
                calibration_manager,
                self,
            )

            if hasattr(self.calibration_window, "calibration_finished"):
                self.calibration_window.calibration_finished.connect(
                    self.calibration_complete
                )

            self.calibration_window.setAttribute(
                Qt.WA_DeleteOnClose,
                True,
            )
            self.calibration_window.show()
            self.calibration_window.raise_()
            self.calibration_window.activateWindow()

        except Exception as error:
            if self.worker.running:
                self.worker.set_enabled(True)
                self.enable_button.setText("●   ACTIVE")
            self.show_error(
                f"Calibration error: {error}"
            )

    def calibration_complete(self):

        try:
            self.worker.engine.apply_calibration()
            self.worker.set_enabled(True)

            self.enable_button.setText(
                "●   ACTIVE"
            )
            self.system_status.setText(
                "CONTROLLER ACTIVE"
            )
            self.engine_status_text(
                "● CALIBRATION APPLIED"
            )
            self.calibration_button.setText(
                "✓   CALIBRATED"
            )

            if self.calibration_window is not None:
                try:
                    self.calibration_window.close()
                except Exception:
                    pass
                self.calibration_window = None

        except Exception as error:
            self.show_error(
                f"Calibration apply error: {error}"
            )

    def start_controller(self):

        self.worker.start()

        if not self.worker.running:
            return

        self.session_start = time.perf_counter()
        self.total_frames = 0
        self.total_processed_frames = 0
        self.total_skipped_frames = 0
        self.total_actions = 0
        self.last_dashboard_update = 0.0

        self.start_button.setText(
            "■   STOP CONTROLLER"
        )
        self.update_tray_actions()

        self.enable_button.setEnabled(
            True
        )

        self.enable_button.setText(
            "●   ACTIVE"
        )

        self.live_badge.setText(
            "LIVE"
        )
        self.live_dot.set_color("#52e5bf")

        self.system_status.setText(
            "SYSTEM ACTIVE"
        )

        self.ai_pill.setText(
            "AI CORE ONLINE"
        )

        self.engine_status_text(
            "● TRACKING ENGINE ACTIVE"
        )

    def stop_controller(self):

        self.worker.stop()

        self.start_button.setText(
            "▶   START CONTROLLER"
        )

        self.enable_button.setEnabled(
            False
        )

        self.enable_button.setText(
            "●   ACTIVE"
        )

        self.live_badge.setText(
            "OFFLINE"
        )
        self.live_dot.set_color("#54606b")

        self.system_status.setText(
            "SYSTEM STANDBY"
        )

        self.ai_pill.setText(
            "AI CORE READY"
        )

        self.camera_label.clear()

        self.camera_label.setText(
            "✦\n\n"
            "GESTUREOS VISION SYSTEM\n\n"
            "CAMERA OFFLINE\n\n"
            "Press  START CONTROLLER"
        )

        self.gesture_label.setText(
            "No Hand"
        )

        self.action_label.setText(
            "NO ACTION"
        )

        self.conf_value.setText("0%")
        self.stab_value.setText("0%")

        self.conf_bar.setValue(0)
        self.stab_bar.setValue(0)

        self.fps_metric.setText("0.0")
        self.latency_metric.setText("—")
        self.hand_metric.setText("None")
        self.state_metric.setText("OFF")

        if hasattr(self, "fps_sparkline"):
            self.fps_sparkline.clear_data()

        self.session_uptime.setText("UPTIME 00:00:00")
        self.capture_metric.setText("0.0")
        self.process_metric.setText("0.0")
        self.process_time_metric.setText("—")
        self.skip_metric.setText("0%")
        self.frame_metric.setText("0")
        self.action_metric.setText("0")
        self.confidence_metric.setText("0%")
        self.stability_metric.setText("0%")
        self.dashboard_status.setText(
            "PERFORMANCE MONITOR READY"
        )
        self.dashboard_dot.set_color("#5fcdb4")

        self.hud_hand.setText("HAND  —")
        self.hud_fps.setText("FPS  —")
        self.hud_latency.setText("LATENCY  —")

        self.detection_status.setText(
            "WAITING FOR HAND..."
        )

        self.engine_status_text(
            "● TRACKING ENGINE STANDBY"
        )
        self.update_tray_actions()

    # ========================================================
    # ENABLE
    # ========================================================

    def toggle_enabled(self):

        if not self.worker.running:
            return

        enabled = not self.worker.controller_enabled

        self.worker.set_enabled(
            enabled
        )

        if enabled:

            self.enable_button.setText(
                "●   ACTIVE"
            )

            self.system_status.setText(
                "CONTROLLER ACTIVE"
            )

            self.engine_status_text(
                "● TRACKING ENGINE ACTIVE"
            )

        else:

            self.enable_button.setText(
                "○   DISABLED"
            )

            self.system_status.setText(
                "CONTROLLER PAUSED"
            )

            self.engine_status_text(
                "○ TRACKING ENGINE PAUSED"
            )

    # ========================================================
    # ENGINE STATUS
    # ========================================================

    def engine_status_text(self, text):

        self.control_info.setText(
            text
        )

    # ========================================================
    # SENSITIVITY
    # ========================================================

    def change_sensitivity(
        self,
        value
    ):

        self.sensitivity_value.setText(
            str(value)
        )

        self.worker.set_sensitivity(
            value
        )

    # ========================================================
    # FRAME
    # ========================================================

    def update_frame(
        self,
        frame
    ):

        if frame is None:
            return

        rgb = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        height, width, channels = (
            rgb.shape
        )

        bytes_per_line = (
            channels * width
        )

        image = QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888
        ).copy()

        pixmap = QPixmap.fromImage(
            image
        )

        scaled = pixmap.scaled(
            self.camera_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.camera_label.setPixmap(
            scaled
        )

    # ========================================================
    # STATE
    # ========================================================

    def update_state(
        self,
        state
    ):

        gesture = state["gesture"]

        hand = state.get("hand") or "Hand"
        if not isinstance(hand, str):
            hand = str(hand)

        confidence = state.get("confidence", 0.0)

        fps = state.get("fps", 0.0)

        action = state.get("action", "NO ACTION")

        enabled = bool(state.get("enabled", False))

        stability = state.get(
            "stability",
            0
        )

        latency = state.get(
            "latency",
            0
        )

        # Normalize confidence/stability before the V6 dashboard
        # uses them. This fixes the first-frame UnboundLocalError.
        try:
            confidence_value = max(0, min(100, int(float(confidence or 0))))
        except (TypeError, ValueError):
            confidence_value = 0

        try:
            stability_value = max(0, min(100, int(float(stability or 0))))
        except (TypeError, ValueError):
            stability_value = 0

        # ====================================================
        # V6 PERFORMANCE INTELLIGENCE
        # ====================================================

        capture_fps = state.get("capture_fps", 0.0)
        processing_fps = state.get("processing_fps", 0.0)
        processing_time_ms = state.get("processing_time_ms", 0.0)
        processed_frames = state.get("processed_frames", 0)
        skipped_frames = state.get("skipped_frames", 0)

        self.total_frames = (
            int(processed_frames) + int(skipped_frames)
        )
        self.total_processed_frames = int(processed_frames)
        self.total_skipped_frames = int(skipped_frames)

        if action in [
            "LEFT CLICK",
            "SCROLL UP",
            "SCROLL DOWN",
            "VOLUME UP",
            "VOLUME DOWN",
            "SCREENSHOT",
            "PAUSE / PLAY",
        ]:
            self.total_actions += 1

        total_seen = self.total_frames
        skip_rate = (
            (self.total_skipped_frames / total_seen) * 100
            if total_seen > 0 else 0
        )

        uptime_seconds = max(
            0,
            int(time.perf_counter() - self.session_start)
        )
        uptime_minutes, uptime_seconds = divmod(
            uptime_seconds,
            60
        )
        uptime_hours, uptime_minutes = divmod(
            uptime_minutes,
            60
        )

        now_dashboard = time.perf_counter()
        if now_dashboard - self.last_dashboard_update >= 0.20:
            self.session_uptime.setText(
                f"UPTIME {uptime_hours:02d}:{uptime_minutes:02d}:{uptime_seconds:02d}"
            )
            self.capture_metric.setText(
                f"{capture_fps:.1f}"
            )
            self.process_metric.setText(
                f"{processing_fps:.1f}"
            )
            self.process_time_metric.setText(
                f"{processing_time_ms:.1f} ms"
            )
            self.skip_metric.setText(
                f"{skip_rate:.0f}%"
            )
            self.frame_metric.setText(
                f"{self.total_frames:,}"
            )
            self.action_metric.setText(
                f"{self.total_actions:,}"
            )
            self.confidence_metric.setText(
                f"{confidence_value}%"
            )
            self.stability_metric.setText(
                f"{stability_value}%"
            )

            if not enabled:
                self.dashboard_status.setText(
                    "CONTROL INPUT PAUSED"
                )
                self.dashboard_dot.set_color("#7a8790")
            elif processing_time_ms > 45:
                self.dashboard_status.setText(
                    "HIGH AI PROCESSING LOAD"
                )
                self.dashboard_dot.set_color("#ffc857")
            elif processing_fps > 0 and processing_fps < 18:
                self.dashboard_status.setText(
                    "LOW AI PROCESSING RATE"
                )
                self.dashboard_dot.set_color("#ffc857")
            else:
                self.dashboard_status.setText(
                    "PERFORMANCE NOMINAL"
                )
                self.dashboard_dot.set_color("#5fcdb4")

            self.last_dashboard_update = now_dashboard

        # Gesture

        self.gesture_label.setText(
            gesture
        )

        self.action_label.setText(
            action
        )

        # Confidence

        self.conf_value.setText(
            f"{confidence_value}%"
        )

        self.conf_bar.setValue(
            confidence_value
        )

        # Stability

        self.stab_value.setText(
            f"{stability_value}%"
        )

        self.stab_bar.setValue(
            stability_value
        )

        # Metrics

        self.fps_metric.setText(
            f"{fps:.1f}"
        )

        self.latency_metric.setText(
            f"{latency:.1f} ms"
        )

        self.hand_metric.setText(
            hand or "None"
        )

        self.state_metric.setText(
            "ON" if enabled else "OFF"
        )

        # HUD

        self.hud_hand.setText(
            f"HAND  {(hand or "NONE").upper()}"
        )

        self.hud_fps.setText(
            f"FPS  {fps:.1f}"
        )

        self.hud_latency.setText(
            f"LATENCY  {latency:.1f} ms"
        )

        # Detection status

        if gesture == "No Hand":

            self.detection_status.setText(
                "SEARCHING FOR HAND..."
            )

        elif stability >= 80:

            self.detection_status.setText(
                "● GESTURE LOCKED"
            )

        elif stability >= 50:

            self.detection_status.setText(
                "◐ ANALYZING GESTURE..."
            )

        else:

            self.detection_status.setText(
                "○ STABILIZING..."
            )

        # Highlight gesture

        self.highlight_mapping(
            gesture
        )

        # History

        important_actions = [
            "LEFT CLICK",
            "SCROLL UP",
            "SCROLL DOWN",
            "VOLUME UP",
            "VOLUME DOWN",
            "SCREENSHOT",
            "PAUSE / PLAY",
        ]

        if action in important_actions:

            if (
                not self.history
                or self.history[0][0] != action
            ):

                self.history.appendleft(
                    (
                        action,
                        time.strftime(
                            "%H:%M:%S"
                        )
                    )
                )

                self.refresh_history()

                if self.toast is not None:
                    self.toast.show_message(action)

        # Live FPS trend

        if hasattr(self, "fps_sparkline"):
            self.fps_sparkline.push(fps)

    # ========================================================
    # GESTURE HIGHLIGHT
    # ========================================================

    def highlight_mapping(
        self,
        gesture
    ):

        for card, card_gesture, _action_label in self.mapping_cards:

            if (
                gesture.upper()
                == card_gesture
            ):

                card.setProperty(
                    "active",
                    True
                )

            else:

                card.setProperty(
                    "active",
                    False
                )

            card.style().unpolish(card)
            card.style().polish(card)
            card.update()

    # ========================================================
    # HISTORY
    # ========================================================

    def refresh_history(self):

        if not self.history:

            self.history_label.setText(
                "No actions recorded yet."
            )

            return

        latest = self.history[0]

        if len(self.history) == 1:

            text = (
                f"● {latest[0]}   "
                f"{latest[1]}"
            )

        else:

            text = (
                f"● {latest[0]}   {latest[1]}"
                f"     ·     "
                f"+{len(self.history) - 1} previous"
            )

        self.history_label.setText(
            text
        )

    # ========================================================
    # ERROR
    # ========================================================

    def show_error(
        self,
        message
    ):

        self.system_status.setText(
            "SYSTEM ERROR"
        )

        self.ai_pill.setText(
            "AI CORE ERROR"
        )
        self.ai_dot.set_color("#ff6a6a")

        self.live_badge.setText(
            "SENSOR ERROR"
        )
        self.live_dot.set_color("#ff6a6a")

        self.action_label.setText(
            "ERROR"
        )

        self.detection_status.setText(
            "CAMERA / AI ERROR"
        )

        # Keep the premium UI, but expose the real exception in the
        # log instead of hiding it behind a generic SENSOR ERROR.
        logger.error("GestureOS camera/AI error: %s", message)

        if self.toast is not None:
            self.toast.show_message(
                f"CAMERA / AI ERROR  ·  {message}"
            )


    # ========================================================
    # CLOSE
    # ========================================================

    def closeEvent(
        self,
        event
    ):
        # --------------------------------------------------------
        # MINIMIZE TO TRAY
        # The window's own close (✕) button just hides the window
        # to the system tray, keeping the controller running in the
        # background. Only the tray's "Exit GestureOS" action (or a
        # platform without tray support) performs a real shutdown.
        # --------------------------------------------------------
        if (
            not self._force_quit
            and self.tray is not None
            and self.tray.isVisible()
        ):
            self.save_settings()
            event.ignore()
            self.hide()

            if self.toast is None:
                self.toast = ToastNotification(self.centralWidget())

            if self.tray is not None:
                self.tray.showMessage(
                    "GestureOS",
                    "Still running in the background. "
                    "Right-click the tray icon to exit.",
                    QSystemTrayIcon.Information,
                    2500,
                )
            return

        # --------------------------------------------------------
        # HARD CLEAN EXIT
        # Closing the main window must also terminate the Qt
        # event loop so the VS Code terminal returns immediately.
        # --------------------------------------------------------
        try:
            self.save_settings()

            if getattr(self, "calibration_window", None) is not None:
                try:
                    self.calibration_window.close()
                except Exception:
                    pass
                self.calibration_window = None

            if self.tray is not None:
                try:
                    self.tray.hide()
                except Exception:
                    pass

            if hasattr(self, "worker") and self.worker is not None:
                try:
                    self.worker.stop()
                except Exception:
                    pass

                try:
                    if getattr(self.worker, "timer", None) is not None:
                        self.worker.timer.stop()
                except Exception:
                    pass

        finally:
            event.accept()

            # Explicitly terminate QApplication. This is important
            # because GestureOS also creates a system-tray icon.
            QTimer.singleShot(0, QApplication.quit)

    # ========================================================
    # STYLE — PREMIUM DARK GLASS THEME
    # ========================================================

# ============================================================
# EXTERNAL STYLESHEET
# ============================================================

def load_stylesheet():
    """Load the UI theme from assets/style.css without touching gesture logic."""
    css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "style.css")
    try:
        with open(css_path, "r", encoding="utf-8") as file:
            return file.read()
    except OSError as error:
        logger.error("Could not load stylesheet %s: %s", css_path, error)
        return ""




# ============================================================
# APPLICATION
# ============================================================

def build_splash_pixmap():
    """Draws a small branded splash screen with QPainter — no image
    asset required, so it costs nothing extra to ship."""

    pixmap = QPixmap(420, 260)
    pixmap.fill(QColor("#05070c"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    painter.setPen(QPen(QColor("#1c2b34")))
    painter.setBrush(QColor("#080d14"))
    painter.drawRoundedRect(pixmap.rect().adjusted(1, 1, -1, -1), 18, 18)

    painter.setPen(QColor("#7dffd6"))
    painter.setFont(QFont("Segoe UI", 34, QFont.Black))
    painter.drawText(
        QRect(0, 70, 420, 60), Qt.AlignCenter, "✦ GESTUREOS"
    )

    painter.setPen(QColor("#5c7079"))
    painter.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
    painter.drawText(
        QRect(0, 130, 420, 26),
        Qt.AlignCenter,
        "AI HAND INTERFACE  ·  COMPUTER VISION SYSTEM",
    )

    painter.setPen(QColor("#3fc9a9"))
    painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
    painter.drawText(
        QRect(0, 210, 420, 24), Qt.AlignCenter, f"Loading  {APP_VERSION}..."
    )

    painter.end()
    return pixmap


def main():

    try:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        app.setApplicationName("GestureOS")
        app.setQuitOnLastWindowClosed(True)

        splash = QSplashScreen(build_splash_pixmap())
        splash.show()
        app.processEvents()

        window = GestureOS()

        QTimer.singleShot(700, lambda: (
            window.show(),
            window.raise_(),
            window.activateWindow(),
            splash.finish(window),
        ))

        return app.exec()

    except Exception:
        logger.exception("Fatal error while starting GestureOS")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
