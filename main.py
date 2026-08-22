import os
import re
import threading
import unicodedata

from kivy.app import App
from kivy.clock import mainthread
from kivy.utils import platform
from kivy.core.text import LabelBase
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Ellipse
from kivy.metrics import dp

import arabic_reshaper
from bidi.algorithm import get_display

from ai_client import AIClient


# =========================================================
# الخط العربي
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "Cairo-Regular.ttf")

if os.path.exists(FONT_PATH):
    try:
        LabelBase.register(
            name="Cairo",
            fn_regular=FONT_PATH
        )
        ARABIC_FONT = "Cairo"
        print("Cairo font loaded successfully")
    except Exception as e:
        print("Cairo font error:", repr(e))
        ARABIC_FONT = "Roboto"
else:
    print("Cairo-Regular.ttf NOT FOUND:", FONT_PATH)
    ARABIC_FONT = "Roboto"


# =========================================================
# تنظيف ومعالجة النص العربي
# =========================================================

def clean_unicode(text):
    """
    إزالة محارف Unicode المخفية ومحارف التحكم
    التي قد تظهر كمربعات □ داخل Kivy.
    """

    if text is None:
        return ""

    text = str(text)

    cleaned = []

    for char in text:

        category = unicodedata.category(char)

        # إزالة محارف التنسيق والتحكم
        if category in ("Cf", "Cc"):
            # نُبقي على newline و tab
            if char not in ("\n", "\t"):
                continue

        cleaned.append(char)

    text = "".join(cleaned)

    # إزالة بعض محارف الاتجاه المعروفة
    text = re.sub(
        r"[\u061C\u200E\u200F\u202A-\u202E\u2066-\u2069]",
        "",
        text
    )

    # إزالة Zero Width characters
    text = re.sub(
        r"[\u200B\u200C\u200D\uFEFF]",
        "",
        text
    )

    # تنظيف المسافات
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    return text.strip()


def fix_text(text):
    """
    تجهيز النص العربي للعرض الصحيح داخل Kivy.
    """

    if text is None:
        return ""

    text = clean_unicode(text)

    if not text:
        return ""

    # إذا لم يوجد عربي، نعيد النص كما هو
    if not re.search(r"[\u0600-\u06FF]", text):
        return text

    try:

        reshaped = arabic_reshaper.reshape(text)

        display_text = get_display(
            reshaped,
            base_dir="R"
        )

        # تنظيف أخير لأي محارف تحكم ظهرت
        display_text = clean_unicode(display_text)

        return display_text

    except Exception as e:

        print(
            "Arabic processing error:",
            repr(e)
        )

        return text


# =========================================================
# صلاحيات Android
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

        if hasattr(Permission, "BLUETOOTH"):
            permissions.append(
                Permission.BLUETOOTH
            )

        if hasattr(Permission, "BLUETOOTH_ADMIN"):
            permissions.append(
                Permission.BLUETOOTH_ADMIN
            )

        if hasattr(Permission, "BLUETOOTH_CONNECT"):
            permissions.append(
                Permission.BLUETOOTH_CONNECT
            )

        request_permissions(
            permissions
        )

        print("Android permissions requested")

    except Exception as e:

        print(
            "Permission error:",
            repr(e)
        )


# =========================================================
# دائرة الحالة
# =========================================================

class CircleWidget(BoxLayout):

    def __init__(self, **kwargs):

        super().__init__(**kwargs)

        self.color = (
            0.2,
            0.6,
            1.0,
            1.0
        )

        self.bind(
            pos=self.update_canvas,
            size=self.update_canvas
        )

    def set_color(self, new_color):

        self.color = new_color

        self.update_canvas()

    def update_canvas(self, *args):

        self.canvas.before.clear()

        with self.canvas.before:

            Color(*self.color)

            size = min(
                self.width,
                self.height
            )

            x = self.x + (
                self.width - size
            ) / 2

            y = self.y + (
                self.height - size
            ) / 2

            Ellipse(
                pos=(x, y),
                size=(size, size)
            )


# =========================================================
# التطبيق
# =========================================================

