import os
import re
import threading

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, RoundedRectangle, Line
from kivy.metrics import dp
from kivy.utils import platform

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import arabic_reshaper
from bidi.algorithm import get_display

from ai_client import AIClient


# =========================================================
# VERSION
# =========================================================

__version__ = "0.2.5"


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "Cairo-Regular.ttf")


# =========================================================
# ARABIC FONT
# =========================================================

def _find_android_arabic_font():
    """Prefer the phone's own Arabic font when Android exposes one."""
    if platform != "android":
        return ""

    preferred_paths = [
        "/system/fonts/NotoNaskhArabic-Regular.ttf",
        "/system/fonts/NotoSansArabic-Regular.ttf",
        "/system/fonts/NotoNaskhArabicUI-Regular.ttf",
        "/system/fonts/NotoSansArabicUI-Regular.ttf",
        "/system/fonts/DroidSansArabic.ttf",
    ]

    for font_path in preferred_paths:
        if os.path.exists(font_path):
            return font_path

    # OEMs can rename system fonts. Search the read-only Android font folder
    # and prefer Noto / Arabic named fonts without requiring any permission.
    try:
        font_dir = "/system/fonts"

        if os.path.isdir(font_dir):
            candidates = []

            for filename in os.listdir(font_dir):
                lower = filename.lower()

                if not lower.endswith((".ttf", ".otf", ".ttc")):
                    continue

                if "arab" not in lower:
                    continue

                score = 0

                if "noto" in lower:
                    score += 10
                if "naskh" in lower:
                    score += 6
                if "sans" in lower:
                    score += 3
                if "regular" in lower:
                    score += 2

                candidates.append(
                    (
                        score,
                        os.path.join(
                            font_dir,
                            filename
                        )
                    )
                )

            if candidates:
                candidates.sort(
                    key=lambda item: item[0],
                    reverse=True
                )
                return candidates[0][1]

    except Exception as exc:
        print(
            "811: Android system Arabic font scan warning:",
            repr(exc)
        )

    return ""


ARABIC_FONT = "Roboto"
ANDROID_ARABIC_FONT_PATH = _find_android_arabic_font()

if ANDROID_ARABIC_FONT_PATH:
    try:
        LabelBase.register(
            name="AndroidArabic",
            fn_regular=ANDROID_ARABIC_FONT_PATH
        )
        ARABIC_FONT = "AndroidArabic"
        print(
            "811: Android system Arabic font loaded:",
            ANDROID_ARABIC_FONT_PATH
        )
    except Exception as exc:
        print(
            "811: Android Arabic font registration error:",
            repr(exc)
        )

if ARABIC_FONT == "Roboto":
    if os.path.exists(FONT_PATH):
        try:
            LabelBase.register(
                name="Cairo",
                fn_regular=FONT_PATH
            )
            ARABIC_FONT = "Cairo"
            print(
                "811: Cairo-Regular.ttf loaded as fallback"
            )
        except Exception as exc:
            print(
                "811: Cairo font registration error:",
                repr(exc)
            )
    else:
        print(
            "811: Cairo-Regular.ttf NOT FOUND:",
            FONT_PATH
        )


# =========================================================
# UNICODE CLEANING
# =========================================================

HIDDEN_UNICODE = (
    "\u061c"
    "\u200b"
    "\u200c"
    "\u200d"
    "\u200e"
    "\u200f"
    "\u202a"
    "\u202b"
    "\u202c"
    "\u202d"
    "\u202e"
    "\u2066"
    "\u2067"
    "\u2068"
    "\u2069"
    "\ufeff"
)

# Kivy wraps text after python-bidi has converted Arabic to visual order.
# If a long visual RTL line is wrapped by Kivy, the resulting rows appear
# bottom-to-top. Wrap the logical Arabic text first, then reshape every row.
OUTPUT_ARABIC_WRAP_CHARS = 30


def clean_unicode(text):
    if text is None:
        return ""

    text = str(text)

    for char in HIDDEN_UNICODE:
        text = text.replace(char, "")

    cleaned = []

    for char in text:
        if char in ("\n", "\t"):
            cleaned.append(char)
            continue

        if ord(char) < 32:
            continue

        cleaned.append(char)

    text = "".join(cleaned)

    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)

    return "\n".join(lines).strip()


def _wrap_logical_line(line, max_chars):
    """Wrap one logical line on words before applying the bidi transform."""
    if not max_chars or len(line) <= max_chars:
        return [line]

    wrapped_lines = []
    current_words = []

    for word in line.split(" "):
        candidate_words = current_words + [word]
        candidate = " ".join(candidate_words)

        if current_words and len(candidate) > max_chars:
            wrapped_lines.append(" ".join(current_words))
            current_words = [word]
        else:
            current_words = candidate_words

    if current_words:
        wrapped_lines.append(" ".join(current_words))

    return wrapped_lines or [line]


def fix_text(text, wrap_at=None):
    """Prepare text for Kivy, wrapping logical Arabic before bidi shaping."""
    clean_text = clean_unicode(text)

    if not clean_text:
        return ""

    logical_lines = []

    for line in clean_text.split("\n"):
        if (
            wrap_at
            and re.search(r"[\u0600-\u06FF]", line)
        ):
            logical_lines.extend(
                _wrap_logical_line(
                    line,
                    wrap_at
                )
            )
        else:
            logical_lines.append(line)

    display_lines = []

    for line in logical_lines:
        if not line:
            display_lines.append("")
            continue

        if not re.search(r"[\u0600-\u06FF]", line):
            display_lines.append(line)
            continue

        try:
            reshaped = arabic_reshaper.reshape(line)
            display_lines.append(
                get_display(
                    reshaped,
                    base_dir="R"
                )
            )
        except Exception as exc:
            print(
                "811: Arabic formatting error:",
                repr(exc)
            )
            display_lines.append(line)

    return "\n".join(display_lines)


