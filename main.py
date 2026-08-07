from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button

class MainApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        self.label = Label(text="Voice Assistant 811\nStatus: Core Engine Active", halign="center")
        btn = Button(text="Test System", size_hint=(1, 0.2))
        btn.bind(on_press=self.on_click)
        
        layout.add_widget(self.label)
        layout.add_widget(btn)
        return layout

    def on_click(self, instance):
        self.label.text = "System Functional!"

if __name__ == "__main__":
    MainApp().run()
