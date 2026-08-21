import os
import threading

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
# إعداد الخط العربي
# =========================================================

FONT_PATH = "Cairo-Regular.ttf"

if os.path.exists(FONT_PATH):
    try:
        LabelBase.register(
            name="Cairo",
            fn_regular=FONT_PATH
        )
        ARABIC_FONT = "Cairo"
    except Exception as e:
        print("Font registration error:", e)
        ARABIC_FONT = "Roboto"
else:
    ARABIC_FONT = "Roboto"


def fix_text(text):
    """
    معالجة النص العربي حتى تظهر الحروف بشكل صحيح.
    """
    if text is None:
        return ""

    text = str(text)

    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception as e:
        print("Arabic text error:", e)
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

        # صلاحيات Bluetooth تختلف حسب إصدار Android.
        # نضيف ما هو متاح فقط.
        if hasattr(Permission, "BLUETOOTH"):
            permissions.append(Permission.BLUETOOTH)

        if hasattr(Permission, "BLUETOOTH_ADMIN"):
            permissions.append(Permission.BLUETOOTH_ADMIN)

        if hasattr(Permission, "BLUETOOTH_CONNECT"):
            permissions.append(Permission.BLUETOOTH_CONNECT)

        request_permissions(permissions)

    except Exception as e:
        print("Permission error:", e)


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
# التطبيق الرئيسي
# =========================================================

class VoiceAssistantApp(App):

    def build(self):

        # طلب الصلاحيات
        request_android_permissions()

        # العميل الموحد للذكاء الاصطناعي
        self.ai_engine = AIClient()

        # منع إرسال أكثر من طلب في نفس الوقت
        self.processing = False

        # =================================================
        # التصميم الرئيسي
        # =================================================

        main_layout = BoxLayout(
            orientation="vertical",
            padding=dp(15),
            spacing=dp(10)
        )

        # =================================================
        # العنوان
        # =================================================

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

        # =================================================
        # مفتاح Groq
        # =================================================

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

        # =================================================
        # مؤشر الحالة
        # =================================================

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

        # =================================================
        # نص الحالة
        # =================================================

        self.status_label = Label(
            text=fix_text("جاهز"),
            font_name=ARABIC_FONT,
            font_size="18sp",
            size_hint_y=None,
            height=dp(35)
        )

        main_layout.add_widget(
            self.status_label
        )

        # =================================================
        # منطقة الرد
        # =================================================

        self.scroll = ScrollView(
            size_hint=(1, 1)
        )

        self.output_label = Label(
            text=fix_text(
                "مرحباً، أنا 811\n"
                "اضغط على الزر لاختبار الاتصال."
            ),
            font_name=ARABIC_FONT,
            font_size="16sp",
            size_hint_y=None,
            halign="center",
            valign="top",
            padding=(dp(10), dp(10))
        )

        # التفاف النص
        self.output_label.bind(
            width=self.update_output_text_size
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

        # =================================================
        # زر التحدث / الاختبار
        # =================================================

        self.speak_btn = Button(
            text=fix_text(
                "اختبار الذكاء الاصطناعي"
            ),
            font_name=ARABIC_FONT,
            font_size="18sp",
            size_hint_y=None,
            height=dp(55)
        )

        self.speak_btn.bind(
            on_press=self.on_speak_click
        )

        main_layout.add_widget(
            self.speak_btn
        )

        # الحالة الابتدائية
        self.set_state(
            "ready",
            "النظام جاهز.",
            (0.2, 0.6, 1.0, 1.0)
        )

        return main_layout

    # =====================================================
    # ضبط حجم النص
    # =====================================================

    def update_output_text_size(
        self,
        instance,
        width
    ):
        instance.text_size = (
            max(width - dp(20), dp(50)),
            None
        )

    def update_output_height(
        self,
        instance,
        texture_size
    ):
        instance.height = texture_size[1] + dp(20)

    # =====================================================
    # حالات التطبيق
    # =====================================================

    def set_state(
        self,
        state,
        message="",
        color=(0.2, 0.6, 1.0, 1.0)
    ):

        self.status_circle.set_color(
            color
        )

        if state == "ready":

            self.status_label.text = fix_text(
                "جاهز"
            )

        elif state == "thinking":

            self.status_label.text = fix_text(
                "جاري التفكير..."
            )

        elif state == "speaking":

            self.status_label.text = fix_text(
                "تم استلام الرد"
            )

        elif state == "error":

            self.status_label.text = fix_text(
                "حدث خطأ"
            )

        elif state == "busy":

            self.status_label.text = fix_text(
                "جارٍ تنفيذ الطلب..."
            )

        else:

            self.status_label.text = fix_text(
                "جاهز"
            )

        if message:

            self.output_label.text = fix_text(
                message
            )

            self.scroll.scroll_y = 1

    # =====================================================
    # الضغط على زر الاختبار
    # =====================================================

    def on_speak_click(self, instance):

        if self.processing:
            return

        # أخذ المفتاح في خيط الواجهة قبل بدء Thread
        groq_key = self.key_input.text.strip()

        if not groq_key:

            self.set_state(
                "error",
                "يرجى إدخال مفتاح Groq API أولاً.",
                (0.9, 0.2, 0.2, 1.0)
            )

            return

        self.processing = True

        self.speak_btn.disabled = True

        self.set_state(
            "thinking",
            "جاري الاتصال بالذكاء الاصطناعي...",
            (1.0, 0.6, 0.0, 1.0)
        )

        threading.Thread(
            target=self.process_ai_request,
            args=(groq_key,),
            daemon=True
        ).start()

    # =====================================================
    # تنفيذ طلب AI
    # =====================================================

    def process_ai_request(
        self,
        groq_key
    ):

        user_prompt = "السلام عليكم"

        try:

            # نستخدم AIClient الموجود أصلًا.
            # المفتاح المدخل من المستخدم يغلب المفتاح الموجود
            # في متغيرات البيئة لهذه الجلسة.

            self.ai_engine.groq_key = (
                groq_key.strip()
            )

            response = self.ai_engine.get_response(
                user_prompt
            )

            if not response:

                response = (
                    "لم يتم استلام رد من الذكاء الاصطناعي."
                )

            self.update_success(
                user_prompt,
                response
            )

        except Exception as e:

            print("AI processing error:", e)

            self.update_error(
                "حدث خطأ أثناء معالجة الطلب."
            )

    # =====================================================
    # تحديث نجاح الطلب على Main Thread
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
            f"أنت:\n{user_prompt}\n\n"
            f"811:\n{response}"
        )

        self.set_state(
            "speaking",
            message,
            (0.2, 0.8, 0.2, 1.0)
        )

    # =====================================================
    # تحديث الخطأ على Main Thread
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
            (0.9, 0.2, 0.2, 1.0)
        )


# =========================================================
# تشغيل التطبيق
# =========================================================

if __name__ == "__main__":
    VoiceAssistantApp().run()