def clean_for_speech(text):
    text = clean_unicode(text)

    if not text:
        return ""

    text = re.sub(r"[*_~`#]", "", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


# =========================================================
# ANDROID PERMISSIONS
# =========================================================

def request_android_permissions():
    if platform != "android":
        return

    try:
        from android.permissions import request_permissions, Permission

        permissions = [
            Permission.RECORD_AUDIO,
            Permission.INTERNET,
            Permission.ACCESS_NETWORK_STATE,
            Permission.MODIFY_AUDIO_SETTINGS,
        ]

        if hasattr(Permission, "BLUETOOTH_CONNECT"):
            permissions.append(Permission.BLUETOOTH_CONNECT)

        if hasattr(Permission, "BLUETOOTH_SCAN"):
            permissions.append(Permission.BLUETOOTH_SCAN)

        if hasattr(Permission, "BLUETOOTH"):
            permissions.append(Permission.BLUETOOTH)

        if hasattr(Permission, "BLUETOOTH_ADMIN"):
            permissions.append(Permission.BLUETOOTH_ADMIN)

        request_permissions(permissions)
        print("811: Android permissions requested")

    except Exception as exc:
        print("811: Permission error:", repr(exc))


# =========================================================
# STATUS ORB
# =========================================================

class StatusOrb(Widget):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.status_color = (
            0.13,
            0.59,
            0.95,
            1.0
        )

        self.bind(
            pos=self._redraw,
            size=self._redraw
        )

    def set_state(self, state):
        colors = {
            "ready": (
                0.13,
                0.59,
                0.95,
                1.0
            ),
            "listening": (
                0.00,
                0.78,
                0.88,
                1.0
            ),
            "thinking": (
                1.00,
                0.60,
                0.08,
                1.0
            ),
            "speaking": (
                0.20,
                0.80,
                0.30,
                1.0
            ),
            "error": (
                0.92,
                0.20,
                0.22,
                1.0
            )
        }

        self.status_color = colors.get(
            state,
            colors["ready"]
        )

        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()

        if self.width <= 0 or self.height <= 0:
            return

        with self.canvas:
            cx = self.center_x
            cy = self.center_y

            radius = min(
                self.width,
                self.height
            ) * 0.22

            Color(
                self.status_color[0],
                self.status_color[1],
                self.status_color[2],
                0.10
            )

            Ellipse(
                pos=(
                    cx - radius * 2.4,
                    cy - radius * 2.4
                ),
                size=(
                    radius * 4.8,
                    radius * 4.8
                )
            )

            Color(
                self.status_color[0],
                self.status_color[1],
                self.status_color[2],
                0.18
            )

            Ellipse(
                pos=(
                    cx - radius * 1.75,
                    cy - radius * 1.75
                ),
                size=(
                    radius * 3.5,
                    radius * 3.5
                )
            )

            Color(*self.status_color)

            Ellipse(
                pos=(
                    cx - radius,
                    cy - radius
                ),
                size=(
                    radius * 2,
                    radius * 2
                )
            )

            Color(
                1,
                1,
                1,
                0.22
            )

            Line(
                circle=(
                    cx,
                    cy,
                    radius * 0.82
                ),
                width=1.2
            )


# =========================================================
# MAIN APP
# =========================================================

class VoiceAssistantApp(App):

    def build(self):
        self.title = "VOICE ASSISTANT 811"

        # -------------------------
        # Core state
        # -------------------------

        self.processing = False
        self.ai_engine = None

        # -------------------------
        # TTS
        # -------------------------

        self.tts = None
        self.tts_ready = False
        self.tts_language_ready = False
        self.tts_init_error = ""
        self.tts_last_result = None
        self.tts_media_volume = None
        self.tts_media_volume_max = None
        self.tts_is_speaking = False
        self._tts_pending_text = ""
        self._tts_listener = None

        # -------------------------
        # SpeechRecognizer
        # -------------------------

        self.speech_recognizer = None
        self.speech_recognizer_ready = False
        self.is_listening = False

        self._speech_listener = None
        self._speech_autoclass = None
        self._last_ui_runnable = None

        self.speech_init_error = ""
        self.speech_last_error_code = 0
        self.speech_last_error_name = ""

        # Prefer Iraqi Arabic, then Saudi Arabic, then generic Arabic,
        # and finally allow Android to use its own default language.
        self.speech_languages = [
            "ar-IQ",
            "ar-SA",
            "ar",
            None
        ]
        self.speech_language_index = 0

        # One automatic recovery is allowed for transient recognizer
        # states such as ERROR_CLIENT / ERROR_RECOGNIZER_BUSY.
        self.speech_recovery_attempts = 0
        self.speech_max_recovery_attempts = 1

        # -------------------------
        # UI
        # -------------------------

        self.arabic_font = ARABIC_FONT

        # -------------------------
        # Native Android Arabic chat renderer
        # -------------------------

        self._chat_raw_text = (
            "مرحباً\n"
            "أنا 811\n"
            "جاهز للعمل معك."
        )
        self.native_chat_scroll = None
        self.native_chat_text = None
        self.native_chat_ready = False
        self.native_chat_error = ""
        self._native_chat_layout_params = None

        request_android_permissions()

        # =================================================
        # AI
        # =================================================

        try:
            self.ai_engine = AIClient()
        except Exception as exc:
            print(
                "811: AIClient init error:",
                repr(exc)
            )
            self.ai_engine = None

        # =================================================
        # ROOT
        # =================================================

        root = BoxLayout(
            orientation="vertical"
        )

        with root.canvas.before:
            Color(
                0.025,
                0.030,
                0.045,
                1.0
            )

            root.background_rect = RoundedRectangle(
                pos=root.pos,
                size=root.size,
                radius=[0]
            )

        root.bind(
            pos=lambda instance, value:
            setattr(
                root.background_rect,
                "pos",
                value
            )
        )

        root.bind(
            size=lambda instance, value:
            setattr(
                root.background_rect,
                "size",
                value
            )
        )

        # =================================================
        # MAIN
        # =================================================

        main = BoxLayout(
            orientation="vertical",
            padding=(
                dp(16),
                dp(16),
                dp(16),
                dp(14)
            ),
            spacing=dp(10)
        )

        # =================================================
        # HEADER
        # =================================================

        header = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            spacing=dp(3)
        )

        self.title_label = Label(
            text="VOICE ASSISTANT 811",
            font_name=self.arabic_font,
            font_size="23sp",
            bold=True,
            color=(
                0.95,
                0.97,
                1.0,
                1.0
            ),
            halign="center",
            valign="middle"
        )

        self.subtitle_label = Label(
            text=fix_text(
                "مساعدك الشخصي الذكي"
            ),
            font_name=self.arabic_font,
            font_size="14sp",
            color=(
                0.55,
                0.65,
                0.78,
                1.0
            ),
            halign="center",
            valign="middle"
        )

        header.add_widget(
            self.title_label
        )

        header.add_widget(
            self.subtitle_label
        )

        main.add_widget(
            header
        )

        # =================================================
        # GROQ
        # =================================================

        key_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            padding=dp(4)
        )

        self.key_input = TextInput(
            hint_text="Groq API Key",
            multiline=False,
            password=True,
            font_size="14sp",
            font_name="Roboto",
            foreground_color=(
                0.90,
                0.93,
                0.98,
                1.0
            ),
            background_color=(
                0.08,
                0.10,
                0.14,
                1.0
            ),
            cursor_color=(
                0.25,
                0.65,
                1.0,
                1.0
            ),
            padding=(
                dp(14),
                dp(12)
            )
        )

        key_container.add_widget(
            self.key_input
        )

        main.add_widget(
            key_container
        )

        # =================================================
        # STATUS
        # =================================================

        status_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(205),
            spacing=dp(2)
        )

        self.status_orb = StatusOrb()

        status_container.add_widget(
            self.status_orb
        )

        self.status_label = Label(
            text=fix_text(
                "جاهز"
            ),
            font_name=self.arabic_font,
            font_size="19sp",
            bold=True,
            color=(
                0.30,
                0.75,
                1.0,
                1.0
            ),
            size_hint_y=None,
            height=dp(42),
            halign="center",
            valign="middle"
        )

        self.status_label.bind(
            width=lambda instance, value:
            setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        status_container.add_widget(
            self.status_label
        )

        main.add_widget(
            status_container
        )

        # =================================================
        # CHAT
        # =================================================

        chat_panel = BoxLayout(
            orientation="vertical",
            padding=dp(3)
        )

        self.scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=dp(4),
            scroll_type=[
                "bars",
                "content"
            ]
        )

        self.output_label = Label(
            text=fix_text(
                self._chat_raw_text,
                wrap_at=OUTPUT_ARABIC_WRAP_CHARS
            ),
            font_name=self.arabic_font,
            font_size="17sp",
            color=(
                0.88,
                0.90,
                0.95,
                1.0
            ),
            size_hint_y=None,
            halign="right",
            valign="top",
            padding=(
                dp(12),
                dp(18)
            ),
            markup=False
        )

        self.output_label.bind(
            width=self._update_output_width
        )

        self.output_label.bind(
            texture_size=self._update_output_height
        )

        self.scroll.add_widget(
            self.output_label
        )

        # Start Arabic conversations from the top of the panel.
        self.scroll.scroll_y = 1

        chat_panel.add_widget(
            self.scroll
        )

        self.chat_panel = chat_panel
        self.chat_panel.bind(
            pos=self._schedule_native_chat_bounds_sync,
            size=self._schedule_native_chat_bounds_sync
        )

        main.add_widget(
            chat_panel
        )

        # =================================================
        # BUTTONS
        # =================================================

        buttons = BoxLayout(
            size_hint_y=None,
            height=dp(60),
            spacing=dp(9)
        )

        self.speak_btn = Button(
            text=fix_text(
                "اضغط للتحدث"
            ),
            font_name=self.arabic_font,
            font_size="18sp",
            bold=True,
            background_normal="",
            background_down="",
            background_color=(
                0.08,
                0.45,
                0.90,
                1.0
            ),
            color=(
                1,
                1,
                1,
                1
            )
        )

        self.speak_btn.bind(
            on_press=self.on_speak_click
        )

        self.clear_btn = Button(
            text=fix_text(
                "مسح"
            ),
            font_name=self.arabic_font,
            font_size="16sp",
            background_normal="",
            background_down="",
            background_color=(
                0.12,
                0.14,
                0.19,
                1.0
            ),
            color=(
                0.85,
                0.88,
                0.93,
                1.0
            )
        )

        self.clear_btn.bind(
            on_press=self.on_clear_click
        )

        buttons.add_widget(
            self.speak_btn
        )

        buttons.add_widget(
            self.clear_btn
        )

        main.add_widget(
            buttons
        )

        # =================================================
        # FOOTER
        # =================================================

        self.footer_label = Label(
            text=fix_text(
                "Speech Recognition • "
                "Native TTS • "
                "Cairo Arabic • "
                "Groq AI"
            ),
            font_name=self.arabic_font,
            font_size="11sp",
            color=(
                0.38,
                0.43,
                0.52,
                1.0
            ),
            size_hint_y=None,
            height=dp(22),
            halign="center",
            valign="middle"
        )

        self.footer_label.bind(
            width=lambda instance, value:
            setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        main.add_widget(
            self.footer_label
        )

        root.add_widget(
            main
        )

        self.set_state(
            "ready"
        )

        if platform == "android":
            # Use Android's own TextView for the conversation text.
            # This gives us the same Arabic shaping, glyph fallback,
            # punctuation and line wrapping used by the phone itself.
            Clock.schedule_once(
                lambda dt:
                self.init_native_chat(),
                0.45
            )

            Clock.schedule_once(
                lambda dt:
                self.init_native_tts(),
                1.0
            )

            # Give the permission dialog a little more time before
            # creating SpeechRecognizer.
            Clock.schedule_once(
                lambda dt:
                self.init_native_speech(),
                2.0
            )

        return root

    # =====================================================
    # UI SIZING
    # =====================================================

    def _update_output_width(
        self,
        instance,
        width
    ):
        instance.text_size = (
            max(
                dp(80),
                width - dp(24)
            ),
            None
        )

    def _update_output_height(
        self,
        instance,
        texture_size
    ):
        instance.height = max(
            dp(90),
            texture_size[1] + dp(20)
        )

    # =====================================================
    # NATIVE ANDROID CHAT TEXT
    # =====================================================

    def init_native_chat(
        self
    ):
        """Create a native Android ScrollView + TextView over the Kivy chat."""
        if platform != "android":
            return

        self._run_on_android_ui(
            self._init_native_chat_on_ui
        )

    def _init_native_chat_on_ui(
        self
    ):
        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            AndroidScrollView = autoclass(
                "android.widget.ScrollView"
            )
            TextView = autoclass(
                "android.widget.TextView"
            )
            FrameLayoutParams = autoclass(
                "android.widget.FrameLayout$LayoutParams"
            )
            ViewGroupParams = autoclass(
                "android.view.ViewGroup$LayoutParams"
            )
            Gravity = autoclass(
                "android.view.Gravity"
            )
            View = autoclass(
                "android.view.View"
            )
            AndroidColor = autoclass(
                "android.graphics.Color"
            )
            TypedValue = autoclass(
                "android.util.TypedValue"
            )
            Typeface = autoclass(
                "android.graphics.Typeface"
            )
            JavaString = autoclass(
                "java.lang.String"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                raise RuntimeError(
                    "Android Activity unavailable for native Arabic text"
                )

            # Remove an older overlay if Android recreated the activity.
            if self.native_chat_scroll is not None:
                try:
                    parent = self.native_chat_scroll.getParent()
                    if parent is not None:
                        parent.removeView(
                            self.native_chat_scroll
                        )
                except Exception:
                    pass

            native_scroll = AndroidScrollView(
                activity
            )
            native_text = TextView(
                activity
            )

            native_scroll.setFillViewport(True)
            native_scroll.setBackgroundColor(
                AndroidColor.TRANSPARENT
            )
            native_scroll.setVerticalScrollBarEnabled(True)
            native_scroll.setClipToPadding(False)

            native_text.setBackgroundColor(
                AndroidColor.TRANSPARENT
            )
            native_text.setTextColor(
                AndroidColor.rgb(
                    224,
                    230,
                    242
                )
            )
            native_text.setTextSize(
                TypedValue.COMPLEX_UNIT_SP,
                17.0
            )
            native_text.setGravity(
                Gravity.RIGHT
                | Gravity.TOP
            )

            try:
                native_text.setTextDirection(
                    View.TEXT_DIRECTION_RTL
                )
                native_text.setTextAlignment(
                    View.TEXT_ALIGNMENT_VIEW_END
                )
            except Exception as direction_exc:
                print(
                    "811: Native chat RTL direction warning:",
                    repr(direction_exc)
                )

            # System sans-serif delegates Arabic shaping and missing glyph
            # fallback to Android, instead of python-bidi presentation forms.
            try:
                native_text.setTypeface(
                    Typeface.create(
                        "sans-serif",
                        Typeface.NORMAL
                    )
                )
            except Exception as font_exc:
                print(
                    "811: Native chat system font warning:",
                    repr(font_exc)
                )

            native_text.setIncludeFontPadding(False)
            native_text.setLineSpacing(
                0.0,
                1.18
            )
            native_text.setTextIsSelectable(True)

            density = float(
                activity.getResources()
                .getDisplayMetrics()
                .density
            )

            pad_h = int(
                12.0 * density
            )
            pad_v = int(
                18.0 * density
            )

            native_text.setPadding(
                pad_h,
                pad_v,
                pad_h,
                pad_v
            )

            native_scroll.addView(
                native_text,
                ViewGroupParams(
                    ViewGroupParams.MATCH_PARENT,
                    ViewGroupParams.WRAP_CONTENT
                )
            )

            params = FrameLayoutParams(
                1,
                1
            )
            params.gravity = (
                Gravity.LEFT
                | Gravity.TOP
            )

            activity.addContentView(
                native_scroll,
                params
            )

            self.native_chat_scroll = native_scroll
            self.native_chat_text = native_text
            self._native_chat_layout_params = params
            self.native_chat_ready = True
            self.native_chat_error = ""

            # Explicit Java String avoids overloaded TextView.setText(int).
            native_text.setText(
                JavaString(
                    clean_unicode(
                        self._chat_raw_text
                    )
                )
            )

            print(
                "811: Native Android Arabic chat renderer ready"
            )

            Clock.schedule_once(
                lambda dt:
                self._activate_native_chat_fallback_switch(),
                0
            )

            Clock.schedule_once(
                lambda dt:
                self._sync_native_chat_bounds(),
                0
            )

        except Exception as exc:
            self.native_chat_ready = False
            self.native_chat_error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            print(
                "811: Native Arabic chat init error:",
                repr(exc)
            )

            Clock.schedule_once(
                lambda dt:
                self._restore_kivy_chat_fallback(),
                0
            )

    def _activate_native_chat_fallback_switch(
        self
    ):
        if not self.native_chat_ready:
            return

        # Keep the Kivy label as an emergency fallback, but hide its visual
        # text while Android TextView is active so there is no double render.
        self.output_label.opacity = 0
        self.scroll.bar_width = 0

    def _restore_kivy_chat_fallback(
        self
    ):
        self.output_label.opacity = 1
        self.scroll.bar_width = dp(4)
        self.output_label.text = fix_text(
            self._chat_raw_text,
            wrap_at=OUTPUT_ARABIC_WRAP_CHARS
        )

    def _set_chat_text(
        self,
        text
    ):
        """Store logical text once; Android renders it natively when possible."""
        self._chat_raw_text = clean_unicode(
            text
        )

        if (
            platform == "android"
            and self.native_chat_ready
            and self.native_chat_text is not None
        ):
            logical_text = self._chat_raw_text

            self._run_on_android_ui(
                lambda:
                self._set_native_chat_text_on_ui(
                    logical_text
                )
            )
            return

        self.output_label.text = fix_text(
            self._chat_raw_text,
            wrap_at=OUTPUT_ARABIC_WRAP_CHARS
        )

        Clock.schedule_once(
            lambda dt:
            setattr(
                self.scroll,
                "scroll_y",
                1
            ),
            0
        )

    def _append_chat_text(
        self,
        text
    ):
        extra = clean_unicode(
            text
        )

        if not extra:
            return

        current = self._chat_raw_text.strip()

        if current:
            combined = (
                current
                + "\n\n"
                + extra
            )
        else:
            combined = extra

        self._set_chat_text(
            combined
        )

    def _set_native_chat_text_on_ui(
        self,
        text
    ):
        try:
            from jnius import autoclass

            JavaString = autoclass(
                "java.lang.String"
            )

            if self.native_chat_text is None:
                return

            self.native_chat_text.setText(
                JavaString(
                    text
                )
            )

            if self.native_chat_scroll is not None:
                self.native_chat_scroll.scrollTo(
                    0,
                    0
                )

        except Exception as exc:
            print(
                "811: Native Arabic chat text error:",
                repr(exc)
            )

            self.native_chat_ready = False

            Clock.schedule_once(
                lambda dt:
                self._restore_kivy_chat_fallback(),
                0
            )

    def _schedule_native_chat_bounds_sync(
        self,
        *args
    ):
        if platform != "android":
            return

        Clock.schedule_once(
            lambda dt:
            self._sync_native_chat_bounds(),
            0
        )

    def _sync_native_chat_bounds(
        self
    ):
        if (
            platform != "android"
            or not self.native_chat_ready
            or self.native_chat_scroll is None
        ):
            return

        try:
            x, y = self.chat_panel.to_window(
                0,
                0
            )

            width = int(
                max(
                    1,
                    self.chat_panel.width
                )
            )
            height = int(
                max(
                    1,
                    self.chat_panel.height
                )
            )
            left = int(
                max(
                    0,
                    x
                )
            )
            top = int(
                max(
                    0,
                    Window.height
                    - (
                        y
                        + self.chat_panel.height
                    )
                )
            )

            self._run_on_android_ui(
                lambda:
                self._apply_native_chat_bounds_on_ui(
                    left,
                    top,
                    width,
                    height
                )
            )

        except Exception as exc:
            print(
                "811: Native chat bounds calculation error:",
                repr(exc)
            )

    def _apply_native_chat_bounds_on_ui(
        self,
        left,
        top,
        width,
        height
    ):
        try:
            from jnius import autoclass

            FrameLayoutParams = autoclass(
                "android.widget.FrameLayout$LayoutParams"
            )
            Gravity = autoclass(
                "android.view.Gravity"
            )

            if self.native_chat_scroll is None:
                return

            params = FrameLayoutParams(
                int(width),
                int(height)
            )
            params.gravity = (
                Gravity.LEFT
                | Gravity.TOP
            )
            params.leftMargin = int(
                left
            )
            params.topMargin = int(
                top
            )

            self.native_chat_scroll.setLayoutParams(
                params
            )
            self._native_chat_layout_params = params
            self.native_chat_scroll.requestLayout()

        except Exception as exc:
            print(
                "811: Native chat bounds apply error:",
                repr(exc)
            )

    def _destroy_native_chat_on_ui(
        self
    ):
        try:
            if self.native_chat_scroll is not None:
                parent = self.native_chat_scroll.getParent()

                if parent is not None:
                    parent.removeView(
                        self.native_chat_scroll
                    )

        except Exception as exc:
            print(
                "811: Native chat destroy error:",
                repr(exc)
            )

        self.native_chat_scroll = None
        self.native_chat_text = None
        self.native_chat_ready = False
        self._native_chat_layout_params = None

    # =====================================================
    # STATES
    # =====================================================

    def set_state(
        self,
        state,
        message=None
    ):
        states = {
            "ready": {
                "text": "جاهز",
                "color": (
                    0.30,
                    0.75,
                    1.0,
                    1.0
                )
            },
            "listening": {
                "text": "جاري الاستماع...",
                "color": (
                    0.10,
                    0.85,
                    0.90,
                    1.0
                )
            },
            "thinking": {
                "text": "جاري التفكير...",
                "color": (
                    1.0,
                    0.65,
                    0.12,
                    1.0
                )
            },
            "speaking": {
                "text": "811 يتحدث الآن",
                "color": (
                    0.20,
                    0.85,
                    0.35,
                    1.0
                )
            },
            "error": {
                "text": "حدث خطأ",
                "color": (
                    1.0,
                    0.28,
                    0.30,
                    1.0
                )
            }
        }

        current = states.get(
            state,
            states["ready"]
        )

        self.status_label.text = fix_text(
            current["text"]
        )

        self.status_label.color = (
            current["color"]
        )

        self.status_orb.set_state(
            state
        )

        if message is not None:
            self._set_chat_text(
                message
            )

        if state == "listening":
            self.speak_btn.text = fix_text(
                "إيقاف الاستماع"
            )

            self.speak_btn.background_color = (
                0.08,
                0.60,
                0.70,
                1.0
            )

        elif state == "thinking":
            self.speak_btn.text = fix_text(
                "جاري التفكير..."
            )

            self.speak_btn.background_color = (
                0.75,
                0.45,
                0.05,
                1.0
            )

        elif state == "speaking":
            self.speak_btn.text = fix_text(
                "يتحدث 811..."
            )

            self.speak_btn.background_color = (
                0.10,
                0.65,
                0.24,
                1.0
            )

        elif state == "error":
            self.speak_btn.text = fix_text(
                "حاول مرة أخرى"
            )

            self.speak_btn.background_color = (
                0.70,
                0.15,
                0.18,
                1.0
            )

        else:
            self.speak_btn.text = fix_text(
                "اضغط للتحدث"
            )

            self.speak_btn.background_color = (
                0.08,
                0.45,
                0.90,
                1.0
            )

    # =====================================================
    # ANDROID MAIN THREAD HELPER
    # =====================================================

    def _run_on_android_ui(
        self,
        func
    ):
        if platform != "android":
            func()
            return

        try:
            from jnius import (
                PythonJavaClass,
                java_method,
                autoclass
            )

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                print(
                    "811: Android Activity unavailable "
                    "for runOnUiThread"
                )
                return

            class UiRunnable(
                PythonJavaClass
            ):
                __javainterfaces__ = [
                    "java/lang/Runnable"
                ]
                __javacontext__ = "app"

                @java_method("()V")
                def run(self):
                    try:
                        func()
                    except Exception as exc:
                        print(
                            "811: Android UI Runnable error:",
                            repr(exc)
                        )

            runnable = UiRunnable()

            # Keep a strong reference while Java may still use it.
            self._last_ui_runnable = runnable

            activity.runOnUiThread(
                runnable
            )

        except Exception as exc:
            print(
                "811: runOnUiThread error:",
                repr(exc)
            )

    # =====================================================
    # NATIVE TTS
    # =====================================================

    def init_native_tts(
        self
    ):
        if platform != "android":
            return

        self._run_on_android_ui(
            self._init_native_tts_on_ui
        )

    def _init_native_tts_on_ui(
        self
    ):
        try:
            from jnius import (
                autoclass,
                PythonJavaClass,
                java_method
            )

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            TextToSpeech = autoclass(
                "android.speech.tts.TextToSpeech"
            )

            Locale = autoclass(
                "java.util.Locale"
            )

            Context = autoclass(
                "android.content.Context"
            )

            AudioManager = autoclass(
                "android.media.AudioManager"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                self.tts_ready = False
                self.tts_language_ready = False
                self.tts_init_error = (
                    "Android Activity unavailable"
                )
                print(
                    "811: TTS init failed:",
                    self.tts_init_error
                )
                return

            if self.tts is not None:
                try:
                    self.tts.stop()
                except Exception:
                    pass

                try:
                    self.tts.shutdown()
                except Exception:
                    pass

                self.tts = None

            self.tts_ready = False
            self.tts_language_ready = False
            self.tts_init_error = ""

            outer = self

            class TTSInitListener(
                PythonJavaClass
            ):
                __javainterfaces__ = [
                    "android/speech/tts/"
                    "TextToSpeech$OnInitListener"
                ]
                __javacontext__ = "app"

                @java_method("(I)V")
                def onInit(
                    self,
                    status
                ):
                    try:
                        if (
                            status
                            != TextToSpeech.SUCCESS
                        ):
                            outer.tts_ready = False
                            outer.tts_language_ready = False
                            outer.tts_init_error = (
                                "TextToSpeech initialization failed "
                                "with status "
                                + str(status)
                            )

                            print(
                                "811: TTS initialization failed:",
                                status
                            )
                            return

                        outer.tts_ready = True
                        outer.tts_language_ready = False
                        outer.tts_init_error = ""

                        locales = [
                            Locale(
                                "ar",
                                "IQ"
                            ),
                            Locale(
                                "ar",
                                "SA"
                            ),
                            Locale(
                                "ar",
                                "AE"
                            ),
                            Locale(
                                "ar",
                                "EG"
                            ),
                            Locale(
                                "ar"
                            )
                        ]

                        for locale in locales:
                            try:
                                available = (
                                    outer.tts
                                    .isLanguageAvailable(
                                        locale
                                    )
                                )

                                if (
                                    available
                                    < TextToSpeech.LANG_AVAILABLE
                                ):
                                    continue

                                result = (
                                    outer.tts
                                    .setLanguage(
                                        locale
                                    )
                                )

                                if (
                                    result
                                    >= TextToSpeech.LANG_AVAILABLE
                                ):
                                    outer.tts_language_ready = True

                                    print(
                                        "811: Arabic TTS ready:",
                                        locale
                                    )
                                    break

                            except Exception as lang_exc:
                                print(
                                    "811: TTS locale error:",
                                    repr(lang_exc)
                                )

                        if not outer.tts_language_ready:
                            outer.tts_init_error = (
                                "No Arabic TTS voice is installed "
                                "or enabled on this device."
                            )

                            print(
                                "811:",
                                outer.tts_init_error
                            )
                            return

                        try:
                            outer.tts.setSpeechRate(
                                0.95
                            )

                            outer.tts.setPitch(
                                1.0
                            )
                        except Exception as voice_exc:
                            print(
                                "811: TTS voice tuning error:",
                                repr(voice_exc)
                            )

                        try:
                            audio_manager = (
                                activity.getSystemService(
                                    Context.AUDIO_SERVICE
                                )
                            )

                            outer.tts_media_volume = (
                                audio_manager
                                .getStreamVolume(
                                    AudioManager.STREAM_MUSIC
                                )
                            )

                            outer.tts_media_volume_max = (
                                audio_manager
                                .getStreamMaxVolume(
                                    AudioManager.STREAM_MUSIC
                                )
                            )

                            print(
                                "811: Media volume:",
                                outer.tts_media_volume,
                                "/",
                                outer.tts_media_volume_max
                            )

                        except Exception as volume_exc:
                            print(
                                "811: Media volume check error:",
                                repr(volume_exc)
                            )

                        pending = outer._tts_pending_text

                        if pending:
                            outer._tts_pending_text = ""

                            outer._run_on_android_ui(
                                lambda:
                                outer._speak_on_android_ui(
                                    pending
                                )
                            )

                    except Exception as exc:
                        outer.tts_ready = False
                        outer.tts_language_ready = False
                        outer.tts_init_error = (
                            type(exc).__name__
                            + ": "
                            + str(exc)
                        )

                        print(
                            "811: TTS callback error:",
                            repr(exc)
                        )

            self._tts_listener = (
                TTSInitListener()
            )

            self.tts = TextToSpeech(
                activity,
                self._tts_listener
            )

            print(
                "811: Native Android TTS created"
            )

        except Exception as exc:
            self.tts = None
            self.tts_ready = False
            self.tts_language_ready = False
            self.tts_init_error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            print(
                "811: Native TTS init error:",
                repr(exc)
            )

    def speak(
        self,
        text
    ):
        if platform != "android":
            print(
                "811 [Desktop TTS]:",
                text
            )
            return

        text = clean_for_speech(
            text
        )

        if not text:
            return

        self._tts_pending_text = text

        self._run_on_android_ui(
            lambda:
            self._speak_on_android_ui(
                text
            )
        )

    def _speak_on_android_ui(
        self,
        text
    ):
        try:
            from jnius import (
                autoclass,
                cast
            )

            TextToSpeech = autoclass(
                "android.speech.tts.TextToSpeech"
            )

            Bundle = autoclass(
                "android.os.Bundle"
            )

            AudioManager = autoclass(
                "android.media.AudioManager"
            )

            JavaString = autoclass(
                "java.lang.String"
            )

            HashMap = autoclass(
                "java.util.HashMap"
            )

            if (
                self.tts is None
                or not self.tts_ready
                or not self.tts_language_ready
            ):
                print(
                    "811: TTS not ready; reinitializing."
                )

                self._tts_pending_text = text
                self._init_native_tts_on_ui()
                return

            utterance_id = (
                "811_utterance_"
                + str(
                    abs(
                        hash(text)
                    )
                )
            )

            queue_mode = int(
                TextToSpeech.QUEUE_FLUSH
            )

            # -------------------------------------------------
            # Android API 21+ modern overload:
            # speak(CharSequence, int, Bundle, String)
            #
            # Pyjnius does not always up-cast a Python string
            # to java.lang.CharSequence automatically.  That
            # was the exact runtime failure seen on the phone.
            # Force the Java types explicitly.
            # -------------------------------------------------

            modern_error = None
            result = None

            try:
                params = Bundle()

                try:
                    params.putInt(
                        TextToSpeech.Engine.KEY_PARAM_STREAM,
                        AudioManager.STREAM_MUSIC
                    )

                    params.putFloat(
                        TextToSpeech.Engine.KEY_PARAM_VOLUME,
                        1.0
                    )
                except Exception as params_exc:
                    print(
                        "811: TTS params warning:",
                        repr(params_exc)
                    )

                java_text = cast(
                    "java.lang.CharSequence",
                    JavaString(text)
                )

                java_utterance_id = JavaString(
                    utterance_id
                )

                result = self.tts.speak(
                    java_text,
                    queue_mode,
                    params,
                    java_utterance_id
                )

                print(
                    "811: TTS modern speak overload used"
                )

            except Exception as exc:
                modern_error = exc

                print(
                    "811: TTS modern speak overload failed:",
                    repr(exc)
                )

            # -------------------------------------------------
            # Defensive fallback:
            # speak(String, int, HashMap)
            #
            # This overload is deprecated by Android but is
            # still present and is very reliable through
            # Pyjnius because every argument has an exact Java
            # class rather than an interface type.
            # -------------------------------------------------

            if result is None:
                legacy_params = HashMap()

                try:
                    legacy_params.put(
                        TextToSpeech.Engine.KEY_PARAM_STREAM,
                        JavaString(
                            str(
                                AudioManager.STREAM_MUSIC
                            )
                        )
                    )

                    legacy_params.put(
                        TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID,
                        JavaString(
                            utterance_id
                        )
                    )
                except Exception as legacy_params_exc:
                    print(
                        "811: TTS legacy params warning:",
                        repr(legacy_params_exc)
                    )

                try:
                    result = self.tts.speak(
                        JavaString(text),
                        queue_mode,
                        legacy_params
                    )

                    print(
                        "811: TTS legacy speak fallback used"
                    )

                except Exception as legacy_exc:
                    self.tts_is_speaking = False
                    self.tts_init_error = (
                        "TTS-02: تعذر استدعاء محرك النطق على هذا الجهاز."
                    )

                    print(
                        "811: TTS legacy speak fallback failed:",
                        repr(legacy_exc)
                    )

                    if modern_error is not None:
                        print(
                            "811: TTS modern failure was:",
                            repr(modern_error)
                        )

                    Clock.schedule_once(
                        lambda dt:
                        self._show_tts_error(),
                        0
                    )
                    return

            self.tts_last_result = int(
                result
            )

            if int(result) == int(
                TextToSpeech.ERROR
            ):
                self.tts_is_speaking = False
                self.tts_init_error = (
                    "TTS-03: محرك Android رفض تشغيل الرد الصوتي."
                )

                print(
                    "811: TTS speak returned ERROR"
                )

                Clock.schedule_once(
                    lambda dt:
                    self._show_tts_error(),
                    0
                )
                return

            self._tts_pending_text = ""
            self.tts_is_speaking = True
            self.tts_init_error = ""

            print(
                "811: TTS speak queued successfully"
            )

            Clock.schedule_once(
                self._watch_tts_completion,
                0.35
            )

        except Exception as exc:
            self.tts_is_speaking = False
            self.tts_init_error = (
                "TTS-01: تعذر تجهيز الرد الصوتي."
            )

            print(
                "811: TTS speak error:",
                repr(exc)
            )

            Clock.schedule_once(
                lambda dt:
                self._show_tts_error(),
                0
            )

    def _watch_tts_completion(
        self,
        dt
    ):
        if platform != "android":
            self.tts_is_speaking = False
            return

        try:
            if (
                self.tts is not None
                and self.tts.isSpeaking()
            ):
                self.tts_is_speaking = True

                Clock.schedule_once(
                    self._watch_tts_completion,
                    0.30
                )
                return

        except Exception as exc:
            print(
                "811: TTS isSpeaking check error:",
                repr(exc)
            )

        self.tts_is_speaking = False
        self._return_to_ready()

    def _show_tts_error(
        self
    ):
        self.processing = False
        self.speak_btn.disabled = False

        details = (
            self.tts_init_error
            or "TTS-00: تعذر تشغيل الرد الصوتي."
        )

        if (
            self.tts_media_volume is not None
            and self.tts_media_volume <= 0
        ):
            details += (
                "\n"
                "مستوى صوت الوسائط في الهاتف يساوي صفر."
            )

        self.status_label.text = fix_text(
            "تعذر تشغيل الرد الصوتي"
        )

        self.status_label.color = (
            1.0,
            0.28,
            0.30,
            1.0
        )

        self.status_orb.set_state(
            "error"
        )

        self._append_chat_text(
            "تشخيص الصوت:\n"
            + details
        )

    # =====================================================
    # MICROPHONE PERMISSION
    # =====================================================

    def _has_record_audio_permission(
        self
    ):
        if platform != "android":
            return False

        try:
            from android.permissions import (
                check_permission,
                Permission
            )

            return bool(
                check_permission(
                    Permission.RECORD_AUDIO
                )
            )

        except Exception as exc:
            print(
                "811: RECORD_AUDIO permission check error:",
                repr(exc)
            )
            return False

    def _request_record_audio_permission(
        self
    ):
        if platform != "android":
            return

        try:
            from android.permissions import (
                request_permissions,
                Permission
            )

            request_permissions(
                [
                    Permission.RECORD_AUDIO
                ]
            )

            print(
                "811: RECORD_AUDIO permission requested"
            )

        except Exception as exc:
            print(
                "811: RECORD_AUDIO permission request error:",
                repr(exc)
            )

    # =====================================================
    # SPEECH ERROR MAP
    # =====================================================

    def _speech_error_info(
        self,
        error_code
    ):
        errors = {
            1: (
                "ERROR_NETWORK_TIMEOUT",
                "انتهت مهلة اتصال خدمة التعرف على الكلام."
            ),
            2: (
                "ERROR_NETWORK",
                "حدث خطأ في شبكة خدمة التعرف على الكلام."
            ),
            3: (
                "ERROR_AUDIO",
                "حدث خطأ أثناء تسجيل الصوت من الميكروفون."
            ),
            4: (
                "ERROR_SERVER",
                "خادم التعرف على الكلام أعاد خطأ."
            ),
            5: (
                "ERROR_CLIENT",
                "أوقف Android جلسة التعرف من جهة التطبيق."
            ),
            6: (
                "ERROR_SPEECH_TIMEOUT",
                "لم يتم اكتشاف كلام خلال المهلة المحددة."
            ),
            7: (
                "ERROR_NO_MATCH",
                "تم سماع صوت لكن لم يتم التعرف على كلمات مطابقة."
            ),
            8: (
                "ERROR_RECOGNIZER_BUSY",
                "محرك التعرف على الكلام مشغول حالياً."
            ),
            9: (
                "ERROR_INSUFFICIENT_PERMISSIONS",
                "صلاحية الميكروفون غير متاحة للتطبيق."
            ),
            10: (
                "ERROR_TOO_MANY_REQUESTS",
                "تم إرسال طلبات كثيرة إلى محرك التعرف."
            ),
            11: (
                "ERROR_SERVER_DISCONNECTED",
                "انقطع الاتصال بخدمة التعرف على الكلام."
            ),
            12: (
                "ERROR_LANGUAGE_NOT_SUPPORTED",
                "لغة التعرف المطلوبة غير مدعومة على هذا الجهاز."
            ),
            13: (
                "ERROR_LANGUAGE_UNAVAILABLE",
                "لغة التعرف المطلوبة مدعومة لكنها غير متاحة حالياً."
            ),
            14: (
                "ERROR_CANNOT_CHECK_SUPPORT",
                "تعذر التحقق من دعم محرك التعرف."
            ),
            15: (
                "ERROR_CANNOT_LISTEN_TO_DOWNLOAD_EVENTS",
                "تعذر الاستماع إلى أحداث تنزيل نموذج اللغة."
            )
        }

        return errors.get(
            int(error_code),
            (
                "ERROR_UNKNOWN",
                "حدث خطأ غير معروف في التعرف على الكلام."
            )
        )

    def _current_speech_language(
        self
    ):
        if (
            self.speech_language_index < 0
            or self.speech_language_index
            >= len(self.speech_languages)
        ):
            self.speech_language_index = 0

        return self.speech_languages[
            self.speech_language_index
        ]

    def _speech_language_label(
        self
    ):
        language = (
            self._current_speech_language()
        )

        if language is None:
            return "SYSTEM_DEFAULT"

        return language

    # =====================================================
    # SPEECH RECOGNIZER INITIALIZATION
    # =====================================================

    def init_native_speech(
        self
    ):
        if platform != "android":
            return

        self._run_on_android_ui(
            self._init_native_speech_on_ui
        )

    def _init_native_speech_on_ui(
        self
    ):
        try:
            from jnius import (
                autoclass,
                PythonJavaClass,
                java_method
            )

            self._speech_autoclass = (
                autoclass
            )

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            SpeechRecognizer = autoclass(
                "android.speech.SpeechRecognizer"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                self.speech_recognizer_ready = False
                self.speech_init_error = (
                    "Android Activity unavailable"
                )

                print(
                    "811:",
                    self.speech_init_error
                )
                return

            available = (
                SpeechRecognizer
                .isRecognitionAvailable(
                    activity
                )
            )

            print(
                "811: SpeechRecognizer availability:",
                bool(available)
            )

            if not available:
                self.speech_recognizer_ready = False
                self.speech_init_error = (
                    "No RecognitionService available"
                )

                print(
                    "811:",
                    self.speech_init_error
                )
                return

            outer = self

            class RecognitionListener(
                PythonJavaClass
            ):
                __javainterfaces__ = [
                    "android/speech/"
                    "RecognitionListener"
                ]
                __javacontext__ = "app"

                @java_method(
                    "(Landroid/os/Bundle;)V"
                )
                def onReadyForSpeech(
                    self,
                    params
                ):
                    outer.on_speech_ready()

                @java_method(
                    "()V"
                )
                def onBeginningOfSpeech(
                    self
                ):
                    outer.on_speech_begin()

                @java_method(
                    "(F)V"
                )
                def onRmsChanged(
                    self,
                    rmsdB
                ):
                    pass

                @java_method(
                    "([B)V"
                )
                def onBufferReceived(
                    self,
                    buffer
                ):
                    pass

                @java_method(
                    "()V"
                )
                def onEndOfSpeech(
                    self
                ):
                    outer.on_speech_end()

                @java_method(
                    "(I)V"
                )
                def onError(
                    self,
                    error
                ):
                    outer.on_speech_error(
                        int(error)
                    )

                @java_method(
                    "(Landroid/os/Bundle;)V"
                )
                def onResults(
                    self,
                    results
                ):
                    # Important:
                    # Extract Java Bundle data inside the Java callback.
                    # Only a normal Python string crosses to Kivy's thread.
                    text = (
                        outer
                        ._extract_speech_results(
                            results
                        )
                    )

                    outer.on_speech_results_text(
                        text
                    )

                @java_method(
                    "(Landroid/os/Bundle;)V"
                )
                def onPartialResults(
                    self,
                    results
                ):
                    text = (
                        outer
                        ._extract_speech_results(
                            results
                        )
                    )

                    outer.on_speech_partial_text(
                        text
                    )

                @java_method(
                    "(ILandroid/os/Bundle;)V"
                )
                def onEvent(
                    self,
                    event_type,
                    params
                ):
                    pass

            self._speech_listener = (
                RecognitionListener()
            )

            recognizer = (
                SpeechRecognizer
                .createSpeechRecognizer(
                    activity
                )
            )

            if recognizer is None:
                self.speech_recognizer_ready = False
                self.speech_init_error = (
                    "createSpeechRecognizer returned null"
                )

                print(
                    "811:",
                    self.speech_init_error
                )
                return

            self.speech_recognizer = recognizer

            self.speech_recognizer.setRecognitionListener(
                self._speech_listener
            )

            self.speech_recognizer_ready = True
            self.speech_init_error = ""

            print(
                "811: SpeechRecognizer READY"
            )

        except Exception as exc:
            self.speech_recognizer = None
            self.speech_recognizer_ready = False

            self.speech_init_error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            print(
                "811: SpeechRecognizer init FAILED:"
            )

            print(
                "811:",
                self.speech_init_error
            )

    # =====================================================
    # START LISTENING
    # =====================================================

    def start_listening(
        self
    ):
        if platform != "android":
            self.set_state(
                "error",
                "الاستماع الصوتي متاح على Android فقط."
            )
            return

        if self.processing:
            return

        if self.is_listening:
            return

        if not self._has_record_audio_permission():
            self._request_record_audio_permission()

            self.set_state(
                "error",
                "صلاحية الميكروفون غير مفعلة.\n"
                "تم طلب صلاحية RECORD_AUDIO.\n"
                "وافق عليها ثم اضغط للتحدث مرة أخرى."
            )
            return

        if not self.speech_recognizer_ready:
            message = (
                "محرك التعرف على الكلام غير جاهز."
            )

            if self.speech_init_error:
                message += (
                    "\n\n"
                    + self.speech_init_error
                )

            self.set_state(
                "error",
                message
            )

            # Try initialization one more time in case permissions
            # were granted after app startup.
            self.init_native_speech()
            return

        self.speech_recovery_attempts = 0

        self._run_on_android_ui(
            self._start_listening_on_ui
        )

    def _start_listening_on_ui(
        self
    ):
        try:
            from jnius import autoclass

            Intent = autoclass(
                "android.content.Intent"
            )

            RecognizerIntent = autoclass(
                "android.speech.RecognizerIntent"
            )

            intent = Intent(
                RecognizerIntent
                .ACTION_RECOGNIZE_SPEECH
            )

            intent.putExtra(
                RecognizerIntent
                .EXTRA_LANGUAGE_MODEL,
                RecognizerIntent
                .LANGUAGE_MODEL_FREE_FORM
            )

            language = (
                self._current_speech_language()
            )

            if language:
                intent.putExtra(
                    RecognizerIntent
                    .EXTRA_LANGUAGE,
                    language
                )

            intent.putExtra(
                RecognizerIntent
                .EXTRA_PARTIAL_RESULTS,
                True
            )

            intent.putExtra(
                RecognizerIntent
                .EXTRA_MAX_RESULTS,
                3
            )

            intent.putExtra(
                RecognizerIntent
                .EXTRA_PROMPT,
                "تحدث الآن"
            )

            print(
                "811: startListening language:",
                self._speech_language_label()
            )

            self.speech_recognizer.startListening(
                intent
            )

            self.is_listening = True

            Clock.schedule_once(
                lambda dt:
                self.set_state(
                    "listening",
                    "جاري الاستماع...\n"
                    "اللغة: "
                    + self._speech_language_label()
                ),
                0
            )

            print(
                "811: startListening OK"
            )

        except Exception as exc:
            self.is_listening = False

            print(
                "811: startListening FAILED:",
                repr(exc)
            )

            message = (
                "تعذر بدء الاستماع.\n"
                + type(exc).__name__
                + ": "
                + str(exc)
            )

            Clock.schedule_once(
                lambda dt:
                self.set_state(
                    "error",
                    message
                ),
                0
            )

    # =====================================================
    # STOP LISTENING
    # =====================================================

    def stop_listening(
        self
    ):
        if self.speech_recognizer is None:
            return

        self._run_on_android_ui(
            self._stop_listening_on_ui
        )

    def _stop_listening_on_ui(
        self
    ):
        try:
            self.speech_recognizer.stopListening()
        except Exception as exc:
            print(
                "811: stopListening error:",
                repr(exc)
            )

        self.is_listening = False

        if not self.processing:
            Clock.schedule_once(
                lambda dt:
                self.set_state(
                    "ready"
                ),
                0
            )

    # =====================================================
    # SPEECH RESULTS
    # =====================================================

    def _extract_speech_results(
        self,
        results
    ):
        if results is None:
            return ""

        try:
            SpeechRecognizer = (
                self._speech_autoclass(
                    "android.speech."
                    "SpeechRecognizer"
                )
            )

            matches = (
                results
                .getStringArrayList(
                    SpeechRecognizer
                    .RESULTS_RECOGNITION
                )
            )

            if matches is None:
                return ""

            if matches.size() == 0:
                return ""

            return str(
                matches.get(0)
            )

        except Exception as exc:
            print(
                "811: speech result error:",
                repr(exc)
            )
            return ""

    # =====================================================
    # SPEECH CALLBACKS
    # =====================================================

    @mainthread
    def on_speech_ready(
        self
    ):
        if not self.processing:
            self.set_state(
                "listening",
                "تحدث الآن...\n"
                "اللغة: "
                + self._speech_language_label()
            )

    @mainthread
    def on_speech_begin(
        self
    ):
        self.set_state(
            "listening",
            "أستمع إليك..."
        )

    @mainthread
    def on_speech_end(
        self
    ):
        if self.is_listening:
            self.set_state(
                "thinking",
                "جاري فهم كلامك..."
            )

    @mainthread
    def on_speech_partial_text(
        self,
        text
    ):
        text = clean_unicode(
            text
        )

        if text:
            self._set_chat_text(
                "أنت:\n"
                + text
            )

    @mainthread
    def on_speech_results_text(
        self,
        text
    ):
        self.is_listening = False
        self.speech_recovery_attempts = 0

        text = clean_unicode(
            text
        )

        if not text:
            self.processing = False
            self.speak_btn.disabled = False

            self.set_state(
                "error",
                "لم أتمكن من فهم الكلام."
            )

            Clock.schedule_once(
                lambda dt:
                self._return_to_ready(),
                2.0
            )
            return

        groq_key = (
            self.key_input
            .text
            .strip()
        )

        if not groq_key:
            self.processing = False
            self.speak_btn.disabled = False

            self.set_state(
                "error",
                "أدخل مفتاح Groq أولاً."
            )
            return

        self.processing = True
        self.speak_btn.disabled = True

        self.set_state(
            "thinking",
            "أنت:\n"
            + text
            + "\n\n"
            + "جاري التفكير..."
        )

        threading.Thread(
            target=self.process_user_text,
            args=(
                text,
                groq_key
            ),
            daemon=True
        ).start()

    @mainthread
    def on_speech_error(
        self,
        error_code
    ):
        self.is_listening = False

        error_code = int(
            error_code
        )

        error_name, description = (
            self._speech_error_info(
                error_code
            )
        )

        self.speech_last_error_code = (
            error_code
        )

        self.speech_last_error_name = (
            error_name
        )

        print(
            "811 SpeechRecognizer error:",
            error_code,
            error_name,
            "| language:",
            self._speech_language_label()
        )

        # -------------------------------------------------
        # Automatic language fallback
        # -------------------------------------------------

        if error_code in (12, 13):
            next_index = (
                self.speech_language_index + 1
            )

            if next_index < len(
                self.speech_languages
            ):
                old_language = (
                    self._speech_language_label()
                )

                self.speech_language_index = (
                    next_index
                )

                new_language = (
                    self._speech_language_label()
                )

                self.set_state(
                    "listening",
                    "لغة التعرف "
                    + old_language
                    + " غير متاحة.\n"
                    + "أجرب تلقائياً: "
                    + new_language
                )

                print(
                    "811: Speech language fallback:",
                    old_language,
                    "->",
                    new_language
                )

                Clock.schedule_once(
                    lambda dt:
                    self._run_on_android_ui(
                        self._start_listening_on_ui
                    ),
                    0.35
                )
                return

        # -------------------------------------------------
        # Permission recovery
        # -------------------------------------------------

        if error_code == 9:
            self._request_record_audio_permission()

            self.processing = False
            self.speak_btn.disabled = False

            self.set_state(
                "error",
                "SpeechRecognizer Error "
                + str(error_code)
                + "\n"
                + error_name
                + "\n\n"
                + description
                + "\n\n"
                + "تم طلب صلاحية الميكروفون مرة أخرى."
            )
            return

        # -------------------------------------------------
        # One safe automatic recognizer recovery
        # -------------------------------------------------

        if (
            error_code in (5, 8, 11)
            and self.speech_recovery_attempts
            < self.speech_max_recovery_attempts
        ):
            self.speech_recovery_attempts += 1

            self.set_state(
                "listening",
                "SpeechRecognizer Error "
                + str(error_code)
                + "\n"
                + error_name
                + "\n\n"
                + "أعيد تهيئة محرك الصوت مرة واحدة..."
            )

            Clock.schedule_once(
                lambda dt:
                self._run_on_android_ui(
                    self._recreate_speech_and_retry_on_ui
                ),
                0.45
            )
            return

        # -------------------------------------------------
        # Final diagnostic error shown on screen
        # -------------------------------------------------

        self.processing = False
        self.speak_btn.disabled = False

        diagnostic_message = (
            "SpeechRecognizer Error "
            + str(error_code)
            + "\n"
            + error_name
            + "\n\n"
            + description
            + "\n\n"
            + "Language: "
            + self._speech_language_label()
        )

        self.set_state(
            "error",
            diagnostic_message
        )

        # Keep the diagnostic visible longer so it can be
        # photographed or copied.
        Clock.schedule_once(
            lambda dt:
            self._return_to_ready(),
            6.0
        )

    # =====================================================
    # SPEECH RECOVERY
    # =====================================================

    def _recreate_speech_and_retry_on_ui(
        self
    ):
        try:
            if self.speech_recognizer is not None:
                try:
                    self.speech_recognizer.cancel()
                except Exception:
                    pass

                try:
                    self.speech_recognizer.destroy()
                except Exception:
                    pass

            self.speech_recognizer = None
            self.speech_recognizer_ready = False
            self._speech_listener = None

            print(
                "811: Recreating SpeechRecognizer..."
            )

            self._init_native_speech_on_ui()

            if not self.speech_recognizer_ready:
                message = (
                    "فشلت إعادة تهيئة SpeechRecognizer.\n"
                    + self.speech_init_error
                )

                Clock.schedule_once(
                    lambda dt:
                    self.set_state(
                        "error",
                        message
                    ),
                    0
                )
                return

            self._start_listening_on_ui()

        except Exception as exc:
            print(
                "811: SpeechRecognizer recovery failed:",
                repr(exc)
            )

            message = (
                "فشلت إعادة تهيئة محرك الصوت.\n"
                + type(exc).__name__
                + ": "
                + str(exc)
            )

            Clock.schedule_once(
                lambda dt:
                self.set_state(
                    "error",
                    message
                ),
                0
            )

    # =====================================================
    # BUTTON
    # =====================================================

    def on_speak_click(
        self,
        instance
    ):
        if self.processing:
            return

        if self.is_listening:
            self.stop_listening()
            return

        groq_key = (
            self.key_input
            .text
            .strip()
        )

        if not groq_key:
            self.set_state(
                "error",
                "يرجى إدخال مفتاح Groq API أولاً."
            )
            return

        self.start_listening()

    # =====================================================
    # AI PIPELINE
    # =====================================================

    def process_user_text(
        self,
        user_text,
        groq_key
    ):
        try:
            if self.ai_engine is None:
                self.update_error(
                    "تعذر تهيئة محرك الذكاء الاصطناعي."
                )
                return

            self.ai_engine.groq_key = (
                groq_key
            )

            response = (
                self.ai_engine
                .get_response(
                    user_text
                )
            )

            response = (
                ""
                if response is None
                else str(response).strip()
            )

            if not response:
                response = (
                    "لم يصلني رد من "
                    "الذكاء الاصطناعي."
                )

            self.update_voice_conversation(
                user_text,
                response
            )

        except Exception as exc:
            print(
                "811: AI pipeline error:",
                repr(exc)
            )

            self.update_error(
                "حدث خطأ أثناء معالجة طلبك."
            )

    @mainthread
    def update_voice_conversation(
        self,
        user_text,
        response
    ):
        self.processing = False
        self.speak_btn.disabled = False

        message = (
            "أنت:\n"
            + user_text
            + "\n\n"
            + "811:\n"
            + response
        )

        self.set_state(
            "speaking",
            message
        )

        self.speak(
            clean_for_speech(
                response
            )
        )

        # The TTS watcher returns the UI to ready when playback ends.

    @mainthread
    def update_error(
        self,
        message
    ):
        self.processing = False
        self.speak_btn.disabled = False

        self.set_state(
            "error",
            message
        )

        Clock.schedule_once(
            lambda dt:
            self._return_to_ready(),
            2.5
        )

    # =====================================================
    # READY
    # =====================================================

    def _return_to_ready(
        self,
        *args
    ):
        if self.processing:
            return

        if self.is_listening:
            return

        self.set_state(
            "ready"
        )

    # =====================================================
    # CLEAR
    # =====================================================

    def on_clear_click(
        self,
        instance
    ):
        if self.processing:
            return

        if self.is_listening:
            self.stop_listening()

        self._set_chat_text(
            "تم مسح الشاشة.\n"
            "أنا 811.\n"
            "جاهز."
        )

        if self.ai_engine is not None:
            try:
                self.ai_engine.clear_history()
            except Exception as exc:
                print(
                    "811: clear_history error:",
                    repr(exc)
                )

        self.set_state(
            "ready"
        )

        self.key_input.focus = False

    # =====================================================
    # STOP
    # =====================================================

    def on_stop(
        self
    ):
        try:
            if self.speech_recognizer is not None:
                self._run_on_android_ui(
                    self._destroy_speech_on_ui
                )

        except Exception as exc:
            print(
                "811: SpeechRecognizer destroy error:",
                repr(exc)
            )

        try:
            if self.tts is not None:
                self.tts.stop()
                self.tts.shutdown()

        except Exception as exc:
            print(
                "811: TTS shutdown error:",
                repr(exc)
            )

        try:
            if self.native_chat_scroll is not None:
                self._run_on_android_ui(
                    self._destroy_native_chat_on_ui
                )

        except Exception as exc:
            print(
                "811: Native chat shutdown error:",
                repr(exc)
            )

        super().on_stop()

    def _destroy_speech_on_ui(
        self
    ):
        try:
            if self.speech_recognizer is not None:
                try:
                    self.speech_recognizer.cancel()
                except Exception:
                    pass

                self.speech_recognizer.destroy()
                self.speech_recognizer = None
                self.speech_recognizer_ready = False
                self._speech_listener = None

                print(
                    "811: SpeechRecognizer destroyed"
                )

        except Exception as exc:
            print(
                "811: SpeechRecognizer shutdown error:",
                repr(exc)
            )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    VoiceAssistantApp().run()
