import os
import threading
import requests

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.metrics import dp

if platform == "android":
    from android.runnable import run_on_ui_thread
else:
    def run_on_ui_thread(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper

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
                {"role": "system", "content": "You are a helpful voice assistant. Keep answers short and natural for speech output."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        response = requests.post(self.url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


# ==========================================
# Main Kivy UI Layout
# ==========================================
class VoiceAssistant811(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(12)
        self.padding = dp(16)

        self.ai_client = GroqClient()
        self.tts_engine = None
        self.tts_ready = False
        self.speech_recognizer = None

        # Title
        self.title_label = Label(
            text="Voice Assistant 811",
            font_size="22sp",
            size_hint_y=None,
            height=dp(40)
        )
        self.add_widget(self.title_label)

        # API Key Input
        self.api_key_input = TextInput(
            hint_text="Paste Groq API Key here...",
            multiline=False,
            password=True,
            font_size="15sp",
            size_hint_y=None,
            height=dp(48),
            write_tab=False
        )
        self.add_widget(self.api_key_input)

        # Action Button
        self.action_button = Button(
            text="Press & Speak",
            font_size="18sp",
            size_hint_y=None,
            height=dp(52)
        )
        self.action_button.bind(on_press=self.on_button_click)
        self.add_widget(self.action_button)

        # Status Label
        self.status_label = Label(
            text="Status: Initializing...",
            font_size="16sp",
            size_hint_y=None,
            height=dp(30),
            color=(0, 1, 0, 1)
        )
        self.add_widget(self.status_label)

        # Info/Output Label
        self.info_label = Label(
            text="System initializing...",
            font_size="15sp",
            halign="center",
            valign="middle"
        )
        self.info_label.bind(size=self._update_text_size)
        self.add_widget(self.info_label)

        Clock.schedule_once(self._init_system, 0.5)

    def _update_text_size(self, instance, value):
        instance.text_size = (value[0], None)

    @mainthread
    def update_status(self, text, color=(1, 1, 1, 1)):
        self.status_label.text = text
        self.status_label.color = color

    @mainthread
    def update_info(self, text):
        self.info_label.text = str(text)

    @mainthread
    def set_button_disabled(self, disabled_flag):
        self.action_button.disabled = disabled_flag

    def _init_system(self, dt):
        if platform == "android":
            self.request_android_permissions()
            self._init_tts()
            self._init_stt()
        else:
            self.update_status("Status: Ready (Desktop)")
            self.update_info("System initialized.")

    def request_android_permissions(self):
        try:
            from android.permissions import request_permissions, check_permission, Permission
            def permission_callback(permissions, results):
                if all(results):
                    self.update_status("Status: Permissions Granted", color=(0, 1, 0, 1))
                else:
                    self.update_status("Status: Permission Denied", color=(1, 0, 0, 1))

            if not check_permission(Permission.RECORD_AUDIO):
                request_permissions([Permission.RECORD_AUDIO], permission_callback)
            else:
                self.update_status("Status: Ready", color=(0, 1, 0, 1))
                self.update_info("System initialized. Press button and speak.")
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
                        self.outer.tts_engine.setLanguage(Locale.US)
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
                    self.outer.update_status("Listening...", color=(0, 1, 1, 1))

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
                    self.outer.update_status("Processing speech...", color=(1, 1, 0, 1))

                @java_method("(I)V")
                def onError(self, error):
                    self.outer.update_status(f"STT Error code: {error}", color=(1, 0, 0, 1))
                    self.outer.set_button_disabled(False)

                @java_method("(Landroid/os/Bundle;)V")
                def onResults(self, results):
                    SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
                    matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    if matches and matches.size() > 0:
                        spoken_text = matches.get(0)
                        self.outer.on_speech_recognized(spoken_text)
                    else:
                        self.outer.update_status("No speech heard", color=(1, 0, 0, 1))
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
                self.tts_engine.speak(str(text), TextToSpeech.QUEUE_FLUSH, params)
            except Exception as e:
                self.update_info(f"Speak error: {e}")

    @run_on_ui_thread
    def start_listening(self):
        if platform == "android" and self.speech_recognizer:
            try:
                from jnius import autoclass
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                Intent = autoclass("android.content.Intent")
                RecognizerIntent = autoclass("android.speech.RecognizerIntent")

                intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US")

                self.speech_recognizer.startListening(intent)
            except Exception as e:
                self.update_info(f"Start listening error: {e}")
                self.set_button_disabled(False)
        else:
            self.on_speech_recognized("Hello, how are you?")

    def on_button_click(self, instance):
        api_key = self.api_key_input.text.strip()
        if not api_key:
            self.update_status("Error: Paste API Key", color=(1, 0, 0, 1))
            return

        self.ai_client.set_api_key(api_key)
        self.set_button_disabled(True)
        self.update_status("Listening...", color=(0, 1, 1, 1))
        self.start_listening()

    def on_speech_recognized(self, spoken_text):
        self.update_info(f"You: {spoken_text}")
        self.update_status("Sending to AI...", color=(1, 1, 0, 1))
        threading.Thread(target=self._run_ai_thread, args=(spoken_text,), daemon=True).start()

    def _run_ai_thread(self, user_prompt):
        try:
            result = self.ai_client.ask(user_prompt)
            self.update_status("Status: AI Response Received", color=(0, 1, 0, 1))
            self.update_info(f"You: {user_prompt}\n\nAI: {result}")
            self.speak_text(result)
        except Exception as e:
            self.update_status("Status: AI Request Failed", color=(1, 0, 0, 1))
            self.update_info(f"Error: {e}")
        finally:
            self.set_button_disabled(False)


class VoiceAssistantApp(App):
    def build(self):
        self.title = "Voice Assistant 811"
        return VoiceAssistant811()


if __name__ == "__main__":
    VoiceAssistantApp().run()
