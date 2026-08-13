import os
import re
import requests

class AIClient:
    def __init__(self, api_key=None):
        # جلب المفتاح
        self.api_key = (api_key or os.environ.get("GROQ_API_KEY", "")).strip()
        
        # رابط API الخاص بـ Groq
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        
        # التعليمات
        self.system_instruction = (
            "أنت مساعد صوتي ذكي واسمك 811. "
            "تحدث باللغة العربية بطلاقة وبأسلوب مختصر ومباشر. "
            "يمنع منعاً باتاً استخدام الإيموجي أو التشكيل الزائد أو رموز Markdown (مثل النجوم والهاشتاق)."
        )
        
        self.history = [{"role": "system", "content": self.system_instruction}]

    def get_response(self, user_text):
        if not self.api_key:
            return "يرجى إدخال مفتاح API في التطبيق."

        try:
            self.history.append({"role": "user", "content": user_text})

            # تقليل السجل للحفاظ على السرعة
            if len(self.history) > 7:
                self.history = [self.history[0]] + self.history[-6:]

            payload = {
                "model": "llama-3.3-70b-versatile", # نموذج سريع جداً
                "messages": self.history,
                "stream": False
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            response = requests.post(self.url, json=payload, headers=headers, timeout=15)
            
            if response.status_code == 200:
                response_json = response.json()
                bot_reply = response_json["choices"][0]["message"]["content"]
                bot_reply = self._clean_text(bot_reply)
                self.history.append({"role": "assistant", "content": bot_reply})
                return bot_reply
            else:
                return f"خطأ في الاتصال (Groq): {response.status_code}"

        except Exception as e:
            return "حدث خطأ في الاتصال بالسيرفر."

    def _clean_text(self, text):
        # إزالة أي رموز غير مرغوبة
        text = re.sub(r'[*#_~`]', '', text)
        return text.strip()

    def clear_history(self):
        self.history = [self.history[0]]
