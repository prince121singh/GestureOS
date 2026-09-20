import cv2
import pyautogui

from core.camera_engine import CameraEngine
from core.controller import GestureController


WINDOW_NAME = "GestureOS - Full Control"


def main():

    engine = CameraEngine()

    controller = GestureController(
        cooldown=0.8,
        sensitivity=30,
    )

    pinch_latched = False
    action_latched = False

    last_gesture = "No Hand"
    last_action = "NO ACTION"

    try:

        print("=" * 65)
        print("GESTUREOS - FULL DESKTOP CONTROL")
        print("=" * 65)
        print()
        print("Point       = Move Cursor")
        print("Pinch       = Left Click")
        print("Peace       = Scroll")
        print("Thumb Up    = Volume Up")
        print("Thumb Down  = Volume Down")
        print("Fist        = Screenshot")
        print("Open Palm   = Pause")
        print()
        print("Q / ESC = Exit")
        print("=" * 65)
        print()

        engine.start()
        controller.enable()

        # ==================================================
        # CAMERA WINDOW
        # ==================================================

        cv2.namedWindow(
            WINDOW_NAME,
            cv2.WINDOW_NORMAL
        )

        cv2.resizeWindow(
            WINDOW_NAME,
            720,
            480
        )

        cv2.moveWindow(
            WINDOW_NAME,
            20,
            40
        )

        print("Camera started.")
        print("Controller enabled.")
        print()

        while engine.is_running():

            data = engine.read()

            if data is None:
                print("No camera frame.")
                break

            frame = data["frame"]
            results = data["results"]

            gesture = data["gesture"]
            hand = data["hand"]
            confidence = data["confidence"]
            fps = data["fps"]

            height, width = frame.shape[:2]

            action = "NO ACTION"

            # ==================================================
            # RESET LATCHES WHEN HAND DISAPPEARS
            # ==================================================

            if gesture == "No Hand":

                pinch_latched = False
                action_latched = False

            # ==================================================
            # POINT -> CURSOR
            # ==================================================

            if (
                gesture == "Point"
                and results.hand_landmarks
            ):

                landmarks = (
                    results.hand_landmarks[0]
                )

                index_tip = landmarks[8]

                x = index_tip.x * width
                y = index_tip.y * height

                moved = controller.move_cursor(
                    x,
                    y,
                    width,
                    height,
                )

                if moved:
                    action = "CURSOR MOVING"
                else:
                    action = "CURSOR ERROR"

                last_action = action

            # ==================================================
            # PINCH -> ONE CLICK
            # ==================================================

            elif gesture == "Pinch":

                action = "PINCH READY"

                if not pinch_latched:

                    mouse_x, mouse_y = (
                        pyautogui.position()
                    )

                    clicked = controller.click()

                    if clicked:

                        action = "LEFT CLICK"

                        print(
                            f"LEFT CLICK "
                            f"X:{mouse_x} "
                            f"Y:{mouse_y}"
                        )

                        pinch_latched = True

                    else:

                        action = "CLICK ERROR"

                last_action = action

            else:

                pinch_latched = False

            # ==================================================
            # PEACE -> SCROLL
            # ==================================================

            if (
                gesture == "Peace"
                and results.hand_landmarks
            ):

                landmarks = (
                    results.hand_landmarks[0]
                )

                wrist_y = landmarks[0].y

                scroll_amount = (
                    controller.scroll(
                        wrist_y
                    )
                )

                if scroll_amount > 0:

                    action = "SCROLL UP"

                elif scroll_amount < 0:

                    action = "SCROLL DOWN"

                else:

                    action = "SCROLL READY"

                last_action = action

            else:

                controller.last_scroll_y = None

            # ==================================================
            # THUMB UP -> VOLUME UP
            # ==================================================

            if (
                gesture == "Thumb Up"
                and not action_latched
            ):

                success = (
                    controller.perform_action(
                        "Volume Up"
                    )
                )

                if success:

                    action = "VOLUME UP"

                    print(
                        "VOLUME UP"
                    )

                    action_latched = True

                else:

                    action = "VOLUME ERROR"

                last_action = action

            # ==================================================
            # THUMB DOWN -> VOLUME DOWN
            # ==================================================

            elif (
                gesture == "Thumb Down"
                and not action_latched
            ):

                success = (
                    controller.perform_action(
                        "Volume Down"
                    )
                )

                if success:

                    action = "VOLUME DOWN"

                    print(
                        "VOLUME DOWN"
                    )

                    action_latched = True

                else:

                    action = "VOLUME ERROR"

                last_action = action

            # ==================================================
            # FIST -> SCREENSHOT
            # ==================================================

            elif (
                gesture == "Fist"
                and not action_latched
            ):

                success = (
                    controller.perform_action(
                        "Screenshot"
                    )
                )

                if success:

                    action = "SCREENSHOT SAVED"

                    print(
                        "SCREENSHOT SAVED"
                    )

                    action_latched = True

                else:

                    action = "SCREENSHOT ERROR"

                last_action = action

            # ==================================================
            # OPEN PALM -> PAUSE
            # ==================================================

            elif (
                gesture == "Open Palm"
                and not action_latched
            ):

                success = (
                    controller.perform_action(
                        "Pause"
                    )
                )

                if success:

                    action = "PAUSE / PLAY"

                    print(
                        "PAUSE / PLAY"
                    )

                    action_latched = True

                else:

                    action = "PAUSE ERROR"

                last_action = action

            # ==================================================
            # RESET ACTION LATCH WHEN GESTURE CHANGES
            # ==================================================

            if gesture != last_gesture:

                if gesture not in [
                    "Thumb Up",
                    "Thumb Down",
                    "Fist",
                    "Open Palm",
                ]:

                    action_latched = False

                else:

                    action_latched = False

            last_gesture = gesture

            # ==================================================
            # HUD
            # ==================================================

            cv2.rectangle(
                frame,
                (15, 15),
                (535, 220),
                (10, 10, 10),
                -1,
            )

            cv2.putText(
                frame,
                "GESTUREOS",
                (30, 48),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                f"Gesture : {gesture}",
                (30, 78),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                f"Hand : {hand}",
                (30, 103),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                f"Confidence : {confidence:.0f}%",
                (30, 128),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                f"FPS : {fps:.1f}",
                (30, 153),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                f"Action : {action}",
                (30, 180),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                "STATUS : ACTIVE",
                (30, 205),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

            # ==================================================
            # POINT VISUAL
            # ==================================================

            if (
                gesture == "Point"
                and results.hand_landmarks
            ):

                index_tip = (
                    results.hand_landmarks[0][8]
                )

                point_x = int(
                    (1.0 - index_tip.x)
                    * width
                )

                point_y = int(
                    index_tip.y
                    * height
                )

                cv2.circle(
                    frame,
                    (point_x, point_y),
                    18,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

                cv2.circle(
                    frame,
                    (point_x, point_y),
                    5,
                    (0, 255, 255),
                    -1,
                    cv2.LINE_AA,
                )

                cv2.putText(
                    frame,
                    "CURSOR",
                    (
                        max(point_x - 40, 10),
                        max(point_y - 25, 30),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

            # ==================================================
            # PINCH VISUAL
            # ==================================================

            if (
                gesture == "Pinch"
                and results.hand_landmarks
            ):

                landmarks = (
                    results.hand_landmarks[0]
                )

                thumb_tip = landmarks[4]
                index_tip = landmarks[8]

                thumb_x = int(
                    (1.0 - thumb_tip.x)
                    * width
                )

                thumb_y = int(
                    thumb_tip.y
                    * height
                )

                index_x = int(
                    (1.0 - index_tip.x)
                    * width
                )

                index_y = int(
                    index_tip.y
                    * height
                )

                cv2.line(
                    frame,
                    (thumb_x, thumb_y),
                    (index_x, index_y),
                    (0, 255, 255),
                    3,
                    cv2.LINE_AA,
                )

                cv2.circle(
                    frame,
                    (thumb_x, thumb_y),
                    10,
                    (0, 255, 255),
                    -1,
                    cv2.LINE_AA,
                )

                cv2.circle(
                    frame,
                    (index_x, index_y),
                    10,
                    (0, 255, 255),
                    -1,
                    cv2.LINE_AA,
                )

                center_x = (
                    thumb_x + index_x
                ) // 2

                center_y = (
                    thumb_y + index_y
                ) // 2

                cv2.circle(
                    frame,
                    (center_x, center_y),
                    24,
                    (0, 255, 255),
                    3,
                    cv2.LINE_AA,
                )

                cv2.putText(
                    frame,
                    "CLICK",
                    (
                        max(center_x - 35, 10),
                        max(center_y - 32, 30),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

            # ==================================================
            # PEACE VISUAL
            # ==================================================

            if (
                gesture == "Peace"
                and results.hand_landmarks
            ):

                wrist = (
                    results.hand_landmarks[0][0]
                )

                peace_x = int(
                    (1.0 - wrist.x)
                    * width
                )

                peace_y = int(
                    wrist.y
                    * height
                )

                cv2.circle(
                    frame,
                    (peace_x, peace_y),
                    25,
                    (255, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

                cv2.putText(
                    frame,
                    "SCROLL",
                    (
                        max(peace_x - 40, 10),
                        max(peace_y - 32, 30),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

            # ==================================================
            # THUMB / FIST / PALM LABEL
            # ==================================================

            gesture_labels = {
                "Thumb Up": "VOLUME +",
                "Thumb Down": "VOLUME -",
                "Fist": "SCREENSHOT",
                "Open Palm": "PAUSE",
            }

            if (
                gesture in gesture_labels
                and results.hand_landmarks
            ):

                wrist = (
                    results.hand_landmarks[0][0]
                )

                label_x = int(
                    (1.0 - wrist.x)
                    * width
                )

                label_y = int(
                    wrist.y
                    * height
                )

                cv2.putText(
                    frame,
                    gesture_labels[gesture],
                    (
                        max(label_x - 50, 10),
                        max(label_y - 30, 30),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

            # ==================================================
            # DISPLAY
            # ==================================================

            cv2.imshow(
                WINDOW_NAME,
                frame,
            )

            key = (
                cv2.waitKey(1)
                & 0xFF
            )

            if (
                key == ord("q")
                or key == 27
            ):
                break

    except Exception as error:

        print()
        print("=" * 65)
        print("GESTUREOS ERROR")
        print("=" * 65)
        print(error)
        print()

        import traceback

        traceback.print_exc()

        input(
            "Press ENTER to close..."
        )

    finally:

        controller.disable()

        engine.stop()

        cv2.destroyAllWindows()

        print()
        print(
            "GestureOS stopped."
        )


if __name__ == "__main__":

    main()