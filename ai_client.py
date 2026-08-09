import os
import requests

class OpenAIClient:
    def __init__(self, api_key=None):
        self.api_key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        self.url = "https://api.openai.com/v1/chat/completions"
        self.model = "gpt-4o-mini"

    def set_api_key(self, api_key):
        self.api_key = (api_key or "").strip()

    def is_ready(self):
        return bool(self.api_key)

    def ask(self, text):
        text = (text or "").strip()
        if not text:
            return "No input text."
        if not self.api_key:
            return "OpenAI API key is missing."

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": text}]
        }
        try:
            response = requests.post(self.url, headers=headers, json=payload, timeout=60)
            if response.status_code != 200:
                try:
                    data = response.json()
                    message = data.get("error", {}).get("message", response.text)
                except Exception:
                    message = response.text
                return f"OpenAI API Error: {message}"
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        except requests.exceptions.Timeout:
            return "OpenAI request timed out."
        except requests.exceptions.ConnectionError:
            return "No internet connection."
        except Exception as e:
            return f"OpenAI bridge error: {e}"
