import ctypes
import os
import re
import threading

from kivy.utils import platform


class LocalQwenClient:
    """
    In-process Local Qwen3.5 client for Voice Assistant 811.

    Runtime path:
    Kivy/Python -> ctypes -> libqwen811.so -> llama.cpp -> GGUF

    No HTTP server, browser, Termux, or remote fallback is used.
    The GGUF model itself is selected separately and must live in a normal
    filesystem path (the Android picker stage will import it to app-private
    storage before calling set_model_path()).
    """

    SYSTEM_PROMPT = (
        "أنت 811، مساعد شخصي ذكي باللغة العربية. "
        "أجب بوضوح ودقة وبأسلوب طبيعي ومختصر ما لم يطلب المستخدم التفصيل. "
        "لا تخترع معلومات أو هوية أو شركة أو مطوراً غير معروف. "
        "لا تعرض التفكير الداخلي أو وسوم <think> في الرد."
    )

    CONTEXT_SIZE = 2048
    THREADS = 4
    MAX_TOKENS = 256
    ABI_VERSION = 1

    def __init__(self):
        self.model_path = ""
        self.model_loaded = False
        self.history = []

        self._lib = None
        self._handle = None
        self._native_path = ""
        self._lock = threading.RLock()

    # =====================================================
    # PUBLIC STATE
    # =====================================================

    def is_available(self):
        return bool(
            self.model_loaded
            and self._handle
            and self._lib is not None
        )

    def native_engine_available(self):
        try:
            self._ensure_native_library()
            return True
        except Exception:
            return False

    def get_native_library_path(self):
        try:
            self._ensure_native_library()
            return self._native_path
        except Exception:
            return ""

    # =====================================================
    # MODEL PATH / LIFECYCLE
    # =====================================================

    def set_model_path(self, model_path):
        model_path = str(model_path or "").strip()

        if not model_path:
            return False

        if not model_path.lower().endswith(".gguf"):
            return False

        with self._lock:
            if (
                self.model_loaded
                and self.model_path == model_path
            ):
                return True

            self._destroy_locked()
            self.model_path = model_path
            self.history = []

        return True

    def load_model(self):
        """
        Load Qwen3.5 2B Q4_K_M from self.model_path.

        This performs heavy native work and should be called from a worker
        thread, never from the Kivy/Android UI thread.
        """
        with self._lock:
            if not self.model_path:
                return {
                    "success": False,
                    "message": "لم يتم اختيار ملف Qwen بصيغة GGUF بعد."
                }

            if not self.model_path.lower().endswith(".gguf"):
                return {
                    "success": False,
                    "message": "الملف المختار ليس ملف GGUF."
                }

            if not os.path.isfile(self.model_path):
                return {
                    "success": False,
                    "message": (
                        "تعذر الوصول إلى ملف النموذج. "
                        "اختر ملف GGUF مرة أخرى."
                    )
                }

            try:
                self._ensure_native_library()
            except Exception as exc:
                self.model_loaded = False
                return {
                    "success": False,
                    "message": (
                        "تعذر تشغيل محرك Local Qwen داخل التطبيق.\n"
                        + str(exc)
                    )
                }

            self._destroy_locked()

            path_bytes = self.model_path.encode(
                "utf-8",
                errors="strict"
            )

            handle_value = self._lib.qwen811_load(
                path_bytes,
                int(self.CONTEXT_SIZE),
                int(self.THREADS)
            )

            if not handle_value:
                self.model_loaded = False
                return {
                    "success": False,
                    "message": self._friendly_native_error(
                        self._last_native_error()
                    )
                }

            self._handle = ctypes.c_void_p(
                handle_value
            )
            self.model_loaded = True
            self.history = []

            return {
                "success": True,
                "message": (
                    "تم تحميل Qwen3.5 2B محلياً بنجاح. "
                    "يمكنك استخدام Local Qwen بدون إنترنت."
                )
            }

    def unload_model(self):
        with self._lock:
            self._destroy_locked()
            self.history = []

    def close(self):
        self.unload_model()

    # =====================================================
    # CHAT
    # =====================================================

    def get_response(self, user_text):
        user_text = self._clean_text(
            user_text
        )

        if not user_text:
            return "لم أستلم نصاً واضحاً."

        with self._lock:
            if not self.is_available():
                return (
                    "Local Qwen غير محمّل بعد. "
                    "اختر ملف Qwen3.5 2B GGUF ثم انتظر اكتمال التحميل."
                )

            prompt, fitted_history = (
                self._fit_prompt_to_context(
                    user_text
                )
            )

            if not prompt:
                return (
                    "الرسالة أكبر من سعة الذاكرة النصية المحلية. "
                    "اختصرها ثم حاول مرة أخرى."
                )

            output_ptr = ctypes.c_void_p()

            status = self._lib.qwen811_generate(
                self._handle,
                prompt.encode(
                    "utf-8",
                    errors="strict"
                ),
                int(self.MAX_TOKENS),
                ctypes.byref(
                    output_ptr
                )
            )

            if status != 0:
                native_error = (
                    self._last_native_error()
                )

                if status == 2:
                    return "تم إيقاف توليد الرد."

                if status == 3:
                    return (
                        "المحادثة تجاوزت سعة Local Qwen. "
                        "امسح المحادثة أو اختصر الرسالة ثم حاول مرة أخرى."
                    )

                return self._friendly_native_error(
                    native_error
                )

            if not output_ptr.value:
                return (
                    "لم يُرجع Local Qwen نصاً."
                )

            try:
                raw = ctypes.string_at(
                    output_ptr.value
                ).decode(
                    "utf-8",
                    errors="replace"
                )
            finally:
                self._lib.qwen811_free_text(
                    output_ptr
                )

            response = self.clean_model_output(
                raw
            )

            if not response:
                response = (
                    "لم يُرجع Local Qwen رداً واضحاً."
                )

            self.history = (
                list(fitted_history)
                + [
                    {
                        "role": "user",
                        "content": user_text
                    },
                    {
                        "role": "assistant",
                        "content": response
                    }
                ]
            )

            # Six full user/assistant turns is a conservative hard bound for
            # the initial 2048-token mobile configuration.
            self._trim_history_turns(
                max_turns=6
            )

            return response

    def clear_history(self):
        with self._lock:
            self.history = []

    def cancel(self):
        """
        Cancellation is intentionally lock-free.

        The native engine uses an atomic cancellation flag, so this call can
        interrupt qwen811_generate() while another worker owns self._lock.
        """
        lib = self._lib
        handle = self._handle

        if (
            lib is None
            or not handle
        ):
            return

        try:
            lib.qwen811_cancel(
                handle
            )
        except Exception:
            pass

    # =====================================================
    # QWEN3.5 TEXT CHAT TEMPLATE
    # =====================================================

    def _format_prompt(
        self,
        user_text,
        history=None
    ):
        """
        Text-only Qwen3.5 chat template, with thinking disabled.
        """
        if history is None:
            history = self.history

        parts = [
            "<|im_start|>system\n",
            self.SYSTEM_PROMPT,
            "<|im_end|>\n"
        ]

        for message in history:
            role = str(
                message.get("role", "")
            ).strip().lower()

            content = self._clean_text(
                message.get("content", "")
            )

            if (
                role not in (
                    "user",
                    "assistant"
                )
                or not content
            ):
                continue

            parts.extend(
                [
                    "<|im_start|>",
                    role,
                    "\n",
                    content,
                    "<|im_end|>\n"
                ]
            )

        parts.extend(
            [
                "<|im_start|>user\n",
                user_text,
                "<|im_end|>\n",
                "<|im_start|>assistant\n",
                "<think>\n\n</think>\n\n"
            ]
        )

        return "".join(
            parts
        )

    def _fit_prompt_to_context(
        self,
        user_text
    ):
        history = list(
            self.history
        )

        while True:
            prompt = self._format_prompt(
                user_text,
                history=history
            )

            token_count = (
                self._lib
                .qwen811_token_count(
                    self._handle,
                    prompt.encode(
                        "utf-8",
                        errors="strict"
                    )
                )
            )

            if token_count < 0:
                return None, []

            if (
                token_count
                + int(self.MAX_TOKENS)
                + 1
                <= int(self.CONTEXT_SIZE)
            ):
                return prompt, history

            if not history:
                return None, []

            history = (
                self._drop_oldest_turn(
                    history
                )
            )

    # =====================================================
    # NATIVE LIBRARY
    # =====================================================

    def _ensure_native_library(self):
        if self._lib is not None:
            return

        native_path = (
            self._resolve_native_library_path()
        )

        if not native_path:
            raise RuntimeError(
                "لم يتم العثور على libqwen811.so داخل التطبيق."
            )

        if not os.path.isfile(
            native_path
        ):
            raise RuntimeError(
                "مكتبة libqwen811.so غير موجودة في مسار Android الأصلي."
            )

        lib = ctypes.CDLL(
            native_path
        )

        lib.qwen811_abi_version.argtypes = []
        lib.qwen811_abi_version.restype = (
            ctypes.c_int
        )

        lib.qwen811_last_error.argtypes = []
        lib.qwen811_last_error.restype = (
            ctypes.c_char_p
        )

        lib.qwen811_load.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int
        ]
        lib.qwen811_load.restype = (
            ctypes.c_void_p
        )

        lib.qwen811_token_count.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p
        ]
        lib.qwen811_token_count.restype = (
            ctypes.c_int
        )

        lib.qwen811_generate.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.POINTER(
                ctypes.c_void_p
            )
        ]
        lib.qwen811_generate.restype = (
            ctypes.c_int
        )

        lib.qwen811_free_text.argtypes = [
            ctypes.c_void_p
        ]
        lib.qwen811_free_text.restype = None

        lib.qwen811_cancel.argtypes = [
            ctypes.c_void_p
        ]
        lib.qwen811_cancel.restype = None

        lib.qwen811_destroy.argtypes = [
            ctypes.c_void_p
        ]
        lib.qwen811_destroy.restype = None

        abi = int(
            lib.qwen811_abi_version()
        )

        if abi != int(
            self.ABI_VERSION
        ):
            raise RuntimeError(
                "إصدار محرك Local Qwen غير متوافق مع التطبيق."
            )

        self._lib = lib
        self._native_path = native_path

    def _resolve_native_library_path(self):
        if platform == "android":
            try:
                from jnius import autoclass

                PythonActivity = autoclass(
                    "org.kivy.android.PythonActivity"
                )

                activity = (
                    PythonActivity.mActivity
                )

                if activity is not None:
                    native_dir = str(
                        activity
                        .getApplicationInfo()
                        .nativeLibraryDir
                    )

                    candidate = os.path.join(
                        native_dir,
                        "libqwen811.so"
                    )

                    if os.path.isfile(
                        candidate
                    ):
                        return candidate
            except Exception:
                pass

        # Developer/non-Android fallback matching the repository layout.
        base_dir = os.path.dirname(
            os.path.abspath(__file__)
        )

        candidate = os.path.join(
            base_dir,
            "libs",
            "arm64-v8a",
            "libqwen811.so"
        )

        if os.path.isfile(
            candidate
        ):
            return candidate

        return ""

    def _last_native_error(self):
        if self._lib is None:
            return ""

        try:
            raw = (
                self._lib
                .qwen811_last_error()
            )

            if not raw:
                return ""

            if isinstance(
                raw,
                bytes
            ):
                return raw.decode(
                    "utf-8",
                    errors="replace"
                ).strip()

            return str(raw).strip()

        except Exception:
            return ""

    def _destroy_locked(self):
        if (
            self._lib is not None
            and self._handle
        ):
            try:
                self._lib.qwen811_destroy(
                    self._handle
                )
            except Exception:
                pass

        self._handle = None
        self.model_loaded = False

    # =====================================================
    # HISTORY
    # =====================================================

    def _drop_oldest_turn(
        self,
        history
    ):
        history = list(
            history
        )

        if not history:
            return []

        if (
            len(history) >= 2
            and history[0].get("role") == "user"
            and history[1].get("role") == "assistant"
        ):
            return history[2:]

        return history[1:]

    def _trim_history_turns(
        self,
        max_turns
    ):
        max_messages = max(
            0,
            int(max_turns) * 2
        )

        while len(
            self.history
        ) > max_messages:
            self.history = (
                self._drop_oldest_turn(
                    self.history
                )
            )

    # =====================================================
    # OUTPUT / ERROR CLEANING
    # =====================================================

    def clean_model_output(
        self,
        text
    ):
        text = str(
            text or ""
        )

        text = re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=(
                re.DOTALL
                | re.IGNORECASE
            )
        )

        text = text.replace(
            "<think>",
            ""
        ).replace(
            "</think>",
            ""
        )

        text = text.replace(
            "<|im_end|>",
            ""
        ).replace(
            "<|im_start|>",
            ""
        )

        return self._clean_text(
            text
        )

    def _friendly_native_error(
        self,
        native_error
    ):
        error = str(
            native_error or ""
        ).strip()

        lower = error.lower()

        if (
            "qwen35 architecture"
            in lower
        ):
            return (
                "الملف ليس نموذج Qwen3.5 الصحيح. "
                "اختر Qwen3.5 2B بصيغة GGUF."
            )

        if (
            "q4_k_m"
            in lower
            or "quantization"
            in lower
        ):
            return (
                "اختر نسخة Qwen3.5 2B بتكميم Q4_K_M."
            )

        if (
            "2b model size"
            in lower
        ):
            return (
                "اختر نموذج Qwen3.5 بحجم 2B."
            )

        if (
            "available memory"
            in lower
            or "insufficient memory"
            in lower
            or "allocation failed"
            in lower
        ):
            return (
                "ذاكرة الهاتف غير كافية لتحميل Local Qwen حالياً. "
                "أغلق التطبيقات الأخرى ثم حاول مرة أخرى."
            )

        if (
            "conversation exceeds context"
            in lower
        ):
            return (
                "المحادثة طويلة على الذاكرة المحلية. "
                "امسح المحادثة أو اختصرها ثم حاول مرة أخرى."
            )

        if "cancelled" in lower:
            return "تم إيقاف توليد الرد."

        if error:
            return (
                "خطأ في Local Qwen:\n"
                + error
            )

        return (
            "حدث خطأ غير معروف داخل محرك Local Qwen."
        )

    def _clean_text(
        self,
        text
    ):
        if text is None:
            return ""

        text = str(
            text
        )

        text = text.replace(
            "\r\n",
            "\n"
        ).replace(
            "\r",
            "\n"
        )

        text = re.sub(
            r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]",
            "",
            text
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

            if line:
                lines.append(
                    line
                )

        return "\n".join(
            lines
        ).strip()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
