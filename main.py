import math
import random
import os
import re
import threading
import requests

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.utils import platform, get_color_from_hex
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp

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
    # 1. إزالة علامات الماركداون مثل النجوم
    text = re.sub(r'\*+', '', str(text))
    # 2. إزالة رموز يونيكود الخفية لمنع ظهور المربعات المفرغة
    text = re.sub(r'[\uE0000-\uE007F\u200B-\u200D\uFEFF\u200e\u200f\u202a-\u202e]', '', text)
    return text.strip()

def fix_text(text):
    if not text:
        return ""
    cleaned_text = clean_text(text)
    if HAS_BIDI:
        try:
            reshaped = arabic_reshaper.reshape(cleaned_text)
            return get_display(reshaped)
        except Exception:
            return cleaned_text
    return cleaned_text

if platform == "android":
    from android.runnable import run_on_ui_thread
else:
    def run_on_ui_thread(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper

# ==========================================
# Arabic Font Helper
# ==========================================
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
# Groq API Client
# ==========================================
class GroqClient:
    def __init__(self, api_key=""):
        self.api_key = api_key.strip()
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def set_api_key(self, api_key):
        self.api_key = api_key.strip()

    @property
    def is_ready(self):
        return bool(self.api_key)

    def ask(self, prompt):
        if not self.is_ready:
            raise ValueError("Groq API key is missing.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a helpful voice assistant. Respond in the same language as the user input (Arabic or English). Keep answers short, concise, and natural for speech output."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        response = requests.post(self.url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


# ==========================================
# Animated Voice Visualizer (Glow Orb & Waves)
# ==========================================
class VoiceVisualizer(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.state = "idle"  # idle, listening, processing, speaking
        self.anim_time = 0
        self.bar_heights = [0.2, 0.4, 0.6, 0.4, 0.2]
        
        self.colors = {
            "idle": (0.2, 0.4, 0.9),       # Calm Blue
            "listening": (0.0, 0.75, 1.0),   # Vibrant Cyan
            "processing": (1.0, 0.65, 0.0),  # Golden Amber
            "speaking": (0.1, 0.85, 0.45)    # Emerald Green
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
                ring_r = base_r + pulse * dp(40)
                alpha = max(0, 1.0 - (pulse / 1.5)) * 0.35
                Color(r_col, g_col, b_col, alpha)
                Line(circle=(cx, cy, ring_r), width=dp(2))

            aura_pulse = math.sin(self.anim_time * 3) * dp(6)
            Color(r_col, g_col, b_col, 0.25)
            Ellipse(
                pos=(cx - (base_r + aura_pulse), cy - (base_r + aura_pulse)),
                size=((base_r + aura_pulse) * 2, (base_r + aura_pulse) * 2)
            )

            Color(r_col, g_col, b_col, 0.9)
            Ellipse(
                pos=(cx - base_r, cy - base_r),
                size=(base_r * 2, base_r * 2)
            )

            Color(1, 1, 1, 0.4)
            highlight_r = base_r * 0.6
            Ellipse(
                pos=(cx - highlight_r * 0.5, cy + highlight_r * 0.1),
                size=(highlight_r, highlight_r * 0.7)
            )

            bar_width = dp(6)
            gap = dp(5)
            total_w = (5 * bar_width) + (4 * gap)
            start_x = cx - (total_w / 2)
            max_bar_h = base_r * 1.1

            Color(1, 1, 1, 0.95)
            for i, h_factor in enumerate(self.bar_heights):
                bar_h = max(dp(8), max_bar_h * h_factor)
                bx = start_x + i * (bar_width + gap)
                by = cy - (bar_h / 2)
                RoundedRectangle(
                    pos=(bx, by),
                    size=(bar_width, bar_h),
                    radius=[dp(3)]
                )


# ==========================================
# Main Kivy UI Layout
# ==========================================
class VoiceAssistant811(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(14)
        self.padding = dp(20)

        with self.canvas.before:
            Color(0.07, 0.07, 0.09, 1)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.ai_client = GroqClient()
        self.tts_engine = None
        self.tts_ready = False
        self.speech_recognizer = None

        self.title_label = Label(
            text="VOICE ASSISTANT 811",
            font_size="20sp",
            bold=True,
            color=(0.9, 0.9, 0.95, 1),
            size_hint_y=None,
            height=dp(35)
        )
        self.add_widget(self.title_label)

        self.api_key_input = TextInput(
            hint_text="Paste Groq API Key here...",
            multiline=False,
            password=True,
            font_size="14sp",
            size_hint_y=None,
            height=dp(46),
            padding=[dp(12), dp(12)],
            background_color=(0.15, 0.15, 0.18, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0, 0.75, 1, 1),
            write_tab=False
        )
        self.add_widget(self.api_key_input)

        self.visualizer = VoiceVisualizer(
            size_hint=(1, 1)
        )
        self.add_widget(self.visualizer)

        self.status_label = Label(
            text="Status: Ready",
            font_size="15sp",
            bold=True,
            size_hint_y=None,
            height=dp(28),
            color=(0, 0.75, 1, 1)
        )
        self.add_widget(self.status_label)

        # إضافة ScrollView لدعم تمرير النصوص الطويلة
        self.scroll_view = ScrollView(
            size_hint=(1, None),
            height=dp(120),
            do_scroll_x=False,
            do_scroll_y=True
        )
        self.info_label = Label(
            text=fix_text("اضغط على الزر وابدأ بالتحدث..."),
            font_size="15sp",
            color=(0.8, 0.8, 0.85, 1),
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
            text="Tap to Speak",
            font_size="17sp",
            bold=True,
            size_hint_y=None,
            height=dp(54),
            background_normal="",
            background_color=(0, 0.45, 0.9, 1)
        )
        self.action_button.bind(on_press=self.on_button_click)
        self.add_widget(self.action_button)

        Clock.schedule_once(self._init_system, 0.5)

    def _update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def _update_text_size(self, instance, value):
        instance.text_size = (value[0], None)

    def _update_label_height(self, instance, value):
        instance.height = max(value[1], dp(120))

    @mainthread
    def update_status(self, text, color=(1, 1, 1, 1), state="idle"):
        self.status_label.text = str(text)
        self.status_label.color = color
        self.visualizer.set_state(state)

    @mainthread
    def update_info(self, text):
        self.info_label.text = fix_text(str(text))
        self.scroll_view.scroll_y = 1.0

    @mainthread
    def set_button_disabled(self, disabled_flag):
        self.action_button.disabled = disabled_flag
        self.action_button.background_color = (0.2, 0.2, 0.25, 1) if disabled_flag else (0, 0.45, 0.9, 1)

    def _init_system(self, dt):
        if platform == "android":
            self.request_android_permissions()
            self._init_tts()
            self._init_stt()
        else:
            self.update_status("Status: Ready (Desktop)", state="idle")
            self.update_info("System initialized.")

    def request_android_permissions(self):
        try:
            from android.permissions import request_permissions, check_permission, Permission
            def permission_callback(permissions, results):
                if all(results):
                    self.update_status("Status: Permissions Granted", color=(0, 1, 0, 1), state="idle")
                else:
                    self.update_status("Status: Permission Denied", color=(1, 0, 0, 1), state="idle")

            if not check_permission(Permission.RECORD_AUDIO):
                request_permissions([Permission.RECORD_AUDIO], permission_callback)
            else:
                self.update_status("Status: Ready", color=(0, 0.75, 1, 1), state="idle")
                self.update_info("System initialized. Press button to speak.")
        except Exception as e:
            self.update_info(f"Permission error: {e}")

    def _init_tts(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            TextToSpeech = autoclass("android.speech.tts.TextToSpeech")

            class TTSInitListener(PythonJavaClass):
                __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
                def __init__(self, outer):
                    super().__init__()
                    self.outer = outer

                @java_method("(I)V")
                def onInit(self, status):
                    if status == TextToSpeech.SUCCESS:
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
                    self.outer.update_status("Listening...", color=(0, 0.75, 1, 1), state="listening")

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
                    self.outer.update_status("Processing speech...", color=(1, 0.65, 0, 1), state="processing")

                @java_method("(I)V")
                def onError(self, error):
                    self.outer.update_status(f"STT Error code: {error}", color=(1, 0.2, 0.2, 1), state="idle")
                    self.outer.set_button_disabled(False)

                @java_method("(Landroid/os/Bundle;)V")
                def onResults(self, results):
                    SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
                    matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    if matches and matches.size() > 0:
                        spoken_text = matches.get(0)
                        self.outer.on_speech_recognized(spoken_text)
                    else:
                        self.outer.update_status("No speech heard", color=(1, 0.3, 0.3, 1), state="idle")
                        self.outer.set_button_disabled(False)

                @java_method("(Landroid/os/Bundle;)V")
                def onPartialResults(self, results):
                    pass

                @java_method("(ILandroid/os/Bundle;)V")
                def onEvent(self, eventType, params):
                    pass

            self.stt_listener = SpeechListener(self)
            self.speech_recognizer = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
            self.speech_recognizer.setRecognitionListener(self.stt_listener)
        except Exception as e:
            self.update_info(f"STT Init Error: {e}")

    def speak_text(self, text):
        if platform == "android" and self.tts_engine and self.tts_ready:
            try:
                from jnius import autoclass
                TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
                HashMap = autoclass("java.util.HashMap")
                params = HashMap()
                clean_speech_text = clean_text(text)
                self.tts_engine.speak(str(clean_speech_text), TextToSpeech.QUEUE_FLUSH, params)
            except Exception as e:
                self.update_info(f"Speak error: {e}")

    @run_on_ui_thread
    def start_listening(self):
        if platform == "android" and self.speech_recognizer:
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                RecognizerIntent = autoclass("android.speech.RecognizerIntent")

                intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)

                self.speech_recognizer.startListening(intent)
            except Exception as e:
                self.update_info(f"Start listening error: {e}")
                self.set_button_disabled(False)
        else:
            self.on_speech_recognized("مرحبا، كيف حالك؟")

    def on_button_click(self, instance):
        api_key = self.api_key_input.text.strip()
        if not api_key:
            self.update_status("Error: Paste API Key", color=(1, 0.2, 0.2, 1), state="idle")
            return

        self.ai_client.set_api_key(api_key)
        self.set_button_disabled(True)
        self.update_status("Listening...", color=(0, 0.75, 1, 1), state="listening")
        self.start_listening()

    def on_speech_recognized(self, spoken_text):
        self.update_info(f"أنت: {spoken_text}")
        self.update_status("Thinking...", color=(1, 0.65, 0, 1), state="processing")
        threading.Thread(target=self._run_ai_thread, args=(spoken_text,), daemon=True).start()

    def _run_ai_thread(self, user_prompt):
        try:
            result = self.ai_client.ask(user_prompt)
            self.update_status("Speaking...", color=(0.1, 0.85, 0.45, 1), state="speaking")
            self.update_info(f"أنت: {user_prompt}\n\nالذكاء الاصطناعي: {result}")
            self.speak_text(result)
        except Exception as e:
            self.update_status("AI Request Failed", color=(1, 0.2, 0.2, 1), state="idle")
            self.update_info(f"Error: {e}")
        finally:
            self.set_button_disabled(False)


class VoiceAssistantApp(App):
    def build(self):
        self.title = "Voice Assistant 811"
        return VoiceAssistant811()


if __name__ == "__main__":
    VoiceAssistantApp().run()
