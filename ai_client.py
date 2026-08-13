import os
import re
import requests

class AIClient:
    def __init__(self, api_key=None):
        self.api_key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
        
        # رابط DeepSeek API (أو يمكنك استبداله برابط Groq)
        self.url = "https://api.deepseek.com/chat/completions"
        
        self.system_instruction = (
            "أنت مساعد صوتي ذكي واسمك 811. "
            "تحدث باللغة العربية بطلاقة وبأسلوب مختصر ومباشر ومناسب للقراءة الصوتية. "
            "يمنع منعاً باتاً استخدام الإيموجي، التشكيل الزائد، أو علامات Markdown مثل (النجوم * أو الهاشتاق #) "
            "لأن الخط المستخدم في الواجهة لا يدعمها وتظهر كمربعات غريبة."
        )
        
        self.history = [{"role": "system", "content": self.system_instruction}]

    def get_response(self, user_text):
        if not self.api_key:
            return "يرجى إدخال مفتاح API أولا."

        try:
            self.history.append({"role": "user", "content": user_text})

            if len(self.history) > 11:
                # الاحتفاظ بالنظام + اخر 10 رسائل
                self.history = [self.history[0]] + self.history[-10:]

            payload = {
                "model": "deepseek-chat",
                "messages": self.history,
                "stream": False
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            response = requests.post(self.url, json=payload, headers=headers, timeout=15)
            response_json = response.json()

            if response.status_code == 200:
                bot_reply = response_json["choices"][0]["message"]["content"]
                bot_reply = self._clean_text(bot_reply)
                self.history.append({"role": "assistant", "content": bot_reply})
                return bot_reply
            else:
                return f"خطأ في الاتصال: {response.status_code}"

        except Exception as e:
            return "خطأ في الشبكة."

    def _clean_text(self, text):
        text = re.sub(r'[*#_~`]', '', text)
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        return text.strip()

    def clear_history(self):
        # الاحتفاظ برسالة النظام فقط عند مسح السجل
        self.history = [self.history[0]]
