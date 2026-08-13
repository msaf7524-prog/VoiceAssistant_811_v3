import os
import re
import requests

class AIClient:
    def __init__(self, api_key=None):
        # جلب مفتاح API من المدخلات أو متغيرات البيئة
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        
        # نقطة الاتصال الخاصة بـ Gemini 2.0 Flash
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.api_key}"
        
        # توجيه النظام الشامل للمساعد 811
        self.system_instruction = (
            "أنت مساعد صوتي ذكي واسمك 811. "
            "تحدث باللغة العربية بطلاقة وبأسلوب مختصر ومباشر ومناسب للقراءة الصوتية. "
            "يمنع منعاً باتاً استخدام الإيموجي، التشكيل الزائد، أو علامات Markdown مثل (النجوم * أو الهاشتاق #) "
            "لأن الخط المستخدم في الواجهة لا يدعمها وتظهر كمربعات غريبة. "
            "استخدم ميزة البحث المباشر دائماً للبحث في الإنترنت وإعطاء إجابات دقيقة ومحدثة عن أي سؤال يطرحه المستخدم في كافة المجالات (أخبار، طقس، معلومات عامة، أسعار، مواصفات، أحداث جارية)."
        )
        
        self.history = []

    def get_response(self, user_text):
        if not self.api_key:
            return "يرجى إدخال مفتاح Gemini API أولا."

        try:
            self.history.append({"role": "user", "parts": [{"text": user_text}]})

            if len(self.history) > 10:
                self.history = self.history[-10:]

            payload = {
                "system_instruction": {
                    "parts": [{"text": self.system_instruction}]
                },
                "contents": self.history,
                "tools": [
                    {"google_search": {}}
                ]
            }

            headers = {"Content-Type": "application/json"}
            response = requests.post(self.url, json=payload, headers=headers, timeout=15)
            response_json = response.json()

            if response.status_code == 200:
                candidates = response_json.get("candidates", [])
                if candidates:
                    bot_reply = candidates[0]["content"]["parts"][0]["text"]
                    bot_reply = self._clean_text(bot_reply)
                    self.history.append({"role": "model", "parts": [{"text": bot_reply}]})
                    return bot_reply
                else:
                    return "لم أستطع الحصول على إجابة."
            elif response.status_code == 401:
                return "خطأ: مفتاح API غير صالح. يرجى استخدام مفتاح Gemini صحيح."
            else:
                return "حدث خطأ في الاتصال بالسيرفر."

        except Exception as e:
            return "خطأ في الاتصال بالشبكة."

    def _clean_text(self, text):
        """تنظيف النص لمنع المربعات الغريبة"""
        text = re.sub(r'[*#_~`]', '', text)
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        return text.strip()

    def clear_history(self):
        self.history = []
