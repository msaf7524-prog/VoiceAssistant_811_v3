import os
import time
import requests
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.clock import Clock
from kivy.utils import platform

# تحديد خط عربي مدمج في أندرويد لحل مشكلة المربعات ()
ARABIC_FONT = None
if platform == 'android':
    font_paths = [
        "/system/fonts/NotoNaskhArabic-Regular.ttf",
        "/system/fonts/NotoSansArabic-Regular.ttf",
        "/system/fonts/DroidSansArabic.ttf"
    ]
    for p in font_paths:
        if os.path.exists(p):
            ARABIC_FONT = p
            break

# استدعاء مكتبات الأندرويد لربط العتاد عبر PyJnius
if platform == 'android':
    from jnius import autoclass, PythonJavaClass, java_method
    
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Context = autoclass('android.content.Context')
    Intent = autoclass('android.content.Intent')
    SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
    RecognizerIntent = autoclass('android.speech.RecognizerIntent')
    TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
    Locale = autoclass('java.util.Locale')
    AudioManager = autoclass('android.media.AudioManager')
    PowerManager = autoclass('android.os.PowerManager')
    Bundle = autoclass('android.os.Bundle')

    # فئة لتشغيل الأوامر داخل Android Main UI Thread لمنع العطل
    class RunnableTask(PythonJavaClass):
        __javainterfaces__ = ['java/lang/Runnable']

        def __init__(self, func):
            super().__init__()
            self.func = func

        @java_method('()V')
        def run(self):
            self.func()

    def run_on_ui_thread(func):
        PythonActivity.mActivity.runOnUiThread(RunnableTask(func))

    # 1. مستمع الاستماع مع خاصية التعافي وقاطع الحديث
    class SpeechListener(PythonJavaClass):
        __javainterfaces__ = ['android/speech/RecognitionListener']

        def __init__(self, app):
            super().__init__()
            self.app = app

        @java_method('(Landroid/os/Bundle;)V')
        def onReadyForSpeech(self, params):
            Clock.schedule_once(lambda dt: self.app.update_status("جاري الإنصات..."))

        @java_method('()V')
        def onBeginningOfSpeech(self): pass

        @java_method('(F)V')
        def onRmsChanged(self, rmsdB): pass

        @java_method('([B)V')
        def onBufferReceived(self, buffer): pass

        @java_method('()V')
        def onEndOfSpeech(self): pass

        @java_method('(I)V')
        def onError(self, error):
            Clock.schedule_once(lambda dt: self.app.restart_listening(), 1.5)

        @java_method('(Landroid/os/Bundle;)V')
        def onResults(self, results):
            matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            if matches and matches.size() > 0:
                text = matches.get(0)
                Clock.schedule_once(lambda dt: self.app.handle_user_input(text))
            else:
                Clock.schedule_once(lambda dt: self.app.restart_listening(), 0.5)

        @java_method('(Landroid/os/Bundle;)V')
        def onPartialResults(self, partialResults):
            matches = partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            if matches and matches.size() > 0:
                text = matches.get(0).lower()
                Clock.schedule_once(lambda dt: self.app.check_barge_in(text))

        @java_method('(ILandroid/os/Bundle;)V')
        def onEvent(self, eventType, params): pass

    # 2. مستمع انتهاء كلام المساعد
    class TTSListener(PythonJavaClass):
        __javainterfaces__ = ['android/speech/tts/UtteranceProgressListener']

        def __init__(self, app):
            super().__init__()
            self.app = app

        @java_method('(Ljava/lang/String;)V')
        def onStart(self, utteranceId):
            self.app.is_speaking = True

        @java_method('(Ljava/lang/String;)V')
        def onDone(self, utteranceId):
            self.app.is_speaking = False
            Clock.schedule_once(lambda dt: self.app.restart_listening())

        @java_method('(Ljava/lang/String;)V')
        def onError(self, utteranceId):
            self.app.is_speaking = False
            Clock.schedule_once(lambda dt: self.app.restart_listening())

    # 3. تهيئة محرك النطق
    class TTSInitListener(PythonJavaClass):
        __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']

        def __init__(self, app):
            super().__init__()
            self.app = app

        @java_method('(I)V')
        def onInit(self, status):
            if status == TextToSpeech.SUCCESS:
                self.app.tts.setLanguage(Locale("ar"))
                self.app.tts.setOnUtteranceProgressListener(TTSListener(self.app))


