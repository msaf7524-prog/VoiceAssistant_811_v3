from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.utils import platform


class VoiceAssistantApp(App):
    def build(self):
        self.root_layout = BoxLayout(
            orientation="vertical",
            padding=24,
            spacing=16
        )

        self.title_label = Label(
            text="Voice Assistant 811\nStatus: Phase 2 Ready",
            halign="center",
            valign="middle",
            font_size="24sp"
        )
        self.title_label.bind(size=self._update_text_size)

        self.info_label = Label(
            text="Android bridge not tested yet.",
            halign="center",
            valign="middle",
            font_size="18sp"
        )
        self.info_label.bind(size=self._update_text_size)

        self.test_button = Button(
            text="Test Android Bridge",
            size_hint_y=None,
            height="56dp",
            font_size="20sp"
        )
        self.test_button.bind(on_press=self.test_android_bridge)

        self.root_layout.add_widget(self.title_label)
        self.root_layout.add_widget(self.info_label)
        self.root_layout.add_widget(self.test_button)

        Clock.schedule_once(self.auto_test, 0.5)
        return self.root_layout

    def _update_text_size(self, instance, value):
        instance.text_size = value

    def auto_test(self, dt):
        self.test_android_bridge(None)

    def test_android_bridge(self, instance):
        lines = []

        if platform == "android":
            lines.append("Platform: Android")

            try:
                from jnius import autoclass

                Build = autoclass("android.os.Build")
                Version = autoclass("android.os.Build$VERSION")

                manufacturer = str(Build.MANUFACTURER)
                model = str(Build.MODEL)
                sdk_int = int(Version.SDK_INT)

                lines.append(f"Device: {manufacturer} {model}")
                lines.append(f"Android API: {sdk_int}")
                lines.append("pyjnius: OK")
            except Exception as e:
                lines.append(f"pyjnius error: {e}")

            try:
                from plyer import storagepath

                documents_dir = storagepath.get_documents_dir()
                lines.append(f"Documents Dir: {documents_dir}")
                lines.append("plyer: OK")
            except Exception as e:
                lines.append(f"plyer error: {e}")
        else:
            lines.append(f"Platform: {platform}")
            lines.append("Run this APK on Android to test pyjnius and plyer.")

        self.info_label.text = "\n".join(lines)


if __name__ == "__main__":
    VoiceAssistantApp().run()
