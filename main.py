import math
import random
import os
import re
import threading
import requests
import json

# قم بوضع مفاتيحك هنا في المتغيرات التالية
GROQ_API_KEY = "YOUR_GROQ_KEY_HERE"
GEMINI_API_KEY = "YOUR_GEMINI_KEY_HERE"

# (باقي مكتبات Kivy والـ UI كما في النسخة السابقة...)
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp

# ==========================================
# دمج ذكاء اصطناعي مزدوج (Groq + Gemini)
# ==========================================
class AIHandler:
    def __init__(self):
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    def ask_groq(self, prompt):
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(self.groq_url, headers=headers, json=payload, timeout=8)
        return response.json()["choices"][0]["message"]["content"].strip()

    def ask_gemini(self, prompt):
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(self.gemini_url, json=payload, timeout=10)
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    def get_answer(self, prompt):
        # المحاولة الأولى: Groq للسرعة
        try:
            return self.ask_groq(prompt)
        except Exception:
            # المحاولة الثانية: Gemini للدقة والموثوقية
            return self.ask_gemini(prompt)

# ==========================================
# (باقي كلاسات التطبيق والـ UI... كما هي)
# ==========================================
# استبدل self.ai_client في تطبيقك بـ self.ai_client = AIHandler()
