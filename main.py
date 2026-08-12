import os
import re
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Rectangle

import arabic_reshaper
from bidi.algorithm import get_display

# دالة تنظيف النص وإعادة تشكيل اللغة العربية
def clean_and_reshape(text):
    if not text:
        return ""
    # حذف رموز Unicode الخفية والإيموجي غير المدعومة التي تسبب المربعات
    text = re.sub(r'[\uE0000-\uE007F\u200B-\u200D\uFEFF]', '', text)
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)

class VoiceAssistantUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=20, spacing=15, **kwargs)

        # 1. إعداد الخلفية الداكنة
        with self.canvas.before:
            Color(0.08, 0.08, 0.11, 1)  # لون خلفية أسود داكن
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # 2. العنوان الرئيسي
        self.add_widget(Label(
            text="VOICE ASSISTANT 811",
            font_size='22sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=35
        ))

        # 3. حقل إدخال Groq API Key بتصميم داكن
        self.api_input = TextInput(
            hint_text="Paste Groq API Key here...",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=45,
            background_color=(0.16, 0.16, 0.2, 1),
            foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.5, 0.5, 0.5, 1),
            padding=[12, 10, 12, 10]
        )
        self.add_widget(self.api_input)

        # 4. عنصر الدائرة المركزية
        self.visualizer = BoxLayout(size_hint=(1, None), height=180)
        with self.visualizer.canvas:
            Color(0.15, 0.45, 0.9, 1)  # اللون الأزرق الإفتراضي
            self.circle = Ellipse(size=(130, 130))
        self.visualizer.bind(pos=self._update_circle, size=self._update_circle)
        self.add_widget(self.visualizer)

        # 5. نص حالة المساعد (Status)
        self.status_label = Label(
            text=clean_and_reshape("Status: Ready"),
            font_size='16sp',
            bold=True,
            color=(0, 0.75, 1, 1),
            size_hint_y=None,
            height=25
        )
        self.add_widget(self.status_label)

        # 6. منطقة المحادثة مع التمرير (ScrollView)
        self.scroll_view = ScrollView(size_hint=(1, 1))
        self.chat_label = Label(
            text=clean_and_reshape("مرحباً بك! اضغط للتحدث."),
            font_size='17sp',
            color=(0.9, 0.9, 0.9, 1),
            size_hint_y=None,
            halign='center',
            valign='top'
        )
        self.chat_label.bind(texture_size=self._update_text_height)
        self.bind(width=self._update_label_width)
        self.scroll_view.add_widget(self.chat_label)
        self.add_widget(self.scroll_view)

        # 7. زر التحدث السفلي
        self.speak_button = Button(
            text="Tap to Speak",
            font_size='18sp',
            bold=True,
            size_hint_y=None,
            height=55,
            background_color=(0, 0.48, 0.95, 1),
            background_normal=''
        )
        self.add_widget(self.speak_button)

    def _update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def _update_circle(self, instance, value):
        cx = instance.x + (instance.width - 130) / 2
        cy = instance.y + (instance.height - 130) / 2
        self.circle.pos = (cx, cy)

    def _update_text_height(self, instance, value):
        instance.height = value[1] + 20
        Clock.schedule_once(lambda dt: setattr(self.scroll_view, 'scroll_y', 0), 0.1)

    def _update_label_width(self, instance, value):
        self.chat_label.text_size = (value - 40, None)

    def update_chat(self, text):
        cleaned = clean_and_reshape(text)
        Clock.schedule_once(lambda dt: setattr(self.chat_label, 'text', cleaned))

    def update_status(self, text, color=(0, 0.75, 1, 1)):
        Clock.schedule_once(lambda dt: self._set_status(text, color))

    def _set_status(self, text, color):
        self.status_label.text = clean_and_reshape(text)
        self.status_label.color = color

class VoiceApp(App):
    def build(self):
        return VoiceAssistantUI()

if __name__ == '__main__':
    VoiceApp().run()
