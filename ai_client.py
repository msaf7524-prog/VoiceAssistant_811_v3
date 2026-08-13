import os
from groq import Groq

class AIClient:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        
        # تعليمات النظام لضبط إجابات الذكاء الاصطناعي
        self.system_instructions = {
            "role": "system",
            "content": (
                "أنت مساعد صوتي ذكي ومحترف يتحدث باللغة العربية بطلاقة. "
                "إجاباتك يجب أن تكون مختصرة ومباشرة ودقيقة ومناسبة لنطق القارئ الصوتي. "
                "يمنع تماماً استخدام الإيموجي أو الرموز التعبيرية أو التشكيل الزائد أو علامات Markdown الخاصة. "
                "تجاهل الأخطاء الإملائية الناتجة عن محول الصوت إلى نص (STT). "
                "تذكر دائماً سياق المحادثة واجعل إجاباتك مرتبطة بما تم نقاشه سابقاً."
            )
        }
        # إنشاء سجل المحادثة
        self.history = [self.system_instructions]

    def get_response(self, user_text):
        try:
            # إضافة رسالة المستخدم إلى السجل
            self.history.append({"role": "user", "content": user_text})

            # الحفاظ على الذاكرة لآخر 10 رسائل فقط لعدم استهلاك الموارد
            if len(self.history) > 11:
                self.history = [self.history[0]] + self.history[-10:]

            # إرسال المحادثة بالكامل لنموذج Groq
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=self.history,
                temperature=0.5,
            )

            bot_reply = response.choices[0].message.content

            # إضافة رد الذكاء الاصطناعي إلى السجل
            self.history.append({"role": "assistant", "content": bot_reply})

            return bot_reply

        except Exception as e:
            return f"حدث خطأ في الاتصال: {str(e)}"

    def clear_history(self):
        """دالة لإعادة ضبط المحادثة والذاكرة عند الحاجة"""
        self.history = [self.system_instructions]
