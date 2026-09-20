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
from PySide6.QtGui import (
    QImage,
    QPixmap,
    QIcon,
    QAction,
    QColor,
    QPainter,
    QPen,
    QFont,
)
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
    QSizePolicy,
)

from core.camera_engine import CameraEngine
from core.controller import GestureController


# ============================================================
# LOGGING
# ============================================================

_LOG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "logs",
)

try:
    os.makedirs(_LOG_DIR, exist_ok=True)
except Exception:
    _LOG_DIR = None

_log_handlers = [
    logging.StreamHandler()
]

if _LOG_DIR:
    try:
        _log_handlers.append(
            logging.FileHandler(
                os.path.join(
                    _LOG_DIR,
                    "gestureos.log",
                ),
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

APP_VERSION = "v6.0 Premium"

REMAPPABLE_GESTURES = [
    "Thumb Up",
    "Thumb Down",
    "Fist",
    "Open Palm",
]

REMAPPABLE_ACTIONS = [
    "Volume Up",
    "Volume Down",
    "Screenshot",
    "Pause",
]

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
# PREMIUM CAMERA VIEW
# ============================================================

class CameraView(QLabel):
    """
    Dedicated camera renderer.

    Keeps the camera feed's original aspect ratio,
    prevents stretching, handles window resizing,
    and provides a clean cinematic camera area.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pixmap = QPixmap()

        self.setAlignment(Qt.AlignCenter)

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        self.setMinimumSize(
            640,
            360,
        )

        self.setScaledContents(False)

        self.setText(
            "✦\n\n"
            "GESTUREOS VISION SYSTEM\n\n"
            "CAMERA OFFLINE\n\n"
            "Press  START CONTROLLER"
        )

    def set_frame(self, pixmap):
        if pixmap is None or pixmap.isNull():
            return

        self._pixmap = pixmap
        self._render_frame()

    def clear_frame(self):
        self._pixmap = QPixmap()

        self.setPixmap(QPixmap())

        self.setText(
            "✦\n\n"
            "GESTUREOS VISION SYSTEM\n\n"
            "CAMERA OFFLINE\n\n"
            "Press  START CONTROLLER"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if not self._pixmap.isNull():
            self._render_frame()

    def _render_frame(self):
        if self._pixmap.isNull():
            return

        available = self.contentsRect()

        if available.width() <= 0:
            return

        if available.height() <= 0:
            return

        scaled = self._pixmap.scaled(
            available.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        self.setPixmap(scaled)


# ============================================================
# CAMERA WORKER
# ============================================================

class CameraWorker(QObject):

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

        self.gesture_history = deque(
            maxlen=10
        )

        self.timer = None

        self.action_map = dict(
            DEFAULT_ACTION_MAP
        )

        self.last_success_time = 0.0
        self.reconnecting = False
        self.reconnect_cooldown = 3.0

    def set_action_map(self, mapping):

        cleaned = {}

        for gesture in REMAPPABLE_GESTURES:

            action = mapping.get(
                gesture
            )

            if action in REMAPPABLE_ACTIONS:
                cleaned[gesture] = action

        for gesture, action in DEFAULT_ACTION_MAP.items():

            cleaned.setdefault(
                gesture,
                action,
            )

        self.action_map = cleaned

    def get_action_map(self):

        return dict(
            self.action_map
        )

    def start(self):

        if self.running:
            return

        try:

            logger.info(
                "Starting camera engine..."
            )

            self.engine.start()

            self.running = True

            self.controller.enable()

            self.controller_enabled = True

            self.gesture_history.clear()

            self.last_success_time = (
                time.perf_counter()
            )

            self.reconnecting = False

            self.timer = QTimer()

            self.timer.timeout.connect(
                self.process_frame
            )

            self.timer.start(15)

            logger.info(
                "Camera engine started."
            )

        except Exception as error:

            self.running = False

            logger.exception(
                "Camera start failed."
            )

            self.error.emit(
                str(error)
            )

    def calculate_stability(
        self,
        gesture,
    ):

        if gesture == "No Hand":

            self.gesture_history.clear()

            return 0

        self.gesture_history.append(
            gesture
        )

        if not self.gesture_history:
            return 0

        matching = sum(
            1
            for item in self.gesture_history
            if item == gesture
        )

        return int(
            (
                matching
                / len(self.gesture_history)
            )
            * 100
        )

    def process_frame(self):

        if not self.running:
            return

        start_time = time.perf_counter()

        try:

            data = self.engine.read()

            if data is None:
                return

            frame = data["frame"]
            results = data["results"]

            gesture = data["gesture"]
            hand = data["hand"]

            confidence = data["confidence"]
            fps = data["fps"]

            action = "NO ACTION"

            stability = self.calculate_stability(
                gesture
            )

            # ==================================================
            # POINT → CURSOR
            # ==================================================

            if (
                gesture == "Point"
                and results.hand_landmarks
                and self.controller_enabled
            ):

                landmarks = (
                    results.hand_landmarks[0]
                )

                index_tip = landmarks[8]

                x = (
                    index_tip.x
                    * frame.shape[1]
                )

                y = (
                    index_tip.y
                    * frame.shape[0]
                )

                if self.controller.move_cursor(
                    x,
                    y,
                    frame.shape[1],
                    frame.shape[0],
                ):

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
                and results.hand_landmarks
                and self.controller_enabled
            ):

                wrist_y = (
                    results.hand_landmarks[0][0].y
                )

                scroll_amount = (
                    self.controller.scroll(
                        wrist_y
                    )
                )

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

            gesture_changed = (
                gesture != self.last_gesture
            )

            cooldown_passed = (
                now - self.last_action_time
                >= 0.9
            )

            can_action = (
                gesture_changed
                or cooldown_passed
            )

            # ==================================================
            # REMAPPABLE GESTURES
            # ==================================================

            if (
                gesture in self.action_map
                and self.controller_enabled
                and can_action
            ):

                mapped_action = (
                    self.action_map[gesture]
                )

                if self.controller.perform_action(
                    mapped_action
                ):

                    action = ACTION_DISPLAY_TEXT.get(
                        mapped_action,
                        mapped_action.upper(),
                    )

                    self.last_action_time = now

            self.last_gesture = gesture

            self.last_success_time = now
            self.reconnecting = False

            latency = (
                time.perf_counter()
                - start_time
            ) * 1000

            state = {
                "gesture": gesture,
                "hand": hand,
                "confidence": confidence,
                "fps": fps,
                "action": action,
                "enabled": self.controller_enabled,
                "stability": stability,
                "latency": latency,
            }

            # Optional performance values if CameraEngine
            # already provides them.
            state["capture_fps"] = data.get(
                "capture_fps",
                fps,
            )

            state["processing_fps"] = data.get(
                "processing_fps",
                fps,
            )

            state["processing_time_ms"] = data.get(
                "processing_time_ms",
                latency,
            )

            state["processed_frames"] = data.get(
                "processed_frames",
                0,
            )

            state["skipped_frames"] = data.get(
                "skipped_frames",
                0,
            )

            self.frame_ready.emit(
                frame
            )

            self.state_ready.emit(
                state
            )

        except Exception as error:

            logger.warning(
                "Frame processing error: %s",
                error,
            )

            self._maybe_reconnect()

            self.error.emit(
                str(error)
            )

    def _maybe_reconnect(self):

        if (
            self.reconnecting
            or not self.running
        ):
            return

        now = time.perf_counter()

        if (
            now - self.last_success_time
            < self.reconnect_cooldown
        ):
            return

        self.reconnecting = True

        logger.info(
            "Attempting camera auto-reconnect..."
        )

        try:

            try:
                self.engine.stop()
            except Exception:
                pass

            self.engine.start()

            self.last_success_time = (
                time.perf_counter()
            )

            logger.info(
                "Camera auto-reconnect succeeded."
            )

        except Exception as reconnect_error:

            logger.error(
                "Camera auto-reconnect failed: %s",
                reconnect_error,
            )

        finally:

            self.reconnecting = False

    def set_enabled(
        self,
        enabled,
    ):

        self.controller_enabled = enabled

        if enabled:

            self.controller.enable()

        else:

            self.controller.disable()

    def set_sensitivity(
        self,
        value,
    ):

        self.controller.set_sensitivity(
            value
        )

    def stop(self):

        self.running = False

        self.gesture_history.clear()

        self.pinch_latched = False
        self.last_gesture = None

        if self.timer is not None:

            try:
                self.timer.stop()
            except Exception:
                pass

            try:
                self.timer.deleteLater()
            except Exception:
                pass

            self.timer = None

        try:
            self.controller.disable()
        except Exception:
            pass

        try:
            self.engine.stop()
        except Exception:
            pass


# ============================================================
# PULSING DOT
# ============================================================

class PulsingDot(QLabel):

    def __init__(
        self,
        color="#52e5bf",
        size=8,
        parent=None,
    ):

        super().__init__(parent)

        self._color = color
        self._size = size

        self.setFixedSize(
            size,
            size,
        )

        self._effect = QGraphicsOpacityEffect(
            self
        )

        self._effect.setOpacity(
            1.0
        )

        self.setGraphicsEffect(
            self._effect
        )

        self._anim = QPropertyAnimation(
            self._effect,
            b"opacity",
            self,
        )

        self._anim.setDuration(
            1100
        )

        self._anim.setStartValue(
            1.0
        )

        self._anim.setKeyValueAt(
            0.5,
            0.35,
        )

        self._anim.setEndValue(
            1.0
        )

        self._anim.setEasingCurve(
            QEasingCurve.InOutSine
        )

        self._anim.setLoopCount(
            -1
        )

        self.set_color(
            color
        )

    def set_color(
        self,
        color,
    ):

        self._color = color

        self.setStyleSheet(
            f"background: {color};"
            f"border-radius: "
            f"{self._size // 2}px;"
        )

    def start_pulse(self):

        if (
            self._anim.state()
            != QPropertyAnimation.Running
        ):

            self._anim.start()

    def stop_pulse(self):

        self._anim.stop()

        self._effect.setOpacity(
            1.0
        )


# ============================================================
# FPS SPARKLINE
# ============================================================

class FpsSparkline(QWidget):

    def __init__(
        self,
        max_points=60,
        parent=None,
    ):

        super().__init__(parent)

        self.max_points = max_points

        self.values = deque(
            maxlen=max_points
        )

        self.setMinimumHeight(
            46
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

    def push(
        self,
        value,
    ):

        try:

            self.values.append(
                float(value)
            )

        except (
            TypeError,
            ValueError,
        ):

            return

        self.update()

    def clear_data(self):

        self.values.clear()

        self.update()

    def paintEvent(
        self,
        event,
    ):

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        rect = self.rect().adjusted(
            4,
            4,
            -4,
            -4,
        )

        if len(self.values) < 2:

            painter.setPen(
                QPen(
                    QColor("#33454f")
                )
            )

            painter.drawText(
                rect,
                Qt.AlignCenter,
                "collecting data...",
            )

            painter.end()

            return

        values = list(
            self.values
        )

        v_min = min(
            values
        )

        v_max = max(
            values
        )

        if (
            v_max - v_min
            < 1e-6
        ):

            v_max = (
                v_min + 1.0
            )

        step_x = (
            rect.width()
            / max(
                1,
                len(values) - 1,
            )
        )

        points = []

        for index, value in enumerate(
            values
        ):

            x = (
                rect.left()
                + index * step_x
            )

            ratio = (
                value - v_min
            ) / (
                v_max - v_min
            )

            y = (
                rect.bottom()
                - ratio * rect.height()
            )

            points.append(
                QPoint(
                    int(x),
                    int(y),
                )
            )

        pen = QPen(
            QColor("#6dffcf")
        )

        pen.setWidthF(
            1.8
        )

        painter.setPen(
            pen
        )

        for i in range(
            len(points) - 1
        ):

            painter.drawLine(
                points[i],
                points[i + 1],
            )

        fill_color = QColor(
            "#6dffcf"
        )

        fill_color.setAlpha(
            28
        )

        painter.setPen(
            Qt.NoPen
        )

        painter.setBrush(
            fill_color
        )

        polygon_points = (
            points
            + [
                QPoint(
                    points[-1].x(),
                    rect.bottom(),
                ),
                QPoint(
                    points[0].x(),
                    rect.bottom(),
                ),
            ]
        )

        painter.drawPolygon(
            polygon_points
        )

        painter.end()


# ============================================================
# TOAST
# ============================================================

class ToastNotification(QFrame):

    def __init__(
        self,
        parent,
    ):

        super().__init__(
            parent
        )

        self.setObjectName(
            "Toast"
        )

        self.setAttribute(
            Qt.WA_TransparentForMouseEvents
        )

        layout = QHBoxLayout(
            self
        )

        layout.setContentsMargins(
            16,
            10,
            16,
            10,
        )

        self.label = QLabel(
            ""
        )

        self.label.setObjectName(
            "ToastLabel"
        )

        layout.addWidget(
            self.label
        )

        self._opacity = (
            QGraphicsOpacityEffect(
                self
            )
        )

        self._opacity.setOpacity(
            0.0
        )

        self.setGraphicsEffect(
            self._opacity
        )

        self._fade_in = (
            QPropertyAnimation(
                self._opacity,
                b"opacity",
                self,
            )
        )

        self._fade_in.setDuration(
            180
        )

        self._fade_in.setStartValue(
            0.0
        )

        self._fade_in.setEndValue(
            1.0
        )

        self._fade_out = (
            QPropertyAnimation(
                self._opacity,
                b"opacity",
                self,
            )
        )

        self._fade_out.setDuration(
            320
        )

        self._fade_out.setStartValue(
            1.0
        )

        self._fade_out.setEndValue(
            0.0
        )

        self._fade_out.finished.connect(
            self.hide
        )

        self._hide_timer = QTimer(
            self
        )

        self._hide_timer.setSingleShot(
            True
        )

        self._hide_timer.timeout.connect(
            self._fade_out.start
        )

        self.hide()

    def show_message(
        self,
        text,
        duration_ms=1800,
    ):

        self.label.setText(
            text
        )

        self.adjustSize()

        self._reposition()

        self._fade_out.stop()

        self._hide_timer.stop()

        self.show()

        self.raise_()

        self._fade_in.stop()

        self._fade_in.start()

        self._hide_timer.start(
            duration_ms
        )

    def _reposition(self):

        parent = self.parentWidget()

        if parent is None:
            return

        margin = 22

        x = (
            parent.width()
            - self.width()
            - margin
        )

        y = (
            margin + 64
        )

        self.move(
            max(0, x),
            y,
        )


# ============================================================
# REMAP DIALOG
# ============================================================

class RemapDialog(QDialog):

    def __init__(
        self,
        current_map,
        parent=None,
    ):

        super().__init__(
            parent
        )

        self.setWindowTitle(
            "Remap Gestures"
        )

        self.setMinimumWidth(
            360
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            22,
            20,
            22,
            20,
        )

        layout.setSpacing(
            14
        )

        heading = QLabel(
            "GESTURE → ACTION"
        )

        heading.setObjectName(
            "Tiny"
        )

        layout.addWidget(
            heading
        )

        form = QFormLayout()

        form.setSpacing(
            10
        )

        self.combos = {}

        for gesture in REMAPPABLE_GESTURES:

            combo = QComboBox()

            combo.addItems(
                REMAPPABLE_ACTIONS
            )

            current_action = (
                current_map.get(
                    gesture,
                    DEFAULT_ACTION_MAP[
                        gesture
                    ],
                )
            )

            if (
                current_action
                in REMAPPABLE_ACTIONS
            ):

                combo.setCurrentText(
                    current_action
                )

            form.addRow(
                f"{gesture}:",
                combo,
            )

            self.combos[
                gesture
            ] = combo

        layout.addLayout(
            form
        )

        hint = QLabel(
            "Each action can only be assigned once — picking a\n"
            "duplicate will be sorted out automatically."
        )

        hint.setObjectName(
            "DockInfo"
        )

        layout.addWidget(
            hint
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
            | QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )

    def resulting_map(self):

        chosen = {}

        used_actions = set()

        for gesture in REMAPPABLE_GESTURES:

            wanted = (
                self.combos[
                    gesture
                ].currentText()
            )

            if wanted in used_actions:

                fallback = (
                    DEFAULT_ACTION_MAP[
                        gesture
                    ]
                )

                if (
                    fallback
                    not in used_actions
                ):

                    wanted = fallback

                else:

                    wanted = next(
                        a
                        for a
                        in REMAPPABLE_ACTIONS
                        if a
                        not in used_actions
                    )

            used_actions.add(
                wanted
            )

            chosen[
                gesture
            ] = wanted

        return chosen


# ============================================================
# ABOUT DIALOG
# ============================================================

class AboutDialog(QDialog):

    def __init__(
        self,
        parent=None,
    ):

        super().__init__(
            parent
        )

        self.setWindowTitle(
            "About GestureOS"
        )

        self.setMinimumWidth(
            340
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            26,
            24,
            26,
            22,
        )

        layout.setSpacing(
            6
        )

        logo = QLabel(
            "✦ GESTUREOS"
        )

        logo.setStyleSheet(
            "font-size: 18px;"
            "font-weight: 900;"
            "letter-spacing: 2px;"
            "color: #7dffd6;"
        )

        layout.addWidget(
            logo
        )

        version = QLabel(
            APP_VERSION
        )

        version.setObjectName(
            "Tiny"
        )

        layout.addWidget(
            version
        )

        layout.addSpacing(
            10
        )

        body = QLabel(
            "AI-powered hand gesture control for your desktop.\n"
            "Built with MediaPipe, OpenCV, PySide6 and PyAutoGUI.\n\n"
            "7 gestures map to cursor, click, scroll, volume,\n"
            "screenshot and media pause/play — fully remappable."
        )

        body.setWordWrap(
            True
        )

        layout.addWidget(
            body
        )

        layout.addSpacing(
            12
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
        )

        buttons.accepted.connect(
            self.accept
        )

        layout.addWidget(
            buttons
        )


# ============================================================
# DRAGGABLE TOP BAR
# ============================================================

class TopBar(QFrame):

    def __init__(
        self,
        parent=None,
    ):

        super().__init__(
            parent
        )

        self._drag_offset = None

    def mousePressEvent(
        self,
        event,
    ):

        if event.button() == Qt.LeftButton:

            window = self.window()

            self._drag_offset = (
                event.globalPosition().toPoint()
                - window.frameGeometry().topLeft()
            )

        super().mousePressEvent(
            event
        )

    def mouseMoveEvent(
        self,
        event,
    ):

        if (
            self._drag_offset is not None
            and event.buttons()
            & Qt.LeftButton
        ):

            window = self.window()

            if window.isMaximized():
                return

            window.move(
                event.globalPosition().toPoint()
                - self._drag_offset
            )

        super().mouseMoveEvent(
            event
        )

    def mouseReleaseEvent(
        self,
        event,
    ):

        self._drag_offset = None

        super().mouseReleaseEvent(
            event
        )

    def mouseDoubleClickEvent(
        self,
        event,
    ):

        window = self.window()

        if window.isMaximized():

            window.showNormal()

        else:

            window.showMaximized()

        super().mouseDoubleClickEvent(
            event
        )


# ============================================================
# MAIN WINDOW
# ============================================================

class GestureOS(QMainWindow):

    def __init__(
        self,
    ):

        super().__init__()

        self.worker = CameraWorker()

        self.history = deque(
            maxlen=8
        )

        self.calibration_window = None
        self.tray = None
        self.tray_menu = None

        self.session_start = (
            time.perf_counter()
        )

        self.total_frames = 0
        self.total_processed_frames = 0
        self.total_skipped_frames = 0
        self.total_actions = 0
        self.last_dashboard_update = 0.0

        self.tray_start_action = None
        self.tray_pause_action = None

        self._pulse_dots = []

        self.settings = QSettings(
            "GestureOS",
            "GestureOS",
        )

        self._force_quit = False

        self.toast = None

        self.setup_window()

        self.build_ui()

        self.connect_worker()

        self.setup_tray()

        self.apply_elevation()

        self.load_settings()

        self.toast = ToastNotification(
            self.centralWidget()
        )

    # ========================================================
    # WINDOW
    # ========================================================

    def setup_window(
        self,
    ):

        self.setWindowTitle(
            "GestureOS — AI Hand Gesture Controller"
        )

        self.setWindowFlag(
            Qt.FramelessWindowHint,
            True,
        )

        self.resize(
            1540,
            940,
        )

        self.setMinimumSize(
            1240,
            780,
        )

        self.setStyleSheet(
            self.stylesheet()
        )

    # ========================================================
    # SHADOW
    # ========================================================

    def make_shadow(
        self,
        blur=36,
        color="#000000",
        alpha=160,
        dx=0,
        dy=10,
    ):

        shadow = (
            QGraphicsDropShadowEffect()
        )

        shadow.setBlurRadius(
            blur
        )

        c = QColor(
            color
        )

        c.setAlpha(
            alpha
        )

        shadow.setColor(
            c
        )

        shadow.setOffset(
            dx,
            dy,
        )

        return shadow

    def make_glow(
        self,
        blur=40,
        color="#35f0c0",
        alpha=120,
    ):

        glow = (
            QGraphicsDropShadowEffect()
        )

        glow.setBlurRadius(
            blur
        )

        c = QColor(
            color
        )

        c.setAlpha(
            alpha
        )

        glow.setColor(
            c
        )

        glow.setOffset(
            0,
            0,
        )

        return glow

    def apply_elevation(
        self,
    ):

        for widget in [
            self.top_bar,
            self.camera_card,
            self.detection_card,
            self.performance_card,
            self.dashboard_card,
            self.control_dock,
        ]:

            widget.setGraphicsEffect(
                self.make_shadow(
                    blur=42,
                    alpha=150,
                    dy=14,
                )
            )

        self.camera_card.setGraphicsEffect(
            self.make_glow(
                blur=55,
                color="#35f0c0",
                alpha=45,
            )
        )

        for (
            card,
            _gesture,
            _action_label,
        ) in self.mapping_cards:

            card.setGraphicsEffect(
                self.make_shadow(
                    blur=18,
                    alpha=110,
                    dy=6,
                )
            )

        for dot in self._pulse_dots:

            dot.start_pulse()

    # ========================================================
    # BUILD UI
    # ========================================================

    def build_ui(
        self,
    ):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        root = QVBoxLayout(
            central
        )

        root.setContentsMargins(
            22,
            20,
            22,
            20,
        )

        root.setSpacing(
            16
        )

        # ====================================================
        # TOP HEADER
        # ====================================================

        header = TopBar()

        header.setObjectName(
            "TopBar"
        )

        self.top_bar = header

        header_layout = QHBoxLayout(
            header
        )

        header_layout.setContentsMargins(
            22,
            16,
            22,
            16,
        )

        logo = QLabel(
            "✦"
        )

        logo.setObjectName(
            "Logo"
        )

        logo.setAlignment(
            Qt.AlignCenter
        )

        header_layout.addWidget(
            logo
        )

        brand_box = QVBoxLayout()

        brand_box.setSpacing(
            3
        )

        title = QLabel(
            "GESTUREOS"
        )

        title.setObjectName(
            "MainTitle"
        )

        subtitle = QLabel(
            "AI HAND INTERFACE  ·  COMPUTER VISION SYSTEM"
        )

        subtitle.setObjectName(
            "SubTitle"
        )

        brand_box.addWidget(
            title
        )

        brand_box.addWidget(
            subtitle
        )

        header_layout.addLayout(
            brand_box
        )

        header_layout.addStretch()

        ai_pill_wrap = QHBoxLayout()

        ai_pill_wrap.setSpacing(
            8
        )

        ai_dot = PulsingDot(
            color="#65ffd0",
            size=8,
        )

        self._pulse_dots.append(
            ai_dot
        )

        self.ai_pill = QLabel(
            "AI CORE READY"
        )

        self.ai_pill.setObjectName(
            "AIPill"
        )

        ai_pill_frame = QFrame()

        ai_pill_frame.setObjectName(
            "AIPillFrame"
        )

        ai_pill_layout = QHBoxLayout(
            ai_pill_frame
        )

        ai_pill_layout.setContentsMargins(
            12,
            7,
            14,
            7,
        )

        ai_pill_layout.setSpacing(
            8
        )

        ai_pill_layout.addWidget(
            ai_dot
        )

        ai_pill_layout.addWidget(
            self.ai_pill
        )

        self.ai_dot = ai_dot

        header_layout.addWidget(
            ai_pill_frame
        )

        self.system_status = QLabel(
            "SYSTEM STANDBY"
        )

        self.system_status.setObjectName(
            "SystemPill"
        )

        header_layout.addWidget(
            self.system_status
        )

        # ====================================================
        # WINDOW CONTROLS
        # ====================================================

        window_controls = QHBoxLayout()

        window_controls.setSpacing(
            6
        )

        window_controls.setContentsMargins(
            14,
            0,
            0,
            0,
        )

        self.more_button = QPushButton(
            "⋮"
        )

        self.more_button.setObjectName(
            "WindowButton"
        )

        self.more_button.setFixedSize(
            32,
            32,
        )

        self.more_button.setCursor(
            Qt.PointingHandCursor
        )

        self.more_button.clicked.connect(
            self.open_more_menu
        )

        window_controls.addWidget(
            self.more_button
        )

        self.minimize_button = QPushButton(
            "—"
        )

        self.minimize_button.setObjectName(
            "WindowButton"
        )

        self.minimize_button.setFixedSize(
            32,
            32,
        )

        self.minimize_button.setCursor(
            Qt.PointingHandCursor
        )

        self.minimize_button.clicked.connect(
            self.showMinimized
        )

        window_controls.addWidget(
            self.minimize_button
        )

        self.close_button = QPushButton(
            "✕"
        )

        self.close_button.setObjectName(
            "CloseButton"
        )

        self.close_button.setFixedSize(
            32,
            32,
        )

        self.close_button.setCursor(
            Qt.PointingHandCursor
        )

        self.close_button.clicked.connect(
            self.close
        )

        window_controls.addWidget(
            self.close_button
        )

        header_layout.addLayout(
            window_controls
        )

        root.addWidget(
            header
        )

        # ====================================================
        # MAIN GRID
        # ====================================================

        main_grid = QGridLayout()

        main_grid.setSpacing(
            16
        )

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
            16,
        )

        cam_top = QHBoxLayout()

        cam_title = QLabel(
            "LIVE VISION"
        )

        cam_title.setObjectName(
            "PanelTitle"
        )

        cam_top.addWidget(
            cam_title
        )

        cam_top.addStretch()

        live_wrap = QHBoxLayout()

        live_wrap.setSpacing(
            6
        )

        self.live_dot = PulsingDot(
            color="#54606b",
            size=7,
        )

        self._pulse_dots.append(
            self.live_dot
        )

        live_wrap.addWidget(
            self.live_dot
        )

        self.live_badge = QLabel(
            "OFFLINE"
        )

        self.live_badge.setObjectName(
            "LiveBadge"
        )

        live_wrap.addWidget(
            self.live_badge
        )

        cam_top.addLayout(
            live_wrap
        )

        camera_layout.addLayout(
            cam_top
        )

        # ====================================================
        # PREMIUM CAMERA VIEW
        # ====================================================

        self.camera_label = CameraView()

        self.camera_label.setObjectName(
            "CameraView"
        )

        self.camera_label.setMinimumSize(
            640,
            360,
        )

        self.camera_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        camera_layout.addWidget(
            self.camera_label,
            1,
        )

        # ====================================================
        # CAMERA HUD
        # ====================================================

        hud = QHBoxLayout()

        hud.setSpacing(
            18
        )

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

            hud.addWidget(
                label
            )

        hud.addStretch()

        camera_layout.addLayout(
            hud
        )

        main_grid.addWidget(
            camera_card,
            0,
            0,
            2,
            7,
        )

        # ====================================================
        # DETECTION PANEL
        # ====================================================

        detection_card = QFrame()

        detection_card.setObjectName(
            "DetectionPanel"
        )

        self.detection_card = (
            detection_card
        )

        detection_layout = QVBoxLayout(
            detection_card
        )

        detection_layout.setContentsMargins(
            22,
            22,
            22,
            22,
        )

        small = QLabel(
            "CURRENT DETECTION"
        )

        small.setObjectName(
            "Tiny"
        )

        detection_layout.addWidget(
            small
        )

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

        detection_layout.addSpacing(
            14
        )

        conf_row = QHBoxLayout()

        conf_name = QLabel(
            "CONFIDENCE"
        )

        conf_name.setObjectName(
            "Tiny"
        )

        self.conf_value = QLabel(
            "0%"
        )

        self.conf_value.setObjectName(
            "Percent"
        )

        conf_row.addWidget(
            conf_name
        )

        conf_row.addStretch()

        conf_row.addWidget(
            self.conf_value
        )

        detection_layout.addLayout(
            conf_row
        )

        self.conf_bar = QProgressBar()

        self.conf_bar.setRange(
            0,
            100,
        )

        self.conf_bar.setValue(
            0
        )

        self.conf_bar.setTextVisible(
            False
        )

        self.conf_bar.setObjectName(
            "Confidence"
        )

        detection_layout.addWidget(
            self.conf_bar
        )

        detection_layout.addSpacing(
            10
        )

        stab_row = QHBoxLayout()

        stab_name = QLabel(
            "STABILITY"
        )

        stab_name.setObjectName(
            "Tiny"
        )

        self.stab_value = QLabel(
            "0%"
        )

        self.stab_value.setObjectName(
            "Percent"
        )

        stab_row.addWidget(
            stab_name
        )

        stab_row.addStretch()

        stab_row.addWidget(
            self.stab_value
        )

        detection_layout.addLayout(
            stab_row
        )

        self.stab_bar = QProgressBar()

        self.stab_bar.setRange(
            0,
            100,
        )

        self.stab_bar.setValue(
            0
        )

        self.stab_bar.setTextVisible(
            False
        )

        self.stab_bar.setObjectName(
            "Stability"
        )

        detection_layout.addWidget(
            self.stab_bar
        )

        detection_layout.addStretch()

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
            3,
        )

        # ====================================================
        # PERFORMANCE PANEL
        # ====================================================

        performance_card = QFrame()

        performance_card.setObjectName(
            "Panel"
        )

        self.performance_card = (
            performance_card
        )

        performance_layout = QVBoxLayout(
            performance_card
        )

        performance_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        perf_title = QLabel(
            "SYSTEM TELEMETRY"
        )

        perf_title.setObjectName(
            "PanelTitle"
        )

        performance_layout.addWidget(
            perf_title
        )

        perf_grid = QGridLayout()

        perf_grid.setSpacing(
            10
        )

        self.fps_metric = self.metric_box(
            perf_grid,
            0,
            0,
            "FPS",
            "0.0",
        )

        self.latency_metric = self.metric_box(
            perf_grid,
            0,
            1,
            "LATENCY",
            "—",
        )

        self.hand_metric = self.metric_box(
            perf_grid,
            1,
            0,
            "HAND",
            "None",
        )

        self.state_metric = self.metric_box(
            perf_grid,
            1,
            1,
            "CONTROL",
            "OFF",
        )

        performance_layout.addLayout(
            perf_grid
        )

        sparkline_title = QLabel(
            "FPS TREND"
        )

        sparkline_title.setObjectName(
            "Tiny"
        )

        performance_layout.addWidget(
            sparkline_title
        )

        self.fps_sparkline = (
            FpsSparkline(
                max_points=60
            )
        )

        self.fps_sparkline.setObjectName(
            "Sparkline"
        )

        performance_layout.addWidget(
            self.fps_sparkline
        )

        main_grid.addWidget(
            performance_card,
            1,
            7,
            1,
            3,
        )

        # ====================================================
        # PERFORMANCE DASHBOARD
        # ====================================================

        dashboard_card = QFrame()

        dashboard_card.setObjectName(
            "Panel"
        )

        self.dashboard_card = (
            dashboard_card
        )

        dashboard_layout = QVBoxLayout(
            dashboard_card
        )

        dashboard_layout.setContentsMargins(
            20,
            16,
            20,
            16,
        )

        dashboard_layout.setSpacing(
            10
        )

        dashboard_top = QHBoxLayout()

        dashboard_title = QLabel(
            "PERFORMANCE INTELLIGENCE"
        )

        dashboard_title.setObjectName(
            "PanelTitle"
        )

        dashboard_top.addWidget(
            dashboard_title
        )

        dashboard_top.addStretch()

        self.session_uptime = QLabel(
            "UPTIME 00:00:00"
        )

        self.session_uptime.setObjectName(
            "DashboardTiny"
        )

        dashboard_top.addWidget(
            self.session_uptime
        )

        dashboard_layout.addLayout(
            dashboard_top
        )

        dash_grid = QGridLayout()

        dash_grid.setSpacing(
            9
        )

        self.capture_metric = (
            self.dashboard_metric(
                dash_grid,
                0,
                0,
                "CAPTURE FPS",
                "0.0",
            )
        )

        self.process_metric = (
            self.dashboard_metric(
                dash_grid,
                0,
                1,
                "AI FPS",
                "0.0",
            )
        )

        self.process_time_metric = (
            self.dashboard_metric(
                dash_grid,
                0,
                2,
                "AI PROCESS",
                "—",
            )
        )

        self.skip_metric = (
            self.dashboard_metric(
                dash_grid,
                0,
                3,
                "SKIP RATE",
                "0%",
            )
        )

        self.frame_metric = (
            self.dashboard_metric(
                dash_grid,
                1,
                0,
                "FRAMES",
                "0",
            )
        )

        self.action_metric = (
            self.dashboard_metric(
                dash_grid,
                1,
                1,
                "ACTIONS",
                "0",
            )
        )

        self.confidence_metric = (
            self.dashboard_metric(
                dash_grid,
                1,
                2,
                "CONFIDENCE",
                "0%",
            )
        )

        self.stability_metric = (
            self.dashboard_metric(
                dash_grid,
                1,
                3,
                "STABILITY",
                "0%",
            )
        )

        dashboard_layout.addLayout(
            dash_grid
        )

        status_row = QHBoxLayout()

        status_row.setSpacing(
            8
        )

        self.dashboard_dot = PulsingDot(
            color="#5fcdb4",
            size=7,
        )

        self._pulse_dots.append(
            self.dashboard_dot
        )

        status_row.addWidget(
            self.dashboard_dot
        )

        self.dashboard_status = QLabel(
            "PERFORMANCE MONITOR READY"
        )

        self.dashboard_status.setObjectName(
            "DashboardStatus"
        )

        status_row.addWidget(
            self.dashboard_status
        )

        status_row.addStretch()

        dashboard_layout.addLayout(
            status_row
        )

        root.addWidget(
            dashboard_card
        )

        root.addLayout(
            main_grid,
            1,
        )

        # ====================================================
        # CONTROL DOCK
        # ====================================================

        control_dock = QFrame()

        control_dock.setObjectName(
            "ControlDock"
        )

        self.control_dock = (
            control_dock
        )

        control_layout = QHBoxLayout(
            control_dock
        )

        control_layout.setContentsMargins(
            18,
            13,
            18,
            13,
        )

        control_layout.setSpacing(
            12
        )

        self.start_button = QPushButton(
            "▶   START CONTROLLER"
        )

        self.start_button.setObjectName(
            "StartButton"
        )

        self.start_button.setCursor(
            Qt.PointingHandCursor
        )

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

        self.calibration_button.setCursor(
            Qt.PointingHandCursor
        )

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

        self.enable_button.setCursor(
            Qt.PointingHandCursor
        )

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

        divider.setFixedWidth(
            1
        )

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

        self.sensitivity_slider.setMinimum(
            10
        )

        self.sensitivity_slider.setMaximum(
            60
        )

        self.sensitivity_slider.setValue(
            30
        )

        self.sensitivity_slider.setMinimumWidth(
            210
        )

        self.sensitivity_slider.setCursor(
            Qt.PointingHandCursor
        )

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
        # GESTURE MATRIX
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

        gesture_grid.setSpacing(
            10
        )

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
            action,
        ) in enumerate(
            mappings
        ):

            card = QFrame()

            card.setObjectName(
                "GestureTile"
            )

            tile_layout = QHBoxLayout(
                card
            )

            tile_layout.setContentsMargins(
                12,
                10,
                12,
                10,
            )

            tile_layout.setSpacing(
                10
            )

            icon_wrap = QFrame()

            icon_wrap.setObjectName(
                "TileIconWrap"
            )

            icon_wrap_layout = QVBoxLayout(
                icon_wrap
            )

            icon_wrap_layout.setContentsMargins(
                0,
                0,
                0,
                0,
            )

            icon_label = QLabel(
                icon
            )

            icon_label.setObjectName(
                "TileIcon"
            )

            icon_label.setAlignment(
                Qt.AlignCenter
            )

            icon_wrap_layout.addWidget(
                icon_label
            )

            tile_layout.addWidget(
                icon_wrap
            )

            text = QVBoxLayout()

            text.setSpacing(
                2
            )

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

            tile_layout.addLayout(
                text
            )

            tile_layout.addStretch()

            row = index // 4
            column = index % 4

            gesture_grid.addWidget(
                card,
                row,
                column,
            )

            self.mapping_cards.append(
                (
                    card,
                    gesture,
                    action_name,
                )
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

        root.addLayout(
            bottom
        )

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

        root.addWidget(
            footer
        )

    # ========================================================
    # DASHBOARD METRIC
    # ========================================================

    def dashboard_metric(
        self,
        grid,
        row,
        column,
        title,
        value,
    ):

        box = QFrame()

        box.setObjectName(
            "DashboardBox"
        )

        layout = QVBoxLayout(
            box
        )

        layout.setContentsMargins(
            10,
            8,
            10,
            8,
        )

        layout.setSpacing(
            3
        )

        title_label = QLabel(
            title
        )

        title_label.setObjectName(
            "DashboardTiny"
        )

        value_label = QLabel(
            value
        )

        value_label.setObjectName(
            "DashboardValue"
        )

        layout.addWidget(
            title_label
        )

        layout.addWidget(
            value_label
        )

        grid.addWidget(
            box,
            row,
            column,
        )

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
        value,
    ):

        box = QFrame()

        box.setObjectName(
            "TelemetryBox"
        )

        layout = QVBoxLayout(
            box
        )

        layout.setContentsMargins(
            12,
            10,
            12,
            10,
        )

        title_label = QLabel(
            title
        )

        title_label.setObjectName(
            "Tiny"
        )

        value_label = QLabel(
            value
        )

        value_label.setObjectName(
            "TelemetryValue"
        )

        layout.addWidget(
            title_label
        )

        layout.addWidget(
            value_label
        )

        grid.addWidget(
            box,
            row,
            column,
        )

        return value_label

    # ========================================================
    # SIGNALS
    # ========================================================

    def connect_worker(
        self,
    ):

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

    def setup_tray(
        self,
    ):

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(
            self
        )

        self.tray.setIcon(
            self.windowIcon()
        )

        self.tray.setToolTip(
            "GestureOS — AI Hand Gesture Controller"
        )

        self.tray_menu = QMenu(
            self
        )

        open_action = QAction(
            "Open GestureOS",
            self,
        )

        open_action.triggered.connect(
            self.show_from_tray
        )

        self.tray_menu.addAction(
            open_action
        )

        self.tray_start_action = QAction(
            "▶ Start Controller",
            self,
        )

        self.tray_start_action.triggered.connect(
            self.tray_toggle_controller
        )

        self.tray_menu.addAction(
            self.tray_start_action
        )

        self.tray_pause_action = QAction(
            "○ Disable Controls",
            self,
        )

        self.tray_pause_action.setEnabled(
            False
        )

        self.tray_pause_action.triggered.connect(
            self.toggle_enabled
        )

        self.tray_menu.addAction(
            self.tray_pause_action
        )

        self.tray_menu.addSeparator()

        calibration_action = QAction(
            "⚙ Calibration",
            self,
        )

        calibration_action.triggered.connect(
            self.open_calibration
        )

        self.tray_menu.addAction(
            calibration_action
        )

        self.tray_menu.addSeparator()

        exit_action = QAction(
            "✕ Exit GestureOS",
            self,
        )

        exit_action.triggered.connect(
            self.exit_application
        )

        self.tray_menu.addAction(
            exit_action
        )

        self.tray.setContextMenu(
            self.tray_menu
        )

        self.tray.activated.connect(
            self.tray_activated
        )

        self.tray.show()

    def tray_activated(
        self,
        reason,
    ):

        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
        ):

            self.show_from_tray()

    def show_from_tray(
        self,
    ):

        self.show()

        self.showNormal()

        self.raise_()

        self.activateWindow()

    def tray_toggle_controller(
        self,
    ):

        if self.worker.running:

            self.stop_controller()

        else:

            self.start_controller()

        self.update_tray_actions()

    def update_tray_actions(
        self,
    ):

        if self.tray_start_action is None:
            return

        if self.worker.running:

            self.tray_start_action.setText(
                "■ Stop Controller"
            )

            self.tray_pause_action.setEnabled(
                True
            )

            self.tray_pause_action.setText(
                "○ Enable Controls"
                if not self.worker.controller_enabled
                else "○ Disable Controls"
            )

        else:

            self.tray_start_action.setText(
                "▶ Start Controller"
            )

            self.tray_pause_action.setEnabled(
                False
            )

            self.tray_pause_action.setText(
                "○ Disable Controls"
            )

    def exit_application(
        self,
    ):

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
    # MORE MENU
    # ========================================================

    def open_more_menu(
        self,
    ):

        menu = QMenu(
            self
        )

        remap_action = QAction(
            "🎛  Remap Gestures",
            self,
        )

        remap_action.triggered.connect(
            self.open_remap_dialog
        )

        menu.addAction(
            remap_action
        )

        menu.addSeparator()

        startup_action = QAction(
            "🚀  Launch at Windows Startup",
            self,
        )

        startup_action.setCheckable(
            True
        )

        startup_action.setChecked(
            self.is_launch_at_startup_enabled()
        )

        startup_action.triggered.connect(
            self.toggle_launch_at_startup
        )

        menu.addAction(
            startup_action
        )

        menu.addSeparator()

        about_action = QAction(
            "ⓘ  About GestureOS",
            self,
        )

        about_action.triggered.connect(
            self.open_about_dialog
        )

        menu.addAction(
            about_action
        )

        menu.exec(
            self.more_button.mapToGlobal(
                self.more_button.rect().bottomRight()
            )
        )

    def open_remap_dialog(
        self,
    ):

        dialog = RemapDialog(
            self.worker.get_action_map(),
            self,
        )

        if dialog.exec() == QDialog.Accepted:

            new_map = (
                dialog.resulting_map()
            )

            self.worker.set_action_map(
                new_map
            )

            self.save_settings()

            self.refresh_gesture_matrix_labels()

            if self.toast is not None:

                self.toast.show_message(
                    "GESTURES REMAPPED"
                )

            logger.info(
                "Gesture map updated: %s",
                new_map,
            )

    def refresh_gesture_matrix_labels(
        self,
    ):

        current_map = (
            self.worker.get_action_map()
        )

        for (
            card,
            gesture,
            action_label,
        ) in self.mapping_cards:

            if gesture in current_map:

                mapped = current_map[
                    gesture
                ]

                action_label.setText(
                    ACTION_DISPLAY_TEXT.get(
                        mapped,
                        mapped.upper(),
                    )
                )

    def open_about_dialog(
        self,
    ):

        AboutDialog(
            self
        ).exec()

    def is_launch_at_startup_enabled(
        self,
    ):

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

                winreg.QueryValueEx(
                    key,
                    "GestureOS",
                )

                return True

            except FileNotFoundError:

                return False

            finally:

                winreg.CloseKey(
                    key
                )

        except Exception:

            return False

    def toggle_launch_at_startup(
        self,
        checked,
    ):

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

                exe_path = os.path.abspath(
                    sys.argv[0]
                )

                winreg.SetValueEx(
                    key,
                    "GestureOS",
                    0,
                    winreg.REG_SZ,
                    f'"{sys.executable}" "{exe_path}"',
                )

                message = (
                    "WILL LAUNCH AT STARTUP"
                )

            else:

                try:

                    winreg.DeleteValue(
                        key,
                        "GestureOS",
                    )

                except FileNotFoundError:

                    pass

                message = (
                    "STARTUP LAUNCH DISABLED"
                )

            winreg.CloseKey(
                key
            )

            if self.toast is not None:

                self.toast.show_message(
                    message
                )

        except Exception as error:

            logger.error(
                "Could not update startup registry entry: %s",
                error,
            )

            if self.toast is not None:

                self.toast.show_message(
                    "COULD NOT UPDATE STARTUP SETTING"
                )

    # ========================================================
    # SETTINGS
    # ========================================================

    def load_settings(
        self,
    ):

        try:

            sensitivity = int(
                self.settings.value(
                    "sensitivity",
                    30,
                )
            )

            sensitivity = max(
                10,
                min(
                    60,
                    sensitivity,
                ),
            )

            self.sensitivity_slider.setValue(
                sensitivity
            )

        except Exception:

            pass

        try:

            action_map = {}

            for gesture in REMAPPABLE_GESTURES:

                key = (
                    f"action_map/{gesture}"
                )

                stored = (
                    self.settings.value(
                        key,
                        None,
                    )
                )

                if (
                    stored
                    in REMAPPABLE_ACTIONS
                ):

                    action_map[
                        gesture
                    ] = stored

            if action_map:

                self.worker.set_action_map(
                    action_map
                )

                self.refresh_gesture_matrix_labels()

        except Exception:

            pass

        try:

            geometry = (
                self.settings.value(
                    "window_geometry",
                    None,
                )
            )

            if geometry is not None:

                self.restoreGeometry(
                    geometry
                )

        except Exception:

            pass

    def save_settings(
        self,
    ):

        try:

            self.settings.setValue(
                "sensitivity",
                self.sensitivity_slider.value(),
            )

            current_map = (
                self.worker.get_action_map()
            )

            for (
                gesture,
                action,
            ) in current_map.items():

                self.settings.setValue(
                    f"action_map/{gesture}",
                    action,
                )

            self.settings.setValue(
                "window_geometry",
                self.saveGeometry(),
            )

            self.settings.sync()

        except Exception as error:

            logger.warning(
                "Could not save settings: %s",
                error,
            )

    # ========================================================
    # CONTROLLER
    # ========================================================

    def toggle_controller(
        self,
    ):

        if self.worker.running:

            self.stop_controller()

        else:

            self.start_controller()

    def open_calibration(
        self,
    ):

        if (
            self.calibration_window
            is not None
        ):

            try:

                if (
                    self.calibration_window.isVisible()
                ):

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

            if (
                gesture_engine is None
                or calibration_manager is None
            ):

                raise RuntimeError(
                    "Calibration services are not initialized. Restart the controller first."
                )

            self.worker.set_enabled(
                False
            )

            self.enable_button.setText(
                "○   DISABLED"
            )

            self.system_status.setText(
                "CALIBRATION MODE"
            )

            self.engine_status_text(
                "● CALIBRATION ENGINE READY"
            )

            self.calibration_window = (
                CalibrationWindow(
                    self.worker.engine,
                    gesture_engine,
                    calibration_manager,
                    self,
                )
            )

            if hasattr(
                self.calibration_window,
                "calibration_finished",
            ):

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

                self.worker.set_enabled(
                    True
                )

                self.enable_button.setText(
                    "●   ACTIVE"
                )

            self.show_error(
                f"Calibration error: {error}"
            )

    def calibration_complete(
        self,
    ):

        try:

            self.worker.engine.apply_calibration()

            self.worker.set_enabled(
                True
            )

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

            if (
                self.calibration_window
                is not None
            ):

                try:

                    self.calibration_window.close()

                except Exception:

                    pass

                self.calibration_window = None

        except Exception as error:

            self.show_error(
                f"Calibration apply error: {error}"
            )

    def start_controller(
        self,
    ):

        self.worker.start()

        if not self.worker.running:
            return

        self.session_start = (
            time.perf_counter()
        )

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

        self.live_dot.set_color(
            "#52e5bf"
        )

        self.system_status.setText(
            "SYSTEM ACTIVE"
        )

        self.ai_pill.setText(
            "AI CORE ONLINE"
        )

        self.ai_dot.set_color(
            "#65ffd0"
        )

        self.engine_status_text(
            "● TRACKING ENGINE ACTIVE"
        )

    def stop_controller(
        self,
    ):

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

        self.live_dot.set_color(
            "#54606b"
        )

        self.system_status.setText(
            "SYSTEM STANDBY"
        )

        self.ai_pill.setText(
            "AI CORE READY"
        )

        self.ai_dot.set_color(
            "#65ffd0"
        )

        self.camera_label.clear_frame()

        self.gesture_label.setText(
            "No Hand"
        )

        self.action_label.setText(
            "NO ACTION"
        )

        self.conf_value.setText(
            "0%"
        )

        self.stab_value.setText(
            "0%"
        )

        self.conf_bar.setValue(
            0
        )

        self.stab_bar.setValue(
            0
        )

        self.fps_metric.setText(
            "0.0"
        )

        self.latency_metric.setText(
            "—"
        )

        self.hand_metric.setText(
            "None"
        )

        self.state_metric.setText(
            "OFF"
        )

        if hasattr(
            self,
            "fps_sparkline",
        ):

            self.fps_sparkline.clear_data()

        self.session_uptime.setText(
            "UPTIME 00:00:00"
        )

        self.capture_metric.setText(
            "0.0"
        )

        self.process_metric.setText(
            "0.0"
        )

        self.process_time_metric.setText(
            "—"
        )

        self.skip_metric.setText(
            "0%"
        )

        self.frame_metric.setText(
            "0"
        )

        self.action_metric.setText(
            "0"
        )

        self.confidence_metric.setText(
            "0%"
        )

        self.stability_metric.setText(
            "0%"
        )

        self.dashboard_status.setText(
            "PERFORMANCE MONITOR READY"
        )

        self.dashboard_dot.set_color(
            "#5fcdb4"
        )

        self.hud_hand.setText(
            "HAND  —"
        )

        self.hud_fps.setText(
            "FPS  —"
        )

        self.hud_latency.setText(
            "LATENCY  —"
        )

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

    def toggle_enabled(
        self,
    ):

        if not self.worker.running:
            return

        enabled = not (
            self.worker.controller_enabled
        )

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

        self.update_tray_actions()

    # ========================================================
    # ENGINE STATUS
    # ========================================================

    def engine_status_text(
        self,
        text,
    ):

        self.control_info.setText(
            text
        )

    # ========================================================
    # SENSITIVITY
    # ========================================================

    def change_sensitivity(
        self,
        value,
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
        frame,
    ):

        if frame is None:
            return

        try:

            if (
                not hasattr(
                    frame,
                    "shape",
                )
                or len(frame.shape) < 2
            ):

                return

            # Convert OpenCV BGR → Qt RGB.
            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB,
            )

            height, width, channels = (
                rgb.shape
            )

            if (
                width <= 0
                or height <= 0
            ):

                return

            bytes_per_line = (
                channels * width
            )

            image = QImage(
                rgb.data,
                width,
                height,
                bytes_per_line,
                QImage.Format_RGB888,
            ).copy()

            if image.isNull():
                return

            pixmap = QPixmap.fromImage(
                image
            )

            if pixmap.isNull():
                return

            # CameraView handles aspect-ratio-safe
            # rendering and resizing.
            self.camera_label.set_frame(
                pixmap
            )

        except Exception as error:

            logger.warning(
                "Camera frame rendering error: %s",
                error,
            )

    # ========================================================
    # STATE
    # ========================================================

    def update_state(
        self,
        state,
    ):

        gesture = state.get(
            "gesture",
            "No Hand",
        )

        hand = state.get(
            "hand",
            "None",
        )

        confidence = state.get(
            "confidence",
            0,
        )

        fps = state.get(
            "fps",
            0.0,
        )

        action = state.get(
            "action",
            "NO ACTION",
        )

        enabled = state.get(
            "enabled",
            False,
        )

        stability = state.get(
            "stability",
            0,
        )

        latency = state.get(
            "latency",
            0,
        )

        try:

            confidence_value = max(
                0,
                min(
                    100,
                    int(confidence),
                ),
            )

        except Exception:

            confidence_value = 0

        try:

            stability_value = max(
                0,
                min(
                    100,
                    int(stability),
                ),
            )

        except Exception:

            stability_value = 0

        capture_fps = state.get(
            "capture_fps",
            0.0,
        )

        processing_fps = state.get(
            "processing_fps",
            0.0,
        )

        processing_time_ms = state.get(
            "processing_time_ms",
            0.0,
        )

        processed_frames = state.get(
            "processed_frames",
            0,
        )

        skipped_frames = state.get(
            "skipped_frames",
            0,
        )

        try:

            self.total_frames = (
                int(processed_frames)
                + int(skipped_frames)
            )

            self.total_processed_frames = (
                int(processed_frames)
            )

            self.total_skipped_frames = (
                int(skipped_frames)
            )

        except Exception:

            pass

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

        total_seen = (
            self.total_frames
        )

        skip_rate = (
            (
                self.total_skipped_frames
                / total_seen
            )
            * 100
            if total_seen > 0
            else 0
        )

        uptime_seconds = max(
            0,
            int(
                time.perf_counter()
                - self.session_start
            ),
        )

        uptime_minutes, uptime_seconds = (
            divmod(
                uptime_seconds,
                60,
            )
        )

        uptime_hours, uptime_minutes = (
            divmod(
                uptime_minutes,
                60,
            )
        )

        now_dashboard = (
            time.perf_counter()
        )

        if (
            now_dashboard
            - self.last_dashboard_update
            >= 0.20
        ):

            self.session_uptime.setText(
                f"UPTIME "
                f"{uptime_hours:02d}:"
                f"{uptime_minutes:02d}:"
                f"{uptime_seconds:02d}"
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

                self.dashboard_dot.set_color(
                    "#7a8790"
                )

            elif (
                processing_time_ms
                > 45
            ):

                self.dashboard_status.setText(
                    "HIGH AI PROCESSING LOAD"
                )

                self.dashboard_dot.set_color(
                    "#ffc857"
                )

            elif (
                processing_fps > 0
                and processing_fps < 18
            ):

                self.dashboard_status.setText(
                    "LOW AI PROCESSING RATE"
                )

                self.dashboard_dot.set_color(
                    "#ffc857"
                )

            else:

                self.dashboard_status.setText(
                    "PERFORMANCE NOMINAL"
                )

                self.dashboard_dot.set_color(
                    "#5fcdb4"
                )

            self.last_dashboard_update = (
                now_dashboard
            )

        # ====================================================
        # GESTURE
        # ====================================================

        self.gesture_label.setText(
            str(gesture)
        )

        self.action_label.setText(
            str(action)
        )

        # ====================================================
        # CONFIDENCE
        # ====================================================

        self.conf_value.setText(
            f"{confidence_value}%"
        )

        self.conf_bar.setValue(
            confidence_value
        )

        # ====================================================
        # STABILITY
        # ====================================================

        self.stab_value.setText(
            f"{stability_value}%"
        )

        self.stab_bar.setValue(
            stability_value
        )

        # ====================================================
        # METRICS
        # ====================================================

        try:

            self.fps_metric.setText(
                f"{float(fps):.1f}"
            )

        except Exception:

            self.fps_metric.setText(
                "0.0"
            )

        try:

            self.latency_metric.setText(
                f"{float(latency):.1f} ms"
            )

        except Exception:

            self.latency_metric.setText(
                "—"
            )

        self.hand_metric.setText(
            str(hand)
        )

        self.state_metric.setText(
            "ON"
            if enabled
            else "OFF"
        )

        # ====================================================
        # HUD
        # ====================================================

        self.hud_hand.setText(
            f"HAND  {str(hand).upper()}"
        )

        try:

            self.hud_fps.setText(
                f"FPS  {float(fps):.1f}"
            )

        except Exception:

            self.hud_fps.setText(
                "FPS  —"
            )

        try:

            self.hud_latency.setText(
                f"LATENCY  {float(latency):.1f} ms"
            )

        except Exception:

            self.hud_latency.setText(
                "LATENCY  —"
            )

        # ====================================================
        # DETECTION STATUS
        # ====================================================

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

        # ====================================================
        # HIGHLIGHT
        # ====================================================

        self.highlight_mapping(
            gesture
        )

        # ====================================================
        # HISTORY
        # ====================================================

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
                or self.history[0][0]
                != action
            ):

                self.history.appendleft(
                    (
                        action,
                        time.strftime(
                            "%H:%M:%S"
                        ),
                    )
                )

                self.refresh_history()

                if self.toast is not None:

                    self.toast.show_message(
                        action
                    )

        # ====================================================
        # FPS TREND
        # ====================================================

        if hasattr(
            self,
            "fps_sparkline",
        ):

            try:

                self.fps_sparkline.push(
                    fps
                )

            except Exception:

                pass

    # ========================================================
    # GESTURE HIGHLIGHT
    # ========================================================

    def highlight_mapping(
        self,
        gesture,
    ):

        gesture_upper = str(
            gesture
        ).upper()

        for (
            card,
            card_gesture,
            _action_label,
        ) in self.mapping_cards:

            if (
                gesture_upper
                == card_gesture
            ):

                card.setProperty(
                    "active",
                    True,
                )

            else:

                card.setProperty(
                    "active",
                    False,
                )

            card.style().unpolish(
                card
            )

            card.style().polish(
                card
            )

            card.update()

    # ========================================================
    # HISTORY
    # ========================================================

    def refresh_history(
        self,
    ):

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
        message,
    ):

        self.system_status.setText(
            "SYSTEM ERROR"
        )

        self.ai_pill.setText(
            "AI CORE ERROR"
        )

        self.ai_dot.set_color(
            "#ff6a6a"
        )

        self.live_badge.setText(
            "SENSOR ERROR"
        )

        self.live_dot.set_color(
            "#ff6a6a"
        )

        self.action_label.setText(
            "ERROR"
        )

        self.detection_status.setText(
            "CAMERA / AI ERROR"
        )

        logger.error(
            "GestureOS Error: %s",
            message,
        )

    # ========================================================
    # CLOSE
    # ========================================================

    def closeEvent(
        self,
        event,
    ):

        if (
            not self._force_quit
            and self.tray is not None
            and self.tray.isVisible()
        ):

            self.save_settings()

            event.ignore()

            self.hide()

            if self.toast is None:

                self.toast = (
                    ToastNotification(
                        self.centralWidget()
                    )
                )

            if self.tray is not None:

                self.tray.showMessage(
                    "GestureOS",
                    "Still running in the background. "
                    "Right-click the tray icon to exit.",
                    QSystemTrayIcon.Information,
                    2500,
                )

            return

        try:

            self.save_settings()

            if (
                getattr(
                    self,
                    "calibration_window",
                    None,
                )
                is not None
            ):

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

            if (
                hasattr(
                    self,
                    "worker",
                )
                and self.worker is not None
            ):

                try:

                    self.worker.stop()

                except Exception:

                    pass

                try:

                    if (
                        getattr(
                            self.worker,
                            "timer",
                            None,
                        )
                        is not None
                    ):

                        self.worker.timer.stop()

                except Exception:

                    pass

        finally:

            event.accept()

            QTimer.singleShot(
                0,
                QApplication.quit,
            )

    # ========================================================
    # STYLE
    # ========================================================

    def stylesheet(
        self,
    ):

        return """
        QMainWindow {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #05070c,
                stop:0.5 #070a11,
                stop:1 #05080d
            );
        }

        QWidget {
            color: #eef4f6;
            font-family:
                "Segoe UI Variable Display",
                "Segoe UI",
                "Inter",
                sans-serif;
        }

        QFrame#TopBar {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0a0f17,
                stop:1 #0b131a
            );
            border: 1px solid #1c2b34;
            border-radius: 20px;
        }

        QLabel#Logo {
            min-width: 50px;
            max-width: 50px;
            min-height: 50px;
            max-height: 50px;
            border-radius: 16px;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #0e2e2a,
                stop:1 #0a1a24
            );
            border: 1px solid #24806c;
            color: #7dffd6;
            font-size: 28px;
            font-weight: 900;
        }

        QLabel#MainTitle {
            color: #ffffff;
            font-size: 26px;
            font-weight: 900;
            letter-spacing: 3.5px;
        }

        QLabel#SubTitle {
            color: #5c7079;
            font-size: 8px;
            font-weight: 800;
            letter-spacing: 2.2px;
        }

        QFrame#AIPillFrame {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0a1f1c,
                stop:1 #0c2420
            );
            border: 1px solid #1d5c4f;
            border-radius: 14px;
        }

        QLabel#AIPill {
            color: #7dffd6;
            font-size: 9px;
            font-weight: 850;
            letter-spacing: 0.6px;
            background: transparent;
            border: none;
        }

        QLabel#SystemPill {
            color: #ffffff;
            background: #10181f;
            border: 1px solid #293944;
            border-radius: 13px;
            padding: 9px 14px;
            font-size: 9px;
            font-weight: 850;
            letter-spacing: 0.6px;
            margin-left: 8px;
        }

        QPushButton#WindowButton {
            min-height: 32px;
            max-height: 32px;
            min-width: 32px;
            max-width: 32px;
            padding: 0;
            border-radius: 9px;
            background: #10181f;
            border: 1px solid #253540;
            color: #9db0ba;
            font-size: 12px;
            font-weight: 900;
        }

        QPushButton#WindowButton:hover {
            background: #17222b;
            border-color: #3a5460;
            color: #ffffff;
        }

        QPushButton#CloseButton {
            min-height: 32px;
            max-height: 32px;
            min-width: 32px;
            max-width: 32px;
            padding: 0;
            border-radius: 9px;
            background: #1c1013;
            border: 1px solid #3a1e22;
            color: #ff9d9d;
            font-size: 11px;
            font-weight: 900;
        }

        QPushButton#CloseButton:hover {
            background: #3a1319;
            border-color: #b0454f;
            color: #ffffff;
        }

        QFrame#Toast {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0a1f1c,
                stop:1 #0c2420
            );
            border: 1px solid #2f8a76;
            border-radius: 12px;
        }

        QLabel#ToastLabel {
            color: #7dffd6;
            font-size: 10px;
            font-weight: 900;
            letter-spacing: 0.8px;
            background: transparent;
            border: none;
        }

        QDialog {
            background: #080d13;
        }

        QComboBox {
            background: #10181f;
            border: 1px solid #293944;
            border-radius: 8px;
            padding: 6px 10px;
            color: #eef4f6;
            font-size: 10px;
            font-weight: 700;
            min-height: 26px;
        }

        QComboBox:hover {
            border-color: #3a5460;
        }

        QComboBox QAbstractItemView {
            background: #10181f;
            border: 1px solid #293944;
            selection-background-color: #1c5c4f;
            color: #eef4f6;
            outline: none;
        }

        QDialogButtonBox QPushButton {
            min-height: 32px;
            background: #10181f;
            border: 1px solid #293944;
            border-radius: 9px;
            color: #eef4f6;
            padding: 0 16px;
        }

        QDialogButtonBox QPushButton:hover {
            border-color: #3fc9a9;
            color: #7dffd6;
        }

        QFrame#CameraPanel {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #080d14,
                stop:1 #060a10
            );
            border: 1px solid #1c2c37;
            border-radius: 22px;
        }

        QLabel#PanelTitle {
            color: #93a3ae;
            font-size: 10px;
            font-weight: 900;
            letter-spacing: 2px;
        }

        QLabel#LiveBadge {
            color: #8fa0aa;
            font-size: 9px;
            font-weight: 900;
            letter-spacing: 1.2px;
        }

        /* ==================================================
           CAMERA VIEW — FIXED
           ================================================== */

        QLabel#CameraView {
            background: #020508;
            border: 1px solid #20333d;
            border-radius: 17px;
            color: #52656e;
            font-size: 13px;
            font-weight: 800;
            padding: 0px;
        }

        QLabel#HUD {
            color: #5c6d77;
            font-size: 8px;
            font-weight: 850;
            letter-spacing: 1.1px;
            background: #0b1218;
            border: 1px solid #1a2731;
            border-radius: 8px;
            padding: 5px 10px;
        }

        QFrame#DetectionPanel {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #0a1a17,
                stop:1 #081512
            );
            border: 1px solid #1e5c50;
            border-radius: 22px;
        }

        QLabel#Tiny {
            color: #5b6c76;
            font-size: 8px;
            font-weight: 900;
            letter-spacing: 1.4px;
        }

        QLabel#BigGesture {
            color: #ffffff;
            font-size: 29px;
            font-weight: 950;
            margin-top: 6px;
            letter-spacing: 0.5px;
        }

        QLabel#CurrentAction {
            color: #7dffd6;
            font-size: 9px;
            font-weight: 900;
            letter-spacing: 1.1px;
        }

        QLabel#Percent {
            color: #7dffd6;
            font-size: 9px;
            font-weight: 900;
        }

        QLabel#DetectionStatus {
            color: #6ba193;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #081713,
                stop:1 #0a1a15
            );
            border: 1px solid #1a4b41;
            border-radius: 10px;
            padding: 9px;
            font-size: 8px;
            font-weight: 900;
            letter-spacing: 0.9px;
        }

        QProgressBar {
            background: #0e1b1e;
            border: 1px solid #1a2f2d;
            border-radius: 5px;
            min-height: 7px;
            max-height: 7px;
            margin-top: 6px;
        }

        QProgressBar::chunk {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #2fa88d,
                stop:1 #6dffcf
            );
            border-radius: 4px;
        }

        QProgressBar#Stability::chunk {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #2c8bcf,
                stop:1 #6fd7ff
            );
            border-radius: 4px;
        }

        QFrame#DashboardBox {
            background: #060b11;
            border: 1px solid #182734;
            border-radius: 11px;
        }

        QLabel#DashboardValue {
            color: #7dffd6;
            font-size: 14px;
            font-weight: 900;
        }

        QLabel#DashboardTiny {
            color: #56707a;
            font-size: 7px;
            font-weight: 900;
            letter-spacing: 1px;
        }

        QLabel#DashboardStatus {
            color: #6fd8bf;
            font-size: 8px;
            font-weight: 900;
            letter-spacing: 0.9px;
            background: transparent;
        }

        QFrame#Panel {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #090f16,
                stop:1 #070c12
            );
            border: 1px solid #1a2a35;
            border-radius: 22px;
        }

        QFrame#TelemetryBox {
            background: #070c12;
            border: 1px solid #192a34;
            border-radius: 13px;
        }

        QLabel#TelemetryValue {
            color: #ffffff;
            font-size: 17px;
            font-weight: 900;
        }

        QFrame#ControlDock {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0a1119,
                stop:1 #0a151d
            );
            border: 1px solid #1e2f3a;
            border-radius: 18px;
        }

        QPushButton {
            min-height: 41px;
            border-radius: 12px;
            padding: 0 18px;
            font-size: 9px;
            font-weight: 900;
            letter-spacing: 0.6px;
        }

        QPushButton#StartButton {
            color: #08130f;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #3ef0c4,
                stop:1 #46c9ff
            );
            border: 1px solid #3ce0b8;
            font-weight: 950;
        }

        QPushButton#StartButton:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #55ffd6,
                stop:1 #5fd4ff
            );
        }

        QPushButton#StartButton:pressed {
            background: #2fc9a2;
        }

        QPushButton#CalibrationButton {
            color: #ffd978;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #241d0a,
                stop:1 #2a220c
            );
            border: 1px solid #8a6d28;
        }

        QPushButton#CalibrationButton:hover {
            color: #fff0b0;
            background: #33290e;
            border-color: #d0ac52;
        }

        QPushButton#ControlButton {
            color: #e7f0f2;
            background: #121b24;
            border: 1px solid #2c3d48;
        }

        QPushButton#ControlButton:hover {
            border-color: #58798a;
            background: #16212b;
        }

        QPushButton:disabled {
            color: #3c474e;
            background: #080c11;
            border-color: #151d23;
        }

        QFrame#Divider {
            background: #253742;
        }

        QLabel#SliderValue {
            color: #7dffd6;
            font-size: 11px;
            font-weight: 900;
            min-width: 18px;
        }

        QLabel#DockInfo {
            color: #55707a;
            font-size: 8px;
            font-weight: 850;
            letter-spacing: 1.1px;
        }

        QSlider::groove:horizontal {
            height: 5px;
            background: #18262f;
            border-radius: 3px;
        }

        QSlider::sub-page:horizontal {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #2c8e7c,
                stop:1 #3fc9a9
            );
            border-radius: 3px;
        }

        QSlider::handle:horizontal {
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 9px;
            background: qradialgradient(
                cx:0.5, cy:0.5, radius:0.6,
                stop:0 #ffffff,
                stop:1 #7dffd6
            );
            border: 1px solid #3fc9a9;
        }

        QFrame#GestureTile {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #0a1119,
                stop:1 #080d13
            );
            border: 1px solid #1a2a35;
            border-radius: 14px;
        }

        QFrame#GestureTile:hover {
            background: #0d1a1c;
            border: 1px solid #2f8a76;
        }

        QFrame#GestureTile[active="true"] {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0c2b24,
                stop:1 #0a2620
            );
            border: 1px solid #47dcb9;
        }

        QFrame#TileIconWrap {
            min-width: 34px;
            max-width: 34px;
            min-height: 34px;
            max-height: 34px;
            background: #0c161c;
            border: 1px solid #203038;
            border-radius: 10px;
        }

        QLabel#TileIcon {
            font-size: 17px;
            background: transparent;
            border: none;
        }

        QLabel#TileGesture {
            color: #e2ecee;
            font-size: 8px;
            font-weight: 900;
            letter-spacing: 0.8px;
        }

        QLabel#TileAction {
            color: #5c6d76;
            font-size: 7px;
            font-weight: 700;
        }

        QLabel#HistoryLine {
            color: #7dffd6;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #081713,
                stop:1 #0a1a15
            );
            border: 1px solid #1a4b41;
            border-radius: 10px;
            padding: 8px 14px;
            font-size: 8px;
            font-weight: 850;
        }

        QLabel#Footer {
            color: #2c3d46;
            font-size: 7px;
            font-weight: 800;
            letter-spacing: 1.8px;
        }
        """


# ============================================================
# SPLASH
# ============================================================

def build_splash_pixmap():

    pixmap = QPixmap(
        420,
        260,
    )

    pixmap.fill(
        QColor("#05070c")
    )

    painter = QPainter(
        pixmap
    )

    painter.setRenderHint(
        QPainter.Antialiasing,
        True,
    )

    painter.setPen(
        QPen(
            QColor("#1c2b34")
        )
    )

    painter.setBrush(
        QColor("#080d14")
    )

    painter.drawRoundedRect(
        pixmap.rect().adjusted(
            1,
            1,
            -1,
            -1,
        ),
        18,
        18,
    )

    painter.setPen(
        QColor("#7dffd6")
    )

    painter.setFont(
        QFont(
            "Segoe UI",
            34,
            QFont.Black,
        )
    )

    painter.drawText(
        QRect(
            0,
            70,
            420,
            60,
        ),
        Qt.AlignCenter,
        "✦ GESTUREOS",
    )

    painter.setPen(
        QColor("#5c7079")
    )

    painter.setFont(
        QFont(
            "Segoe UI",
            9,
            QFont.DemiBold,
        )
    )

    painter.drawText(
        QRect(
            0,
            130,
            420,
            26,
        ),
        Qt.AlignCenter,
        "AI HAND INTERFACE  ·  COMPUTER VISION SYSTEM",
    )

    painter.setPen(
        QColor("#3fc9a9")
    )

    painter.setFont(
        QFont(
            "Segoe UI",
            8,
            QFont.Bold,
        )
    )

    painter.drawText(
        QRect(
            0,
            210,
            420,
            24,
        ),
        Qt.AlignCenter,
        f"Loading  {APP_VERSION}...",
    )

    painter.end()

    return pixmap


# ============================================================
# APPLICATION
# ============================================================

def main():

    try:

        app = QApplication.instance()

        if app is None:

            app = QApplication(
                sys.argv
            )

        app.setApplicationName(
            "GestureOS"
        )

        app.setQuitOnLastWindowClosed(
            True
        )

        splash = QSplashScreen(
            build_splash_pixmap()
        )

        splash.show()

        app.processEvents()

        window = GestureOS()

        def show_window():

            window.show()
            window.raise_()
            window.activateWindow()

            splash.finish(
                window
            )

        QTimer.singleShot(
            700,
            show_window,
        )

        return app.exec()

    except Exception:

        logger.exception(
            "Fatal error while starting GestureOS"
        )

        import traceback

        traceback.print_exc()

        return 1


if __name__ == "__main__":

    sys.exit(
        main()
    )