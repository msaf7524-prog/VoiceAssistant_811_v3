import math
import random
import os
import re
import threading
import requests
import json

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp

# ==========================================
# 🔑 مفاتيح الـ API
# ==========================================
GROQ_API_KEY = "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"
GEMINI_API_KEY = "AQ.Ab8RN6KkUgKsAetuELPjj2IvhP6zWXTXtu8tkv3sCWDeoSBpLg"

# ==========================================
# Arabic Text Shaping & BiDi Handler
# ==========================================
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_BIDI = True
except ImportError:
    HAS_BIDI = False

def clean_text(text):
    if not text:
        return ""
    text = str(text)
    text = text.replace('*', '').replace('`', '').replace('#', '')
    text = re.sub(r'[\u200B-\u200D\uFEFF\u200e\u200f\u202a-\u202e\uE000-\uF8FF]', '', text)
    return text.strip()

def fix_text(text):
    if not text:
        return ""
    cleaned = clean_text(text)
    if HAS_BIDI:
        try:
            reshaped = arabic_reshaper.reshape(cleaned)
            return get_display(reshaped)
        except Exception:
            return cleaned
    return cleaned

if platform == "android":
    from android.runnable import run_on_ui_thread
else:
    def run_on_ui_thread(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper

def get_arabic_font():
    if platform == "android":
        possible_fonts = [
            "/system/fonts/NotoSansArabic-Regular.ttf",
            "/system/fonts/NotoNaskhArabic-Regular.ttf",
            "/system/fonts/NotoSansArabicUI-Regular.ttf",
            "/system/fonts/DroidSansArabic.ttf"
        ]
        for font_path in possible_fonts:
            if os.path.exists(font_path):
                return font_path
    return None

ARABIC_FONT = get_arabic_font()

# ==========================================
# AI Handler
# ==========================================
class AIHandler:
    def __init__(self):
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
        self.system_prompt = (
            "You are a smart and fast Arabic voice assistant named 811. "
            "Keep your responses short, natural, accurate, clear, and without markdown or special formatting."
        )

    def ask_groq(self, prompt):
        clean_key = GROQ_API_KEY.strip()
        if not clean_key or "ضع_مفتاح" in clean_key:
            raise ValueError("مفتاح Groq غير مضبوط")
        
        headers = {
            "Authorization": f"Bearer {clean_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5
        }
        response = requests.post(self.groq_url, headers=headers, json=payload, timeout=8)
        if response.status_code != 200:
            raise ValueError(f"Groq Error: {response.status_code}")
        return response.json()["choices"][0]["message"]["content"].strip()

    def ask_gemini(self, prompt):
        clean_key = GEMINI_API_KEY.strip()
        if not clean_key or "ضع_مفتاح" in clean_key:
            raise ValueError("مفتاح Gemini غير مضبوط")

        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={clean_key}"
        payload = {
            "contents": [{
                "parts": [{"text": f"{self.system_prompt}\n\nالسؤال: {prompt}"}]
            }]
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(gemini_url, headers=headers, json=payload, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"Gemini Error: {response.status_code}")
        
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    def ask(self, prompt):
        try:
            return self.ask_groq(prompt)
        except Exception:
            return self.ask_gemini(prompt)

# ==========================================
# Animated Visualizer
# ==========================================
class VoiceVisualizer(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.state = "idle"
        self.anim_time = 0
        self.bar_heights = [0.2, 0.4, 0.6, 0.4, 0.2]
        
        self.colors = {
            "idle": (0.2, 0.4, 0.9),
            "listening": (0.0, 0.75, 1.0),
            "processing": (1.0, 0.65, 0.0),
            "speaking": (0.1, 0.85, 0.45)
        }
        
        self.bind(pos=self.update_canvas, size=self.update_canvas)
        Clock.schedule_interval(self.animate, 1.0 / 30.0)

    def set_state(self, new_state):
        if new_state in self.colors:
            self.state = new_state

    def animate(self, dt):
        self.anim_time += dt
        if self.state in ("listening", "speaking"):
            mult = 1.0 if self.state == "speaking" else 0.8
            self.bar_heights = [
                0.2 + mult * 0.7 * math.sin(self.anim_time * 8 + i * 0.8)**2
                for i in range(5)
            ]
        elif self.state == "processing":
            self.bar_heights = [
                0.3 + 0.3 * math.sin(self.anim_time * 12 + i)
                for i in range(5)
            ]
        else:
            self.bar_heights = [
                0.15 + 0.1 * math.sin(self.anim_time * 2 + i)
                for i in range(5)
            ]
        self.update_canvas()

    def update_canvas(self, *args):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        base_r = min(self.width, self.height) * 0.25
        r_col, g_col, b_col = self.colors.get(self.state, (0.2, 0.4, 0.9))
        
        with self.canvas:
            for i in range(3):
                pulse = (self.anim_time * 1.5 + i * 0.5) % 1.5
                ring_r = base_r + pulse * dp(30)
                alpha = max(0, 1.0 - (pulse / 1.5)) * 0.35
                Color(r_col, g_col, b_col, alpha)
                Line(circle=(cx, cy, ring_r), width=dp(2))

            aura_pulse = math.sin(self.anim_time * 3) * dp(5)
            Color(r_col, g_col, b_col, 0.25)
            Ellipse(
                pos=(cx - (base_r + aura_pulse), cy - (base_r + aura_pulse)),
                size=((base_r + aura_pulse) * 2, (base_r + aura_pulse) * 2)
            )

            Color(r_col, g_col, b_col, 0.9)
            Ellipse(pos=(cx - base_r, cy - base_r), size=(base_r * 2, base_r * 2))

            bar_width = dp(5)
            gap = dp(4)
            total_w = (5 * bar_width) + (4 * gap)
            start_x = cx - (total_w / 2)
            max_bar_h = base_r * 1.0

            Color(1, 1, 1, 0.95)
            for i, h_factor in enumerate(self.bar_heights):
                bar_h = max(dp(6), max_bar_h * h_factor)
                bx = start_x + i * (bar_width + gap)
                by = cy - (bar_h / 2)
                RoundedRectangle(pos=(bx, by), size=(bar_width, bar_h), radius=[dp(2)])

# ==========================================
# Main UI Layout
# ==========================================
class VoiceAssistant811(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(12)
        self.padding = dp(16)

        self.listen_mode = "PASSIVE"
        self.wake_words = ["811", "ثمانية", "مساعد", "يا مساعد", "يا 811", "ثمانمئة"]
        self.active_retries = 0

        with self.canvas.before:
            Color(0.07, 0.07, 0.09, 1)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.ai_handler = AIHandler()
        self.tts_engine = None
        self.tts_ready = False
        self.speech_recognizer = None

        self.title_label = Label(
            text="VOICE ASSISTANT 811",
            font_size="18sp",
            bold=True,
            color=(0.9, 0.9, 0.95, 1),
            size_hint_y=None,
            height=dp(30)
        )
        self.add_widget(self.title_label)

        self.visualizer = VoiceVisualizer(size_hint_y=None, height=dp(180))
        self.add_widget(self.visualizer)

        self.status_label = Label(
            text=fix_text("جارٍ بدء الإنصات..."),
            font_size="14sp",
            bold=True,
            size_hint_y=None,
            height=dp(25),
            color=(0, 0.75, 1, 1)
        )
        if ARABIC_FONT:
            self.status_label.font_name = ARABIC_FONT
        self.add_widget(self.status_label)

        self.scroll_view = ScrollView(size_hint=(1, 1), do_scroll_x=False, do_scroll_y=True)
        self.info_label = Label(
            text=fix_text("قل (يا 811) أو (يا مساعد) لتفعيل المساعد تلقائياً..."),
            font_size="14sp",
            color=(0.85, 0.85, 0.9, 1),
            halign="center",
            valign="middle",
            size_hint_y=None
        )
        if ARABIC_FONT:
            self.info_label.font_name = ARABIC_FONT

        self.info_label.bind(texture_size=self._update_label_height)
        self.info_label.bind(size=self._update_text_size)
        self.scroll_view.add_widget(self.info_label)
        self.add_widget(self.scroll_view)

        self.action_button = Button(
            text=fix_text("المساعد يعمل تلقائياً (مناداة)"),
            font_size="16sp",
            bold=True,
            size_hint_y=None,
            height=dp(52),
            background_normal="",
            background_color=(0, 0.45, 0.9, 1)
        )
        if ARABIC_FONT:
            self.action_button.font_name = ARABIC_FONT
        self.action_button.bind(on_press=self.on_manual_restart)
        self.add_widget(self.action_button)

        Clock.schedule_once(self._init_system, 0.5)

    def _update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def _update_text_size(self, instance, value):
        instance.text_size = (value[0], None)

    def _update_label_height(self, instance, value):
        instance.height = max(value[1], self.scroll_view.height)

    @mainthread
    def update_status(self, text, color=(1, 1, 1, 1), state="idle"):
        self.status_label.text = fix_text(str(text))
        self.status_label.color = color
        self.visualizer.set_state(state)

    @mainthread
    def update_info(self, text):
        self.info_label.text = fix_text(str(text))
        self.scroll_view.scroll_y = 1.0

    def _init_system(self, dt):
        if platform == "android":
            self.request_android_permissions()
            self._init_tts()
            self._init_stt()
        else:
            self.update_status("جاهز (سطح المكتب)", state="idle")

    def request_android_permissions(self):
        try:
            from android.permissions import request_permissions, check_permission, Permission
            def permission_callback(permissions, results):
                if all(results):
                    self.start_passive_listening()
            if not check_permission(Permission.RECORD_AUDIO):
                request_permissions([Permission.RECORD_AUDIO], permission_callback)
            else:
                self.start_passive_listening()
        except Exception as e:
            self.update_info(f"Permission error: {e}")

    def _init_tts(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
            Locale = autoclass("java.util.Locale")

            class TTSInitListener(PythonJavaClass):
                __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
                def __init__(self, outer):
                    super().__init__()
                    self.outer = outer

                @java_method("(I)V")
                def onInit(self, status):
                    if status == TextToSpeech.SUCCESS:
                        try:
                            self.outer.tts_engine.setLanguage(Locale("ar"))
                        except Exception:
                            pass
                        self.outer.tts_ready = True

            self.listener = TTSInitListener(self)
            self.tts_engine = TextToSpeech(PythonActivity.mActivity, self.listener)
        except Exception as e:
            self.update_info(f"TTS Init Error: {e}")

    @run_on_ui_thread
    def _init_stt(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")

            class SpeechListener(PythonJavaClass):
                __javainterfaces__ = ["android/speech/RecognitionListener"]

                def __init__(self, outer):
                    super().__init__()
                    self.outer = outer

                @java_method("(Landroid/os/Bundle;)V")
                def onReadyForSpeech(self, params):
                    if self.outer.listen_mode == "ACTIVE":
                        self.outer.update_status("أسمعك الآن... تفضل بسؤالك", color=(0, 0.85, 0.45, 1), state="listening")
                    else:
                        self.outer.update_status("في انتظار مناداة (811) أو (يا مساعد)...", color=(0, 0.75, 1, 1), state="idle")

                @java_method("()V")
                def onBeginningOfSpeech(self):
                    pass

                @java_method("(F)V")
                def onRmsChanged(self, rmsdB):
                    pass

                @java_method("([B)V")
                def onBufferReceived(self, buffer):
                    pass

                @java_method("()V")
                def onEndOfSpeech(self):
                    pass

                @java_method("(I)V")
                def onError(self, error):
                    if self.outer.listen_mode == "ACTIVE" and self.outer.active_retries < 2:
                        self.outer.active_retries += 1
                        Clock.schedule_once(lambda dt: self.outer.start_listening_intent(), 0.5)
                    else:
                        self.outer.active_retries = 0
                        Clock.schedule_once(lambda dt: self.outer.start_passive_listening(), 0.5)

                @java_method("(Landroid/os/Bundle;)V")
                def onResults(self, results):
                    SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
                    matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    if matches and matches.size() > 0:
                        text = matches.get(0)
                        self.outer.handle_speech_results(text)
                    else:
                        self.outer.restart_listening_loop()

                @java_method("(Landroid/os/Bundle;)V")
                def onPartialResults(self, results):
                    pass

                @java_method("(ILandroid/os/Bundle;)V")
                def onEvent(self, eventType, params):
                    pass

            self.stt_listener = SpeechListener(self)
            self.speech_recognizer = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
            self.speech_recognizer.setRecognitionListener(self.stt_listener)
            self.start_passive_listening()
        except Exception as e:
            self.update_info(f"STT Init Error: {e}")

    def speak_text(self, text, on_complete_callback=None):
        clean_speech_text = clean_text(text)
        if platform == "android" and self.tts_engine and self.tts_ready:
            try:
                from jnius import autoclass
                TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
                HashMap = autoclass("java.util.HashMap")
                params = HashMap()
                self.tts_engine.speak(str(clean_speech_text), TextToSpeech.QUEUE_FLUSH, params)
                
                # تقدير زمني دقيق لطول الكلام لحين انتهاء النطق قبل فتح الميكروفون
                words_count = len(clean_speech_text.split())
                duration = max(1.8, words_count * 0.35)
                
                if on_complete_callback:
                    Clock.schedule_once(lambda dt: on_complete_callback(), duration)
            except Exception as e:
                self.update_info(f"Speak error: {e}")
                if on_complete_callback:
                    Clock.schedule_once(lambda dt: on_complete_callback(), 1.0)
        else:
            if on_complete_callback:
                Clock.schedule_once(lambda dt: on_complete_callback(), 1.0)

    def start_passive_listening(self):
        self.listen_mode = "PASSIVE"
        self.active_retries = 0
        self.start_listening_intent()

    def start_active_listening(self):
        self.listen_mode = "ACTIVE"
        self.start_listening_intent()

    @run_on_ui_thread
    def start_listening_intent(self):
        if platform == "android" and self.speech_recognizer:
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                RecognizerIntent = autoclass("android.speech.RecognizerIntent")

                intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ar-SA")
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ar-SA")

                self.speech_recognizer.startListening(intent)
            except Exception:
                pass

    def restart_listening_loop(self):
        self.start_passive_listening()

    def handle_speech_results(self, spoken_text):
        spoken_clean = spoken_text.lower()
        
        if self.listen_mode == "PASSIVE":
            triggered = any(word in spoken_clean for word in self.wake_words)
            if triggered:
                self.update_status("تم رصد المنادى!", color=(0, 0.85, 0.45, 1), state="speaking")
                self.update_info("811: تفضل أسمعك...")
                self.speak_text("تفضل أسمعك", on_complete_callback=self.start_active_listening)
            else:
                self.start_passive_listening()

        elif self.listen_mode == "ACTIVE":
            self.active_retries = 0
            self.update_info(f"أنت: {spoken_text}")
            self.update_status("جاري التفكير مع الذكاء الاصطناعي...", color=(1, 0.65, 0, 1), state="processing")
            threading.Thread(target=self._run_ai_thread, args=(spoken_text,), daemon=True).start()

    def _run_ai_thread(self, user_prompt):
        try:
            result = self.ai_handler.ask(user_prompt)
            self.update_status("يتحدث الآن...", color=(0.1, 0.85, 0.45, 1), state="speaking")
            self.update_info(f"أنت: {user_prompt}\n\nالذكاء الاصطناعي: {result}")
            self.speak_text(result, on_complete_callback=self.start_passive_listening)
        except Exception as e:
            self.update_status("حدث خطأ في الاتصال", color=(1, 0.2, 0.2, 1), state="idle")
            self.update_info(str(e))
            Clock.schedule_once(lambda dt: self.start_passive_listening(), 3.0)

    def on_manual_restart(self, instance):
        self.start_passive_listening()


class VoiceAssistantApp(App):
    def build(self):
        self.title = "Voice Assistant 811"
        return VoiceAssistant811()


if __name__ == "__main__":
    VoiceAssistantApp().run()
