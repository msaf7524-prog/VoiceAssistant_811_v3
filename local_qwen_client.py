import re


class LocalQwenClient:
    """
    Safe first step for Local Qwen integration.

    This file does not run llama.cpp yet.
    It only prepares the local provider without breaking the current APK build.
    """

    SYSTEM_PROMPT = (
        "أنت 811، مساعد شخصي ذكي باللغة العربية. "
        "أجب بوضوح ودقة، ولا تخترع هوية أو شركة أو مطوراً غير معروف. "
        "لا تعرض وسوم <think> أو التفكير الداخلي في الرد."
    )

    def __init__(self):
        self.model_path = ""
        self.model_loaded = False

    def is_available(self):
        return self.model_loaded

    def set_model_path(self, model_path):
        self.model_path = str(model_path or "").strip()
        self.model_loaded = False

        if not self.model_path:
            return False

        lower_path = self.model_path.lower()

        if not lower_path.endswith(".gguf"):
            return False

        return True

    def load_model(self):
        """
        Placeholder.

        The real Android llama.cpp loader will be connected in the next step.
        """
        if not self.model_path:
            return {
                "success": False,
                "message": "لم يتم اختيار ملف GGUF بعد."
            }

        self.model_loaded = False

        return {
            "success": False,
            "message": (
                "Local Qwen لم يتم ربطه بعد داخل التطبيق. "
                "هذه خطوة تجهيز آمنة فقط."
            )
        }

    def get_response(self, user_text):
        user_text = self._clean_text(user_text)

        if not user_text:
            return "لم أستلم نصاً واضحاً."

        if not self.model_loaded:
            return (
                "Local Qwen غير جاهز بعد. "
                "سنربطه في الخطوة التالية بدون التأثير على Gemini و Groq."
            )

        return "Local Qwen جاهز للربط في الخطوة التالية."

    def clean_model_output(self, text):
        text = self._clean_text(text)

        text = re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE
        )

        text = text.replace("<think>", "")
        text = text.replace("</think>", "")

        return self._clean_text(text)

    def _clean_text(self, text):
        if text is None:
            return ""

        text = str(text)

        text = text.replace("\r\n", "\n").replace("\r", "\n")

        text = re.sub(
            r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]",
            "",
            text
        )

        lines = []

        for line in text.split("\n"):
            line = re.sub(r"[ \t]+", " ", line).strip()
            if line:
                lines.append(line)

        return "\n".join(lines).strip()