class VoiceAssistantApp(App):

    def build(self):

        request_android_permissions()

        self.ai_engine = AIClient()

        self.processing = False

        main_layout = BoxLayout(
            orientation="vertical",
            padding=dp(15),
            spacing=dp(10)
        )

        # =====================================================
        # العنوان
        # =====================================================

        self.title_label = Label(
            text="VOICE ASSISTANT 811",
            font_size="22sp",
            bold=True,
            size_hint_y=None,
            height=dp(40)
        )

        main_layout.add_widget(
            self.title_label
        )

        # =====================================================
        # مفتاح Groq
        # =====================================================

        self.key_input = TextInput(
            hint_text="Paste Groq API Key here...",
            multiline=False,
            password=True,
            size_hint_y=None,
            height=dp(45)
        )

        main_layout.add_widget(
            self.key_input
        )

        # =====================================================
        # مؤشر الحالة
        # =====================================================

        self.indicator_layout = BoxLayout(
            size_hint_y=None,
            height=dp(100)
        )

        self.status_circle = CircleWidget()

        self.indicator_layout.add_widget(
            self.status_circle
        )

        main_layout.add_widget(
            self.indicator_layout
        )

        # =====================================================
        # الحالة
        # =====================================================

        self.status_label = Label(
            text=fix_text("جاهز"),
            font_name=ARABIC_FONT,
            font_size="18sp",
            size_hint_y=None,
            height=dp(40),
            halign="center",
            valign="middle",
            markup=False
        )

        self.status_label.bind(
            width=lambda instance, value:
            setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        main_layout.add_widget(
            self.status_label
        )

        # =====================================================
        # منطقة الرد
        # =====================================================

        self.scroll = ScrollView(
            size_hint=(1, 1)
        )

        self.output_label = Label(
            text=fix_text(
                "مرحباً\n"
                "أنا 811\n"
                "اختبر الاتصال بالذكاء الاصطناعي"
            ),
            font_name=ARABIC_FONT,
            font_size="17sp",
            size_hint_y=None,
            halign="center",
            valign="top",
            padding=(
                dp(10),
                dp(10)
            ),
            markup=False
        )

        self.output_label.bind(
            width=self.update_output_width
        )

        self.output_label.bind(
            texture_size=self.update_output_height
        )

        self.scroll.add_widget(
            self.output_label
        )

        main_layout.add_widget(
            self.scroll
        )

        # =====================================================
        # زر اختبار الذكاء الاصطناعي
        # =====================================================

        self.speak_btn = Button(
            text=fix_text(
                "اختبار الذكاء الاصطناعي"
            ),
            font_name=ARABIC_FONT,
            font_size="18sp",
            size_hint_y=None,
            height=dp(60),
            markup=False
        )

        self.speak_btn.bind(
            on_press=self.on_speak_click
        )

        main_layout.add_widget(
            self.speak_btn
        )

        # =====================================================
        # الحالة الابتدائية
        # =====================================================

        self.set_state(
            "ready",
            "النظام جاهز",
            (
                0.2,
                0.6,
                1.0,
                1.0
            )
        )

        return main_layout

    # =====================================================
    # حجم النص
    # =====================================================

    def update_output_width(
        self,
        instance,
        width
    ):

        instance.text_size = (
            max(
                width - dp(20),
                dp(80)
            ),
            None
        )

    def update_output_height(
        self,
        instance,
        texture_size
    ):

        instance.height = (
            texture_size[1]
            + dp(30)
        )

    # =====================================================
    # حالات المساعد
    # =====================================================

    def set_state(
        self,
        state,
        message="",
        color=(
            0.2,
            0.6,
            1.0,
            1.0
        )
    ):

        self.status_circle.set_color(
            color
        )

        if state == "ready":

            status = "جاهز"

        elif state == "thinking":

            status = "جاري التفكير..."

        elif state == "speaking":

            status = "تم استلام الرد"

        elif state == "error":

            status = "حدث خطأ"

        elif state == "busy":

            status = "جارٍ التنفيذ..."

        else:

            status = "جاهز"

        self.status_label.text = fix_text(
            status
        )

        if message:

            self.output_label.text = fix_text(
                message
            )

            self.scroll.scroll_y = 1

    # =====================================================
    # الضغط على الزر
    # =====================================================

    def on_speak_click(
        self,
        instance
    ):

        if self.processing:
            return

        groq_key = (
            self.key_input.text.strip()
        )

        if not groq_key:

            self.set_state(
                "error",
                "يرجى إدخال مفتاح Groq API",
                (
                    0.9,
                    0.2,
                    0.2,
                    1.0
                )
            )

            return

        self.processing = True

        self.speak_btn.disabled = True

        self.set_state(
            "thinking",
            "جاري الاتصال بالذكاء الاصطناعي...",
            (
                1.0,
                0.6,
                0.0,
                1.0
            )
        )

        threading.Thread(
            target=self.process_ai_request,
            args=(groq_key,),
            daemon=True
        ).start()

    # =====================================================
    # طلب الذكاء الاصطناعي
    # =====================================================

    def process_ai_request(
        self,
        groq_key
    ):

        user_prompt = "السلام عليكم"

        try:

            print("=" * 50)
            print("811 AI TEST START")
            print("Prompt:", user_prompt)
            print("Groq key received:", bool(groq_key))

            self.ai_engine.groq_key = groq_key

            response = (
                self.ai_engine.get_response(
                    user_prompt
                )
            )

            print("AI response:", repr(response))

            if not response:

                response = (
                    "لم يتم استلام رد من الذكاء الاصطناعي."
                )

            self.update_success(
                user_prompt,
                response
            )

        except Exception as e:

            # مهم جداً لمعرفة الخطأ الحقيقي في Logcat
            print("=" * 50)
            print("811 AI ERROR")
            print("Exception type:", type(e).__name__)
            print("Exception:", repr(e))
            print("Exception text:", str(e))
            print("=" * 50)

            self.update_error(
                "تعذر الاتصال بمحرك الذكاء الاصطناعي\n\n"
                + type(e).__name__
                + ": "
                + str(e)
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
            + str(response)
        )

        self.set_state(
            "speaking",
            message,
            (
                0.2,
                0.8,
                0.2,
                1.0
            )
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
            message,
            (
                0.9,
                0.2,
                0.2,
                1.0
            )
        )


# =========================================================
# تشغيل التطبيق
# =========================================================

if __name__ == "__main__":
    VoiceAssistantApp().run()
