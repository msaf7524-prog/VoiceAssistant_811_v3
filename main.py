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
# المسارات
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "Cairo-Regular.ttf")


# =========================================================
# الخط العربي Cairo
# =========================================================

ARABIC_FONT = "Roboto"

if os.path.exists(FONT_PATH):
    try:
        LabelBase.register(
            name="Cairo",
            fn_regular=FONT_PATH
        )
        ARABIC_FONT = "Cairo"
        print("811: Cairo-Regular.ttf loaded successfully")
    except Exception as exc:
        print("811: Cairo font registration error:", repr(exc))
else:
    print("811: Cairo-Regular.ttf NOT FOUND:", FONT_PATH)


# =========================================================
# معالجة النص العربي
# =========================================================

def clean_unicode(text):
    """
    تنظيف محارف Unicode غير المرغوبة مع إبقاء
    الأسطر والفواصل المفيدة.
    """
    if text is None:
        return ""

    text = str(text)

    cleaned = []

    for char in text:
        code = ord(char)

        # إبقاء newline / tab
        if char in ("\n", "\t"):
            cleaned.append(char)
            continue

        # حذف محارف التحكم غير المرغوبة
        if code < 32:
            continue

        # حذف محارف directionality / zero width الشائعة
        if code in (
            0x061C,
            0x200B,
            0x200C,
            0x200D,
            0x200E,
            0x200F,
            0x202A,
            0x202B,
            0x202C,
            0x202D,
            0x202E,
            0x2066,
            0x2067,
            0x2068,
            0x2069,
            0xFEFF,
        ):
            continue

        cleaned.append(char)

    text = "".join(cleaned)

    # تقليل المسافات فقط داخل الأسطر
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)

    return "\n".join(lines).strip()


def fix_text(text):
    """
    تجهيز النص العربي للعرض الصحيح داخل Kivy.
    """
    text = clean_unicode(text)

    if not text:
        return ""

    # لا حاجة لإعادة تشكيل النصوص غير العربية
    if not re.search(r"[\u0600-\u06FF]", text):
        return text

    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(
            reshaped,
            base_dir="R"
        )
    except Exception as exc:
        print("811: Arabic processing error:", repr(exc))
        return text


def clean_for_speech(text):
    """
    تنظيف الرد قبل إرساله إلى Android TTS.
    لا نرسل النص المعكوس الذي تستخدمه Kivy للعرض.
    """
    text = clean_unicode(text)

    if not text:
        return ""

    # إزالة رموز التنسيق غير الضرورية
    text = re.sub(r"[*_~`#]", "", text)

    # إزالة مسافات زائدة
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


# =========================================================
# صلاحيات Android
# =========================================================

def request_android_permissions():
    """
    طلب الصلاحيات اللازمة عند تشغيل Android.
    """
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

        # Android الحديث
        if hasattr(Permission, "BLUETOOTH_CONNECT"):
            permissions.append(Permission.BLUETOOTH_CONNECT)

        if hasattr(Permission, "BLUETOOTH_SCAN"):
            permissions.append(Permission.BLUETOOTH_SCAN)

        # التوافق مع الإصدارات الأقدم
        if hasattr(Permission, "BLUETOOTH"):
            permissions.append(Permission.BLUETOOTH)

        if hasattr(Permission, "BLUETOOTH_ADMIN"):
            permissions.append(Permission.BLUETOOTH_ADMIN)

        request_permissions(permissions)

        print("811: Android permissions requested")

    except Exception as exc:
        print("811: Permission error:", repr(exc))


# =========================================================
# دائرة الحالة
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

        Clock.schedule_once(
            lambda dt: self._redraw(),
            0
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
                0.75,
                0.85,
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
                0.78,
                0.30,
                1.0
            ),
            "error": (
                0.92,
                0.20,
                0.22,
                1.0
            ),
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

            # الهالة الخارجية
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

            # الهالة الثانية
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

            # الدائرة الأساسية
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

            # الحلقة الداخلية
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
# بطاقة نصية
# =========================================================

class RoundedPanel(Widget):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.bind(
            pos=self._redraw,
            size=self._redraw
        )

    def _redraw(self, *args):
        self.canvas.before.clear()

        with self.canvas.before:

            Color(
                0.055,
                0.065,
                0.090,
                1.0
            )

            RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[
                    dp(18)
                ]
            )


# =========================================================
# التطبيق
# =========================================================

