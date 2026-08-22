import os
import threading
import requests

# 1. تنزيل الخط العربي تلقائياً وتسجيله في Kivy قبل بناء الواجهة
FONT_PATH = "Cairo-Regular.ttf"
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/cairo/static/Cairo-Regular.ttf"

def prepare_arabic_font():
    if not os.path.exists(FONT_PATH):
        try:
            print("Downloading Arabic font...")
            res = requests.get(FONT_URL, timeout=15)
            if res.status_code == 200:
                with open(FONT_PATH, "wb") as f:
                    f.write(res.content)
                print("Arabic font downloaded successfully!")
        except Exception as e:
            print(f"Font download error: {e}")

prepare_arabic_font()

from kivy.core.text import LabelBase
if os.path.exists(FONT_PATH):
    # استبدال الخط الافتراضي بالنظام بالخط العربي
    LabelBase.register(name='Roboto', fn_regular=FONT_PATH)

import arabic_reshaper
from bidi.algorithm import get_display

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.utils import platform

from ai_client import AIClient


def fix_text(text):
    """معالجة وتعديل اتجاه النص العربي"""
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


class VoiceAssistantApp(App):
    def build(self):
        self.title = "VOICE ASSISTANT 811"
        self.ai_client = None
        self.tts = None

        # تهيئة محرك الصوت في الأندرويد
        if platform == 'android':
            self.init_android_tts()

        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)

        # حقل إدخال مفتاح Groq API
        self.api_input = TextInput(
            hint_text="Paste Groq API Key here...",
            multiline=False,
            size_hint_y=0.1
        )
        layout.add_widget(self.api_input)

        # نص حالة الاتصال
        self.status_label = Label(
            text=fix_text("جاهز"),
            font_size='20sp',
            size_hint_y=0.1
        )
        layout.add_widget(self.status_label)

        # شاشة عرض الرد النصي
        self.chat_label = Label(
            text=fix_text("انتظار الاختبار..."),
            font_size='16sp',
            size_hint_y=0.65,
            halign='center',
            valign='middle'
        )
        self.chat_label.bind(size=self.chat_label.setter('text_size'))
        layout.add_widget(self.chat_label)

        # زر اختبار الذكاء الاصطناعي
        self.btn_test = Button(
            text=fix_text("اختبار الذكاء الاصطناعي"),
            size_hint_y=0.15,
            font_size='18sp'
        )
        self.btn_test.bind(on_press=self.start_ai_test)
        layout.add_widget(self.btn_test)

        return layout

    def init_android_tts(self):
        """تهيئة محرك TextToSpeech المباشر في أندرويد"""
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
            Locale = autoclass('java.util.Locale')

            activity = PythonActivity.mActivity
            self.tts = TextToSpeech(activity, None)
            self.tts.setLanguage(Locale("ar"))
        except Exception as e:
            print(f"Android TTS Init Error: {e}")

    def speak(self, text):
        """نطق النص عبر محرك أندرويد الصوتي"""
        if platform == 'android' and self.tts:
            try:
                from jnius import autoclass
                TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
                self.tts.speak(text, TextToSpeech.QUEUE_FLUSH, None, None)
            except Exception as e:
                print(f"Speak Execution Error: {e}")

    def start_ai_test(self, instance):
        api_key = self.api_input.text.strip()
        if not api_key:
            self.status_label.text = fix_text("يرجى إدخال API Key أولاً")
            return

        self.status_label.text = fix_text("جاري التفكير...")
        self.btn_test.disabled = True

        threading.Thread(target=self._process_ai_request, args=(api_key,), daemon=True).start()

    def _process_ai_request(self, api_key):
        try:
            if not self.ai_client:
                self.ai_client = AIClient(groq_key=api_key)

            prompt = "السلام عليكم"
            response_text = self.ai_client.get_response(prompt)

            Clock.schedule_once(lambda dt: self._update_ui_and_speak(prompt, response_text))
        except Exception as e:
            Clock.schedule_once(lambda dt: self._handle_error(str(e)))

    def _update_ui_and_speak(self, prompt, response):
        self.status_label.text = fix_text("تم استقبال الرد")
        display_chat = f"أنت:\n{prompt}\n\n811:\n{response}"
        self.chat_label.text = fix_text(display_chat)
        self.btn_test.disabled = False

        # تشغيل الصوت تلقائياً فور استلام الرد
        self.speak(response)

    def _handle_error(self, error_msg):
        self.status_label.text = fix_text("حدث خطأ في الاتصال")
        self.chat_label.text = fix_text(f"الخطأ:\n{error_msg}")
        self.btn_test.disabled = False


if __name__ == "__main__":
    VoiceAssistantApp().run()
