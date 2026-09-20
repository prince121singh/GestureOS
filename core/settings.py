import copy
import json
from pathlib import Path


class GestureSettings:

    # ============================================================
    # CORE GESTURES
    # ============================================================

    GESTURES = [
        "Point",
        "Pinch",
        "Peace",
        "Thumb Up",
        "Thumb Down",
        "Fist",
        "Open Palm",
        "Three Fingers",
        "Rock Sign",
    ]

    # ============================================================
    # AVAILABLE SAFE ACTIONS
    # ============================================================

    ACTIONS = [
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
    ]

    # ============================================================
    # DEFAULT SETTINGS
    # ============================================================

    DEFAULTS = {
        "profile": "Balanced",

        "sensitivity": 30,

        "performance_mode": "Balanced",

        "enabled_gestures": {
            "Point": True,
            "Pinch": True,
            "Peace": True,
            "Thumb Up": True,
            "Thumb Down": True,
            "Fist": True,
            "Open Palm": True,
            "Three Fingers": True,
            "Rock Sign": True,
        },

        "gesture_mappings": {
            "Point": "Cursor",
            "Pinch": "Click",
            "Peace": "Scroll",
            "Thumb Up": "Volume Up",
            "Thumb Down": "Volume Down",
            "Fist": "Screenshot",
            "Open Palm": "Pause",
            "Three Fingers": "No Action",
            "Rock Sign": "No Action",
        },
    }

    # ============================================================
    # BUILT-IN PROFILES
    # ============================================================

    PROFILES = {

        "Performance": {
            "sensitivity": 45,
            "performance_mode": "Performance",
        },

        "Balanced": {
            "sensitivity": 30,
            "performance_mode": "Balanced",
        },

        "Accuracy": {
            "sensitivity": 20,
            "performance_mode": "Accuracy",
        },
    }

    # ============================================================
    # INIT
    # ============================================================

    def __init__(
        self,
        filename="gesture_settings.json",
    ):

        self.base_dir = (
            Path(__file__).resolve().parent.parent
        )

        self.file_path = (
            self.base_dir / filename
        )

        self.data = self._load()

    # ============================================================
    # LOAD
    # ============================================================

    def _load(self):

        if not self.file_path.exists():
            return self._copy_defaults()

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8",
            ) as file:

                saved = json.load(file)

            data = self._copy_defaults()

            if not isinstance(saved, dict):
                return data

            # ----------------------------------------------------
            # BASIC SETTINGS
            # ----------------------------------------------------

            if "profile" in saved:

                profile = str(
                    saved["profile"]
                )

                if profile:
                    data["profile"] = profile

            if "sensitivity" in saved:

                try:

                    data["sensitivity"] = max(
                        10,
                        min(
                            60,
                            int(
                                saved["sensitivity"]
                            ),
                        ),
                    )

                except Exception:
                    pass

            if "performance_mode" in saved:

                mode = str(
                    saved["performance_mode"]
                )

                if mode in {
                    "Performance",
                    "Balanced",
                    "Accuracy",
                }:

                    data["performance_mode"] = mode

            # ----------------------------------------------------
            # ENABLED GESTURES
            # ----------------------------------------------------

            enabled = saved.get(
                "enabled_gestures"
            )

            if isinstance(enabled, dict):

                for gesture in self.GESTURES:

                    if gesture in enabled:

                        data[
                            "enabled_gestures"
                        ][gesture] = bool(
                            enabled[gesture]
                        )

            # ----------------------------------------------------
            # CUSTOM MAPPINGS
            # ----------------------------------------------------

            mappings = saved.get(
                "gesture_mappings"
            )

            if isinstance(mappings, dict):

                for gesture in self.GESTURES:

                    if gesture not in mappings:
                        continue

                    action = str(
                        mappings[gesture]
                    )

                    if action in self.ACTIONS:

                        data[
                            "gesture_mappings"
                        ][gesture] = action

            # ----------------------------------------------------
            # BACKWARD COMPATIBILITY
            # ----------------------------------------------------

            # Older V6/V5 settings files do not have
            # gesture_mappings. Defaults are already applied.

            return data

        except Exception as error:

            print(
                f"GestureSettings load error: {error}"
            )

            return self._copy_defaults()

    # ============================================================
    # DEFAULT COPY
    # ============================================================

    def _copy_defaults(self):

        return copy.deepcopy(
            self.DEFAULTS
        )

    # ============================================================
    # SAVE
    # ============================================================

    def save(self):

        try:

            self.file_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with open(
                self.file_path,
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    self.data,
                    file,
                    indent=4,
                    ensure_ascii=False,
                )

            return True

        except Exception as error:

            print(
                f"GestureSettings save error: {error}"
            )

            return False

    # ============================================================
    # PROFILE
    # ============================================================

    def set_profile(
        self,
        profile,
    ):

        if profile not in self.PROFILES:
            return False

        profile_data = self.PROFILES[
            profile
        ]

        self.data["profile"] = profile

        self.data["sensitivity"] = (
            profile_data["sensitivity"]
        )

        self.data["performance_mode"] = (
            profile_data["performance_mode"]
        )

        self.save()

        return True

    def get_profile(self):

        return self.data.get(
            "profile",
            "Balanced",
        )

    def get_profiles(self):

        return list(
            self.PROFILES.keys()
        )

    # ============================================================
    # CUSTOM PROFILE SUPPORT
    # ============================================================

    def create_custom_profile(
        self,
        name,
    ):

        name = str(name).strip()

        if not name:
            return False

        if name in self.PROFILES:
            return False

        # Custom profile metadata is kept in the
        # settings file without changing built-in profiles.

        custom_profiles = self.data.setdefault(
            "custom_profiles",
            {},
        )

        if name in custom_profiles:
            return False

        custom_profiles[name] = {
            "sensitivity": self.get_sensitivity(),
            "performance_mode": (
                self.get_performance_mode()
            ),
            "enabled_gestures": (
                self.get_enabled_gestures()
            ),
            "gesture_mappings": (
                self.get_gesture_mappings()
            ),
        }

        self.data["profile"] = name

        self.save()

        return True

    def get_custom_profiles(self):

        custom_profiles = self.data.get(
            "custom_profiles",
            {},
        )

        if not isinstance(
            custom_profiles,
            dict,
        ):
            return []

        return list(
            custom_profiles.keys()
        )

    def load_custom_profile(
        self,
        name,
    ):

        custom_profiles = self.data.get(
            "custom_profiles",
            {},
        )

        if not isinstance(
            custom_profiles,
            dict,
        ):
            return False

        profile = custom_profiles.get(
            name
        )

        if not isinstance(
            profile,
            dict,
        ):
            return False

        # ----------------------------------------------------
        # Sensitivity
        # ----------------------------------------------------

        if "sensitivity" in profile:

            try:

                self.data["sensitivity"] = max(
                    10,
                    min(
                        60,
                        int(
                            profile["sensitivity"]
                        ),
                    ),
                )

            except Exception:
                pass

        # ----------------------------------------------------
        # Performance
        # ----------------------------------------------------

        mode = profile.get(
            "performance_mode"
        )

        if mode in {
            "Performance",
            "Balanced",
            "Accuracy",
        }:

            self.data[
                "performance_mode"
            ] = mode

        # ----------------------------------------------------
        # Enabled gestures
        # ----------------------------------------------------

        enabled = profile.get(
            "enabled_gestures"
        )

        if isinstance(enabled, dict):

            for gesture in self.GESTURES:

                if gesture in enabled:

                    self.data[
                        "enabled_gestures"
                    ][gesture] = bool(
                        enabled[gesture]
                    )

        # ----------------------------------------------------
        # Gesture mappings
        # ----------------------------------------------------

        mappings = profile.get(
            "gesture_mappings"
        )

        if isinstance(mappings, dict):

            for gesture in self.GESTURES:

                action = mappings.get(
                    gesture
                )

                if action in self.ACTIONS:

                    self.data[
                        "gesture_mappings"
                    ][gesture] = action

        self.data["profile"] = name

        self.save()

        return True

    def delete_custom_profile(
        self,
        name,
    ):

        custom_profiles = self.data.get(
            "custom_profiles",
            {},
        )

        if not isinstance(
            custom_profiles,
            dict,
        ):
            return False

        if name not in custom_profiles:
            return False

        del custom_profiles[name]

        if self.get_profile() == name:

            self.data["profile"] = "Balanced"

            balanced = self.PROFILES[
                "Balanced"
            ]

            self.data["sensitivity"] = (
                balanced["sensitivity"]
            )

            self.data["performance_mode"] = (
                balanced["performance_mode"]
            )

        self.save()

        return True

    def save_current_as_profile(
        self,
        name,
    ):

        name = str(name).strip()

        if not name:
            return False

        custom_profiles = self.data.setdefault(
            "custom_profiles",
            {},
        )

        custom_profiles[name] = {
            "sensitivity": self.get_sensitivity(),
            "performance_mode": (
                self.get_performance_mode()
            ),
            "enabled_gestures": (
                self.get_enabled_gestures()
            ),
            "gesture_mappings": (
                self.get_gesture_mappings()
            ),
        }

        self.data["profile"] = name

        self.save()

        return True

    # ============================================================
    # SENSITIVITY
    # ============================================================

    def set_sensitivity(
        self,
        value,
    ):

        try:
            value = int(value)
        except Exception:
            value = 30

        value = max(
            10,
            min(
                60,
                value,
            ),
        )

        self.data["sensitivity"] = value

        # Changing settings manually means the user
        # is effectively using a custom configuration.

        if self.data.get("profile") in self.PROFILES:

            self.data["profile"] = "Custom"

        self.save()

        return value

    def get_sensitivity(self):

        try:

            return int(
                self.data.get(
                    "sensitivity",
                    30,
                )
            )

        except Exception:

            return 30

    # ============================================================
    # PERFORMANCE MODE
    # ============================================================

    def set_performance_mode(
        self,
        mode,
    ):

        allowed = {
            "Performance",
            "Balanced",
            "Accuracy",
        }

        if mode not in allowed:
            return False

        self.data[
            "performance_mode"
        ] = mode

        if self.data.get("profile") in self.PROFILES:

            self.data["profile"] = "Custom"

        self.save()

        return True

    def get_performance_mode(self):

        mode = self.data.get(
            "performance_mode",
            "Balanced",
        )

        if mode not in {
            "Performance",
            "Balanced",
            "Accuracy",
        }:

            return "Balanced"

        return mode

    # ============================================================
    # GESTURE ENABLE / DISABLE
    # ============================================================

    def set_gesture_enabled(
        self,
        gesture,
        enabled,
    ):

        if gesture not in self.GESTURES:
            return False

        self.data[
            "enabled_gestures"
        ][gesture] = bool(
            enabled
        )

        if self.data.get("profile") in self.PROFILES:

            self.data["profile"] = "Custom"

        self.save()

        return True

    def is_gesture_enabled(
        self,
        gesture,
    ):

        return bool(
            self.data[
                "enabled_gestures"
            ].get(
                gesture,
                True,
            )
        )

    def get_enabled_gestures(self):

        return dict(
            self.data[
                "enabled_gestures"
            ]
        )

    # ============================================================
    # GESTURE MAPPINGS
    # ============================================================

    def set_gesture_mapping(
        self,
        gesture,
        action,
    ):

        if gesture not in self.GESTURES:
            return False

        if action not in self.ACTIONS:
            return False

        self.data[
            "gesture_mappings"
        ][gesture] = action

        if self.data.get("profile") in self.PROFILES:

            self.data["profile"] = "Custom"

        self.save()

        return True

    def get_gesture_mapping(
        self,
        gesture,
    ):

        return self.data[
            "gesture_mappings"
        ].get(
            gesture,
            "No Action",
        )

    def get_gesture_mappings(self):

        return dict(
            self.data[
                "gesture_mappings"
            ]
        )

    def reset_gesture_mappings(self):

        self.data[
            "gesture_mappings"
        ] = dict(
            self.DEFAULTS[
                "gesture_mappings"
            ]
        )

        self.save()

        return True

    # ============================================================
    # ACTIONS
    # ============================================================

    def get_actions(self):

        return list(
            self.ACTIONS
        )

    # ============================================================
    # RESET
    # ============================================================

    def reset(self):

        self.data = self._copy_defaults()

        self.save()

        return True

    # ============================================================
    # EXPORT CURRENT SETTINGS
    # ============================================================

    def get_all(self):

        return {
            "profile": self.get_profile(),

            "sensitivity": self.get_sensitivity(),

            "performance_mode": (
                self.get_performance_mode()
            ),

            "enabled_gestures": (
                self.get_enabled_gestures()
            ),

            "gesture_mappings": (
                self.get_gesture_mappings()
            ),

            "custom_profiles": (
                self.get_custom_profiles()
            ),
        }