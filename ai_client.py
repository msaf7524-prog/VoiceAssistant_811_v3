import os
import re
import requests

class AIClient:
    def __init__(self, api_key=None):
        # جلب مفتاح API من متغيرات البيئة أو المدخلات
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        
        # نقطة الاتصال الخاصة بـ Gemini 2.0 Flash مع دعم البحث المباشر
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.api_key}"
        
        # توجيه النظام الخاص بالمساعد 811
        self.system_instruction = (
            "أنت مساعد صوتي ذكي واسمك 811. "
            "تحدث باللغة العربية بطلاقة وبأسلوب مختصر ومباشر ومناسب للقراءة الصوتية. "
            "يمنع منعاً باتاً استخدام الإيموجي، التشكيل الزائد، أو علامات Markdown مثل (النجوم * أو الهاشتاق #) "
            "لأن الخط المستخدم في الواجهة لا يدعمها وتظهر كمربعات غريبة. "
            "استخدم ميزة البحث المباشر دائماً لإعطاء إجابات دقيقة ومحدثة عن أسعار الهواتف، المواصفات التقنية في العراق والعالم، والأخبار الحالية."
        )
        
        # سجل المحادثة للربط بين الأسئلة والأجوبة
        self.history = []

    def get_response(self, user_text):
        if not self.api_key:
            return "خطأ: لم يتم ضبط مفتاح GEMINI_API_KEY."

        try:
            # إضافة سؤال المستخدم إلى السجل
            self.history.append({"role": "user", "parts": [{"text": user_text}]})

            # الاحتفاظ بآخر 10 رسائل فقط للحفاظ على الذاكرة وسرعة الاستجابة
            if len(self.history) > 10:
                self.history = self.history[-10:]

            # تجهيز الطلب مع تفعيل أداة البحث المباشر من جوجل (google_search)
            payload = {
                "system_instruction": {
                    "parts": [{"text": self.system_instruction}]
                },
                "contents": self.history,
                "tools": [
                    {"google_search": {}}
                ]
            }

            headers = {"Content-Type": "application/json"}
            
            # إرسال الطلب لـ API
            response = requests.post(self.url, json=payload, headers=headers, timeout=15)
            response_json = response.json()

            if response.status_code == 200:
                candidates = response_json.get("candidates", [])
                if candidates:
                    bot_reply = candidates[0]["content"]["parts"][0]["text"]
                    
                    # تنظيف النص لضمان عدم ظهور رموز تشوه الواجهة
                    bot_reply = self._clean_text(bot_reply)

                    # إضافة رد الذكاء الاصطناعي إلى السجل
                    self.history.append({"role": "model", "parts": [{"text": bot_reply}]})
                    return bot_reply
                else:
                    return "لم أستطع الحصول على إجابة."
            else:
                error_msg = response_json.get("error", {}).get("message", "خطأ في الاتصال")
                return f"خطأ: {error_msg}"

        except Exception as e:
            return f"خطأ في الشبكة: {str(e)}"

    def _clean_text(self, text):
        """تنظيف النص لمنع المربعات الغريبة وتشويه الخط"""
        # إزالة علامات النجوم والتنسيقات (Markdown)
        text = re.sub(r'[*#_~`]', '', text)
        # إزالة الإيموجي والرموز التعبيرية غير المدعومة في الخط
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        return text.strip()

    def clear_history(self):
        """تصفير ذاكرة المحادثة"""
        self.history = []
