import os
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from ai_client import OpenAIClient


class VoiceAssistant811(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.spacing = dp(14)
        self.padding = dp(16)

        self.ai_client = OpenAIClient()
        self.tts_engine = None
        self.tts_ready = False

        self.title_label = Label(
            text="Voice Assistant 811\nPhase 5 - Speech & AI",
            font_size="22sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(95)
        )
        self.title_label.bind(size=self._sync_text_size)

        self.status_label = Label(
            text="Initializing...",
            font_size="18sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(80)
        )
        self.status_label.bind(size=self._sync_text_size)

        self.info_label = Label(
            text="System initializing...",
            font_size="16sp",
            halign="center",
            valign="middle"
        )
        self.info_label.bind(size=self._sync_text_size)

        self.api_key_input = TextInput(
            hint_text="Paste API Key here...",
            multiline=False,
            password=True,
            font_size="16sp",
            size_hint_y=None,
            height=dp(50),
            write_tab=False
        )

        self.test_ai_button = Button(
            text="Test AI & Speak",
            font_size="18sp",
            size_hint_y=None,
            height=dp(52)
        )
        self.test_ai_button.bind(on_press=self.test_ai)

        self.add_widget(self.title_label)
        self.add_widget(self.status_label)
        self.add_widget(self.info_label)
        self.add_widget(self.api_key_input)
        self.add_widget(self.test_ai_button)

        Clock.schedule_once(self._init_system, 0.5)

    def _sync_text_size(self, instance, value):
        instance.text_size = (value[0], None)

    def _init_system(self, dt):
        if platform == "android":
            self._request_permissions()
            self._init_tts()
        else:
            self.status_label.text = "Desktop Platform"

    def _request_permissions(self):
        try:
            from android.permissions import Permission, request_permissions, check_permission
            
            def permission_callback(permissions, results):
                if all(results):
                    self.status_label.text = "Microphone: GRANTED"
                else:
                    self.status_label.text = "Microphone: DENIED"

            if not check_permission(Permission.RECORD_AUDIO):
                request_permissions([Permission.RECORD_AUDIO], permission_callback)
            else:
                self.status_label.text = "Microphone: GRANTED"
        except Exception as e:
            self.status_label.text = f"Permission error: {e}"

    def _init_tts(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method

            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
            Locale = autoclass('java.util.Locale')

            class TTSOnInitListener(PythonJavaClass):
                __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']

                def __init__(self, outer):
                    super().__init__()
                    self.outer = outer

                @java_method('(I)V')
                def onInit(self, status):
                    if status == TextToSpeech.SUCCESS:
                        self.outer.tts_engine.setLanguage(Locale.US)
                        self.outer.tts_ready = True

            self.listener = TTSOnInitListener(self)
            self.tts_engine = TextToSpeech(PythonActivity.mActivity, self.listener)
        except Exception as e:
            self.info_label.text = f"TTS init error: {e}"

    def speak_text(self, text):
        if platform == "android" and self.tts_engine and self.tts_ready:
            try:
                from jnius import autoclass
                TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
                self.tts_engine.speak(text, TextToSpeech.QUEUE_FLUSH, None, None)
            except Exception as e:
                self.info_label.text = f"Speak error: {e}"

    def test_ai(self, instance):
        api_key = self.api_key_input.text.strip()
        self.ai_client.set_api_key(api_key)

        if not self.ai_client.is_ready():
            self.status_label.text = "Please paste an API key"
            return

        self.status_label.text = "Sending request to AI..."
        self.test_ai_button.disabled = True

        Clock.schedule_once(self._run_ai_test, 0.2)

    def _run_ai_test(self, dt):
        try:
            prompt = "Say hello in one short sentence."
            result = self.ai_client.ask(prompt)
            self.status_label.text = "AI Response Received"
            self.info_label.text = result
            self.speak_text(result)
        except Exception as e:
            self.status_label.text = "AI Request Failed"
            self.info_label.text = str(e)
        finally:
            self.test_ai_button.disabled = False


class VoiceAssistantApp(App):
    def build(self):
        self.title = "Voice Assistant 811"
        return VoiceAssistant811()


if __name__ == "__main__":
    VoiceAssistantApp().run()
