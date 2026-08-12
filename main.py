import os
import re
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle

import arabic_reshaper
from bidi.algorithm import get_display

# دالة تنظيف النص من الرموز الخفية (Unicode Tags) التي تسبب ظهور المربعات
def clean_arabic_text(text):
    if not text:
        return ""
    # إزالة رموز التنسيق غير المطبوعة ورموز Unicode الخفية التي يرسلها الذكاء الاصطناعي
    text = re.sub(r'[\uE0000-\uE007F\u200B-\u200D\uFEFF\u200e\u200f\u202a-\u202e]', '', text)
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)

class VoiceAssistantUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=[15, 10, 15, 10], spacing=10, **kwargs)

        # خلفية التطبيق الداكنة
        with self.canvas.before:
            Color(0.07, 0.07, 0.09, 1)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # 1. العنوان الرئيسي
        self.add_widget(Label(
            text="VOICE ASSISTANT 811",
            font_size='22sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=35
        ))

        # 2. حقل إدخال API Key
        self.api_input = TextInput(
            hint_text="Paste Groq API Key here...",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=42,
            background_color=(0.15, 0.15, 0.18, 1),
            foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.4, 0.4, 0.4, 1),
            padding=[10, 8, 10, 8]
        )
        self.add_widget(self.api_input)

        # 3. العنصر البصري الدائري (المحاكي للتصميم السابق)
        self.visualizer = FloatLayout(size_hint=(1, None), height=220)
        with self.visualizer.canvas:
            # الحلقة الخارجية الأولى
            Color(0.08, 0.25, 0.4, 0.3)
            self.ring2 = Ellipse(size=(210, 210))
            
            # الحلقة الخارجية الثانية
            Color(0.1, 0.35, 0.55, 0.5)
            self.ring1 = Ellipse(size=(170, 170))

            # الدائرة المركزية
            self.circle_color = Color(0.0, 0.68, 0.94, 1) # أزرق فاتح
            self.core_circle = Ellipse(size=(130, 130))

            # خطوط الموجه الصوتية الداخلية (Wave lines)
            Color(1, 1, 1, 0.9)
            self.bar1 = RoundedRectangle(size=(6, 35), radius=[3])
            self.bar2 = RoundedRectangle(size=(6, 55), radius=[3])
            self.bar3 = RoundedRectangle(size=(6, 40), radius=[3])
            self.bar4 = RoundedRectangle(size=(6, 25), radius=[3])

        self.visualizer.bind(pos=self._update_visualizer, size=self._update_visualizer)
        self.add_widget(self.visualizer)

        # 4. نص حالة المساعد
        self.status_label = Label(
            text="Listening...",
            font_size='16sp',
            bold=True,
            color=(0.0, 0.75, 1, 1),
            size_hint_y=None,
            height=25
        )
        self.add_widget(self.status_label)

        # 5. حاوية عرض المحادثة المقاومة للقطع والمتداخلة مع دعم التمرير (ScrollView)
        self.scroll_view = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.chat_label = Label(
            text=clean_arabic_text("مرحباً بك! اضغط للتحدث."),
            font_size='16sp',
            color=(0.9, 0.9, 0.9, 1),
            size_hint_y=None,
            halign='center',
            valign='top'
        )
        self.chat_label.bind(texture_size=self._update_chat_height)
        self.bind(width=self._update_chat_width)
        
        self.scroll_view.add_widget(self.chat_label)
        self.add_widget(self.scroll_view)

        # 6. زر التحدث السفلي
        self.speak_button = Button(
            text="Tap to Speak",
            font_size='18sp',
            bold=True,
            size_hint_y=None,
            height=50,
            background_color=(0.0, 0.48, 0.95, 1),
            background_normal=''
        )
        self.add_widget(self.speak_button)

    def _update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def _update_visualizer(self, instance, value):
        cx = instance.x + instance.width / 2
        cy = instance.y + instance.height / 2

        self.ring2.pos = (cx - 105, cy - 105)
        self.ring1.pos = (cx - 85, cy - 85)
        self.core_circle.pos = (cx - 65, cy - 65)

        # موقع أعمدة الموجه الصوتية
        self.bar1.pos = (cx - 20, cy - 17.5)
        self.bar2.pos = (cx - 7, cy - 27.5)
        self.bar3.pos = (cx + 6, cy - 20)
        self.bar4.pos = (cx + 19, cy - 12.5)

    def _update_chat_height(self, instance, value):
        instance.height = max(value[1] + 20, self.scroll_view.height)
        Clock.schedule_once(lambda dt: setattr(self.scroll_view, 'scroll_y', 0), 0.1)

    def _update_chat_width(self, instance, value):
        self.chat_label.text_size = (value - 30, None)

    def update_chat_text(self, text):
        cleaned = clean_arabic_text(text)
        Clock.schedule_once(lambda dt: setattr(self.chat_label, 'text', cleaned))

    def update_status(self, text, color=(0.0, 0.75, 1, 1)):
        Clock.schedule_once(lambda dt: self._set_status(text, color))

    def _set_status(self, text, color):
        self.status_label.text = text
        self.status_label.color = color

class VoiceApp(App):
    def build(self):
        return VoiceAssistantUI()

if __name__ == '__main__':
    VoiceApp().run()
