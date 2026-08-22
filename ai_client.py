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

        # =====================================================
        # Groq URLs
        # =====================================================

        self.groq_base_url = (
            "https://api.groq.com/openai/v1"
        )

        self.groq_chat_url = (
            self.groq_base_url +
            "/chat/completions"
        )

        self.groq_models_url = (
            self.groq_base_url +
            "/models"
        )

        # =====================================================
        # الموديلات الرسمية التي نفضلها
        # =====================================================

        self.preferred_models = [

            "llama-3.1-8b-instant",

            "llama-3.3-70b-versatile",

            "openai/gpt-oss-20b",

            "openai/gpt-oss-120b",

        ]

        # سيتم تحديده بعد فحص الموديلات
        self.groq_model = None

        # =====================================================
        # تعليمات المساعد
        # =====================================================

        self.system_instruction = (
            "أنت مساعد صوتي ذكي واسمك 811. "
            "تحدث باللغة العربية بطلاقة. "
            "كن مختصرًا ومباشرًا وواضحًا. "
            "لا تستخدم Markdown أو رموزًا غير ضرورية."
        )

        # =====================================================
        # سجل المحادثة
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

        try:

            print("")
            print("====================================")
            print("811 AI CLIENT START")
            print("====================================")

            if not user_text or not user_text.strip():

                return (
                    "ERROR: لم يتم إدخال نص."
                )

            user_text = user_text.strip()

            # -------------------------------------------------
            # فحص المفتاح
            # -------------------------------------------------

            if not self.groq_key:

                return (
                    "GROQ ERROR\n\n"
                    "مفتاح Groq API فارغ."
                )

            print(
                "GROQ KEY:",
                self._mask_key(self.groq_key)
            )

            # -------------------------------------------------
            # اكتشاف موديل متاح
            # -------------------------------------------------

            print(
                "GROQ MODEL:",
                self.groq_model
            )

            if not self.groq_model:

                model_result = (
                    self._detect_available_model()
                )

                if not model_result["success"]:

                    return (
                        "GROQ MODEL DISCOVERY ERROR\n\n"
                        + model_result["error"]
                    )

                self.groq_model = (
                    model_result["model"]
                )

            print(
                "SELECTED GROQ MODEL:",
                self.groq_model
            )

            # -------------------------------------------------
            # إرسال الطلب
            # -------------------------------------------------

            result = self._call_groq(
                user_text
            )

            if result["success"]:

                return result["text"]

            # -------------------------------------------------
            # إذا كان الموديل غير موجود
            # نحاول اكتشاف موديل آخر مرة واحدة
            # -------------------------------------------------

            error_text = result["error"]

            if (
                "model_not_found" in error_text.lower()
                or "does not exist" in error_text.lower()
                or "404" in error_text
            ):

                print(
                    "MODEL FAILED - TRYING DISCOVERY AGAIN"
                )

                self.groq_model = None

                model_result = (
                    self._detect_available_model()
                )

                if model_result["success"]:

                    self.groq_model = (
                        model_result["model"]
                    )

                    print(
                        "NEW MODEL:",
                        self.groq_model
                    )

                    result = self._call_groq(
                        user_text
                    )

                    if result["success"]:

                        return result["text"]

                    error_text = (
                        result["error"]
                    )

            return (
                "GROQ ERROR\n\n"
                + error_text
            )

        except Exception as e:

            print(
                "========== AI CLIENT FATAL ERROR =========="
            )

            print(
                "TYPE:",
                type(e).__name__
            )

            print(
                "EXCEPTION:",
                repr(e)
            )

            return (
                "AI CLIENT ERROR\n\n"
                f"Type: {type(e).__name__}\n"
                f"Exception: {repr(e)}"
            )

    # =========================================================
    # اكتشاف الموديل المتاح
    # =========================================================

    def _detect_available_model(self):

        try:

            headers = {
                "Authorization":
                    f"Bearer {self.groq_key}",

                "Content-Type":
                    "application/json",

                "Accept":
                    "application/json"
            }

            print("")
            print(
                "===================================="
            )
            print(
                "GROQ MODEL DISCOVERY"
            )
            print(
                "===================================="
            )

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
                "MODELS RAW:"
            )

            print(
                response.text[:8000]
            )

            # -------------------------------------------------
            # HTTP error
            # -------------------------------------------------

            if response.status_code != 200:

                return {
                    "success": False,
                    "model": None,
                    "error":
                        self._format_http_error(
                            response
                        )
                }

            # -------------------------------------------------
            # JSON
            # -------------------------------------------------

            try:

                data = response.json()

            except Exception as e:

                return {
                    "success": False,
                    "model": None,
                    "error": (
                        "فشل تحليل قائمة موديلات Groq.\n"
                        f"Type: {type(e).__name__}\n"
                        f"Exception: {repr(e)}\n\n"
                        f"Raw:\n"
                        f"{response.text[:5000]}"
                    )
                }

            # -------------------------------------------------
            # استخراج الموديلات
            # -------------------------------------------------

            models = data.get(
                "data",
                []
            )

            available_models = []

            for item in models:

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

            print(
                "AVAILABLE MODELS:"
            )

            for model in available_models:

                print(
                    " -",
                    model
                )

            # -------------------------------------------------
            # لا توجد موديلات
            # -------------------------------------------------

            if not available_models:

                return {
                    "success": False,
                    "model": None,
                    "error": (
                        "Groq أعاد قائمة موديلات فارغة."
                    )
                }

            # =================================================
            # اختيار الموديل المفضل
            # =================================================

            for preferred in (
                self.preferred_models
            ):

                if preferred in (
                    available_models
                ):

                    print(
                        "PREFERRED MODEL FOUND:",
                        preferred
                    )

                    return {
                        "success": True,
                        "model": preferred,
                        "error": ""
                    }

            # =================================================
            # اختيار موديل نصي تلقائي
            # =================================================

            blocked_words = [

                "whisper",
                "tts",
                "speech",
                "guard",
                "embed",
                "moderation"

            ]

            candidates = []

            for model_id in (
                available_models
            ):

                low = model_id.lower()

                blocked = False

                for word in blocked_words:

                    if word in low:

                        blocked = True

                        break

                if not blocked:

                    candidates.append(
                        model_id
                    )

            if candidates:

                selected = candidates[0]

                print(
                    "AUTO SELECTED MODEL:",
                    selected
                )

                return {
                    "success": True,
                    "model": selected,
                    "error": ""
                }

            # =================================================
            # فشل الاختيار
            # =================================================

            return {
                "success": False,
                "model": None,
                "error": (
                    "تم العثور على موديلات Groq "
                    "لكن لم نجد موديل محادثة مناسبًا.\n\n"
                    "Available models:\n"
                    +
                    "\n".join(
                        available_models[:100]
                    )
                )
            }

        # =====================================================
        # Timeout
        # =====================================================

        except requests.exceptions.Timeout as e:

            print(
                "MODEL DISCOVERY TIMEOUT:",
                repr(e)
            )

            return {
                "success": False,
                "model": None,
                "error": (
                    "انتهت مهلة الاتصال بـ Groq.\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

        # =====================================================
        # Connection
        # =====================================================

        except requests.exceptions.ConnectionError as e:

            print(
                "MODEL DISCOVERY CONNECTION ERROR:",
                repr(e)
            )

            return {
                "success": False,
                "model": None,
                "error": (
                    "تعذر الاتصال بخادم Groq.\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

        # =====================================================
        # General
        # =====================================================

        except Exception as e:

            print(
                "MODEL DISCOVERY UNKNOWN ERROR:",
                repr(e)
            )

            return {
                "success": False,
                "model": None,
                "error": (
                    "خطأ غير متوقع أثناء اكتشاف الموديل.\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

    # =========================================================
    # إرسال Chat Completion
    # =========================================================

    def _call_groq(self, user_text):

        try:

            # -------------------------------------------------
            # نسخ التاريخ
            # -------------------------------------------------

            messages = list(
                self.history
            )

            messages.append(
                {
                    "role": "user",
                    "content": user_text
                }
            )

            # -------------------------------------------------
            # منع تضخم المحادثة
            # -------------------------------------------------

            if len(messages) > 7:

                messages = (
                    [messages[0]]
                    +
                    messages[-6:]
                )

            # -------------------------------------------------
            # البيانات
            # -------------------------------------------------

            payload = {

                "model":
                    self.groq_model,

                "messages":
                    messages,

                "temperature":
                    0.3,

                "max_tokens":
                    512,

                "stream":
                    False
            }

            headers = {

                "Authorization":
                    f"Bearer {self.groq_key}",

                "Content-Type":
                    "application/json",

                "Accept":
                    "application/json"
            }

            print("")
            print(
                "===================================="
            )
            print(
                "GROQ CHAT REQUEST"
            )
            print(
                "===================================="
            )

            print(
                "MODEL:",
                self.groq_model
            )

            print(
                "URL:",
                self.groq_chat_url
            )

            print(
                "PROMPT:",
                user_text
            )

            # -------------------------------------------------
            # الطلب
            # -------------------------------------------------

            response = requests.post(

                self.groq_chat_url,

                json=payload,

                headers=headers,

                timeout=30
            )

            # -------------------------------------------------
            # طباعة الحالة
            # -------------------------------------------------

            print(
                "CHAT STATUS:",
                response.status_code
            )

            print(
                "CHAT RAW:"
            )

            print(
                response.text[:8000]
            )

            # -------------------------------------------------
            # HTTP error
            # -------------------------------------------------

            if response.status_code != 200:

                return {

                    "success":
                        False,

                    "text":
                        "",

                    "error":
                        self._format_http_error(
                            response
                        )
                }

            # -------------------------------------------------
            # JSON
            # -------------------------------------------------

            try:

                data = response.json()

            except Exception as e:

                return {

                    "success":
                        False,

                    "text":
                        "",

                    "error": (
                        "فشل تحليل استجابة Groq.\n"
                        f"Type: {type(e).__name__}\n"
                        f"Exception: {repr(e)}\n\n"
                        f"Raw:\n"
                        f"{response.text[:5000]}"
                    )
                }

            # -------------------------------------------------
            # استخراج الإجابة
            # -------------------------------------------------

            try:

                choices = data.get(
                    "choices",
                    []
                )

                if not choices:

                    raise ValueError(
                        "choices فارغة"
                    )

                message = choices[0].get(
                    "message",
                    {}
                )

                answer = message.get(
                    "content",
                    ""
                )

            except Exception as e:

                return {

                    "success":
                        False,

                    "text":
                        "",

                    "error": (
                        "بنية استجابة Groq غير متوقعة.\n"
                        f"Type: {type(e).__name__}\n"
                        f"Exception: {repr(e)}\n\n"
                        "JSON:\n"
                        +
                        json.dumps(
                            data,
                            ensure_ascii=False
                        )[:5000]
                    )
                }

            # -------------------------------------------------
            # تنظيف
            # -------------------------------------------------

            answer = self._clean_text(
                answer
            )

            if not answer:

                return {

                    "success":
                        False,

                    "text":
                        "",

                    "error":
                        "Groq أعاد ردًا فارغًا."
                }

            # -------------------------------------------------
            # إضافة للمحادثة
            # -------------------------------------------------

            self.history.append(

                {
                    "role":
                        "user",

                    "content":
                        user_text
                }
            )

            self.history.append(

                {
                    "role":
                        "assistant",

                    "content":
                        answer
                }
            )

            print(
                "GROQ ANSWER:",
                answer
            )

            return {

                "success":
                    True,

                "text":
                    answer,

                "error":
                    ""
            }

        # =====================================================
        # Timeout
        # =====================================================

        except requests.exceptions.Timeout as e:

            print(
                "GROQ TIMEOUT:",
                repr(e)
            )

            return {

                "success":
                    False,

                "text":
                    "",

                "error": (
                    "REQUEST TIMEOUT\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

        # =====================================================
        # SSL
        # =====================================================

        except requests.exceptions.SSLError as e:

            print(
                "GROQ SSL ERROR:",
                repr(e)
            )

            return {

                "success":
                    False,

                "text":
                    "",

                "error": (
                    "SSL/TLS ERROR\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

        # =====================================================
        # Connection
        # =====================================================

        except requests.exceptions.ConnectionError as e:

            print(
                "GROQ CONNECTION ERROR:",
                repr(e)
            )

            return {

                "success":
                    False,

                "text":
                    "",

                "error": (
                    "CONNECTION ERROR\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

        # =====================================================
        # General
        # =====================================================

        except Exception as e:

            print(
                "GROQ UNKNOWN ERROR:",
                repr(e)
            )

            return {

                "success":
                    False,

                "text":
                    "",

                "error": (
                    "UNKNOWN ERROR\n"
                    f"Type: {type(e).__name__}\n"
                    f"Exception: {repr(e)}"
                )
            }

    # =========================================================
    # تنسيق خطأ HTTP
    # =========================================================

    def _format_http_error(self, response):

        try:

            data = response.json()

            print(
                "HTTP ERROR JSON:",
                json.dumps(
                    data,
                    ensure_ascii=False
                )[:5000]
            )

            if isinstance(
                data,
                dict
            ):

                error = data.get(
                    "error"
                )

                if isinstance(
                    error,
                    dict
                ):

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
                    +
                    json.dumps(
                        data,
                        ensure_ascii=False
                    )[:4000]
                )

        except Exception as e:

            print(
                "HTTP ERROR PARSE ERROR:",
                repr(e)
            )

            return (
                f"HTTP {response.status_code}\n"
                f"Type: {type(e).__name__}\n"
                f"Exception: {repr(e)}\n"
                f"Raw: {response.text[:5000]}"
            )

        return (
            f"HTTP {response.status_code}\n"
            f"Raw: {response.text[:5000]}"
        )

    # =========================================================
    # إخفاء جزء من مفتاح API في Logcat
    # =========================================================

    def _mask_key(self, key):

        if not key:

            return "(empty)"

        if len(key) <= 8:

            return "********"

        return (
            key[:4]
            +
            "********"
            +
            key[-4:]
        )

    # =========================================================
    # تنظيف الإجابة
    # =========================================================

    def _clean_text(self, text):

        if not text:

            return ""

        text = str(text)

        # إزالة Markdown البسيط

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
                "role":
                    "system",

                "content":
                    self.system_instruction
            }

        ]

        self.groq_model = None
