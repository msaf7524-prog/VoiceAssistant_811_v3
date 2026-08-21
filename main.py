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
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp

# معالجة الخط العربي لضمان عدم ظهور المربعات
import arabic_reshaper
from bidi.algorithm import get_display

FONT_PATH = "Cairo-Regular.ttf"
if os.path.exists(FONT_PATH):
    LabelBase.register(name="Cairo", fn_regular=FONT_PATH)
    ARABIC_FONT = "Cairo"
else:
    ARABIC_FONT = "Roboto"

def fix_text(text):
    if not text:
        return ""
    try:
        clean = re.sub(r'[*#_~`]', '', text)
        reshaped = arabic_reshaper.reshape(clean)
        return get_display(reshaped)
    except Exception:
        return text

# طلب أذونات الأندرويد عند التشغيل
def request_android_permissions():
    if platform == 'android':
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.RECORD_AUDIO,
                Permission.INTERNET,
                Permission.ACCESS_NETWORK_STATE,
                Permission.MODIFY_AUDIO_SETTINGS
            ])
        except Exception as e:
            print(f"Permissions request failed: {e}")

# محرك الذكاء الاصطناعي المزدوَج
class DualAIEngine:
    def __init__(self):
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
        self.system_prompt = "أنت مساعد صوتي ذكي اسمه 811. أجب بأسلوب عربي مختصر ومباشر وبدون إيموجي أو رموز."

    def get_response(self, prompt, groq_key, gemini_key):
        # المحاولة الأولى: Groq
        if groq_key and groq_key.strip():
            try:
                headers = {"Authorization": f"Bearer {groq_key.strip()}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }
                res = requests.post(self.groq_url, json=payload, headers=headers, timeout=10)
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                pass

        # المحاولة الثانية: Gemini (عند فشل Groq أو خطأ 401)
        if gemini_key and gemini_key.strip():
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key.strip()}"
                payload = {"contents": [{"parts": [{"text": f"{self.system_prompt}\nالمستخدم: {prompt}"}]}]}
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
                if res.status_code == 200:
                    return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception:
                pass

        return "تعذر الاتصال بالذكاء الاصطناعي. تحقق من صحة المفتاح والتوصيل بالشبكة."

# عنصر رسم الدائرة الصوتية الملونة والنابضة
class PulsingCircle(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.color = (0.13, 0.59, 0.95, 1) # أزرق افتراضي
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def set_state_color(self, state):
        if state == "ready":
            self.color = (0.13, 0.59, 0.95, 1) # أزرق
        elif state == "listening":
            self.color = (0.0, 0.73, 0.83, 1) # أيثريوم / سماوي
        elif state == "thinking":
            self.color = (1.0, 0.6, 0.0, 1)   # برتقالي
        elif state == "speaking":
            self.color = (0.3, 0.69, 0.31, 1) # أخضر
        self.update_canvas()

    def update_canvas(self, *args):
        self.canvas.clear()
        with self.canvas:
            cx, cy = self.center_x, self.center_y
            r = min(self.width, self.height) * 0.3
            
            # دوائر الهالة الخارجية
            Color(self.color[0], self.color[1], self.color[2], 0.2)
            Ellipse(pos=(cx - r*1.3, cy - r*1.3), size=(r*2.6, r*2.6))
            
            Color(self.color[0], self.color[1], self.color[2], 0.4)
            Ellipse(pos=(cx - r*1.15, cy - r*1.15), size=(r*2.3, r*2.3))

            # الدائرة المركزية
            Color(*self.color)
            Ellipse(pos=(cx - r, cy - r), size=(r*2, r*2))

# الواجهة الرئيسية للتطبيق
class VoiceAssistantUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=dp(15), spacing=dp(10), **kwargs)
        
        # العنوان العلوي
        self.add_widget(Label(
            text="VOICE ASSISTANT 811",
            font_size='22sp',
            bold=True,
            size_hint_y=None,
            height=dp(40),
            color=(1, 1, 1, 1)
        ))

        # حقل إدخال مفتاح Groq
        self.api_input = TextInput(
            hint_text="Paste Groq API Key here...",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(45),
            background_color=(0.15, 0.15, 0.2, 1),
            foreground_color=(1, 1, 1, 1)
        )
        self.add_widget(self.api_input)

        # الدائرة النابضة للتفاعل الصوتي
        self.circle_widget = PulsingCircle(size_hint_y=0.35)
        self.add_widget(self.circle_widget)

        # نص الحالة (Ready, Listening, Thinking, Speaking)
        self.status_label = Label(
            text="Ready",
            font_size='18sp',
            bold=True,
            size_hint_y=None,
            height=dp(30),
            color=(0.13, 0.59, 0.95, 1)
        )
        self.add_widget(self.status_label)

        # منطقة المحادثة والنصوص
        self.scroll = ScrollView(size_hint=(1, 0.35))
        self.chat_label = Label(
            text=fix_text("اضغط على الزر بالأسفل للبدء..."),
            font_name=ARABIC_FONT,
            font_size='16sp',
            size_hint_y=None,
            halign='center',
            valign='middle',
            color=(0.9, 0.9, 0.9, 1)
        )
        self.chat_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        self.scroll.add_widget(self.chat_label)
        self.add_widget(self.scroll)

        # زر التحدث الرئيسي
        self.speak_btn = Button(
            text="Tap to Speak",
            font_size='18sp',
            bold=True,
            size_hint_y=None,
            height=dp(55),
            background_color=(0.1, 0.45, 0.91, 1)
        )
        self.speak_btn.bind(on_press=self.start_voice_interaction)
        self.add_widget(self.speak_btn)

        self.ai_engine = DualAIEngine()

    def set_state(self, state, status_text):
        self.status_label.text = status_text
        self.circle_widget.set_state_color(state)

    def start_voice_interaction(self, instance):
        # محاكاة بدء الاستماع واستقبال الصوت
        self.set_state("listening", "Listening...")
        self.chat_label.text = fix_text("جاري الاستماع...")
        
        # تنفيذ العملية في خلفية مستقلا لمنع تجميد الواجهة
        threading.Thread(target=self.process_pipeline).start()

    def process_pipeline(self):
        # محاكاة إدخال صوتي للمستخدم (يمكن ربطه بـ SpeechRecognizer الخاص بأندرويد)
        user_query = "السلام عليكم"
        
        Clock.schedule_once(lambda dt: self.set_state("thinking", "Thinking..."))
        Clock.schedule_once(lambda dt: setattr(self.chat_label, 'text', fix_text(f"أنت: {user_query}")))

        # جلب المفتاح المكتوب أو استخدام المفتاح الاحتياطي
        groq_key = self.api_input.text.strip()
        gemini_key = os.environ.get("GEMINI_API_KEY", "")

        # طلب الرد من الذكاء الاصطناعي
        ai_response = self.ai_engine.get_response(user_query, groq_key, gemini_key)

        # تحديث الواجهة فور استلام الرد
        Clock.schedule_once(lambda dt: self.display_response(user_query, ai_response))

    @mainthread
    def display_response(self, query, response):
        self.set_state("speaking", "Speaking...")
        full_text = f"أنت: {query}\n\nالذكاء الاصطناعي: {response}"
        self.chat_label.text = fix_text(full_text)
        
        # العودة لحالة الاستعداد بعد العرض
        Clock.schedule_once(lambda dt: self.set_state("ready", "Ready"), 4)

class VoiceAssistantApp(App):
    def build(self):
        request_android_permissions()
        return VoiceAssistantUI()

if __name__ == '__main__':
    VoiceAssistantApp().run()
