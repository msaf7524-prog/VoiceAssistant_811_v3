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
            text="Voice Assistant 811\nStatus: Phase 3 Ready",
            halign="center",
            valign="middle",
            font_size="24sp"
        )
        self.title_label.bind(size=self._update_text_size)

        self.status_label = Label(
            text="Microphone permission not checked yet.",
            halign="center",
            valign="middle",
            font_size="18sp"
        )
        self.status_label.bind(size=self._update_text_size)

        self.permission_button = Button(
            text="Request Mic Permission",
            size_hint_y=None,
            height="56dp",
            font_size="20sp"
        )
        self.permission_button.bind(on_press=self.request_mic_permission)

        self.test_button = Button(
            text="Test Android & Mic Setup",
            size_hint_y=None,
            height="56dp",
            font_size="20sp"
        )
        self.test_button.bind(on_press=self.test_environment)

        self.root_layout.add_widget(self.title_label)
        self.root_layout.add_widget(self.status_label)
        self.root_layout.add_widget(self.permission_button)
        self.root_layout.add_widget(self.test_button)

        Clock.schedule_once(self.auto_setup, 0.5)
        return self.root_layout

    def _update_text_size(self, instance, value):
        instance.text_size = value

    def auto_setup(self, dt):
        self.test_environment(None)

    def request_mic_permission(self, instance):
        if platform != "android":
            self.status_label.text = "Not running on Android."
            return

        try:
            from android.permissions import request_permissions, Permission, check_permission
            already_granted = check_permission(Permission.RECORD_AUDIO)
            if already_granted:
                self.status_label.text = "Microphone permission already granted."
                return

            request_permissions([Permission.RECORD_AUDIO], self.on_permissions_result)
            self.status_label.text = "Requesting microphone permission..."
        except Exception as e:
            self.status_label.text = f"Permission request error: {e}"

    def on_permissions_result(self, permissions, grants):
        try:
            granted = True
            for g in grants:
                if not g:
                    granted = False
                    break

            if granted:
                self.status_label.text = "Microphone permission granted."
            else:
                self.status_label.text = "Microphone permission denied."
        except Exception as e:
            self.status_label.text = f"Permission callback error: {e}"

    def test_environment(self, instance):
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

            try:
                from android.permissions import check_permission, Permission
                mic_ok = check_permission(Permission.RECORD_AUDIO)
                lines.append(f"RECORD_AUDIO permission: {'GRANTED' if mic_ok else 'NOT GRANTED'}")
            except Exception as e:
                lines.append(f"android.permissions error: {e}")
        else:
            lines.append(f"Platform: {platform}")
            lines.append("Run this APK on Android to test permissions and mic setup.")

        self.status_label.text = "\n".join(lines)


if __name__ == "__main__":
    VoiceAssistantApp().run()
