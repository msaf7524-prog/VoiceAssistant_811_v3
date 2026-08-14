import os
import requests
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.switch import Switch
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock

# Gemini API Endpoint & Key
GEMINI_API_KEY = os.environ.get("AQ.Ab8RN6KkUgKsAetuELPjj2IvhP6zWXTXtu8tkv3sCWDeoSBpLg", "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")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

class VoiceApp(App):
    def build(self):
        self.mic_sensitivity = 0.5
        self.bluetooth_enabled = False

        # Main Layout
        self.main_layout = BoxLayout(orientation='vertical', padding=15, spacing=10)

        # Header / Status
        self.status_label = Label(
            text="المساعد الصوتي جاهز للاستماع...",
            size_hint_y=0.2,
            font_size='18sp'
        )
        self.main_layout.add_widget(self.status_label)

        # Area for Output Text
        self.output_label = Label(
            text="سيظهر الرد هنا...",
            size_hint_y=0.5,
            text_size=(None, None),
            halign='center',
            valign='middle'
        )
        self.main_layout.add_widget(self.output_label)

        # Action Buttons
        btn_layout = BoxLayout(size_hint_y=0.15, spacing=10)
        
        self.talk_btn = Button(text="تحدث الآن 🎙️", background_color=(0.2, 0.6, 1, 1))
        self.talk_btn.bind(on_press=self.on_talk)
        btn_layout.add_widget(self.talk_btn)

        self.settings_btn = Button(text="الإعدادات ⚙️", size_hint_x=0.3)
        self.settings_btn.bind(on_press=self.open_settings)
        btn_layout.add_widget(self.settings_btn)

        self.main_layout.add_widget(btn_layout)

        return self.main_layout

    def open_settings(self, instance):
        # Settings Popup (Side / Modal Menu)
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)

        # Mic Sensitivity Controls
        content.add_widget(Label(text=f"حساسية الميكروفون: {int(self.mic_sensitivity * 100)}%"))
        sens_slider = Slider(min=0, max=1, value=self.mic_sensitivity)
        sens_slider.bind(value=self.on_sensitivity_change)
        content.add_widget(sens_slider)

        # Bluetooth Toggle
        bt_layout = BoxLayout(spacing=10)
        bt_layout.add_widget(Label(text="استخدام البلوتوث:"))
        bt_switch = Switch(active=self.bluetooth_enabled)
        bt_switch.bind(active=self.on_bluetooth_toggle)
        bt_layout.add_widget(bt_switch)
        content.add_widget(bt_layout)

        # Close Button
        close_btn = Button(text="حفظ وإغلاق", size_hint_y=0.3)
        content.add_widget(close_btn)

        popup = Popup(title="إعدادات التطبيق", content=content, size_hint=(0.85, 0.6))
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

    def on_sensitivity_change(self, instance, value):
        self.mic_sensitivity = value

    def on_bluetooth_toggle(self, instance, value):
        self.bluetooth_enabled = value

    def on_talk(self, instance):
        self.status_label.text = "جاري معالجة الطلب..."
        # محاكاة إرسال نص للـ Gemini API
        self.send_to_gemini("مرحباً، كيف يمكنك مساعدتي اليوم؟")

    def send_to_gemini(self, prompt_text):
        payload = {
            "contents": [{
                "parts": [{"text": prompt_text}]
            }]
        }
        headers = {'Content-Type': 'application/json'}

        try:
            response = requests.post(GEMINI_URL, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                reply = data['candidates'][0]['content']['parts'][0]['text']
                self.output_label.text = reply
                self.status_label.text = "تم استقبال الرد بنجاح!"
            else:
                self.output_label.text = f"خطأ في الاتصال: {response.status_code}"
                self.status_label.text = "فشل الطلب"
        except Exception as e:
            self.output_label.text = f"تعذر الاتصال بالخدمة: {str(e)}"
            self.status_label.text = "حدث خطأ"

if __name__ == '__main__':
    VoiceApp().run()
