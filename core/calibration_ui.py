from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class CalibrationWindow(QDialog):

    calibration_finished = Signal()

    GESTURES = [
        "Pinch",
        "Point",
        "Peace",
        "Thumb Up",
        "Thumb Down",
        "Fist",
        "Open Palm",
        "Three Fingers",
        "Rock Sign",
    ]

    REQUIRED_SAMPLES = 30

    def __init__(
        self,
        camera_engine,
        gesture_engine,
        calibration_manager,
        parent=None,
    ):
        super().__init__(parent)

        self.camera_engine = camera_engine
        self.gesture_engine = gesture_engine
        self.calibration_manager = calibration_manager

        self.current_gesture = self.GESTURES[0]

        self.samples_collected = 0
        self.calibrating = False
        self.finished = False

        self.timer = None

        self.setWindowTitle(
            "GestureOS • Calibration Mode"
        )

        self.setMinimumSize(
            820,
            650,
        )

        self.resize(
            900,
            700,
        )

        self.setModal(False)

        self.setStyleSheet(
            self.stylesheet()
        )

        self.build_ui()
        self.setup_timer()

        self.update_gesture_ui()

    # =========================================================
    # UI
    # =========================================================

    def build_ui(self):

        root = QVBoxLayout(self)

        root.setContentsMargins(
            28,
            24,
            28,
            24,
        )

        root.setSpacing(18)

        # =====================================================
        # HEADER
        # =====================================================

        header = QHBoxLayout()

        title_box = QVBoxLayout()

        title = QLabel(
            "GESTURE CALIBRATION"
        )

        title.setObjectName(
            "Title"
        )

        subtitle = QLabel(
            "Train GestureOS for your hand position and movement"
        )

        subtitle.setObjectName(
            "Subtitle"
        )

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(
            title_box
        )

        header.addStretch()

        self.status_badge = QLabel(
            "● PAUSED"
        )

        self.status_badge.setObjectName(
            "StatusBadge"
        )

        header.addWidget(
            self.status_badge
        )

        root.addLayout(
            header
        )

        # =====================================================
        # GESTURE SELECTOR
        # =====================================================

        selector_card = QFrame()

        selector_card.setObjectName(
            "Card"
        )

        selector_layout = QHBoxLayout(
            selector_card
        )

        selector_layout.setContentsMargins(
            18,
            14,
            18,
            14,
        )

        selector_title = QLabel(
            "CALIBRATE GESTURE"
        )

        selector_title.setObjectName(
            "SmallTitle"
        )

        selector_layout.addWidget(
            selector_title
        )

        selector_layout.addStretch()

        self.gesture_combo = QComboBox()

        self.gesture_combo.addItems(
            self.GESTURES
        )

        self.gesture_combo.setMinimumWidth(
            250
        )

        self.gesture_combo.currentTextChanged.connect(
            self.change_gesture
        )

        selector_layout.addWidget(
            self.gesture_combo
        )

        root.addWidget(
            selector_card
        )

        # =====================================================
        # MAIN CALIBRATION CARD
        # =====================================================

        calibration_card = QFrame()

        calibration_card.setObjectName(
            "CalibrationCard"
        )

        calibration_layout = QVBoxLayout(
            calibration_card
        )

        calibration_layout.setContentsMargins(
            24,
            24,
            24,
            24,
        )

        calibration_layout.setSpacing(
            18
        )

        self.gesture_title = QLabel(
            self.current_gesture.upper()
        )

        self.gesture_title.setObjectName(
            "GestureTitle"
        )

        self.gesture_title.setAlignment(
            Qt.AlignCenter
        )

        calibration_layout.addWidget(
            self.gesture_title
        )

        # =====================================================
        # SAMPLE COUNT
        # =====================================================

        sample_header = QHBoxLayout()

        sample_label = QLabel(
            "SAMPLES"
        )

        sample_label.setObjectName(
            "SmallTitle"
        )

        sample_header.addWidget(
            sample_label
        )

        sample_header.addStretch()

        self.sample_value = QLabel(
            "0 / 30"
        )

        self.sample_value.setObjectName(
            "Value"
        )

        sample_header.addWidget(
            self.sample_value
        )

        calibration_layout.addLayout(
            sample_header
        )

        self.sample_bar = QProgressBar()

        self.sample_bar.setRange(
            0,
            self.REQUIRED_SAMPLES
        )

        self.sample_bar.setValue(
            0
        )

        self.sample_bar.setTextVisible(
            False
        )

        self.sample_bar.setObjectName(
            "SampleBar"
        )

        calibration_layout.addWidget(
            self.sample_bar
        )

        # =====================================================
        # CONFIDENCE
        # =====================================================

        confidence_header = QHBoxLayout()

        confidence_label = QLabel(
            "CONFIDENCE"
        )

        confidence_label.setObjectName(
            "SmallTitle"
        )

        confidence_header.addWidget(
            confidence_label
        )

        confidence_header.addStretch()

        self.confidence_value = QLabel(
            "0%"
        )

        self.confidence_value.setObjectName(
            "Value"
        )

        confidence_header.addWidget(
            self.confidence_value
        )

        calibration_layout.addLayout(
            confidence_header
        )

        self.confidence_bar = QProgressBar()

        self.confidence_bar.setRange(
            0,
            100
        )

        self.confidence_bar.setValue(
            0
        )

        self.confidence_bar.setTextVisible(
            False
        )

        self.confidence_bar.setObjectName(
            "ConfidenceBar"
        )

        calibration_layout.addWidget(
            self.confidence_bar
        )

        # =====================================================
        # STABILITY
        # =====================================================

        stability_header = QHBoxLayout()

        stability_label = QLabel(
            "STABILITY"
        )

        stability_label.setObjectName(
            "SmallTitle"
        )

        stability_header.addWidget(
            stability_label
        )

        stability_header.addStretch()

        self.stability_value = QLabel(
            "0%"
        )

        self.stability_value.setObjectName(
            "Value"
        )

        stability_header.addWidget(
            self.stability_value
        )

        calibration_layout.addLayout(
            stability_header
        )

        self.stability_bar = QProgressBar()

        self.stability_bar.setRange(
            0,
            100
        )

        self.stability_bar.setValue(
            0
        )

        self.stability_bar.setTextVisible(
            False
        )

        self.stability_bar.setObjectName(
            "StabilityBar"
        )

        calibration_layout.addWidget(
            self.stability_bar
        )

        root.addWidget(
            calibration_card
        )

        # =====================================================
        # BUTTONS
        # =====================================================

        buttons = QHBoxLayout()

        buttons.setSpacing(
            12
        )

        self.start_button = QPushButton(
            "▶  START CALIBRATION"
        )

        self.start_button.setObjectName(
            "PrimaryButton"
        )

        self.start_button.clicked.connect(
            self.toggle_calibration
        )

        buttons.addWidget(
            self.start_button
        )

        self.next_button = QPushButton(
            "NEXT GESTURE  →"
        )

        self.next_button.setObjectName(
            "SecondaryButton"
        )

        self.next_button.clicked.connect(
            self.next_gesture
        )

        buttons.addWidget(
            self.next_button
        )

        self.reset_button = QPushButton(
            "↻  RESET"
        )

        self.reset_button.setObjectName(
            "DangerButton"
        )

        self.reset_button.clicked.connect(
            self.reset_calibration
        )

        buttons.addWidget(
            self.reset_button
        )

        root.addLayout(
            buttons
        )

        # =====================================================
        # INFO
        # =====================================================

        self.info_label = QLabel(
            "Keep the selected gesture steady • 30 valid samples are required"
        )

        self.info_label.setObjectName(
            "Info"
        )

        self.info_label.setAlignment(
            Qt.AlignCenter
        )

        root.addWidget(
            self.info_label
        )

    # =========================================================
    # TIMER
    # =========================================================

    def setup_timer(self):

        self.timer = QTimer(
            self
        )

        self.timer.setInterval(
            80
        )

        self.timer.timeout.connect(
            self.update_calibration
        )

    # =========================================================
    # CHANGE GESTURE
    # =========================================================

    def change_gesture(
        self,
        gesture,
    ):

        if self.calibrating:
            self.stop_calibration()

        self.current_gesture = gesture

        self.samples_collected = 0

        self.sample_bar.setValue(
            0
        )

        self.sample_value.setText(
            f"0 / {self.REQUIRED_SAMPLES}"
        )

        self.gesture_title.setText(
            gesture.upper()
        )

        self.info_label.setText(
            "Keep the selected gesture steady • 30 valid samples are required"
        )

        self.status_badge.setText(
            "● PAUSED"
        )

    # =========================================================
    # UPDATE GESTURE UI
    # =========================================================

    def update_gesture_ui(self):

        self.gesture_title.setText(
            self.current_gesture.upper()
        )

        self.sample_value.setText(
            f"{self.samples_collected} / {self.REQUIRED_SAMPLES}"
        )

        self.sample_bar.setValue(
            self.samples_collected
        )

    # =========================================================
    # START / STOP
    # =========================================================

    def toggle_calibration(self):

        if self.calibrating:
            self.stop_calibration()
        else:
            self.start_calibration()

    def start_calibration(self):

        try:

            self.calibration_manager.start(
                self.current_gesture
            )

            self.samples_collected = 0

            self.sample_bar.setValue(
                0
            )

            self.sample_value.setText(
                f"0 / {self.REQUIRED_SAMPLES}"
            )

            self.calibrating = True

            self.start_button.setText(
                "■  STOP CALIBRATION"
            )

            self.status_badge.setText(
                "● RECORDING"
            )

            self.info_label.setText(
                f"Hold {self.current_gesture} steady..."
            )

            self.timer.start()

        except Exception as error:

            QMessageBox.warning(
                self,
                "Calibration Error",
                str(error),
            )

    def stop_calibration(self):

        self.calibrating = False

        if self.timer is not None:
            self.timer.stop()

        try:
            self.calibration_manager.stop()
        except Exception:
            pass

        self.start_button.setText(
            "▶  START CALIBRATION"
        )

        self.status_badge.setText(
            "● PAUSED"
        )

    # =========================================================
    # UPDATE CALIBRATION
    # =========================================================

    def update_calibration(self):

        if not self.calibrating:
            return

        try:

            confidence = self.get_confidence()
            stability = self.get_stability()

            confidence_value = self.to_percent(
                confidence
            )

            stability_value = self.to_percent(
                stability
            )

            self.confidence_bar.setValue(
                confidence_value
            )

            self.confidence_value.setText(
                f"{confidence_value}%"
            )

            self.stability_bar.setValue(
                stability_value
            )

            self.stability_value.setText(
                f"{stability_value}%"
            )

            # -------------------------------------------------
            # VALID SAMPLE
            # -------------------------------------------------

            if (
                confidence_value >= 55
                and stability_value >= 45
            ):

                self.add_valid_sample(
                    confidence,
                    stability
                )

        except Exception as error:

            self.stop_calibration()

            QMessageBox.warning(
                self,
                "Calibration Error",
                str(error),
            )

    # =========================================================
    # CONFIDENCE
    # =========================================================

    def get_confidence(self):

        try:

            value = self.gesture_engine.get_last_confidence()

            if value is None:
                value = self.gesture_engine.get_confidence()

            return float(
                value
            )

        except Exception:

            try:
                return float(
                    self.gesture_engine.confidence
                )
            except Exception:
                return 0.0

    # =========================================================
    # STABILITY
    # =========================================================

    def get_stability(self):

        try:

            return float(
                self.gesture_engine.get_stability()
            )

        except Exception:

            try:
                return float(
                    self.gesture_engine.stability
                )
            except Exception:
                return 0.0

    # =========================================================
    # PERCENT CONVERSION
    # =========================================================

    def to_percent(
        self,
        value,
    ):

        value = float(
            value
        )

        if value <= 1.0:
            value *= 100

        return max(
            0,
            min(
                100,
                int(value)
            )
        )

    # =========================================================
    # ADD VALID SAMPLE
    # =========================================================

    def add_valid_sample(
        self,
        confidence,
        stability,
    ):

        if self.samples_collected >= self.REQUIRED_SAMPLES:
            return

        # IMPORTANT:
        # CalibrationManager requires:
        # gesture + confidence + stability

        self.calibration_manager.add_sample(
            self.current_gesture,
            float(confidence),
            float(stability),
        )

        self.samples_collected += 1

        self.sample_bar.setValue(
            self.samples_collected
        )

        self.sample_value.setText(
            f"{self.samples_collected} / {self.REQUIRED_SAMPLES}"
        )

        if (
            self.samples_collected
            >= self.REQUIRED_SAMPLES
        ):

            self.finish_current_gesture()

    # =========================================================
    # FINISH CURRENT GESTURE
    # =========================================================

    def finish_current_gesture(self):

        self.stop_calibration()

        try:

            self.calibration_manager.calibrate_gesture(
                self.current_gesture
            )

        except Exception:
            pass

        self.info_label.setText(
            f"✓ {self.current_gesture} calibrated successfully"
        )

        self.status_badge.setText(
            "● COMPLETE"
        )

        current_index = self.GESTURES.index(
            self.current_gesture
        )

        if current_index >= len(
            self.GESTURES
        ) - 1:

            self.finish_all()

    # =========================================================
    # NEXT GESTURE
    # =========================================================

    def next_gesture(self):

        if self.calibrating:
            self.stop_calibration()

        current_index = self.GESTURES.index(
            self.current_gesture
        )

        next_index = (
            current_index + 1
        )

        if next_index >= len(
            self.GESTURES
        ):

            self.finish_all()

            return

        self.gesture_combo.setCurrentIndex(
            next_index
        )

    # =========================================================
    # FINISH ALL
    # =========================================================

    def finish_all(self):

        if self.finished:
            return

        self.finished = True

        try:

            self.calibration_manager.calibrate_all()

        except Exception:
            pass

        try:

            self.calibration_manager.save_profile()

        except Exception as error:

            QMessageBox.warning(
                self,
                "Calibration Save Error",
                str(error),
            )

        self.status_badge.setText(
            "● CALIBRATION SAVED"
        )

        self.info_label.setText(
            "✓ Calibration profile saved successfully"
        )

        self.start_button.setEnabled(
            False
        )

        self.next_button.setEnabled(
            False
        )

        self.calibration_finished.emit()

    # =========================================================
    # RESET
    # =========================================================

    def reset_calibration(self):

        if self.calibrating:
            self.stop_calibration()

        reply = QMessageBox.question(
            self,
            "Reset Calibration",
            "Reset the calibration profile?",
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:

            self.calibration_manager.reset()

        except Exception:
            pass

        self.samples_collected = 0
        self.finished = False

        self.sample_bar.setValue(
            0
        )

        self.sample_value.setText(
            f"0 / {self.REQUIRED_SAMPLES}"
        )

        self.confidence_bar.setValue(
            0
        )

        self.confidence_value.setText(
            "0%"
        )

        self.stability_bar.setValue(
            0
        )

        self.stability_value.setText(
            "0%"
        )

        self.status_badge.setText(
            "● PAUSED"
        )

        self.info_label.setText(
            "Calibration profile reset"
        )

        self.start_button.setEnabled(
            True
        )

        self.next_button.setEnabled(
            True
        )

    # =========================================================
    # CLOSE
    # =========================================================

    def closeEvent(
        self,
        event,
    ):

        try:

            if self.calibrating:
                self.stop_calibration()

        except Exception:
            pass

        event.accept()

    # =========================================================
    # STYLE
    # =========================================================

    def stylesheet(self):

        return """

        QDialog {
            background: #05080d;
            color: #eaf2f4;
        }

        QLabel {
            color: #eaf2f4;
            font-family: "Segoe UI";
        }

        QLabel#Title {
            color: #ffffff;
            font-size: 27px;
            font-weight: 900;
            letter-spacing: 2px;
        }

        QLabel#Subtitle {
            color: #61727d;
            font-size: 11px;
            font-weight: 600;
        }

        QLabel#StatusBadge {
            color: #ffd76b;
            background: #211b08;
            border: 1px solid #765e1e;
            border-radius: 10px;
            padding: 12px 18px;
            font-size: 10px;
            font-weight: 900;
        }

        QFrame#Card {
            background: #0a0f16;
            border: 1px solid #1d2b35;
            border-radius: 16px;
        }

        QFrame#CalibrationCard {
            background: #0b1018;
            border: 1px solid #202f3a;
            border-radius: 18px;
        }

        QLabel#SmallTitle {
            color: #667984;
            font-size: 9px;
            font-weight: 900;
            letter-spacing: 1.2px;
        }

        QLabel#GestureTitle {
            color: #78a9ff;
            font-size: 29px;
            font-weight: 950;
            letter-spacing: 2px;
        }

        QLabel#Value {
            color: #ffffff;
            font-size: 10px;
            font-weight: 900;
        }

        QLabel#Info {
            color: #566873;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }

        QComboBox {
            min-height: 38px;
            background: #111824;
            border: 1px solid #293746;
            border-radius: 9px;
            padding: 0 12px;
            color: #ffffff;
            font-size: 10px;
            font-weight: 700;
        }

        QComboBox:hover {
            border-color: #4e7198;
        }

        QComboBox QAbstractItemView {
            background: #0c131c;
            color: #ffffff;
            border: 1px solid #2a3946;
            selection-background-color: #193a64;
            selection-color: #ffffff;
        }

        QProgressBar {
            background: #111922;
            border: 1px solid #1d2c37;
            border-radius: 5px;
            min-height: 8px;
            max-height: 8px;
        }

        QProgressBar::chunk {
            background: #55a4ff;
            border-radius: 4px;
        }

        QProgressBar#ConfidenceBar::chunk {
            background: #62e6bd;
            border-radius: 4px;
        }

        QProgressBar#StabilityBar::chunk {
            background: #55cfff;
            border-radius: 4px;
        }

        QProgressBar#SampleBar::chunk {
            background: #a98cff;
            border-radius: 4px;
        }

        QPushButton {
            min-height: 44px;
            border-radius: 10px;
            padding: 0 18px;
            font-size: 9px;
            font-weight: 900;
            letter-spacing: 0.5px;
        }

        QPushButton#PrimaryButton {
            color: #ffffff;
            background: #163b6b;
            border: 1px solid #387ac2;
        }

        QPushButton#PrimaryButton:hover {
            background: #1b4b85;
            border-color: #5ba7ff;
        }

        QPushButton#SecondaryButton {
            color: #dce8f2;
            background: #111824;
            border: 1px solid #2b3948;
        }

        QPushButton#SecondaryButton:hover {
            background: #182331;
            border-color: #4c6175;
        }

        QPushButton#DangerButton {
            color: #ff8998;
            background: #241116;
            border: 1px solid #63303b;
        }

        QPushButton#DangerButton:hover {
            background: #34151c;
            border-color: #a24a5c;
        }

        QPushButton:disabled {
            color: #46525a;
            background: #090d12;
            border-color: #182028;
        }

        """
