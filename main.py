import os
import sys
import time
import json
import requests
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, Ellipse
from kivy.utils import platform

# مكتبات معالجة اللغة العربية
import arabic_reshaper
from bidi.algorithm import get_display

# استدعاء مكتبات أندرويد عبر Pyjnius عند التشغيل على الهاتف
if platform == 'android':
    from jnius import autoclass, PythonJavaClass, java_method
    
    Context = autoclass('android.content.Context')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    AudioManager = autoclass('android.media.AudioManager')
    Intent = autoclass('android.content.Intent')
    RecognizerIntent = autoclass('android.speech.RecognizerIntent')
    SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
    TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
    Locale = autoclass('java.util.Locale')

def fix_arabic(text):
    if not text:
        return ""
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)

# إعدادات واجهة Kivy المباشرة بنفس التصميم والألوان الأصلية
KV = '''
<MainScreen>:
    canvas.before:
        Color:
            rgba: 0.05, 0.05, 0.07, 1
        Rectangle:
            pos: self.pos,
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: [20, 40, 20, 20]
        spacing: 20

        # العنوان الرئيسي
        Label:
            text: 'VOICE ASSISTANT 811'
            font_size: '22sp'
            bold: True
            color: 1, 1, 1, 1
            size_hint_y: None
            height: '40dp'

        # منطقة المؤشر التفاعلي (Animated Visualizer Circle)
        FloatLayout:
            size_hint_y: 0.4
            
            # الدائرة الخارجيّة العميقة
            Widget:
                id: outer_circle
                size_hint: None, None
                size: '220dp', '220dp'
                pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                canvas:
                    Color:
                        rgba: root.circle_bg_color
                    Ellipse:
                        pos: self.pos
                        size: self.size

            # الدائرة الداخلية المتحركة
            Widget:
                id: inner_circle
                size_hint: None, None
                size: '140dp', '140dp'
                pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                canvas:
                    Color:
                        rgba: root.circle_main_color
                    Ellipse:
                        pos: self.pos
                        size: self.size

            # أيقونة/نقاط الحالة داخل الدائرة
            Label:
                text: '• • • •'
                font_size: '20sp'
                bold: True
                color: 1, 1, 1, 0.8
                pos_hint: {'center_x': 0.5, 'center_y': 0.5}

        # نص حالة النظام
        Label:
            text: root.status_text
            font_size: '18sp'
            bold: True
            color: root.status_color
            size_hint_y: None
            height: '30dp'

        # منطقة المحادثة والنصوص
        BoxLayout:
            orientation: 'vertical'
            spacing: 10
            size_hint_y: 0.35

            Label:
                text: root.user_text
                font_size: '16sp'
                color: 0.8, 0.8, 0.8, 1
                text_size: self.width, None
                halign: 'center'
                valign: 'middle'

            Label:
                text: root.ai_text
                font_size: '16sp'
                color: 0.9, 0.9, 0.9, 1
                text_size: self.width, None
                halign: 'center'
                valign: 'middle'

        # زر التحدث السفلي
        Button:
            text: 'Tap to Speak'
            font_size: '18sp'
            bold: True
            background_normal: ''
            background_color: 0, 0.47, 0.95, 1
            size_hint_y: None
            height: '55dp'
            on_press: root.on_tap_speak()
'''

Builder.load_string(KV)

