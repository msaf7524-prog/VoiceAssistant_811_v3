import os
import re
import requests

class AIClient:
    def __init__(self, groq_key=None, gemini_key=None):
        # جلب المفاتيح لضمان العمل على أكثر من خادم
        self.groq_key = (groq_key or os.environ.get("GROQ_API_KEY", "")).strip()
        self.gemini_key = (gemini_key or os.environ.get("GEMINI_API_KEY", "")).strip()
        
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
        
        self.system_instruction = (
            "أنت مساعد صوتي ذكي واسمك 811. "
            "تحدث باللغة العربية بطلاقة وبأسلوب مختصر ومباشر. "
            "يمنع منعاً باتاً استخدام الإيموجي أو التشكيل أو رموز المارك داون مثل النجوم والهاشتاق."
        )
        
        self.history = [{"role": "system", "content": self.system_instruction}]

    def get_response(self, user_text):
        if not user_text or not user_text.strip():
            return "لم أسمع شيئاً، يرجى المحاولة مرة أخرى."

        # 1. المحاولة الأساسية: Groq API
        if self.groq_key:
            response = self._call_groq(user_text)
            if response and not response.startswith("ERR_"):
                return response

        # 2. الخيار الاحتياطي التلقائي: Gemini API (في حال فشل Groq أو خطأ 401)
        if self.gemini_key:
            response = self._call_gemini(user_text)
            if response and not response.startswith("ERR_"):
                return response

        return "خطأ: تعذر الاتصال بمحركات الذكاء الاصطناعي. يرجى التحقق من المفتاح والإنترنت."

    def _call_groq(self, user_text):
        try:
            temp_history = list(self.history)
            temp_history.append({"role": "user", "content": user_text})
            
            if len(temp_history) > 7:
                temp_history = [temp_history[0]] + temp_history[-6:]

            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": temp_history,
                "stream": False
            }
            headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json"
            }
            
            res = requests.post(self.groq_url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                bot_reply = res.json()["choices"][0]["message"]["content"]
                bot_reply = self._clean_text(bot_reply)
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": bot_reply})
                return bot_reply
            return f"ERR_GROQ_{res.status_code}"
        except Exception:
            return "ERR_GROQ_TIMEOUT"

    def _call_gemini(self, user_text):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": f"{self.system_instruction}\n\nسؤال المستخدم: {user_text}"}]}]
            }
            headers = {"Content-Type": "application/json"}
            
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                bot_reply = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return self._clean_text(bot_reply)
            return f"ERR_GEMINI_{res.status_code}"
        except Exception:
            return "ERR_GEMINI_TIMEOUT"

    def _clean_text(self, text):
        text = re.sub(r'[*#_~`"\'\-\[\]]', '', text)
        return text.strip()

    def clear_history(self):
        self.history = [self.history[0]]
