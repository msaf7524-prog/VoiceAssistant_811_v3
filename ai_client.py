import os
import requests

class OpenAIClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.url = "https://api.openai.com/v1/chat/completions"
        self.model = "gpt-4o-mini"

    def set_api_key(self, api_key):
        self.api_key = (api_key or "").strip()

    def is_ready(self):
        return bool(self.api_key)

    def ask(self, text):
        text = (text or "").strip()
        if not text:
            return "لم يصل أي نص."
        if not self.api_key:
            return "مفتاح OpenAI API غير موجود."

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": text}
            ]
        }

        try:
            response = requests.post(self.url, headers=headers, json=payload, timeout=60)
            if response.status_code != 200:
                try:
                    data = response.json()
                    message = data.get("error", {}).get("message", "Unknown API error")
                except Exception:
                    message = response.text
                return f"OpenAI API Error: {message}"

            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
            return "تم استلام الرد، لكن لم أتمكن من استخراج النص."

        except requests.exceptions.Timeout:
            return "انتهت مهلة الاتصال بخدمة OpenAI."
        except requests.exceptions.ConnectionError:
            return "تعذر الاتصال بالإنترنت."
        except Exception as e:
            return f"خطأ في OpenAI Bridge: {str(e)}"
