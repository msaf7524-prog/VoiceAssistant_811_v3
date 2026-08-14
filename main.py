import math
import random
import os
import re
import threading
import requests

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp

# ==========================================
# Arabic Text Shaping
# ==========================================
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_BIDI = True
except ImportError:
    HAS_BIDI = False

def clean_text(text):
    if not text: return ""
    text = str(text).replace('*', '').replace('`', '').replace('#', '')
    return re.sub(r'[\u200B-\u200D\uFEFF\u200e\u200f\u202a-\u202e\uE000-\uF8FF]', '', text).strip()

def fix_text(text):
    if not text: return ""
    cleaned = clean_text(text)
    if HAS_BIDI:
        try: return get_display(arabic_reshaper.reshape(cleaned))
        except: return cleaned
    return cleaned

if platform == "android":
    from android.runnable import run_on_ui_thread
else:
    def run_on_ui_thread(func):
        def wrapper(*args, **kwargs): return func(*args, **kwargs)
        return wrapper

# ==========================================
# Groq API Client
# ==========================================
class GroqClient:
    def __init__(self):
        self.api_key = ""
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def set_api_key(self, api_key):
        # تنظيف المفتاح من أي نصوص زائدة أو رموز كولون
        key = api_key.strip()
        if ":" in key: key = key.split(":")[-1].strip()
        self.api_key = key

    def ask(self, prompt):
        if not self.api_key: raise ValueError("مفتاح API مفقود.")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a voice assistant. Respond in short Arabic text. No formatting."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        response = requests.post(self.url, headers=headers, json=payload, timeout=20)
        if response.status_code == 401: raise ValueError("مفتاح API غير صحيح أو منتهي.")
        if response.status_code != 200: raise ValueError(f"خطأ في الاتصال: {response.status_code}")
        return response.json()["choices"][0]["message"]["content"].strip()

# ==========================================
# UI Classes (VoiceVisualizer, etc.) - [تم الإبقاء عليها كما هي]
# ==========================================
# (يمكنك استخدام الكود السابق للـ UI هنا لضمان التطابق)

# ==========================================
# Main App Logic
# ==========================================
class VoiceAssistant811(BoxLayout):
    # ... (تأكد من الاحتفاظ بجميع وظائف الـ UI السابقة) ...
    
    def _run_ai_thread(self, user_prompt):
        try:
            result = self.ai_client.ask(user_prompt)
            self.update_status("Speaking...", color=(0.1, 0.85, 0.45, 1), state="speaking")
            self.update_info(f"أنت: {user_prompt}\n\n811: {result}")
            self.speak_text(result)
        except Exception as e:
            self.update_status("خطأ", color=(1, 0.2, 0.2, 1), state="idle")
            self.update_info(str(e))
        finally:
            self.set_button_disabled(False)

# [باقي الكود كما في ملفك السابق تماماً]
