import os
from groq import Groq

class AIClient:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        # 1. إنشاء سجل المحادثة وتحديد تعليمات النظام (System Prompt)
        self.history = [
            {
                "role": "system",
                "content": (
                    "أنت مساعد صوتي ذكي ومفيد يتحدث باللغة العربية بطلاقة. "
                    "إجاباتك يجب أن تكون مختصرة ومباشرة ومناسبة للقراءة الصوتية. "
                    "تجاهل الأخطاء الإملائية الناتجة عن محول الصوت لنص (STT). "
                    "لا تستخدم الإيموجي أو التنسيقات الخاصة أو الرموز الغريبة في إجاباتك."
                )
            }
        ]

    def get_response(self, user_text):
        try:
            # 2. إضافة نص المستخدم الحالي إلى السجل
            self.history.append({"role": "user", "content": user_text})

            # 3. الحفاظ على حجم السجل (مثلاً الاحتفاظ بآخر 10 رسائل فقط لتجنب استهلاك الـ Tokens)
            if len(self.history) > 11:
                self.history = [self.history[0]] + self.history[-10:]

            # 4. إرسال السجل بالكامل لـ Groq API
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",  # أو النموذج المعين لديك
                messages=self.history,
                temperature=0.6,
            )

            bot_reply = response.choices[0].message.content

            # 5. حفظ رد الذكاء الاصطناعي في السجل
            self.history.append({"role": "assistant", "content": bot_reply})

            return bot_reply

        except Exception as e:
            return f"حدث خطأ في الاتصال: {str(e)}"

    def clear_history(self):
        """دالة لإعادة ضبط المحادثة عند الحاجة"""
        self.history = [self.history[0]]
