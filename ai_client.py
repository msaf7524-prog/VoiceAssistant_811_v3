import os
import re
import json
import requests


class AIClient:

    def __init__(self, groq_key=None, gemini_key=None):

        # =====================================================
        # API KEYS
        # =====================================================

        self.groq_key = (
            groq_key
            or os.environ.get("GROQ_API_KEY", "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")
        ).strip()

        self.gemini_key = (
            gemini_key
            or os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6IZyX0tU7zsXyPuAIspztPJKTdKDic9MXbM1F49v6NAxg")
        ).strip()

        # =====================================================
        # GROQ
        # =====================================================

        self.groq_url = (
            "https://api.groq.com/openai/v1/chat/completions"
        )

        # نموذج Groq الحالي المستخدم للاختبار
        self.groq_model = "llama-3.1-8b-instant"

        # =====================================================
        # GEMINI
        # =====================================================

        self.gemini_model = "gemini-1.5-flash"

        # =====================================================
        # SYSTEM INSTRUCTION
        # =====================================================

        self.system_instruction = (
            "أنت مساعد صوتي ذكي واسمك 811. "
            "تحدث باللغة العربية بطلاقة وبأسلوب مختصر ومباشر. "
            "لا تستخدم الإيموجي. "
            "لا تستخدم Markdown. "
            "لا تستخدم النجوم أو الهاشتاق أو الرموز الزائدة."
        )

        # =====================================================
        # CONVERSATION HISTORY
        # =====================================================

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

            return (
                "لم أسمع شيئاً، "
                "يرجى المحاولة مرة أخرى."
            )

        user_text = user_text.strip()

        # -----------------------------------------------------
        # محاولة Groq
        # -----------------------------------------------------

        if self.groq_key:

            groq_result = self._call_groq(user_text)

            if groq_result["success"]:

                return groq_result["text"]

            # نطبع الخطأ الكامل في Logcat / GitHub logs
            print(
                "========== GROQ FAILED =========="
            )

            print(
                groq_result["error"]
            )

            print(
                "================================="
            )

        else:

            print(
                "GROQ_API_KEY is empty."
            )

        # -----------------------------------------------------
        # محاولة Gemini كخطة احتياطية
        # -----------------------------------------------------

        if self.gemini_key:

            gemini_result = self._call_gemini(
                user_text
            )

            if gemini_result["success"]:

                return gemini_result["text"]

            print(
                "========== GEMINI FAILED =========="
            )

            print(
                gemini_result["error"]
            )

            print(
                "==================================="
            )

        # -----------------------------------------------------
        # رسالة مفصلة للمستخدم
        # -----------------------------------------------------

        if not self.groq_key and not self.gemini_key:

            return (
                "لم يتم إدخال مفتاح الذكاء الاصطناعي."
            )

        return (
            "تعذر الاتصال بمحرك الذكاء الاصطناعي.\n\n"
            "راجع رسالة الخطأ التفصيلية في Logcat."
        )

    # =========================================================
    # GROQ REQUEST
    # =========================================================

    def _call_groq(self, user_text):

        try:

            # -------------------------------------------------
            # بناء History مؤقت
            # -------------------------------------------------

            temp_history = list(
                self.history
            )

            temp_history.append(
                {
                    "role": "user",
                    "content": user_text
                }
            )

            # لا نرسل History ضخمة
            if len(temp_history) > 7:

                temp_history = (
                    [temp_history[0]]
                    + temp_history[-6:]
                )

            # -------------------------------------------------
            # Payload
            # -------------------------------------------------

            payload = {
                "model": self.groq_model,
                "messages": temp_history,
                "temperature": 0.3,
                "max_tokens": 512,
                "stream": False
            }

            # -------------------------------------------------
            # Headers
            # -------------------------------------------------

            headers = {
                "Authorization": (
                    f"Bearer {self.groq_key}"
                ),
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            print(
                "========== GROQ REQUEST =========="
            )

            print(
                f"Model: {self.groq_model}"
            )

            print(
                f"URL: {self.groq_url}"
            )

            print(
                "Sending request..."
            )

            # -------------------------------------------------
            # HTTP REQUEST
            # -------------------------------------------------

            response = requests.post(
                self.groq_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            # -------------------------------------------------
            # BASIC DEBUG
            # -------------------------------------------------

            print(
                "========== GROQ RESPONSE =========="
            )

            print(
                f"HTTP Status: {response.status_code}"
            )

            print(
                f"Content-Type: "
                f"{response.headers.get('Content-Type')}"
            )

            # -------------------------------------------------
            # SUCCESS
            # -------------------------------------------------

            if response.status_code == 200:

                try:

                    data = response.json()

                except Exception as e:

                    return {
                        "success": False,
                        "text": "",
                        "error": (
                            "Groq returned HTTP 200 "
                            "but JSON parsing failed.\n"
                            f"Exception: {repr(e)}\n"
                            f"Raw response: "
                            f"{response.text[:2000]}"
                        )
                    }

                try:

                    bot_reply = (
                        data["choices"][0]
                        ["message"]["content"]
                    )

                except Exception as e:

                    return {
                        "success": False,
                        "text": "",
                        "error": (
                            "Groq JSON structure "
                            "was unexpected.\n"
                            f"Exception: {repr(e)}\n"
                            f"JSON: "
                            f"{json.dumps(data, ensure_ascii=False)[:4000]}"
                        )
                    }

                bot_reply = self._clean_text(
                    bot_reply
                )

                if not bot_reply:

                    return {
                        "success": False,
                        "text": "",
                        "error": (
                            "Groq returned an empty response."
                        )
                    }

                # ---------------------------------------------
                # حفظ المحادثة
                # ---------------------------------------------

                self.history.append(
                    {
                        "role": "user",
                        "content": user_text
                    }
                )

                self.history.append(
                    {
                        "role": "assistant",
                        "content": bot_reply
                    }
                )

                print(
                    "Groq request SUCCESS."
                )

                return {
                    "success": True,
                    "text": bot_reply,
                    "error": ""
                }

            # -------------------------------------------------
            # HTTP ERROR
            # -------------------------------------------------

            error_details = self._extract_http_error(
                response
            )

            return {
                "success": False,
                "text": "",
                "error": (
                    f"Groq HTTP Error: "
                    f"{response.status_code}\n"
                    f"{error_details}"
                )
            }

        # =====================================================
        # REQUEST EXCEPTIONS
        # =====================================================

        except requests.exceptions.Timeout as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "Groq timeout.\n"
                    f"Exception: {repr(e)}"
                )
            }

        except requests.exceptions.SSLError as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "Groq SSL/TLS error.\n"
                    f"Exception: {repr(e)}"
                )
            }

        except requests.exceptions.ConnectionError as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "Groq connection error.\n"
                    f"Exception: {repr(e)}"
                )
            }

        except requests.exceptions.RequestException as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "Groq requests error.\n"
                    f"Exception: {repr(e)}"
                )
            }

        except Exception as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "Unexpected Groq exception.\n"
                    f"Exception type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

    # =========================================================
    # GEMINI
    # =========================================================

    def _call_gemini(self, user_text):

        try:

            url = (
                "https://generativelanguage.googleapis.com/"
                "v1beta/models/"
                f"{self.gemini_model}:generateContent"
                f"?key={self.gemini_key}"
            )

            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": (
                                    f"{self.system_instruction}\n\n"
                                    f"سؤال المستخدم: "
                                    f"{user_text}"
                                )
                            }
                        ]
                    }
                ]
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )

            print(
                "========== GEMINI RESPONSE =========="
            )

            print(
                f"HTTP Status: {response.status_code}"
            )

            if response.status_code == 200:

                try:

                    data = response.json()

                except Exception as e:

                    return {
                        "success": False,
                        "text": "",
                        "error": (
                            "Gemini JSON parsing failed.\n"
                            f"Exception: {repr(e)}"
                        )
                    }

                try:

                    bot_reply = (
                        data["candidates"][0]
                        ["content"]["parts"][0]["text"]
                    )

                except Exception as e:

                    return {
                        "success": False,
                        "text": "",
                        "error": (
                            "Gemini JSON structure "
                            "was unexpected.\n"
                            f"Exception: {repr(e)}\n"
                            f"JSON: "
                            f"{json.dumps(data, ensure_ascii=False)[:4000]}"
                        )
                    }

                bot_reply = self._clean_text(
                    bot_reply
                )

                if bot_reply:

                    return {
                        "success": True,
                        "text": bot_reply,
                        "error": ""
                    }

                return {
                    "success": False,
                    "text": "",
                    "error": (
                        "Gemini returned an empty response."
                    )
                }

            error_details = self._extract_http_error(
                response
            )

            return {
                "success": False,
                "text": "",
                "error": (
                    f"Gemini HTTP Error: "
                    f"{response.status_code}\n"
                    f"{error_details}"
                )
            }

        except Exception as e:

            return {
                "success": False,
                "text": "",
                "error": (
                    "Unexpected Gemini exception.\n"
                    f"Exception type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

    # =========================================================
    # استخراج رسالة HTTP
    # =========================================================

    def _extract_http_error(self, response):

        try:

            data = response.json()

            if isinstance(data, dict):

                error = data.get(
                    "error"
                )

                if isinstance(error, dict):

                    message = error.get(
                        "message",
                        ""
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
                        f"Message: {message}\n"
                        f"Type: {error_type}\n"
                        f"Code: {code}"
                    )

                return (
                    "JSON Error:\n"
                    + json.dumps(
                        data,
                        ensure_ascii=False
                    )[:3000]
                )

        except Exception as e:

            return (
                "Could not parse error JSON.\n"
                f"Exception: {repr(e)}\n"
                f"Raw response: "
                f"{response.text[:3000]}"
            )

        return (
            f"Raw response: "
            f"{response.text[:3000]}"
        )

    # =========================================================
    # تنظيف الرد
    # =========================================================

    def _clean_text(self, text):

        if text is None:
            return ""

        text = str(text)

        # حذف Markdown الشائع
        text = re.sub(
            r"[*#_~`]",
            "",
            text
        )

        # إزالة علامات الاقتباس الزائدة
        text = re.sub(
            r"[\"']",
            "",
            text
        )

        # لا نحذف الشرطة داخل الكلمات أو الأرقام.
        # نحذف فقط الشرطات الزائدة كبداية للسطر.
        text = re.sub(
            r"(?m)^\s*[-•]\s*",
            "",
            text
        )

        # تنظيف المسافات
        text = re.sub(
            r"[ \t]+",
            " ",
            text
        )

        # تنظيف الأسطر الفارغة الكثيرة
        text = re.sub(
            r"\n{3,}",
            "\n\n",
            text
        )

        return text.strip()

    # =========================================================
    # مسح الذاكرة
    # =========================================================

    def clear_history(self):

        self.history = [
            {
                "role": "system",
                "content": self.system_instruction
            }
        ]
