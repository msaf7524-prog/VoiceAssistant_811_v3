import os
import requests
import threading
import time

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.switch import Switch
from kivy.clock import Clock
from kivy.properties import ListProperty, StringProperty

# وضع مفتاح Gemini API هنا مباشرة أو قراءته من البيئة
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6KkUgKsAetuELPjj2IvhP6zWXTXtu8tkv3sCWDeoSBpLg")

KV = """
<MainScreen>:
    orientation: 'vertical'
    canvas.before:
        Color:
            rgba: 0, 0, 0, 1
        Rectangle:
            pos: self.pos
            size: self.size

    # العنوان العلوي الأصلي
    Label:
        text: "VOICE ASSISTANT 811"
        font_size: '22sp'
        bold: True
        color: 1, 1, 1, 1
        size_hint_y: 0.15

    # المنطقة المركزية (الدائرة التفاعلية)
    BoxLayout:
        orientation: 'vertical'
        size_hint_y: 0.73
        padding: [20, 10]
        spacing: 15

        Widget:
            size_hint_y: 0.1

        AnchorLayout:
            anchor_x: 'center'
            anchor_y: 'center'
            size_hint_y: 0.45

            Widget:
                id: status_circle
                size_hint: None, None
                size: dp(130), dp(130)
                canvas:
                    Color:
                        rgba: root.circle_color
                    Ellipse:
                        pos: self.pos
                        size: self.size

        # نص الحالة والرد الصوتي
        Label:
            text: root.status_text
            font_size: '18sp'
            color: 0, 0.82, 1, 1
            halign: 'center'
            valign: 'middle'
            size_hint_y: 0.2

        Label:
            text: root.transcript_text
            font_size: '15sp'
            color: 0.85, 0.85, 0.85, 1
            halign: 'center'
            valign: 'middle'
            size_hint_y: 0.25

    # الشريط السفلي للأزرار (الواجهة الأصلية)
    BoxLayout:
        orientation: 'horizontal'
        size_hint_y: 0.12
        spacing: 2

        Button:
            text: root.timer_button_text
            background_normal: ''
            background_color: root.timer_button_color
            font_size: '16sp'
            bold: True
            size_hint_x: 0.65
            on_press: root.toggle_timer()

        Button:
            text: "الإعدادات"
            background_normal: ''
            background_color: 0.25, 0.25, 0.25, 1
            font_size: '16sp'
            size_hint_x: 0.35
            on_press: root.open_settings()
"""

class MainScreen(BoxLayout):
    circle_color = ListProperty([0, 0.82, 1, 1])  # السماوي الأصلي عند الجاهزية
    status_text = StringProperty("أسمعك الآن... تفضل بسؤالك")
    transcript_text = StringProperty("")
    timer_button_text = StringProperty("تفعيل 6 ساعات")
    timer_button_color = ListProperty([0, 0.47, 0.87, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_active = False
        self.remaining_seconds = 6 * 3600
        self.timer_event = None
        self.mic_sensitivity = 0.5
        self.bluetooth_enabled = False

    def toggle_timer(self):
        """تفعيل عداد الـ 6 ساعات وتشغيل الإنصات المباشر"""
        if not self.is_active:
            self.is_active = True
            self.timer_button_color = [0, 0.78, 0.32, 1]  # اللون الأخضر عند التفعيل
            self.timer_event = Clock.schedule_interval(self.update_timer, 1.0)
            self.start_ai_interaction("مرحباً بك، كيف يمكنك مساعدتي اليوم؟")
        else:
            self.is_active = False
            if self.timer_event:
                self.timer_event.cancel()
                self.timer_event = None
            self.timer_button_text = "تفعيل 6 ساعات"
            self.timer_button_color = [0, 0.47, 0.87, 1]
            self.circle_color = [0, 0.82, 1, 1]
            self.status_text = "أسمعك الآن... تفضل بسؤالك"
            self.transcript_text = ""

    def update_timer(self, dt):
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            hrs, rem = divmod(self.remaining_seconds, 3600)
            mins, secs = divmod(rem, 60)
            self.timer_button_text = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        else:
            self.toggle_timer()

    def start_ai_interaction(self, user_prompt):
        """تغيير لون الدائرة وإرسال الطلب للذكاء الاصطناعي"""
        self.circle_color = [1, 0.2, 0.2, 1]  # الدائرة الحمراء الأصلية أثناء المعالجة
        self.status_text = "جاري التفكير والتواصل مع Gemini..."
        threading.Thread(target=self.call_gemini_api, args=(user_prompt,), daemon=True).start()

    def call_gemini_api(self, prompt_text):
        """الاتصال بـ Gemini API وإصلاح خطأ 400 و 401"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [{"text": prompt_text}]
            }]
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=12)
            if response.status_code == 200:
                data = response.json()
                reply = data['candidates'][0]['content']['parts'][0]['text']
                Clock.schedule_once(lambda dt: self.update_ui_success(reply))
            elif response.status_code == 401:
                Clock.schedule_once(lambda dt: self.update_ui_error("خطأ 401: مفتاح API غير صالح أو مفقود"))
            else:
                Clock.schedule_once(lambda dt: self.update_ui_error(f"خطأ من السيرفر: {response.status_code}"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_ui_error("تعذر الاتصال بالشبكة"))

    def update_ui_success(self, reply):
        self.circle_color = [0, 0.82, 1, 1]
        self.status_text = "يتحدث الآن..."
        self.transcript_text = reply

    def update_ui_error(self, err_msg):
        self.circle_color = [1, 0.2, 0.2, 1]
        self.status_text = err_msg

    def open_settings(self):
        """نافذة الإعدادات الأصلية"""
        content = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        lbl_sens = Label(text=f"حساسية الميكروفون: {int(self.mic_sensitivity * 100)}%", size_hint_y=0.2)
        content.add_widget(lbl_sens)

        slider = Slider(min=0, max=1, value=self.mic_sensitivity, size_hint_y=0.3)
        slider.bind(value=lambda inst, val: setattr(self, 'mic_sensitivity', val))
        content.add_widget(slider)

        bt_box = BoxLayout(spacing=10, size_hint_y=0.25)
        bt_box.add_widget(Label(text="خيارات البلوتوث:"))
        bt_switch = Switch(active=self.bluetooth_enabled)
        bt_switch.bind(active=lambda inst, val: setattr(self, 'bluetooth_enabled', val))
        bt_box.add_widget(bt_switch)
        content.add_widget(bt_box)

        close_btn = Button(text="إغلاق الإعدادات", size_hint_y=0.25, background_color=(0.3, 0.3, 0.3, 1))
        content.add_widget(close_btn)

        popup = Popup(title="811 الإعدادات", content=content, size_hint=(0.85, 0.55))
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

class VoiceAssistant811App(App):
    def build(self):
        Builder.load_string(KV)
        return MainScreen()

if __name__ == '__main__':
    VoiceAssistant811App().run()
