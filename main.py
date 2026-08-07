from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from ai_client import OpenAIClient

class VoiceAssistantApp(App):
    def build(self):
        self.ai_client = OpenAIClient()
        
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)

        self.title_label = Label(
            text="Voice Assistant 811\nStatus: Phase 4A Ready",
            font_size='20sp',
            halign='center'
        )
        layout.add_widget(self.title_label)

        self.status_label = Label(
            text="أدخل API Key واضغط اختبار الاتصال",
            font_size='14sp',
            halign='center',
            size_hint_y=None,
            height=120
        )
        layout.add_widget(self.status_label)

        self.api_input = TextInput(
            hint_text="Paste OpenAI API Key here...",
            multiline=False,
            password=True,
            size_hint_y=None,
            height=50
        )
        layout.add_widget(self.api_input)

        btn_test_ai = Button(
            text="اختبار الاتصال بالذكاء الاصطناعي (Test AI)",
            size_hint_y=None,
            height=50
        )
        btn_test_ai.bind(on_press=self.test_ai)
        layout.add_widget(btn_test_ai)

        btn_mic = Button(
            text="فحص إذن الميكروفون (Mic Check)",
            size_hint_y=None,
            height=50
        )
        btn_mic.bind(on_press=self.check_mic_permission)
        layout.add_widget(btn_mic)

        return layout

    def check_mic_permission(self, instance):
        if platform == 'android':
            from android.permissions import request_permissions, Permission, check_permission
            if check_permission(Permission.RECORD_AUDIO):
                self.status_label.text = "Microphone permission already granted."
            else:
                request_permissions([Permission.RECORD_AUDIO])
                self.status_label.text = "Requesting microphone permission..."
        else:
            self.status_label.text = "Not running on Android."

    def test_ai(self, instance):
        key = self.api_input.text.strip()
        if not key:
            self.status_label.text = "الرجاء إدخال API Key أولاً!"
            return

        self.status_label.text = "جاري الاتصال بـ OpenAI..."
        self.ai_client.set_api_key(key)
        
        result = self.ai_client.ask("قل فقط: Voice Assistant 811 متصل بنجاح.")
        self.status_label.text = f"النتيجة:\n{result}"

if __name__ == '__main__':
    VoiceAssistantApp().run()
