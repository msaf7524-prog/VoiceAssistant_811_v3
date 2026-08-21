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

        self.groq_base_url = (
            "https://api.groq.com/openai/v1"
        )

        self.groq_chat_url = (
            f"{self.groq_base_url}/chat/completions"
        )

        self.groq_models_url = (
            f"{self.groq_base_url}/models"
        )

        # ترتيب الموديلات التي نفضلها
        self.preferred_models = [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
        ]

        self.groq_model = None

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

    # =========================================================
    # الدالة الرئيسية
    # =========================================================

    def get_response(self, user_text):

        if not user_text or not user_text.strip():
            return "ERROR: لم يتم إدخال نص."

        user_text = user_text.strip()

        if not self.groq_key:
            return "ERROR: GROQ API KEY فارغ."

        # إذا لم نحدد موديلًا بعد، نكتشف الموديلات المتاحة
        if not self.groq_model:

            model_result = self._detect_available_model()

            if not model_result["success"]:
                return (
                    "GROQ MODEL DISCOVERY ERROR\n\n"
                    + model_result["error"]
                )

            self.groq_model = model_result["model"]

        result = self._call_groq(user_text)

        if result["success"]:
            return result["text"]

        return (
            "GROQ ERROR\n\n"
            + result["error"]
        )

    # =========================================================
    # اكتشاف الموديلات المتاحة للمفتاح
    # =========================================================

    def _detect_available_model(self):

        try:

            headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            print("========== GROQ MODEL DISCOVERY ==========")

            response = requests.get(
                self.groq_models_url,
                headers=headers,
                timeout=20
            )

            print(
                "MODELS STATUS:",
                response.status_code
            )

            print(
                "MODELS RAW:",
                response.text[:5000]
            )

            if response.status_code != 200:

                return {
                    "success": False,
                    "model": None,
                    "error": self._format_http_error(
                        response
                    )
                }

            try:
                data = response.json()
            except Exception as e:
                return {
                    "success": False,
                    "model": None,
                    "error": (
                        "فشل تحليل قائمة الموديلات.\n"
                        f"Exception: {repr(e)}\n"
                        f"Raw: {response.text[:3000]}"
                    )
                }

            models = data.get("data", [])

            available_models = []

            for item in models:

                if not isinstance(item, dict):
                    continue

                model_id = item.get("id")

                if model_id:
                    available_models.append(
                        model_id
                    )

            if not available_models:

                return {
                    "success": False,
                    "model": None,
                    "error": (
                        "Groq أعاد قائمة موديلات فارغة."
                    )
                }

            print(
                "AVAILABLE MODELS:",
                available_models
            )

            # أولًا: نبحث عن الموديلات المفضلة
            for preferred in self.preferred_models:

                if preferred in available_models:

                    print(
                        "SELECTED MODEL:",
                        preferred
                    )

                    return {
                        "success": True,
                        "model": preferred,
                        "error": ""
                    }

            # إذا لم نجد موديلًا مفضلًا،
            # نحاول اختيار موديل نصي مناسب تلقائيًا
            candidates = []

            for model_id in available_models:

                low = model_id.lower()

                if (
                    "guard" not in low
                    and "whisper" not in low
                    and "tts" not in low
                    and "speech" not in low
                    and "embed" not in low
                ):
                    candidates.append(model_id)

            if candidates:

                selected = candidates[0]

                return {
                    "success": True,
                    "model": selected,
                    "error": ""
                }

            return {
                "success": False,
                "model": None,
                "error": (
                    "تم العثور على موديلات، "
                    "لكن لم نجد موديل محادثة مناسبًا.\n\n"
                    "Available models:\n"
                    + "\n".join(available_models[:50])
                )
            }

        except requests.exceptions.Timeout as e:

            return {
                "success": False,
                "model": None,
                "error": (
                    "انتهت مهلة اكتشاف موديلات Groq.\n"
                    f"Exception: {repr(e)}"
                )
            }

        except requests.exceptions.ConnectionError as e:

            return {
                "success": False,
                "model": None,
                "error": (
                    "تعذر الاتصال بخادم Groq أثناء "
                    "اكتشاف الموديلات.\n"
                    f"Exception: {repr(e)}"
                )
            }

        except Exception as e:

            return {
                "success": False,
                "model": None,
                "error": (
                    "خطأ غير متوقع أثناء اكتشاف الموديلات.\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

    # =========================================================
    # Groq Chat
    # =========================================================

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

            print("========== GROQ CHAT ==========")
            print(
                "MODEL:",
                self.groq_model
            )

            response = requests.post(
                self.groq_chat_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            print(
                "CHAT STATUS:",
                response.status_code
            )

            print(
                "CHAT RAW:",
                response.text[:5000]
            )

            if response.status_code != 200:

                return {
                    "success": False,
                    "text": "",
                    "error": self._format_http_error(
                        response
                    )
                }

            try:
                data = response.json()
            except Exception as e:
                return {
                    "success": False,
                    "text": "",
                    "error": (
                        "فشل تحليل استجابة Groq.\n"
                        f"Exception: {repr(e)}\n"
                        f"Raw: {response.text[:3000]}"
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
                        "بنية استجابة Groq غير متوقعة.\n"
                        f"Exception: {repr(e)}\n"
                        f"JSON:\n"
                        f"{json.dumps(data, ensure_ascii=False)[:4000]}"
                    )
                }

            answer = self._clean_text(
                answer
            )

            if not answer:

                return {
                    "success": False,
                    "text": "",
                    "error": (
                        "Groq أعاد ردًا فارغًا."
                    )
                }

            self.history.append({
                "role": "user",
                "content": user_text
            })

            self.history.append({
                "role": "assistant",
                "content": answer
            })

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

    # =========================================================
    # تنسيق أخطاء HTTP
    # =========================================================

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

    # =========================================================
    # تنظيف النص
    # =========================================================

    def _clean_text(self, text):

        if not text:
            return ""

        text = str(text)

        text = re.sub(
            r"[*#_~`]",
            "",
            text
        )

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

    # =========================================================
    # مسح سجل المحادثة
    # =========================================================

    def clear_history(self):

        self.history = [
            {
                "role": "system",
                "content": self.system_instruction
            }
        ]

        # نجبر البرنامج على إعادة اكتشاف الموديل
        self.groq_model = None
