import os
import re
import threading

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
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

__version__ = "0.2.0"


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

FONT_PATH = os.path.join(
    BASE_DIR,
    "Cairo-Regular.ttf"
)


# =========================================================
# ARABIC FONT
# =========================================================

ARABIC_FONT = "Roboto"

if os.path.exists(FONT_PATH):
    try:
        LabelBase.register(
            name="Cairo",
            fn_regular=FONT_PATH
        )

        ARABIC_FONT = "Cairo"

        print(
            "811: Cairo-Regular.ttf loaded successfully"
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


def clean_unicode(text):
    if text is None:
        return ""

    text = str(text)

    for char in HIDDEN_UNICODE:
        text = text.replace(
            char,
            ""
        )

    cleaned = []

    for char in text:

        if char in (
            "\n",
            "\t"
        ):
            cleaned.append(char)
            continue

        if ord(char) < 32:
            continue

        cleaned.append(char)

    text = "".join(cleaned)

    lines = []

    for line in text.splitlines():
        line = re.sub(
            r"[ \t]+",
            " ",
            line
        ).strip()

        lines.append(line)

    return "\n".join(lines).strip()


def fix_text(text):
    clean_text = clean_unicode(text)

    if not clean_text:
        return ""

    if not re.search(
        r"[\u0600-\u06FF]",
        clean_text
    ):
        return clean_text

    try:

        reshaped = (
            arabic_reshaper.reshape(
                clean_text
            )
        )

        return get_display(
            reshaped,
            base_dir="R"
        )

    except Exception as exc:

        print(
            "811: Arabic formatting error:",
            repr(exc)
        )

        return clean_text


def clean_for_speech(text):
    text = clean_unicode(text)

    if not text:
        return ""

    text = re.sub(
        r"[*_~`#]",
        "",
        text
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# ANDROID PERMISSIONS
# =========================================================

def request_android_permissions():

    if platform != "android":
        return

    try:

        from android.permissions import (
            request_permissions,
            Permission
        )

        permissions = [
            Permission.RECORD_AUDIO,
            Permission.INTERNET,
            Permission.ACCESS_NETWORK_STATE,
            Permission.MODIFY_AUDIO_SETTINGS,
        ]

        if hasattr(
            Permission,
            "BLUETOOTH_CONNECT"
        ):
            permissions.append(
                Permission.BLUETOOTH_CONNECT
            )

        if hasattr(
            Permission,
            "BLUETOOTH_SCAN"
        ):
            permissions.append(
                Permission.BLUETOOTH_SCAN
            )

        if hasattr(
            Permission,
            "BLUETOOTH"
        ):
            permissions.append(
                Permission.BLUETOOTH
            )

        if hasattr(
            Permission,
            "BLUETOOTH_ADMIN"
        ):
            permissions.append(
                Permission.BLUETOOTH_ADMIN
            )

        request_permissions(
            permissions
        )

        print(
            "811: Android permissions requested"
        )

    except Exception as exc:

        print(
            "811: Permission error:",
            repr(exc)
        )


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

        if self.width <= 0:
            return

        if self.height <= 0:
            return

        with self.canvas:

            cx = self.center_x
            cy = self.center_y

            radius = (
                min(
                    self.width,
                    self.height
                ) * 0.22
            )

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

            Color(
                *self.status_color
            )

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

        self.title = (
            "VOICE ASSISTANT 811"
        )

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
        self._tts_listener = None

        # -------------------------
        # SpeechRecognizer
        # -------------------------

        self.speech_recognizer = None
        self.speech_recognizer_ready = False
        self.is_listening = False

        self._speech_listener = None
        self._speech_autoclass = None

        self.speech_init_error = ""

        # -------------------------
        # UI
        # -------------------------

        self.arabic_font = ARABIC_FONT

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

            root.background_rect = (
                RoundedRectangle(
                    pos=root.pos,
                    size=root.size,
                    radius=[0]
                )
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
            text=(
                "VOICE ASSISTANT 811"
            ),
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
                "مرحباً\n"
                "أنا 811\n"
                "جاهز للعمل معك."
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
            halign="center",
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

        chat_panel.add_widget(
            self.scroll
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

            Clock.schedule_once(
                lambda dt:
                self.init_native_tts(),
                1.0
            )

            Clock.schedule_once(
                lambda dt:
                self.init_native_speech(),
                1.5
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

            self.output_label.text = (
                fix_text(
                    message
                )
            )

            Clock.schedule_once(
                lambda dt:
                setattr(
                    self.scroll,
                    "scroll_y",
                    0
                ),
                0
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

            activity = (
                PythonActivity.mActivity
            )

            if activity is None:

                func()

                return

            outer = self

            class UiRunnable(
                PythonJavaClass
            ):

                __javainterfaces__ = [
                    "java/lang/Runnable"
                ]

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

            self._last_ui_runnable = runnable

            activity.runOnUiThread(
                runnable
            )

        except Exception as exc:

            print(
                "811: runOnUiThread error:",
                repr(exc)
            )

            func()

    # =====================================================
    # NATIVE TTS
    # =====================================================

    def init_native_tts(
        self
    ):

        if platform != "android":
            return

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

            activity = (
                PythonActivity.mActivity
            )

            if activity is None:
                return

            outer = self

            class TTSInitListener(
                PythonJavaClass
            ):

                __javainterfaces__ = [
                    "android/speech/tts/"
                    "TextToSpeech$OnInitListener"
                ]

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

                            print(
                                "811: TTS initialization failed:",
                                status
                            )

                            return

                        outer.tts_ready = True

                        outer.tts_language_ready = False

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
                                    >=
                                    TextToSpeech
                                    .LANG_AVAILABLE
                                ):

                                    result = (
                                        outer.tts
                                        .setLanguage(
                                            locale
                                        )
                                    )

                                    if (
                                        result
                                        >=
                                        TextToSpeech
                                        .LANG_AVAILABLE
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
                                    repr(
                                        lang_exc
                                    )
                                )

                        try:

                            outer.tts.setSpeechRate(
                                0.92
                            )

                            outer.tts.setPitch(
                                1.0
                            )

                        except Exception:
                            pass

                    except Exception as exc:

                        outer.tts_ready = False

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

        if not self.tts_ready:
            return

        if not self.tts_language_ready:
            return

        text = clean_for_speech(
            text
        )

        if not text:
            return

        try:

            from jnius import autoclass

            TextToSpeech = autoclass(
                "android.speech.tts.TextToSpeech"
            )

            Build = autoclass(
                "android.os.Build"
            )

            if (
                Build.VERSION.SDK_INT
                >= 21
            ):

                self.tts.speak(
                    text,
                    TextToSpeech.QUEUE_FLUSH,
                    None,
                    "811_utterance"
                )

            else:

                self.tts.speak(
                    text,
                    TextToSpeech.QUEUE_FLUSH,
                    None
                )

        except Exception as exc:

            print(
                "811: TTS speak error:",
                repr(exc)
            )

    # =====================================================
    # SPEECH RECOGNIZER INITIALIZATION
    # =====================================================

    def init_native_speech(
        self
    ):

        if platform != "android":
            return

        # Everything below is forced to Android UI thread.
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

            activity = (
                PythonActivity.mActivity
            )

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

                    outer.on_speech_results(
                        results
                    )

                @java_method(
                    "(Landroid/os/Bundle;)V"
                )
                def onPartialResults(
                    self,
                    results
                ):

                    outer.on_speech_partial_results(
                        results
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

            return

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

            intent.putExtra(
                RecognizerIntent
                .EXTRA_LANGUAGE,
                "ar-IQ"
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

            self.is_listening = True

            self.set_state(
                "listening",
                "جاري الاستماع..."
            )

            self.speech_recognizer.startListening(
                intent
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

            self.set_state(
                "error",
                "تعذر بدء الاستماع.\n"
                + type(exc).__name__
                + ": "
                + str(exc)
            )

    # =====================================================
    # STOP LISTENING
    # =====================================================

    def stop_listening(
        self
    ):

        if (
            self.speech_recognizer
            is None
        ):
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

            self.set_state(
                "ready"
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
                "تحدث الآن..."
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
    def on_speech_partial_results(
        self,
        results
    ):

        text = (
            self._extract_speech_results(
                results
            )
        )

        text = clean_unicode(
            text
        )

        if text:

            self.output_label.text = (
                fix_text(
                    "أنت:\n"
                    + text
                )
            )

    @mainthread
    def on_speech_results(
        self,
        results
    ):

        self.is_listening = False

        text = (
            self._extract_speech_results(
                results
            )
        )

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

        print(
            "811 SpeechRecognizer error:",
            error_code
        )

        errors = {

            1:
                "خطأ في الشبكة.",

            2:
                "تعذر الاتصال بخدمة التعرف.",

            3:
                "تعذر تسجيل الصوت.",

            4:
                "تعذر فهم طلب الاستماع.",

            5:
                "تعذر مطابقة الكلام.",

            6:
                "انتهت مهلة الاستماع.",

            7:
                "لم يتم العثور على كلام.",

            8:
                "طلبات كثيرة جدًا.",

            9:
                "صلاحية الميكروفون غير متاحة.",

            10:
                "تم رفض طلب الاستماع.",

            11:
                "لم تتوفر شبكة مناسبة.",

            12:
                "الخدمة غير متاحة.",

            13:
                "ميزة التعرف غير متاحة."
        }

        message = errors.get(
            int(error_code),
            "حدث خطأ في التعرف على الكلام."
        )

        self.processing = False

        self.speak_btn.disabled = False

        self.set_state(
            "error",
            message
        )

        Clock.schedule_once(
            lambda dt:
            self._return_to_ready(),
            2.0
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

        Clock.schedule_once(
            lambda dt:
            self._return_to_ready(),
            2.5
        )

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

        self.output_label.text = fix_text(
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

            if (
                self.speech_recognizer
                is not None
            ):

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

        super().on_stop()

    def _destroy_speech_on_ui(
        self
    ):

        try:

            if self.speech_recognizer is not None:

                self.speech_recognizer.cancel()

                self.speech_recognizer.destroy()

                self.speech_recognizer = None

                self.speech_recognizer_ready = False

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
