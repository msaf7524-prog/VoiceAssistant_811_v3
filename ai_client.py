import os
import re
import datetime
import requests


class AIClient:
    """Small, defensive Groq chat client used by Voice Assistant 811."""

    def __init__(self, groq_key=None, gemini_key=None):
        self.groq_key = (
            groq_key
            or os.environ.get("GROQ_API_KEY", "")
        ).strip()

        # Kept for backward compatibility with the current app.
        self.gemini_key = (
            gemini_key
            or os.environ.get("GEMINI_API_KEY", "")
        ).strip()

        self.groq_base_url = "https://api.groq.com/openai/v1"
        self.groq_chat_url = (
            self.groq_base_url
            + "/chat/completions"
        )
        self.groq_models_url = (
            self.groq_base_url
            + "/models"
        )

        # Quality first. Faster/smaller models remain as fallbacks.
        self.preferred_models = [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant",
        ]

        self.groq_model = None

        today = datetime.date.today().isoformat()

        self.system_instruction = (
            "أنت 811، مساعد شخصي ذكي للمستخدم. "
            "أجب بالعربية السليمة والواضحة والطبيعية، "
            "وافهم اللهجة العراقية عندما يستخدمها المستخدم. "
            "الأولوية للدقة ثم الوضوح ثم الاختصار. "
            "لا تخترع أرقاماً أو حقائق أو مصادر. "
            "إذا لم تكن متأكداً من معلومة متغيرة زمنياً فقل ذلك بوضوح. "
            "لا تدّعي أن لديك وصولاً مباشراً للويب أو بيانات حية "
            "ما لم تُزوَّد بها فعلاً. "
            "تجنب Markdown والرموز الزائدة لأن الرد سيُعرض ويُنطق صوتياً. "
            "استخدم جُملاً عربية طبيعية وسهلة النطق. "
            "تاريخ الجهاز الحالي: "
            + today
            + "."
        )

        self.history = [
            {
                "role": "system",
                "content": self.system_instruction,
            }
        ]

    # =========================================================
    # PUBLIC API
    # =========================================================

    def get_response(self, user_text):
        user_text = self._clean_text(
            user_text
        )

        if not user_text:
            return "لم أسمع أو أستلم نصاً واضحاً."

        if not self.groq_key:
            return "مفتاح Groq API غير موجود."

        try:
            if not self.groq_model:
                model_result = (
                    self._detect_available_model()
                )

                if not model_result["success"]:
                    return (
                        "تعذر اختيار نموذج Groq.\n"
                        + model_result["error"]
                    )

                self.groq_model = (
                    model_result["model"]
                )

            result = self._call_groq(
                user_text
            )

            if result["success"]:
                return result["text"]

            error_text = (
                result["error"]
                or ""
            )

            # A model can disappear from the account/provider list.
            # Rediscover once instead of permanently failing.
            low = error_text.lower()

            if (
                "model_not_found" in low
                or "does not exist" in low
                or "404" in low
            ):
                self.groq_model = None

                model_result = (
                    self._detect_available_model()
                )

                if model_result["success"]:
                    self.groq_model = (
                        model_result["model"]
                    )

                    retry_result = (
                        self._call_groq(
                            user_text
                        )
                    )

                    if retry_result["success"]:
                        return retry_result["text"]

                    error_text = (
                        retry_result["error"]
                    )

            return (
                "حدث خطأ أثناء الاتصال بـ Groq.\n"
                + error_text
            ).strip()

        except Exception as exc:
            print(
                "811: AI client fatal error:",
                type(exc).__name__,
                repr(exc)
            )

            return (
                "تعذر إكمال الطلب حالياً. "
                "حاول مرة أخرى بعد قليل."
            )

    def clear_history(self):
        self.history = [
            {
                "role": "system",
                "content": self.system_instruction,
            }
        ]

    # =========================================================
    # MODEL DISCOVERY
    # =========================================================

    def _detect_available_model(self):
        try:
            response = requests.get(
                self.groq_models_url,
                headers=self._headers(),
                timeout=20,
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "model": None,
                    "error": self._format_http_error(
                        response
                    ),
                }

            data = response.json()

            available_models = []

            for item in data.get("data", []):
                if not isinstance(item, dict):
                    continue

                model_id = item.get("id")

                if model_id:
                    available_models.append(
                        str(model_id)
                    )

            if not available_models:
                return {
                    "success": False,
                    "model": None,
                    "error": (
                        "Groq أعاد قائمة نماذج فارغة."
                    ),
                }

            for preferred in self.preferred_models:
                if preferred in available_models:
                    print(
                        "811: selected Groq model:",
                        preferred
                    )

                    return {
                        "success": True,
                        "model": preferred,
                        "error": "",
                    }

            blocked_words = (
                "whisper",
                "tts",
                "speech",
                "guard",
                "embed",
                "moderation",
                "audio",
            )

            candidates = []

            for model_id in available_models:
                low = model_id.lower()

                if any(
                    word in low
                    for word in blocked_words
                ):
                    continue

                candidates.append(
                    model_id
                )

            if not candidates:
                return {
                    "success": False,
                    "model": None,
                    "error": (
                        "لم يتم العثور على نموذج محادثة مناسب."
                    ),
                }

            # Prefer larger general-purpose models when the provider
            # exposes a model that is not in our explicit list.
            def quality_score(model_id):
                low = model_id.lower()
                score = 0

                if "120b" in low:
                    score += 120
                elif "70b" in low:
                    score += 70
                elif "32b" in low:
                    score += 32
                elif "20b" in low:
                    score += 20
                elif "8b" in low:
                    score += 8

                if "versatile" in low:
                    score += 20

                if "instant" in low:
                    score -= 10

                return score

            candidates.sort(
                key=quality_score,
                reverse=True
            )

            selected = candidates[0]

            print(
                "811: auto-selected Groq model:",
                selected
            )

            return {
                "success": True,
                "model": selected,
                "error": "",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "model": None,
                "error": (
                    "انتهت مهلة الاتصال بخدمة Groq."
                ),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "model": None,
                "error": (
                    "تعذر الاتصال بخدمة Groq. "
                    "تحقق من الإنترنت."
                ),
            }

        except Exception as exc:
            print(
                "811: model discovery error:",
                type(exc).__name__,
                repr(exc)
            )

            return {
                "success": False,
                "model": None,
                "error": (
                    "حدث خطأ غير متوقع أثناء اختيار النموذج."
                ),
            }

    # =========================================================
    # CHAT COMPLETION
    # =========================================================

    def _call_groq(
        self,
        user_text
    ):
        messages = list(
            self.history
        )

        messages.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        # Keep enough context for a useful conversation without
        # letting mobile requests grow indefinitely.
        if len(messages) > 13:
            messages = (
                [messages[0]]
                + messages[-12:]
            )

        payload = {
            "model": self.groq_model,
            "messages": messages,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 700,
            "stream": False,
        }

        try:
            response = requests.post(
                self.groq_chat_url,
                headers=self._headers(),
                json=payload,
                timeout=35,
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "text": "",
                    "error": self._format_http_error(
                        response
                    ),
                }

            data = response.json()
            choices = data.get(
                "choices",
                []
            )

            if not choices:
                return {
                    "success": False,
                    "text": "",
                    "error": (
                        "Groq لم يُرجع إجابة."
                    ),
                }

            message = (
                choices[0]
                .get("message", {})
            )

            answer = self._clean_text(
                message.get(
                    "content",
                    ""
                )
            )

            if not answer:
                return {
                    "success": False,
                    "text": "",
                    "error": (
                        "وصل رد فارغ من Groq."
                    ),
                }

            self.history.append(
                {
                    "role": "user",
                    "content": user_text,
                }
            )

            self.history.append(
                {
                    "role": "assistant",
                    "content": answer,
                }
            )

            # Hard cap the saved history as well.
            if len(self.history) > 13:
                self.history = (
                    [self.history[0]]
                    + self.history[-12:]
                )

            return {
                "success": True,
                "text": answer,
                "error": "",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "text": "",
                "error": (
                    "انتهت مهلة انتظار رد Groq."
                ),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "text": "",
                "error": (
                    "انقطع الاتصال بخدمة Groq."
                ),
            }

        except ValueError:
            return {
                "success": False,
                "text": "",
                "error": (
                    "تعذر قراءة استجابة Groq."
                ),
            }

        except Exception as exc:
            print(
                "811: Groq request error:",
                type(exc).__name__,
                repr(exc)
            )

            return {
                "success": False,
                "text": "",
                "error": (
                    "حدث خطأ غير متوقع أثناء طلب Groq."
                ),
            }

    # =========================================================
    # HELPERS
    # =========================================================

    def _headers(self):
        return {
            "Authorization": (
                "Bearer "
                + self.groq_key
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _format_http_error(
        self,
        response
    ):
        status = getattr(
            response,
            "status_code",
            "?"
        )

        detail = ""

        try:
            data = response.json()

            if isinstance(data, dict):
                error = data.get(
                    "error",
                    data
                )

                if isinstance(error, dict):
                    detail = str(
                        error.get(
                            "message",
                            ""
                        )
                    )
                else:
                    detail = str(error)

        except Exception:
            detail = str(
                getattr(
                    response,
                    "text",
                    ""
                )
            )

        detail = self._clean_text(
            detail
        )

        if len(detail) > 700:
            detail = (
                detail[:700]
                + "..."
            )

        if detail:
            return (
                "HTTP "
                + str(status)
                + ": "
                + detail
            )

        return (
            "HTTP "
            + str(status)
        )

    def _mask_key(
        self,
        key
    ):
        key = str(
            key or ""
        )

        if len(key) <= 8:
            return "********"

        return (
            key[:4]
            + "..."
            + key[-4:]
        )

    def _clean_text(
        self,
        text
    ):
        if text is None:
            return ""

        text = str(text)

        # Remove control characters that cause display/TTS issues while
        # preserving normal newlines.
        text = re.sub(
            r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]",
            "",
            text
        )

        text = text.replace(
            "\r\n",
            "\n"
        ).replace(
            "\r",
            "\n"
        )

        lines = []

        for line in text.split("\n"):
            line = re.sub(
                r"[ \t]+",
                " ",
                line
            ).strip()

            lines.append(line)

        return "\n".join(
            lines
        ).strip()
