import os
import re
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.text import LabelBase

import arabic_reshaper
from bidi.algorithm import get_display

# تنظيف النص من الرموز الخفية والإيموجي التي تسبب ظهور المربعات المفرغة
def clean_and_reshape(text):
    if not text:
        return ""
    # إزالة رموز Unicode الخفية ورموز التنسيق غير المدعومة
    text = re.sub(r'[\uE0000-\uE007F\u200B-\u200D\uFEFF]', '', text)
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)

class VoiceAssistantUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=15, spacing=10, **kwargs)

        # 1. العنوان الرئيسي
        self.title_label = Label(
            text="VOICE ASSISTANT 811",
            font_size='22sp',
            bold=True,
            size_hint_y=None,
            height=40
        )
        self.add_widget(self.title_label)

        # 2. حقل إدخال API Key
        self.api_input = TextInput(
            hint_text="Paste Groq API Key here...",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=45
        )
        self.add_widget(self.api_input)

        # 3. نص حالة النظام (Listening, Speaking, Ready)
        self.status_label = Label(
            text=clean_and_reshape("Status: Ready"),
            font_size='16sp',
            color=(0, 0.7, 1, 1),
            size_hint_y=None,
            height=30
        )
        self.add_widget(self.status_label)

        # 4. حاوية التمرير (ScrollView) لعرض المحادثة بدون تداخل
        self.scroll_view = ScrollView(size_hint=(1, 1))
        
        self.chat_label = Label(
            text=clean_and_reshape("مرحباً بك! اضغط للتحدث."),
            font_size='18sp',
            size_hint_y=None,
            text_size=(self.width, None),
            halign='center',
            valign='top'
        )
        
        # ضبط ارتفاع Label تلقائياً حسب طول النص وضبط العرض مع الشاشة
        self.chat_label.bind(texture_size=self.update_text_height)
        self.bind(width=self.update_label_width)
        
        self.scroll_view.add_widget(self.chat_label)
        self.add_widget(self.scroll_view)

        # 5. زر التحدث الرئيسي في الأسفل
        self.speak_button = Button(
            text="Tap to Speak",
            font_size='18sp',
            bold=True,
            size_hint_y=None,
            height=60,
            background_color=(0, 0.5, 1, 1)
        )
        self.speak_button.bind(on_press=self.on_speak_click)
        self.add_widget(self.speak_button)

    def update_text_height(self, instance, value):
        instance.height = value[1] + 20
        # التمرير التلقائي لأسفل عند إضافة نص جديد
        Clock.schedule_once(lambda dt: setattr(self.scroll_view, 'scroll_y', 0), 0.1)

    def update_label_width(self, instance, value):
        self.chat_label.text_size = (value - 40, None)

    def update_chat_text(self, text):
        cleaned = clean_and_reshape(text)
        Clock.schedule_once(lambda dt: setattr(self.chat_label, 'text', cleaned))

    def update_status(self, text, color=(0, 0.7, 1, 1)):
        Clock.schedule_once(lambda dt: self._set_status(text, color))

    def _set_status(self, text, color):
        self.status_label.text = clean_and_reshape(text)
        self.status_label.color = color

    def on_speak_click(self, instance):
        # الكود الخاص بالاستماع والمعالجة الصوتية يوضع هنا
        pass

class VoiceApp(App):
    def build(self):
        return VoiceAssistantUI()

if __name__ == '__main__':
    VoiceApp().run()