class MainScreen(FloatLayout):
    status_text = 'Ready'
    status_color = [0, 0.7, 1, 1]  # أزرق للسكون
    circle_main_color = [0.12, 0.3, 0.7, 1]
    circle_bg_color = [0.08, 0.15, 0.3, 0.4]

    user_text = ''
    ai_text = ''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.groq_api_key = "YOUR_GROQ_API_KEY_HERE"
        self.gemini_api_key = "YOUR_GEMINI_API_KEY_HERE"
        self.is_listening = False
        
        # تفعيل إعدادات الصوت والبلوتوث عند الإقلاع
        Clock.schedule_once(lambda dt: self.init_android_audio(), 1)

    def init_android_audio(self):
        """إعداد قناة الصوت للبلوتوث ومنع أندرويد من إيقاف التطبيق"""
        if platform == 'android':
            try:
                activity = PythonActivity.mActivity
                audio_manager = activity.getSystemService(Context.AUDIO_SERVICE)
                
                # توجيه المايك والسماعة إلى البلوتوث (SCO) تلقائياً عند الاتصال
                if audio_manager.isBluetoothScoAvailableOffCall():
                    audio_manager.startBluetoothSco()
                    audio_manager.setBluetoothScoOn(True)
                
                audio_manager.setMode(AudioManager.MODE_NORMAL)
                self.update_status("Permissions Granted & Audio Ready", [0, 1, 0, 1])
            except Exception as e:
                print(f"Audio Init Error: {e}")

    def update_status(self, text, color, user_msg="", ai_msg=""):
        """تحديث الحالة والواجهة التفاعلية بأمان من داخل الخيوط البرمجية"""
        def _update(dt):
            self.status_text = text
            self.status_color = color
            
            # تغيير لون الحلقة حسب الحالة (تفكير = أصفر/برتقالي، نطق = أخضر، جاهز = أزرق)
            if color == [1, 0.6, 0, 1]:  # Thinking...
                self.circle_main_color = [0.9, 0.55, 0, 1]
                self.circle_bg_color = [0.4, 0.25, 0, 0.4]
            elif color == [0, 0.8, 0.3, 1]:  # Speaking...
                self.circle_main_color = [0.1, 0.8, 0.4, 1]
                self.circle_bg_color = [0.05, 0.35, 0.15, 0.4]
            else:  # Ready / Passive
                self.circle_main_color = [0.12, 0.3, 0.7, 1]
                self.circle_bg_color = [0.08, 0.15, 0.3, 0.4]

            if user_msg:
                self.user_text = fix_arabic(user_msg)
            if ai_msg:
                self.ai_text = fix_arabic(ai_msg)

        Clock.schedule_once(_update)

    def on_tap_speak(self):
        """بدء عملية الاستماع يدوياً أو إعادة ضبط الحلقة"""
        if not self.is_listening:
            self.start_listening_process()

    def start_listening_process(self):
        self.is_listening = True
        self.update_status("Listening...", [0, 0.7, 1, 1], user_msg="أنت: جاري الاستماع...")
        
        # تشغيل خيط معالجة بالخلفية لمنع تجمد الشاشة
        threading.Thread(target=self._dummy_listen_and_process, daemon=True).start()

    def _dummy_listen_and_process(self):
        """محاكة مؤقتة للاستماع والمعالجة لاختبار الربط واستقرار الخدمة"""
        time.sleep(2)
        query = "من هو رئيس الوزراء الحالي للعراق"
        self.update_status("Thinking...", [1, 0.6, 0, 1], user_msg=f"أنت: {query}")

        # طلب الإجابة من الذكاء الاصطناعي
        response_text = self.query_ai_backend(query)
        
        self.update_status("Speaking...", [0, 0.8, 0.3, 1], ai_msg=f"الذكاء الاصطناعي: {response_text}")
        time.sleep(4)
        
        # العودة التلقائية لحالة الاستعداد
        self.is_listening = False
        self.update_status("Ready", [0, 0.7, 1, 1])

    def query_ai_backend(self, prompt):
        """المحرك الأساسي للذكاء الاصطناعي: Groq بأساس و Gemini كاحتياطي"""
        # 1. محاولة استخدام Groq API
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "أنت مساعد صوتي ذكي باسم 811. أجب بشكل مختصر ودقيق ومباشر جداً باللغة العربية."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 150
            }
            res = requests.post(url, json=payload, headers=headers, timeout=6)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"Groq failed: {e}")

        # 2. التحويل التلقائي إلى Gemini API في حال تعثر Groq
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": f"أجب بإيجاز شديد: {prompt}"}]}]
            }
            res = requests.post(url, json=payload, headers=headers, timeout=6)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            print(f"Gemini failed: {e}")

        return "حدث خطأ في الاتصال بشبكة الذكاء الاصطناعي."

class VoiceApp(App):
    def build(self):
        return MainScreen()

    def on_pause(self):
        # السماح للتطبيق بالعمل المستمر في الخلفية وعدم إغلاقه عند إغلاق الشاشة
        return True

    def on_resume(self):
        pass

if __name__ == '__main__':
    VoiceApp().run()
