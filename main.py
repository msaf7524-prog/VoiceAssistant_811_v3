import os
import re
import threading
import requests
from kivy.app import App
from kivy.clock import Clock, mainthread
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

# 1. إعداد الخط العربي
FONT_PATH = "Cairo-Regular.ttf"
if os.path.exists(FONT_PATH):
    LabelBase.register(name="Cairo", fn_regular=FONT_PATH)
    ARABIC_FONT = "Cairo"
else:
    ARABIC_FONT = "Roboto"

# دالة معالجة النصوص العربية لمنع الحروف المنفصلة والمربعات
def fix_text(text):
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text

# طلب صلاحيات الأندرويد
def request_android_permissions():
    if platform == "android":
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.RECORD_AUDIO,
                Permission.MODIFY_AUDIO_SETTINGS,
                Permission.BLUETOOTH,
                Permission.BLUETOOTH_CONNECT
            ])
        except Exception as e:
            print(f"Permission error: {e}")

# 2. محرك الاتصال بالذكاء الاصطناعي مع إظهار تفاصيل الخطأ
class DualAIEngine:
    def __init__(self):
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
        self.system_prompt = "أنت مساعد صوتي اسمه 811. أجب بأسلوب عربي مختصر ومباشر جداً بدون رموز."

    def get_response(self, prompt, groq_key, gemini_key=""):
        # محاولة الاتصال بـ Groq
        if groq_key and groq_key.strip():
            try:
                headers = {
                    "Authorization": f"Bearer {groq_key.strip()}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }
                res = requests.post(self.groq_url, json=payload, headers=headers, timeout=10)
                if res.status_code == 200:
                    return True, res.json()["choices"][0]["message"]["content"].strip()
                else:
                    return False, f"خطأ Groq ({res.status_code}):\n{res.text}"
            except Exception as e:
                return False, f"فشل الاتصال بـ Groq:\n{str(e)}"
        
        return False, "يرجى إدخال مفتاح Groq API Key أولاً."

# 3. دائرة مؤشر الحالة
class CircleWidget(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.color = (0.2, 0.6, 1, 1)
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def set_color(self, new_color):
        self.color = new_color
        self.update_canvas()

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.color)
            size = min(self.width, self.height)
            x = self.x + (self.width - size) / 2
            y = self.y + (self.height - size) / 2
            Ellipse(pos=(x, y), size=(size, size))

# 4. التطبيق الرئيسي
class VoiceAssistantApp(App):
    def build(self):
        request_android_permissions()
        self.ai_engine = DualAIEngine()

        main_layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))

        # العنوان
        self.title_label = Label(
            text="VOICE ASSISTANT 811",
            font_size='22sp',
            bold=True,
            size_hint_y=None,
            height=dp(40)
        )
        main_layout.add_widget(self.title_label)

        # حقل إدخال المفتاح
        self.key_input = TextInput(
            hint_text="Paste Groq API Key here...",
            multiline=False,
            password=True,
            size_hint_y=None,
            height=dp(45)
        )
        main_layout.add_widget(self.key_input)

        # دائرة الحالة
        self.indicator_layout = BoxLayout(size_hint_y=None, height=dp(100))
        self.status_circle = CircleWidget()
        self.indicator_layout.add_widget(self.status_circle)
        main_layout.add_widget(self.indicator_layout)

        # نص الحالة
        self.status_label = Label(
            text=fix_text("Ready / جاهز"),
            font_name=ARABIC_FONT,
            font_size='18sp',
            size_hint_y=None,
            height=dp(35)
        )
        main_layout.add_widget(self.status_label)

        # منطقة عرض النصوص والردود
        self.scroll = ScrollView(size_hint=(1, 1))
        self.output_label = Label(
            text=fix_text("اضغط على الزر للبدء..."),
            font_name=ARABIC_FONT,
            font_size='16sp',
            size_hint_y=None,
            halign='center',
            valign='middle'
        )
        self.output_label.bind(texture_size=self.output_label.setter('size'))
        self.scroll.add_widget(self.output_label)
        main_layout.add_widget(self.scroll)

        # زر التحدث
        self.speak_btn = Button(
            text=fix_text("Tap to Speak / اضغط للتحدث"),
            font_name=ARABIC_FONT,
            font_size='18sp',
            size_hint_y=None,
            height=dp(55)
        )
        self.speak_btn.bind(on_press=self.on_speak_click)
        main_layout.add_widget(self.speak_btn)

        return main_layout

    def set_state(self, state, message="", color=(0.2, 0.6, 1, 1)):
        self.status_circle.set_color(color)
        if state == "thinking":
            self.status_label.text = fix_text("Thinking... / جاري التفكير")
        elif state == "speaking":
            self.status_label.text = fix_text("Speaking... / يتكلم الآن")
        elif state == "error":
            self.status_label.text = fix_text("Error / خطأ في الاتصال")
        else:
            self.status_label.text = fix_text("Ready / جاهز")

        if message:
            self.output_label.text = fix_text(message)

    def on_speak_click(self, instance):
        self.set_state("thinking", message="جاري إرسال الطلب...", color=(1, 0.6, 0, 1))
        threading.Thread(target=self.process_ai_request, args=("السلام عليكم",), daemon=True).start()

    def process_ai_request(self, user_prompt):
        groq_key = self.key_input.text.strip()
        success, response = self.ai_engine.get_response(user_prompt, groq_key)

        @mainthread
        def update_ui():
            if success:
                self.set_state("speaking", message=f"أنت: {user_prompt}\n\nالذكاء الاصطناعي:\n{response}", color=(0.2, 0.8, 0.2, 1))
            else:
                self.set_state("error", message=response, color=(0.9, 0.2, 0.2, 1))

        update_ui()

if __name__ == '__main__':
    VoiceAssistantApp().run()