class VoiceAssistantApp(App):
    def build(self):
        # 🔑 مفاتيح API الخاصة بك:
        self.gemini_api_key = "AQ.Ab8RN6KKUg...sCwDeoSBpLg" # مفتاح Gemini الأول والأحدث
        self.groq_api_key ="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"            # مفتاح Groq الاحتياطي
        
        self.is_speaking = False
        self.is_6hour_active = False
        self.remaining_seconds = 6 * 3600
        self.wake_lock = None
        self.speech_recognizer = None
        self.tts = None
        self.audio_manager = None

        # التصميم الرئيسي
        root = FloatLayout()

        # العنوان الرئيسي
        title_label = Label(
            text="VOICE ASSISTANT 811",
            font_size='22sp',
            bold=True,
            color=(1, 1, 1, 1),
            pos_hint={'center_x': 0.5, 'top': 0.96},
            size_hint=(1, 0.08)
        )
        root.add_widget(title_label)

        # نص الحالة الوسطى
        self.status_label = Label(
            text="في انتظار مناداة [811] أو [يا مساعد]...",
            font_size='16sp',
            font_name=ARABIC_FONT,
            color=(0.3, 0.7, 1, 1),
            pos_hint={'center_x': 0.5, 'center_y': 0.7},
            size_hint=(0.9, 0.1)
        )
        root.add_widget(self.status_label)

        # منطقة المحادثة النصية (Chat Log)
        scroll = ScrollView(
            pos_hint={'center_x': 0.5, 'center_y': 0.38},
            size_hint=(0.9, 0.45)
        )
        self.chat_label = Label(
            text="",
            font_size='15sp',
            font_name=ARABIC_FONT,
            color=(0.9, 0.9, 0.9, 1),
            size_hint_y=None,
            halign='right',
            valign='top'
        )
        self.chat_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        self.chat_label.bind(width=lambda instance, value: setattr(instance, 'text_size', (value, None)))
        scroll.add_widget(self.chat_label)
        root.add_widget(scroll)

        # شريط الأزرار السفلي
        bottom_bar = BoxLayout(
            orientation='horizontal',
            size_hint=(1, 0.1),
            pos_hint={'x': 0, 'y': 0},
            padding=[15, 10, 15, 10],
            spacing=10
        )

        # الزر الأول: تفعيل 6 ساعات
        self.btn_6hours = Button(
            text="تفعيل 6 ساعات",
            font_name=ARABIC_FONT,
            size_hint=(0.65, 1),
            background_normal='',
            background_color=(0.0, 0.47, 0.84, 1),
            font_size='15sp',
            bold=True
        )
        self.btn_6hours.bind(on_press=self.toggle_6hour_mode)

        # الزر الثاني: الإعدادات
        self.btn_settings = Button(
            text="الإعدادات",
            font_name=ARABIC_FONT,
            size_hint=(0.35, 1),
            background_normal='',
            background_color=(0.17, 0.17, 0.18, 1),
            font_size='15sp',
            bold=True
        )
        self.btn_settings.bind(on_press=self.open_settings)

        bottom_bar.add_widget(self.btn_6hours)
        bottom_bar.add_widget(self.btn_settings)
        root.add_widget(bottom_bar)

        # تهيئة النظام في أندرويد
        Clock.schedule_once(lambda dt: self.init_android_system(), 1)

        return root

    def init_android_system(self):
        if platform == 'android':
            def _init():
                try:
                    activity = PythonActivity.mActivity
                    
                    # 1. إعداد الصوت والبلوتوث
                    self.audio_manager = activity.getSystemService(Context.AUDIO_SERVICE)
                    if self.audio_manager.isBluetoothA2dpOn() or self.audio_manager.isBluetoothScoAvailableOffCall():
                        self.audio_manager.startBluetoothSco()
                        self.audio_manager.setBluetoothScoOn(True)

                    # 2. قفل منع خمول المعالج (WakeLock)
                    power_manager = activity.getSystemService(Context.POWER_SERVICE)
                    self.wake_lock = power_manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Voice811::Lock")

                    # 3. تهيئة TTS والاستماع داخل Main UI Thread
                    self.tts = TextToSpeech(activity, TTSInitListener(self))
                    self.speech_recognizer = SpeechRecognizer.createSpeechRecognizer(activity)
                    self.speech_recognizer.setRecognitionListener(SpeechListener(self))
                    
                    self.restart_listening()
                except Exception as e:
                    self.update_status(f"خطأ العتاد: {str(e)}")

            run_on_ui_thread(_init)

    def update_status(self, text):
        self.status_label.text = text

    def add_to_chat(self, sender, text):
        self.chat_label.text += f"\n\n{sender}: {text}"

    def restart_listening(self):
        if platform == 'android' and self.speech_recognizer:
            def _start():
                try:
                    self.speech_recognizer.cancel()
                    intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                    intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ar-SA")
                    intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
                    self.speech_recognizer.startListening(intent)
                    self.update_status("أسمعك الآن... تفضل بسؤالك")
                except Exception as e:
                    Clock.schedule_once(lambda dt: self.restart_listening(), 2)

            run_on_ui_thread(_start)

    def check_barge_in(self, partial_text):
        if self.is_speaking and ("811" in partial_text or "توقف" in partial_text or "ثمن ميه" in partial_text):
            if platform == 'android' and self.tts:
                self.tts.stop()
            self.is_speaking = False
            self.update_status("تم إيقاف النطق! تفضل بسؤالك الجديد...")

    def handle_user_input(self, user_text):
        self.add_to_chat("أنت", user_text)
        
        if "811" in user_text or "يا مساعد" in user_text or "مساعد" in user_text:
            self.speak_out("تفضل أسمعك...")
            return

        threading.Thread(target=self.query_dual_ai, args=(user_text,)).start()

    def query_dual_ai(self, prompt):
        Clock.schedule_once(lambda dt: self.update_status("جاري التفكير والتوليد..."))
        
        system_instruction = "أنت مساعد صوتي ذكي اسمه 811. أجب بإيجاز ووضوح باللهجة العراقية أو العربية الفصحى البسيطة."
        
        # 1. Gemini (الأحدث)
        try:
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": [{"text": f"{system_instruction}\n\nالسؤال: {prompt}"}]}]
            }
            
            res = requests.post(gemini_url, json=payload, headers=headers, timeout=8)
            if res.status_code == 200:
                answer = res.json()['candidates'][0]['content']['parts'][0]['text']
                Clock.schedule_once(lambda dt: self.add_to_chat("811 (Gemini)", answer))
                Clock.schedule_once(lambda dt: self.speak_out(answer))
                return
        except Exception as e:
            print(f"Gemini API Error: {e}")

        # 2. Groq (الاحتياطي)
        try:
            groq_url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 300
            }
            
            res = requests.post(groq_url, json=payload, headers=headers, timeout=6)
            if res.status_code == 200:
                answer = res.json()['choices'][0]['message']['content']
                Clock.schedule_once(lambda dt: self.add_to_chat("811 (Groq)", answer))
                Clock.schedule_once(lambda dt: self.speak_out(answer))
                return
        except Exception as e:
            print(f"Groq API Error: {e}")

        Clock.schedule_once(lambda dt: self.speak_out("عذراً، متعذر الاتصال بالسيرفرات حالياً"))

    def speak_out(self, text):
        if platform == 'android' and self.tts:
            self.update_status("يتحدث الآن...")
            params = Bundle()
            self.tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, "811_utterance")
        else:
            self.update_status(f"نطق: {text}")

    def toggle_6hour_mode(self, instance):
        if not self.is_6hour_active:
            self.is_6hour_active = True
            if self.wake_lock and not self.wake_lock.isHeld():
                self.wake_lock.acquire()
            Clock.schedule_interval(self.update_timer, 1)
            self.btn_6hours.background_color = (0.1, 0.7, 0.3, 1)
        else:
            self.stop_6hour_mode()

    def update_timer(self, dt):
        if self.remaining_seconds > 0 and self.is_6hour_active:
            self.remaining_seconds -= 1
            hrs = self.remaining_seconds // 3600
            mins = (self.remaining_seconds % 3600) // 60
            secs = self.remaining_seconds % 60
            self.btn_6hours.text = f"نشط: {hrs:02d}:{mins:02d}:{secs:02d}"
        else:
            self.stop_6hour_mode()

    def stop_6hour_mode(self):
        self.is_6hour_active = False
        Clock.unschedule(self.update_timer)
        self.remaining_seconds = 6 * 3600
        self.btn_6hours.text = "تفعيل 6 ساعات"
        self.btn_6hours.background_color = (0.0, 0.47, 0.84, 1)
        if self.wake_lock and self.wake_lock.isHeld():
            self.wake_lock.release()

    def open_settings(self, instance):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        content.add_widget(Label(text="حساسية المايكروفون:", font_name=ARABIC_FONT))
        content.add_widget(Slider(min=0, max=100, value=80))
        btn_close = Button(text="إغلاق الإعدادات", font_name=ARABIC_FONT, size_hint=(1, 0.3))
        content.add_widget(btn_close)
        
        popup = Popup(title="إعدادات المساعد 811", title_font=ARABIC_FONT, content=content, size_hint=(0.8, 0.5))
        btn_close.bind(on_press=popup.dismiss)
        popup.open()


if __name__ == '__main__':
    VoiceAssistantApp().run()
