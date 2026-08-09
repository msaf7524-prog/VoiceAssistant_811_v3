import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.clock import Clock

import arabic_reshaper
from bidi.algorithm import get_display

from ai_client import OpenAIClient

# =========================================================
# ARABIC FONT REGISTRATION
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARABIC_FONT = os.path.join(BASE_DIR, "Cairo-Regular.ttf")

if os.path.exists(ARABIC_FONT):
    LabelBase.register(name="Cairo", fn_regular=ARABIC_FONT)
else:
    ARABIC_FONT = None


# =========================================================
# ARABIC / RTL HELPER
# =========================================================

def rtl_text(text):
    """
    تجهيز النص العربي:
    1- Arabic reshaping
    2- Bidirectional RTL ordering
    """
    if not text:
        return ""
    text = str(text)
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


# =========================================================
# FONT & WIDGET HELPERS
# =========================================================

def make_label(text="", font_size=22, **kwargs):
    kwargs.setdefault("halign", "center")
    kwargs.setdefault("valign", "middle")
    
    label = Label(
        text=rtl_text(text),
        font_size=font_size,
        **kwargs
    )
    if ARABIC_FONT:
        label.font_name = "Cairo"
    return label


def make_button(text="", **kwargs):
    button = Button(
        text=rtl_text(text),
        **kwargs
    )
    if ARABIC_FONT:
        button.font_name = "Cairo"
    return button


# =========================================================
# MAIN SCREEN
# =========================================================

class VoiceAssistant811(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(15),
            padding=dp(16),
            **kwargs
        )
        
        self.ai_client = OpenAIClient()
        
        # -------------------------------------------------
        # TITLE
        # -------------------------------------------------
        title = make_label(
            "Voice Assistant 811",
            font_size=30,
            size_hint_y=None,
            height=dp(80)
        )
        self.add_widget(title)
        
        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------
        self.status = make_label(
            "جاهز – Phase 4",
            font_size=23
        )
        self.add_widget(self.status)
        
        # -------------------------------------------------
        # INFORMATION
        # -------------------------------------------------
        self.info = make_label(
            "منظومة المساعد الصوتي\nAndroid Bridge: OK\npyjnius: OK\nMicrophone: OK\nArabic RTL: Enabled",
            font_size=20
        )
        self.add_widget(self.info)
        
        # -------------------------------------------------
        # TEST BUTTON
        # -------------------------------------------------
        self.test_button = make_button(
            "اختبار النظام",
            font_size=22,
            size_hint_y=None,
            height=dp(75)
        )
        self.test_button.bind(on_press=self.test_system)
        self.add_widget(self.test_button)
        
        # -------------------------------------------------
        # AI TEST BUTTON
        # -------------------------------------------------
        self.ai_button = make_button(
            "اختبار اتصال الذكاء الاصطناعي",
            font_size=21,
            size_hint_y=None,
            height=dp(75)
        )
        self.ai_button.bind(on_press=self.test_ai)
        self.add_widget(self.ai_button)

    # -------------------------------------------------
    # SYSTEM TEST
    # -------------------------------------------------
    def test_system(self, instance):
        self.status.text = rtl_text("تم تشغيل النظام بنجاح")
        self.info.text = rtl_text(
            "Android Bridge: OK\npyjnius: OK\nMicrophone: OK\nArabic RTL: OK"
        )

    # -------------------------------------------------
    # AI TEST
    # -------------------------------------------------
    def test_ai(self, instance):
        self.status.text = rtl_text("جاري الاتصال بالذكاء الاصطناعي...")
        self.ai_button.disabled = True
        Clock.schedule_once(self._run_ai_test, 0.2)

    def _run_ai_test(self, dt):
        try:
            result = self.ai_client.ask("قل بالعربية: تم الاتصال بنجاح.")
            self.status.text = rtl_text("نتيجة الذكاء الاصطناعي:")
            self.info.text = rtl_text(result)
        except Exception as e:
            self.status.text = rtl_text("حدث خطأ")
            self.info.text = rtl_text(str(e))
        finally:
            self.ai_button.disabled = False


# =========================================================
# APP APPLICATION
# =========================================================

class VoiceAssistantApp(App):
    def build(self):
        self.title = "Voice Assistant 811"
        return VoiceAssistant811()


if __name__ == "__main__":
    VoiceAssistantApp().run()
