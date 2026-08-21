import os
import re
import json
import requests


class AIClient:

    def __init__(self, groq_key=None, gemini_key=None):

        self.groq_key = (
            groq_key or os.environ.get("GROQ_API_KEY", "")
        ).strip()

        self.gemini_key = (
            gemini_key or os.environ.get("GEMINI_API_KEY", "")
        ).strip()

        self.groq_url = (
            "https://api.groq.com/openai/v1/chat/completions"
        )

        self.groq_model = "llama-3.1-8b-instant"

        self.system_instruction = (
            "أنت مساعد صوتي ذكي واسمك 811. "
            "تحدث باللغة العربية بطلاقة وبأسلوب مختصر ومباشر. "
            "لا تستخدم الإيموجي أو Markdown."
        )

        self.history = [
            {
                "role": "system",
                "content": self.system_instruction
            }
        ]

    def get_response(self, user_text):

        if not user_text or not user_text.strip():
            return "ERROR: لم يتم إدخال نص."

        user_text = user_text.strip()

        if not self.groq_key:
            return "ERROR: GROQ API KEY فارغ."

        result = self._call_groq(user_text)

        if result["success"]:
            return result["text"]

        # نعيد الخطأ الحقيقي إلى الشاشة
        return (
            "GROQ ERROR\n\n"
            + result["error"]
        )

    def _call_groq(self, user_text):

        try:

            messages = list(self.history)

            messages.append({
                "role": "user",
                "content": user_text
            })

            if len(messages) > 7:
                messages = [
                    messages[0]
                ] + messages[-6:]

            payload = {
                "model": self.groq_model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 512,
                "stream": False
            }

            headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            print("========== GROQ DEBUG ==========")
            print("MODEL:", self.groq_model)
            print("URL:", self.groq_url)
            print("KEY PRESENT:", bool(self.groq_key))

            response = requests.post(
                self.groq_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            print("STATUS:", response.status_code)
            print("RAW RESPONSE:", response.text[:4000])

            if response.status_code != 200:

                return {
                    "success": False,
                    "text": "",
                    "error": self._format_http_error(response)
                }

            try:
                data = response.json()
            except Exception as e:
                return {
                    "success": False,
                    "text": "",
                    "error": (
                        "JSON PARSE ERROR\n"
                        f"Exception: {repr(e)}\n\n"
                        f"Raw:\n{response.text[:3000]}"
                    )
                }

            try:
                answer = (
                    data["choices"][0]
                    ["message"]["content"]
                )
            except Exception as e:
                return {
                    "success": False,
                    "text": "",
                    "error": (
                        "INVALID GROQ RESPONSE\n"
                        f"Exception: {repr(e)}\n\n"
                        f"JSON:\n"
                        f"{json.dumps(data, ensure_ascii=False)[:3000]}"
                    )
                }

            answer = self._clean_text(answer)

            if not answer:
                return {
                    "success": False,
                    "text": "",
                    "error": "Groq returned an empty response."
                }

            self.history.append({
                "role": "user",
                "content": user_text
            })

            self.history.append({
                "role": "assistant",
                "content": answer
            })

            print("GROQ SUCCESS")

            return {
                "success": True,
                "text": answer,
                "error": ""
            }

        except requests.exceptions.Timeout as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "REQUEST TIMEOUT\n"
                    f"Exception: {repr(e)}"
                )
            }

        except requests.exceptions.SSLError as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "SSL/TLS ERROR\n"
                    f"Exception: {repr(e)}"
                )
            }

        except requests.exceptions.ConnectionError as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "CONNECTION ERROR\n"
                    f"Exception: {repr(e)}"
                )
            }

        except Exception as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "UNKNOWN ERROR\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

    def _format_http_error(self, response):

        try:
            data = response.json()

            if isinstance(data, dict):

                error = data.get("error")

                if isinstance(error, dict):

                    message = error.get(
                        "message",
                        "Unknown error"
                    )

                    error_type = error.get(
                        "type",
                        ""
                    )

                    code = error.get(
                        "code",
                        ""
                    )

                    return (
                        f"HTTP {response.status_code}\n"
                        f"Message: {message}\n"
                        f"Type: {error_type}\n"
                        f"Code: {code}"
                    )

                return (
                    f"HTTP {response.status_code}\n"
                    + json.dumps(
                        data,
                        ensure_ascii=False
                    )[:3000]
                )

        except Exception as e:

            return (
                f"HTTP {response.status_code}\n"
                f"Exception: {repr(e)}\n"
                f"Raw: {response.text[:3000]}"
            )

        return (
            f"HTTP {response.status_code}\n"
            f"Raw: {response.text[:3000]}"
        )

    def _clean_text(self, text):

        if not text:
            return ""

        text = str(text)

        text = re.sub(r"[*#_~`]", "", text)

        text = re.sub(
            r"(?m)^\s*[-•]\s*",
            "",
            text
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text
        )

        text = re.sub(
            r"\n{3,}",
            "\n\n",
            text
        )

        return text.strip()

    def clear_history(self):

        self.history = [
            {
                "role": "system",
                "content": self.system_instruction
            }
        ]
