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

        self.title_label = Label(
            text="Voice Assistant 811\nPhase 4A Ready",
            font_size="26sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(95)
        )
        self.title_label.bind(size=self._sync_text_size)

        self.status_label = Label(
            text="Ready",
            font_size="20sp",
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(90)
        )
        self.status_label.bind(size=self._sync_text_size)

        self.info_label = Label(
            text="Android Bridge: OK\nMicrophone: OK\nOpenAI: not tested yet",
            font_size="18sp",
            halign="center",
            valign="middle"
        )
        self.info_label.bind(size=self._sync_text_size)

        self.api_key_input = TextInput(
            hint_text="Paste OpenAI API Key here...",
            multiline=False,
            password=True,
            font_size="18sp",
            size_hint_y=None,
            height=dp(52),
            write_tab=False
        )

        self.test_ai_button = Button(
            text="Test AI",
            font_size="20sp",
            size_hint_y=None,
            height=dp(56)
        )
        self.test_ai_button.bind(on_press=self.test_ai)

        self.mic_check_button = Button(
            text="Mic Check",
            font_size="20sp",
            size_hint_y=None,
            height=dp(56)
        )
        self.mic_check_button.bind(on_press=self.check_mic)

        self.add_widget(self.title_label)
        self.add_widget(self.status_label)
        self.add_widget(self.info_label)
        self.add_widget(self.api_key_input)
        self.add_widget(self.test_ai_button)
        self.add_widget(self.mic_check_button)

        Clock.schedule_once(self._startup_check, 0.3)

    def _sync_text_size(self, instance, value):
        instance.text_size = (value[0], None)

    def _startup_check(self, dt):
        lines = []
        if platform == "android":
            lines.append("Platform: Android")
            try:
                from jnius import autoclass
                Build = autoclass("android.os.Build")
                Version = autoclass("android.os.Build$VERSION")
                lines.append(f"Device: {Build.MANUFACTURER} {Build.MODEL}")
                lines.append(f"Android API: {int(Version.SDK_INT)}")
            except Exception as e:
                lines.append(f"pyjnius error: {e}")

            try:
                from android.permissions import Permission, check_permission
                mic_ok = check_permission(Permission.RECORD_AUDIO)
                lines.append(f"RECORD_AUDIO: {'GRANTED' if mic_ok else 'NOT GRANTED'}")
            except Exception:
                lines.append("RECORD_AUDIO: unavailable")
        else:
            lines.append(f"Platform: {platform}")

        self.info_label.text = "\n".join(lines)
        self.status_label.text = "Phase 4A ready"

    def check_mic(self, instance):
        self.status_label.text = "Checking microphone..."
        Clock.schedule_once(self._do_mic_check, 0.15)

    def _do_mic_check(self, dt):
        if platform != "android":
            self.status_label.text = "Mic check is for Android only"
            return

        try:
            from android.permissions import Permission, check_permission
            if check_permission(Permission.RECORD_AUDIO):
                self.status_label.text = "Microphone permission granted"
            else:
                self.status_label.text = "Microphone permission NOT granted"
        except Exception as e:
            self.status_label.text = f"Mic check error: {e}"

    def test_ai(self, instance):
        api_key = self.api_key_input.text.strip()
        self.ai_client.set_api_key(api_key)

        if not self.ai_client.is_ready():
            self.status_label.text = "Please paste an OpenAI API key"
            return

        self.status_label.text = "Sending request to OpenAI..."
        self.test_ai_button.disabled = True
        self.mic_check_button.disabled = True

        Clock.schedule_once(self._run_ai_test, 0.2)

    def _run_ai_test(self, dt):
        try:
            result = self.ai_client.ask("Reply with a short confirmation that the connection works.")
            self.status_label.text = "AI test completed"
            self.info_label.text = result
        except Exception as e:
            self.status_label.text = "AI test failed"
            self.info_label.text = str(e)
        finally:
            self.test_ai_button.disabled = False
            self.mic_check_button.disabled = False


class VoiceAssistantApp(App):
    def build(self):
        self.title = "Voice Assistant 811"
        return VoiceAssistant811()


if __name__ == "__main__":
    VoiceAssistantApp().run()
