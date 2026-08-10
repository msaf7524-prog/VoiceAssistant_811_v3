import os
import threading
import requests

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout

# -----------------------------------------------------------------------------
# Groq API Client
# -----------------------------------------------------------------------------
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
        response = requests.post(self.url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


# -----------------------------------------------------------------------------
# Android Pyjnius Listeners
# -----------------------------------------------------------------------------
if platform == "android":
    from jnius import PythonJavaClass, java_method, autoclass

    class SpeechListener(PythonJavaClass):
        __javainterfaces__ = ['android/speech/RecognitionListener']

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method('(I)V')
        def onError(self, error):
            self.callback('error', error)

        @java_method('(Landroid/os/Bundle;)V')
        def onResults(self, results):
            ArrayList = autoclass('java.util.ArrayList')
            matches = results.getStringArrayList(autoclass('android.speech.SpeechRecognizer').RESULTS_RECOGNITION)
            if matches and matches.size() > 0:
                text = str(matches.get(0))
                self.callback('results', text)
            else:
                self.callback('error', 7)

        @java_method('(Landroid/os/Bundle;)V')
        def onPartialResults(self, results):
            pass

        @java_method('(ILandroid/os/Bundle;)V')
        def onEvent(self, eventType, params):
            pass

        @java_method('([B)V')
        def onBufferReceived(self, buffer):
            pass

        @java_method('()V')
        def onBeginningOfSpeech(self):
            self.callback('status', 'Listening... Speak now!')

        @java_method('(F)V')
        def onRmsChanged(self, rmsdB):
            pass

        @java_method('()V')
        def onEndOfSpeech(self):
            self.callback('status', 'Processing speech...')

        @java_method('(Landroid/os/Bundle;)V')
        def onReadyForSpeech(self, params):
            self.callback('status', 'Microphone active. Say something...')


    class TTSInitListener(PythonJavaClass):
        __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method('(I)V')
        def onInit(self, status):
            self.callback(status)


# -----------------------------------------------------------------------------
# Main UI Layout
# -----------------------------------------------------------------------------
KV_BUILDER = """
<VoiceAssistant811>:
    orientation: 'vertical'
    padding: 20
    spacing: 15

    Label:
        text: "Voice Assistant 811"
        font_size: '22sp'
        bold: True
        size_hint_y: None
        height: 40

    TextInput:
        id: api_key_input
        hint_text: "Paste Groq API Key here"
        multiline: False
        password: True
        size_hint_y: None
        height: 45

    Button:
        id: voice_button
        text: "Press & Speak"
        font_size: '18sp'
        bold: True
        size_hint_y: None
        height: 60
        on_press: root.start_voice_pipeline()

    Label:
        id: status_label
        text: "Status: Ready"
        size_hint_y: None
        height: 30
        color: 0.3, 0.8, 0.3, 1

    ScrollView:
        Label:
            id: info_label
            text: "System initialized. Press button and speak."
            size_hint_y: None
            height: self.texture_size[1]
            text_size: self.width, None
            valign: 'top'
"""

Builder.load_string(KV_BUILDER)


class VoiceAssistant811(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ai_client = GroqClient()
        self.is_listening = False
        self.processing_ai = False
        self.mic_permission_granted = False
        self.speech_ready = False
        self.tts_ready = False
        self.speech_recognizer = None
        self.tts_engine = None

        Clock.schedule_once(self._post_init, 0.5)

    def _post_init(self, dt):
        if platform == "android":
            self._check_permissions()
            self._init_speech_recognizer()
            self._init_tts()

    def _check_permissions(self):
        if platform != "android":
            return
        from android.permissions import check_permission, PERMISSION
        self.mic_permission_granted = check_permission(PERMISSION.RECORD_AUDIO)

    def request_mic_permission(self, on_complete_callback=None):
        if platform != "android":
            return
        from android.permissions import request_permissions, PERMISSION
        def callback(permissions, results):
            self.mic_permission_granted = all(results)
            if self.mic_permission_granted and on_complete_callback:
                on_complete_callback()
            elif not self.mic_permission_granted:
                self.ids.status_label.text = "Microphone permission denied"
        request_permissions([PERMISSION.RECORD_AUDIO], callback)

    def _init_speech_recognizer(self):
        if platform != "android":
            return
        try:
            from jnius import autoclass
            SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            if SpeechRecognizer.isRecognitionAvailable(activity):
                self.speech_recognizer = SpeechRecognizer.createSpeechRecognizer(activity)
                self.speech_listener = SpeechListener(self._speech_callback)
                self.speech_recognizer.setRecognitionListener(self.speech_listener)
                self.speech_ready = True
        except Exception as e:
            self.speech_ready = False

    def _init_tts(self):
        if platform != "android":
            return
        try:
            from jnius import autoclass
            TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            self.tts_listener = TTSInitListener(self._tts_init_callback)
            self.tts_engine = TextToSpeech(activity, self.tts_listener)
        except Exception:
            self.tts_ready = False

    def _tts_init_callback(self, status):
        from jnius import autoclass
        TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
        self.tts_ready = (status == TextToSpeech.SUCCESS)

    def start_voice_pipeline(self):
        api_key = self.ids.api_key_input.text.strip()
        self.ai_client.set_api_key(api_key)

        if not self.ai_client.is_ready:
            self.ids.status_label.text = "Please enter Groq API Key first."
            return

        if platform == "android" and not self.mic_permission_granted:
            self.request_mic_permission(on_complete_callback=self._start_listening)
            return

        self._start_listening()

    def _start_listening(self):
        if platform != "android":
            self.ids.status_label.text = "Voice speech is Android only."
            return

        if not self.speech_ready or not self.speech_recognizer:
            self._init_speech_recognizer()
            if not self.speech_ready:
                self.ids.status_label.text = "Speech Recognizer unavailable."
                return

        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            RecognizerIntent = autoclass('android.speech.RecognizerIntent')

            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)

            self.is_listening = True
            self.ids.voice_button.disabled = True
            self.ids.voice_button.text = "Listening..."
            self.ids.status_label.text = "Activating Microphone..."

            self.speech_recognizer.startListening(intent)
        except Exception as e:
            self._reset_button()
            self.ids.status_label.text = "Failed to start microphone."
            self.ids.info_label.text = str(e)

    def _speech_callback(self, event_type, data):
        if event_type == 'status':
            Clock.schedule_once(lambda dt: setattr(self.ids.status_label, 'text', str(data)), 0)
        elif event_type == 'results':
            Clock.schedule_once(lambda dt: self._on_speech_captured(data), 0)
        elif event_type == 'error':
            Clock.schedule_once(lambda dt: self._on_speech_error(data), 0)

    def _on_speech_captured(self, text):
        self.is_listening = False
        self.ids.info_label.text = f"You said: {text}"
        self.ids.status_label.text = "Sending to AI..."
        self._send_to_ai(text)

    def _on_speech_error(self, error_code):
        self.is_listening = False
        self._reset_button()
        errors = {
            6: "Speech timeout. Try speaking faster.",
            7: "No speech recognized. Please try again.",
            9: "Microphone permission error."
        }
        msg = errors.get(int(error_code), f"Listening error code: {error_code}")
        self.ids.status_label.text = msg

    def _send_to_ai(self, user_text):
        self.processing_ai = True
        self.ids.voice_button.text = "AI Thinking..."

        def worker():
            try:
                reply = self.ai_client.ask(user_text)
                Clock.schedule_once(lambda dt: self._on_ai_reply(user_text, reply), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_ai_error(str(e)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _on_ai_reply(self, user_text, reply):
        self.processing_ai = False
        self._reset_button()
        self.ids.status_label.text = "AI Reply Received"
        self.ids.info_label.text = f"You: {user_text}\n\nAI: {reply}"
        self.speak_text(reply)

    def _on_ai_error(self, err_msg):
        self.processing_ai = False
        self._reset_button()
        self.ids.status_label.text = "AI Request Failed"
        self.ids.info_label.text = err_msg

    def _reset_button(self):
        self.ids.voice_button.disabled = False
        self.ids.voice_button.text = "Press & Speak"

    def speak_text(self, text):
        if platform != "android" or not self.tts_engine or not self.tts_ready:
            return
        try:
            from jnius import autoclass
            TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
            Locale = autoclass('java.util.Locale')
            self.tts_engine.setLanguage(Locale.US)
            self.tts_engine.speak(text, TextToSpeech.QUEUE_FLUSH, None, "voice_811")
        except Exception:
            pass

    def cleanup_android(self):
        if platform != "android":
            return
        if self.speech_recognizer:
            try:
                self.speech_recognizer.destroy()
            except Exception:
                pass
        if self.tts_engine:
            try:
                self.tts_engine.shutdown()
            except Exception:
                pass


class VoiceAssistantApp(App):
    def build(self):
        self.root_widget = VoiceAssistant811()
        return self.root_widget

    def on_stop(self):
        if hasattr(self, "root_widget"):
            self.root_widget.cleanup_android()


if __name__ == "__main__":
    VoiceAssistantApp().run()
