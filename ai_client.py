import os
import re
import datetime
import requests

# GitHub Actions creates app_secrets.py only inside the build workspace.
# It is packaged into the APK but is never committed to the public repository.
try:
    from app_secrets import (
        GEMINI_API_KEY as BUNDLED_GEMINI_API_KEY,
        GROQ_API_KEY as BUNDLED_GROQ_API_KEY,
    )
except Exception:
    BUNDLED_GEMINI_API_KEY = ""
    BUNDLED_GROQ_API_KEY = ""


class AIClient:
    """
    Defensive multi-provider AI client for Voice Assistant 811.

    Providers:
    - Gemini 3.7 Flash (preferred when a Gemini key is entered)
    - Groq (kept fully compatible as a fallback / existing provider)

    No API key is hard-coded in source control.
    """

    GEMINI_PRIMARY_MODEL = "gemini-3.7-flash"
    GEMINI_FALLBACK_MODEL = "gemini-3.1-flash-lite"

    def __init__(
        self,
        groq_key=None,
        gemini_key=None,
        provider="auto"
    ):
        self.groq_key = (
            groq_key
            or os.environ.get("GROQ_API_KEY", "")
            or BUNDLED_GROQ_API_KEY
        ).strip()

        self.gemini_key = (
            gemini_key
            or os.environ.get("GEMINI_API_KEY", "")
            or os.environ.get("GOOGLE_API_KEY", "")
            or BUNDLED_GEMINI_API_KEY
        ).strip()

        self.provider = str(
            provider or "auto"
        ).strip().lower()

        self.groq_base_url = (
            "https://api.groq.com/openai/v1"
        )
        self.groq_chat_url = (
            self.groq_base_url
            + "/chat/completions"
        )
        self.groq_models_url = (
            self.groq_base_url
            + "/models"
        )

        self.gemini_base_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
        )
        self.gemini_model = (
            self.GEMINI_PRIMARY_MODEL
        )

        # Quality first. Faster/smaller models remain as fallbacks.
        self.preferred_models = [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant",
        ]

        self.groq_model = None

        today = (
            datetime.date.today()
            .isoformat()
        )

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

        # If a constructor key is already available, resolve provider now.
        if self.provider == "auto":
            if self.gemini_key:
                self.provider = "gemini"
            elif self.groq_key:
                self.provider = "groq"

    # =========================================================
    # PUBLIC API
    # =========================================================

    def get_default_api_key(
        self
    ):
        """
        Return the preferred built-in/runtime key without exposing it in logs.
        Gemini is preferred when both providers are available.
        """
        if self.gemini_key:
            return self.gemini_key

        if self.groq_key:
            return self.groq_key

        return ""

    def has_bundled_keys(
        self
    ):
        return bool(
            BUNDLED_GEMINI_API_KEY
            or BUNDLED_GROQ_API_KEY
        )

    @staticmethod
    def identify_provider(
        api_key
    ):
        """
        Detect the provider without exposing/logging the key.

        Groq keys use the gsk_ prefix. Gemini/Google keys have changed forms
        over time, so every non-Groq key is treated as Gemini.
        """
        key = str(
            api_key or ""
        ).strip()

        if not key:
            return ""

        if key.lower().startswith(
            "gsk_"
        ):
            return "groq"

        return "gemini"

    def set_api_key(
        self,
        api_key
    ):
        key = str(
            api_key or ""
        ).strip()

        provider = (
            self.identify_provider(
                key
            )
        )

        if provider == "groq":
            self.groq_key = key
            self.provider = "groq"

        elif provider == "gemini":
            self.gemini_key = key
            self.provider = "gemini"

        return provider

    def get_provider_name(
        self
    ):
        if self.provider == "gemini":
            return "Gemini"

        if self.provider == "groq":
            return "Groq"

        return "AI"

    def get_response(
        self,
        user_text
    ):
        user_text = self._clean_text(
            user_text
        )

        if not user_text:
            return (
                "لم أسمع أو أستلم نصاً واضحاً."
            )

        provider = self.provider

        if provider == "auto":
            if self.gemini_key:
                provider = "gemini"
            elif self.groq_key:
                provider = "groq"

        if provider == "gemini":
            if not self.gemini_key:
                return (
                    "مفتاح Gemini API غير موجود."
                )

            return self._get_gemini_response(
                user_text
            )

        if provider == "groq":
            if not self.groq_key:
                return (
                    "مفتاح Groq API غير موجود."
                )

            return self._get_groq_response(
                user_text
            )

        return (
            "مفتاح الذكاء الاصطناعي غير موجود."
        )

    def clear_history(
        self
    ):
        self.history = [
            {
                "role": "system",
                "content": self.system_instruction,
            }
        ]

    # =========================================================
    # GEMINI 3.7 FLASH
    # =========================================================

    def _get_gemini_response(
        self,
        user_text
    ):
        try:
            result = self._call_gemini(
                user_text,
                self.gemini_model
            )

            if result["success"]:
                return result["text"]

            error_text = (
                result["error"]
                or ""
            )

            low = error_text.lower()

            # If the primary model is temporarily unavailable on the account,
            # use the lightweight current Gemini fallback exactly once.
            if (
                self.gemini_model
                != self.GEMINI_FALLBACK_MODEL
                and (
                    "404" in low
                    or "not found" in low
                    or "not supported" in low
                )
            ):
                fallback = (
                    self.GEMINI_FALLBACK_MODEL
                )

                print(
                    "811: Gemini primary unavailable; "
                    "trying fallback model:",
                    fallback
                )

                retry_result = (
                    self._call_gemini(
                        user_text,
                        fallback
                    )
                )

                if retry_result["success"]:
                    self.gemini_model = fallback
                    return retry_result["text"]

                error_text = (
                    retry_result["error"]
                )

            return (
                "حدث خطأ أثناء الاتصال بـ Gemini.\n"
                + error_text
            ).strip()

        except Exception as exc:
            print(
                "811: Gemini client fatal error:",
                type(exc).__name__,
                repr(exc)
            )

            return (
                "تعذر إكمال الطلب حالياً. "
                "حاول مرة أخرى بعد قليل."
            )

    def _call_gemini(
        self,
        user_text,
        model
    ):
        contents = []

        # Convert the same compact 811 history to Gemini roles.
        for item in self.history:
            role = item.get(
                "role",
                ""
            )

            if role == "system":
                continue

            if role == "assistant":
                gemini_role = "model"
            elif role == "user":
                gemini_role = "user"
            else:
                continue

            content = self._clean_text(
                item.get(
                    "content",
                    ""
                )
            )

            if not content:
                continue

            contents.append(
                {
                    "role": gemini_role,
                    "parts": [
                        {
                            "text": content
                        }
                    ],
                }
            )

        contents.append(
            {
                "role": "user",
                "parts": [
                    {
                        "text": user_text
                    }
                ],
            }
        )

        # Keep enough context for continuity without letting mobile payloads
        # grow forever.
        if len(contents) > 12:
            contents = contents[-12:]

        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": self.system_instruction
                    }
                ]
            },
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": 900
            },
        }

        url = (
            self.gemini_base_url
            + str(model)
            + ":generateContent"
        )

        try:
            response = requests.post(
                url,
                headers={
                    "x-goog-api-key": (
                        self.gemini_key
                    ),
                    "Content-Type": (
                        "application/json"
                    ),
                    "Accept": (
                        "application/json"
                    ),
                    "x-goog-api-client": (
                        "voice-assistant-811/0.3.1"
                    ),
                },
                json=payload,
                timeout=40,
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

            candidates = data.get(
                "candidates",
                []
            )

            if not candidates:
                block_reason = ""

                try:
                    block_reason = str(
                        data.get(
                            "promptFeedback",
                            {}
                        ).get(
                            "blockReason",
                            ""
                        )
                    )
                except Exception:
                    block_reason = ""

                error = (
                    "Gemini لم يُرجع إجابة."
                )

                if block_reason:
                    error += (
                        " سبب الإيقاف: "
                        + block_reason
                    )

                return {
                    "success": False,
                    "text": "",
                    "error": error,
                }

            content = (
                candidates[0]
                .get(
                    "content",
                    {}
                )
            )

            parts = content.get(
                "parts",
                []
            )

            text_parts = []

            for part in parts:
                if not isinstance(
                    part,
                    dict
                ):
                    continue

                value = part.get(
                    "text"
                )

                if value:
                    text_parts.append(
                        str(value)
                    )

            answer = self._clean_text(
                "\n".join(
                    text_parts
                )
            )

            if not answer:
                return {
                    "success": False,
                    "text": "",
                    "error": (
                        "وصل رد فارغ من Gemini."
                    ),
                }

            self._append_history(
                user_text,
                answer
            )

            print(
                "811: Gemini response OK | model:",
                model
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
                    "انتهت مهلة انتظار رد Gemini."
                ),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "text": "",
                "error": (
                    "تعذر الاتصال بخدمة Gemini. "
                    "تحقق من الإنترنت."
                ),
            }

        except ValueError:
            return {
                "success": False,
                "text": "",
                "error": (
                    "تعذر قراءة استجابة Gemini."
                ),
            }

        except Exception as exc:
            print(
                "811: Gemini request error:",
                type(exc).__name__,
                repr(exc)
            )

            return {
                "success": False,
                "text": "",
                "error": (
                    "حدث خطأ غير متوقع أثناء طلب Gemini."
                ),
            }

    # =========================================================
    # GROQ
    # =========================================================

    def _get_groq_response(
        self,
        user_text
    ):
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

    # =========================================================
    # GROQ MODEL DISCOVERY
    # =========================================================

    def _detect_available_model(
        self
    ):
        try:
            response = requests.get(
                self.groq_models_url,
                headers=self._groq_headers(),
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

            for item in data.get(
                "data",
                []
            ):
                if not isinstance(
                    item,
                    dict
                ):
                    continue

                model_id = item.get(
                    "id"
                )

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

            def quality_score(
                model_id
            ):
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

            selected = (
                candidates[0]
            )

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
    # GROQ CHAT COMPLETION
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
                headers=self._groq_headers(),
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
                .get(
                    "message",
                    {}
                )
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

            self._append_history(
                user_text,
                answer
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
    # HISTORY + HELPERS
    # =========================================================

    def _append_history(
        self,
        user_text,
        answer
    ):
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

        if len(self.history) > 13:
            self.history = (
                [self.history[0]]
                + self.history[-12:]
            )

    def _groq_headers(
        self
    ):
        return {
            "Authorization": (
                "Bearer "
                + self.groq_key
            ),
            "Content-Type": (
                "application/json"
            ),
            "Accept": (
                "application/json"
            ),
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

            if isinstance(
                data,
                dict
            ):
                error = data.get(
                    "error",
                    data
                )

                if isinstance(
                    error,
                    dict
                ):
                    detail = str(
                        error.get(
                            "message",
                            ""
                        )
                    )
                else:
                    detail = str(
                        error
                    )

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

        for line in text.split(
            "\n"
        ):
            line = re.sub(
                r"[ \t]+",
                " ",
                line
            ).strip()

            lines.append(
                line
            )

        return "\n".join(
            lines
        ).strip()