class VoiceAssistantApp(App):

    def build(self):

        self.title = "VOICE ASSISTANT 811"

        self.processing = False

        self.ai_engine = None

        # Native Android TTS
        self.tts = None
        self.tts_ready = False
        self.tts_language_ready = False

        # حفظ الخط المرجعي
        self.arabic_font = ARABIC_FONT

        request_android_permissions()

        # تهيئة AI
        try:
            self.ai_engine = AIClient()
        except Exception as exc:
            print(
                "811: AIClient init error:",
                repr(exc)
            )
            self.ai_engine = None

        # -------------------------------------------------
        # الخلفية
        # -------------------------------------------------

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
                radius=[
                    dp(0)
                ]
            )

        root.bind(
            pos=lambda instance, value: setattr(
                root.background_rect,
                "pos",
                value
            ),
            size=lambda instance, value: setattr(
                root.background_rect,
                "size",
                value
            )
        )

        # -------------------------------------------------
        # الحاوية الرئيسية
        # -------------------------------------------------

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
        # Header
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

        main.add_widget(header)

        # =================================================
        # API Key Panel
        # =================================================

        key_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            padding=(
                dp(4),
                dp(4),
                dp(4),
                dp(4)
            )
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
        # الحالة + Orb
        # =================================================

        status_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(205),
            spacing=dp(2)
        )

        self.status_orb = StatusOrb(
            size_hint_y=1
        )

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
            width=lambda instance, value: setattr(
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
        # الرسائل
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
            width=self._update_output_width,
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
        # أزرار التحكم
        # =================================================

        buttons = BoxLayout(
            size_hint_y=None,
            height=dp(60),
            spacing=dp(9)
        )

        self.speak_btn = Button(
            text=fix_text(
                "اختبار 811"
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
        # Footer
        # =================================================

        self.footer_label = Label(
            text=fix_text(
                "Local Native TTS • Cairo Arabic • Groq AI"
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
            width=lambda instance, value: setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        main.add_widget(
            self.footer_label
        )

        root.add_widget(main)

        # الحالة الابتدائية
        self.set_state(
            "ready",
            "النظام جاهز"
        )

        # تهيئة TTS بعد بناء الواجهة
        if platform == "android":
            Clock.schedule_once(
                lambda dt: self.init_native_tts(),
                1.0
            )

        return root

    # =====================================================
    # حجم النص
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
    # تغيير الحالة
    # =====================================================

    def set_state(
        self,
        state,
        message=""
    ):

        state_text = {
            "ready": "جاهز",
            "listening": "جاري الاستماع...",
            "thinking": "جاري التفكير...",
            "speaking": "811 يتحدث الآن",
            "error": "حدث خطأ"
        }

        state_colors = {
            "ready": (
                0.30,
                0.75,
                1.0,
                1.0
            ),
            "listening": (
                0.10,
                0.85,
                0.90,
                1.0
            ),
            "thinking": (
                1.0,
                0.65,
                0.12,
                1.0
            ),
            "speaking": (
                0.20,
                0.85,
                0.35,
                1.0
            ),
            "error": (
                1.0,
                0.28,
                0.30,
                1.0
            )
        }

        status = state_text.get(
            state,
            "جاهز"
        )

        color = state_colors.get(
            state,
            state_colors["ready"]
        )

        self.status_label.text = fix_text(
            status
        )

        self.status_label.color = color

        self.status_orb.set_state(
            state
        )

        if message:
            self.output_label.text = fix_text(
                message
            )

            Clock.schedule_once(
                lambda dt: setattr(
                    self.scroll,
                    "scroll_y",
                    0
                ),
                0
            )

    # =====================================================
    # Android Native TTS
    # =====================================================

    def init_native_tts(self):
        """
        تهيئة Android TextToSpeech باستخدام PyJNIus.
        """

        if platform != "android":
            print(
                "811: Native TTS available only on Android"
            )
            return

        try:
            from jnius import autoclass, PythonJavaClass, java_method

            self._PythonJavaClass = PythonJavaClass
            self._java_method = java_method
            self._autoclass = autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            TextToSpeech = autoclass(
                "android.speech.tts.TextToSpeech"
            )

            Locale = autoclass(
                "java.util.Locale"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                print(
                    "811: Android activity unavailable"
                )
                return

            outer = self

            class TTSInitListener(PythonJavaClass):

                __javainterfaces__ = [
                    "android/speech/tts/TextToSpeech$OnInitListener"
                ]

                @java_method("(I)V")
                def onInit(self, status):

                    try:
                        success = (
                            status
                            == TextToSpeech.SUCCESS
                        )

                        if not success:
                            outer.tts_ready = False
                            print(
                                "811: TTS initialization failed:"
                                f" {status}"
                            )
                            return

                        outer.tts_ready = True
                        outer.tts_language_ready = False

                        # الأفضلية للعربية العراقية ثم العربية العامة
                        candidates = [
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

                        for locale in candidates:

                            try:
                                availability = (
                                    outer.tts.isLanguageAvailable(
                                        locale
                                    )
                                )

                                if availability >= (
                                    TextToSpeech.LANG_AVAILABLE
                                ):
                                    result = (
                                        outer.tts.setLanguage(
                                            locale
                                        )
                                    )

                                    if result >= (
                                        TextToSpeech.LANG_AVAILABLE
                                    ):
                                        outer.tts_language_ready = True

                                        print(
                                            "811: Arabic TTS ready:"
                                            f" {locale}"
                                        )

                                        break

                            except Exception as lang_exc:
                                print(
                                    "811: TTS locale error:",
                                    repr(lang_exc)
                                )

                        if not outer.tts_language_ready:
                            print(
                                "811: Arabic TTS language "
                                "is not available on device"
                            )

                        try:
                            outer.tts.setSpeechRate(
                                0.92
                            )

                            outer.tts.setPitch(
                                1.00
                            )

                        except Exception as rate_exc:
                            print(
                                "811: TTS rate/pitch error:",
                                repr(rate_exc)
                            )

                    except Exception as exc:
                        outer.tts_ready = False
                        print(
                            "811: TTS init callback error:",
                            repr(exc)
                        )

            listener = TTSInitListener()

            self._tts_listener = listener

            self.tts = TextToSpeech(
                activity,
                listener
            )

            print(
                "811: Native Android TTS object created"
            )

        except Exception as exc:
            self.tts = None
            self.tts_ready = False
            self.tts_language_ready = False

            print(
                "811: Native TTS initialization error:",
                repr(exc)
            )

    def speak(self, text):
        """
        نطق النص باستخدام Android Native TTS فقط.
        لا يتم إرسال النص إلى خدمة خارجية.
        """

        if platform != "android":
            print(
                "811 [Desktop TTS simulation]:",
                text
            )
            return

        if not text:
            return

        if not self.tts_ready:
            print(
                "811: TTS is not ready yet"
            )
            return

        if not self.tts_language_ready:
            print(
                "811: Arabic TTS language is unavailable"
            )
            return

        try:
            from jnius import autoclass

            TextToSpeech = autoclass(
                "android.speech.tts.TextToSpeech"
            )

            Build = autoclass(
                "android.os.Build"
            )

            clean_text = clean_for_speech(
                text
            )

            if not clean_text:
                return

            # Android API 21+
            if Build.VERSION.SDK_INT >= 21:

                self.tts.speak(
                    clean_text,
                    TextToSpeech.QUEUE_FLUSH,
                    None,
                    "811_utterance"
                )

            else:

                self.tts.speak(
                    clean_text,
                    TextToSpeech.QUEUE_FLUSH,
                    None
                )

            print(
                "811: Native TTS speak executed"
            )

        except Exception as exc:
            print(
                "811: TTS speak error:",
                repr(exc)
            )

    # =====================================================
    # اختبار الذكاء الاصطناعي
    # =====================================================

    def on_speak_click(self, instance):

        if self.processing:
            return

        groq_key = self.key_input.text.strip()

        if not groq_key:
            self.set_state(
                "error",
                "يرجى إدخال مفتاح Groq API أولاً."
            )
            return

        if self.ai_engine is None:
            self.set_state(
                "error",
                "تعذر تهيئة AIClient."
            )
            return

        self.processing = True

        self.speak_btn.disabled = True

        self.set_state(
            "thinking",
            "جاري الاتصال بالذكاء الاصطناعي..."
        )

        thread = threading.Thread(
            target=self.process_ai_request,
            args=(groq_key,),
            daemon=True
        )

        thread.start()

    def process_ai_request(self, groq_key):

        user_prompt = "السلام عليكم"

        try:

            self.ai_engine.groq_key = (
                groq_key
            )

            response = (
                self.ai_engine.get_response(
                    user_prompt
                )
            )

            if response is None:
                response = ""

            response = str(
                response
            ).strip()

            if not response:
                response = (
                    "لم يتم استلام رد من "
                    "الذكاء الاصطناعي."
                )

            self.update_success(
                user_prompt,
                response
            )

        except Exception as exc:

            print(
                "811: AI processing error:",
                repr(exc)
            )

            self.update_error(
                "حدث خطأ أثناء معالجة الطلب."
            )

    # =====================================================
    # نجاح
    # =====================================================

    @mainthread
    def update_success(
        self,
        user_prompt,
        response
    ):

        self.processing = False

        self.speak_btn.disabled = False

        message = (
            "أنت:\n"
            + user_prompt
            + "\n\n"
            + "811:\n"
            + response
        )

        self.set_state(
            "speaking",
            message
        )

        # الكلام الحقيقي
        self.speak(
            response
        )

        # العودة إلى Ready بعد بداية الكلام
        Clock.schedule_once(
            lambda dt: self._return_to_ready(),
            1.5
        )

    # =====================================================
    # خطأ
    # =====================================================

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
            lambda dt: self._return_to_ready(),
            2.5
        )

    def _return_to_ready(self, *args):
        if not self.processing:
            self.set_state(
                "ready"
            )

    # =====================================================
    # مسح
    # =====================================================

    def on_clear_click(self, instance):

        if self.processing:
            return

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
    # إغلاق التطبيق
    # =====================================================

    def on_stop(self):

        try:
            if self.tts is not None:
                self.tts.stop()
                self.tts.shutdown()

                print(
                    "811: Native TTS shutdown complete"
                )
        except Exception as exc:
            print(
                "811: TTS shutdown error:",
                repr(exc)
            )

        super().on_stop()


# =========================================================
# التشغيل
# =========================================================

if __name__ == "__main__":
    VoiceAssistantApp().run()
