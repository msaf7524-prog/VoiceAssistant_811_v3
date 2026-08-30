import os
import json
import math
import re
import threading
import time
import unicodedata
from io import BytesIO

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Ellipse, RoundedRectangle, Line
from kivy.metrics import dp
from kivy.utils import platform

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import arabic_reshaper
from bidi.algorithm import get_display

from ai_client import AIClient


# =========================================================
# VERSION 0.3.1
# =========================================================

__version__ = "0.3.1"


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "Cairo-Regular.ttf")


# =========================================================
# ARABIC FONT
# =========================================================

def _find_phone_arabic_font():
    """Use Android's own Noto Arabic font without placing native Views over Kivy."""
    if platform != "android":
        return ""

    preferred_paths = [
        "/system/fonts/NotoSansArabic-Regular.ttf",
        "/system/fonts/NotoSansArabicUI-Regular.ttf",
        "/system/fonts/NotoNaskhArabic-Regular.ttf",
        "/system/fonts/NotoNaskhArabicUI-Regular.ttf",
        "/system/fonts/NotoKufiArabic-Regular.ttf",
        "/system/fonts/DroidSansArabic.ttf",
        "/system/fonts/DroidSansFallback.ttf",
    ]

    for font_path in preferred_paths:
        if os.path.isfile(font_path):
            return font_path

    # OEMs sometimes rename Noto files. Only accept Arabic Noto/Droid fonts;
    # do not pick an arbitrary OEM font because it may lack presentation forms.
    try:
        font_dir = "/system/fonts"
        if os.path.isdir(font_dir):
            candidates = []
            for filename in os.listdir(font_dir):
                lower = filename.lower()
                if not lower.endswith((".ttf", ".otf")):
                    continue
                if "arab" not in lower:
                    continue
                if "noto" not in lower and "droid" not in lower:
                    continue

                score = 0
                if "notosansarabic" in lower:
                    score += 100
                if "notonaskharabic" in lower:
                    score += 90
                if "notokufiarabic" in lower:
                    score += 80
                if "ui" in lower:
                    score += 8
                if "regular" in lower:
                    score += 6
                if any(x in lower for x in ("bold", "black", "thin", "light")):
                    score -= 20

                candidates.append((score, os.path.join(font_dir, filename)))

            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                return candidates[0][1]
    except Exception as exc:
        print("811: Android Arabic font scan warning:", repr(exc))

    return ""


ARABIC_FONT = "Roboto"
PHONE_ARABIC_FONT_PATH = _find_phone_arabic_font()

if PHONE_ARABIC_FONT_PATH:
    try:
        LabelBase.register(
            name="PhoneArabic",
            fn_regular=PHONE_ARABIC_FONT_PATH
        )
        ARABIC_FONT = "PhoneArabic"
        print(
            "811: Phone Arabic font loaded:",
            PHONE_ARABIC_FONT_PATH
        )
    except Exception as exc:
        print(
            "811: Phone Arabic font registration error:",
            repr(exc)
        )

if ARABIC_FONT == "Roboto":
    if os.path.exists(FONT_PATH):
        try:
            LabelBase.register(
                name="Cairo",
                fn_regular=FONT_PATH
            )
            ARABIC_FONT = "Cairo"
            print("811: Cairo-Regular.ttf loaded as Arabic fallback")
        except Exception as exc:
            print("811: Cairo font registration error:", repr(exc))
    else:
        print("811: Cairo-Regular.ttf NOT FOUND:", FONT_PATH)


# =========================================================
# UNICODE CLEANING
# =========================================================

HIDDEN_UNICODE = (
    "\u061c"
    "\u200b"
    "\u200c"
    "\u200d"
    "\u200e"
    "\u200f"
    "\u202a"
    "\u202b"
    "\u202c"
    "\u202d"
    "\u202e"
    "\u2066"
    "\u2067"
    "\u2068"
    "\u2069"
    "\ufe0e"
    "\ufe0f"
    "\ufeff"
)

# Kivy wraps text after python-bidi has converted Arabic to visual order.
# If a long visual RTL line is wrapped by Kivy, the resulting rows appear
# bottom-to-top. Wrap the logical Arabic text first, then reshape every row.
OUTPUT_ARABIC_WRAP_CHARS = 30

# Disable Arabic ligature substitution. Some fonts/devices can show a missing
# glyph square for presentation-form ligatures even when normal Arabic letters
# are available. Individual letter shaping remains enabled.
ARABIC_RESHAPER = arabic_reshaper.ArabicReshaper(
    configuration={
        "support_ligatures": False,
        "delete_harakat": True,
        "support_zwj": True,
    }
)


def clean_unicode(text):
    if text is None:
        return ""

    text = unicodedata.normalize("NFKC", str(text))

    for char in HIDDEN_UNICODE:
        text = text.replace(char, "")

    cleaned = []

    for char in text:
        if char in ("\n", "\t"):
            cleaned.append(char)
            continue

        if ord(char) < 32:
            continue

        cleaned.append(char)

    text = "".join(cleaned)

    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)

    return "\n".join(lines).strip()


def _wrap_logical_line(line, max_chars):
    """Wrap one logical line on words before applying the bidi transform."""
    if not max_chars or len(line) <= max_chars:
        return [line]

    wrapped_lines = []
    current_words = []

    for word in line.split(" "):
        candidate_words = current_words + [word]
        candidate = " ".join(candidate_words)

        if current_words and len(candidate) > max_chars:
            wrapped_lines.append(" ".join(current_words))
            current_words = [word]
        else:
            current_words = candidate_words

    if current_words:
        wrapped_lines.append(" ".join(current_words))

    return wrapped_lines or [line]


def fix_text(text, wrap_at=None):
    """Prepare text for Kivy, wrapping logical Arabic before bidi shaping."""
    clean_text = clean_unicode(text)

    if not clean_text:
        return ""

    logical_lines = []

    for line in clean_text.split("\n"):
        if (
            wrap_at
            and re.search(r"[\u0600-\u06FF]", line)
        ):
            logical_lines.extend(
                _wrap_logical_line(
                    line,
                    wrap_at
                )
            )
        else:
            logical_lines.append(line)

    display_lines = []

    for line in logical_lines:
        if not line:
            display_lines.append("")
            continue

        if not re.search(r"[\u0600-\u06FF]", line):
            display_lines.append(line)
            continue

        try:
            reshaped = ARABIC_RESHAPER.reshape(line)
            display_lines.append(
                get_display(
                    reshaped,
                    base_dir="R"
                )
            )
        except Exception as exc:
            print(
                "811: Arabic formatting error:",
                repr(exc)
            )
            display_lines.append(line)

    return "\n".join(display_lines)


def clean_for_speech(text):
    text = clean_unicode(text)

    if not text:
        return ""

    text = re.sub(r"[*_~`#]", "", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


# =========================================================
# ANDROID PERMISSIONS
# =========================================================

def request_android_permissions():
    if platform != "android":
        return

    try:
        from android.permissions import request_permissions, Permission

        permissions = [
            Permission.RECORD_AUDIO,
            Permission.INTERNET,
            Permission.ACCESS_NETWORK_STATE,
            Permission.MODIFY_AUDIO_SETTINGS,
        ]

        if hasattr(Permission, "POST_NOTIFICATIONS"):
            permissions.append(Permission.POST_NOTIFICATIONS)

        if hasattr(Permission, "BLUETOOTH_CONNECT"):
            permissions.append(Permission.BLUETOOTH_CONNECT)

        if hasattr(Permission, "BLUETOOTH_SCAN"):
            permissions.append(Permission.BLUETOOTH_SCAN)

        if hasattr(Permission, "BLUETOOTH"):
            permissions.append(Permission.BLUETOOTH)

        if hasattr(Permission, "BLUETOOTH_ADMIN"):
            permissions.append(Permission.BLUETOOTH_ADMIN)

        request_permissions(permissions)
        print("811: Android permissions requested")

    except Exception as exc:
        print("811: Permission error:", repr(exc))


# =========================================================
# STATUS ORB
# =========================================================

class StatusOrb(Widget):
    """Static futuristic voice core. No animation or timers."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.status_color = (0.13, 0.59, 0.95, 1.0)
        self.voice_level = 0.0
        self.wave_bars = None
        self.current_state = "ready"
        self.pulse_phase = 0.0
        self.pulse_energy = 0.0
        self._pulse_last_time = None
        self.bind(pos=self._redraw, size=self._redraw)

    def set_state(self, state):
        colors = {
            "ready": (0.13, 0.59, 0.95, 1.0),
            "listening": (0.00, 0.78, 0.88, 1.0),
            "thinking": (1.00, 0.60, 0.08, 1.0),
            "speaking": (0.20, 0.80, 0.30, 1.0),
            "error": (0.92, 0.20, 0.22, 1.0),
        }
        previous_state = self.current_state
        self.current_state = state
        self.status_color = colors.get(state, colors["ready"])

        if state not in ("listening", "speaking"):
            self.voice_level = 0.0
            self.wave_bars = None
            self.pulse_phase = 0.0
            self.pulse_energy = 0.0
            self._pulse_last_time = None
        elif previous_state != state:
            # Begin each listening/speaking phase from the core. This prevents
            # a state change from making a ring appear to reverse inward.
            self.pulse_phase = 0.0
            self.pulse_energy = 0.0
            self._pulse_last_time = time.monotonic()

        self._redraw()

    def set_voice_level(self, level):
        """Update the orb from Android SpeechRecognizer RMS loudness."""
        try:
            target = max(0.0, min(1.0, float(level)))
        except Exception:
            target = 0.0

        # Stronger visual sensitivity: lift quiet/medium speech so movement is
        # clearly visible, while still clamping loud speech safely at 1.0.
        if target > 0.0:
            target = min(
                1.0,
                (target * 1.45) ** 0.68
            )

        # Quick attack + controlled release. This is intentionally more
        # responsive than Build #137 so the motion is visibly stronger.
        if target >= self.voice_level:
            old_weight = 0.28
            new_weight = 0.72
        else:
            old_weight = 0.66
            new_weight = 0.34

        self.voice_level = (
            self.voice_level * old_weight
            + target * new_weight
        )

        # Drive the rings from REAL ELAPSED TIME rather than callback count.
        # SpeechRecognizer can deliver RMS callbacks much faster than Android
        # TTS Visualizer, which was why the user's rings raced excessively.
        if self.current_state in ("listening", "speaking"):
            now = time.monotonic()

            if self._pulse_last_time is None:
                elapsed = 0.0
            else:
                elapsed = max(
                    0.0,
                    min(0.12, now - self._pulse_last_time)
                )

            self._pulse_last_time = now

            if self.voice_level > 0.035:
                if self.current_state == "listening":
                    # User voice: deliberately slowed down a lot.
                    cycles_per_second = (
                        0.26
                        + (self.voice_level * 0.11)
                    )
                else:
                    # 811 voice: cinematic slow-motion, still audio reactive.
                    cycles_per_second = (
                        0.22
                        + (self.voice_level * 0.09)
                    )

                self.pulse_phase = (
                    self.pulse_phase
                    + (elapsed * cycles_per_second)
                ) % 1.0

            self.pulse_energy = (
                self.pulse_energy * 0.38
                + self.voice_level * 0.62
            )

        self._redraw()

    def set_tts_waveform(self, level, bars):
        """Update center bars from the actual Android TTS output waveform."""
        self.set_voice_level(level)

        try:
            values = tuple(
                min(
                    1.0,
                    (
                        max(
                            0.0,
                            min(1.0, float(value))
                        )
                        * 1.55
                    ) ** 0.66
                )
                for value in bars
            )
        except Exception:
            values = ()

        if len(values) == 5:
            if self.wave_bars is None:
                self.wave_bars = values
            else:
                # Smooth each bar independently with a quick attack and
                # a gentler release. This removes harsh jumps while keeping
                # the waveform visibly tied to 811's real speech.
                smoothed_bars = []

                for old_value, new_value in zip(
                    self.wave_bars,
                    values
                ):
                    if new_value >= old_value:
                        old_weight = 0.24
                        new_weight = 0.76
                    else:
                        old_weight = 0.58
                        new_weight = 0.42

                    smoothed_bars.append(
                        (old_value * old_weight)
                        + (new_value * new_weight)
                    )

                self.wave_bars = tuple(
                    smoothed_bars
                )

        self._redraw()

    def _redraw(self, *args):
        self.canvas.clear()

        if self.width <= 0 or self.height <= 0:
            return

        with self.canvas:
            cx = self.center_x
            cy = self.center_y
            level = max(
                0.0,
                min(1.0, self.voice_level)
            )

            # The luminous core may breathe with speech, but the travelling
            # rings use a FIXED base radius. This is critical: if ring radius
            # is multiplied by the changing voice level, a drop in loudness
            # can visually pull a ring backward toward the center.
            base_radius = (
                min(self.width, self.height)
                * 0.27
            )
            reactive_scale = 1.0 + (level * 0.19)
            radius = (
                base_radius
                * reactive_scale
            )

            # Soft outer aura.
            Color(
                self.status_color[0],
                self.status_color[1],
                self.status_color[2],
                0.055
            )
            Ellipse(
                pos=(cx - radius * 1.78, cy - radius * 1.78),
                size=(radius * 3.56, radius * 3.56)
            )

            # Three cinematic rings EMIT from the core and ONLY travel
            # outward. They fade to invisible at the outside edge before a
            # new ring is born at the core, so there is no visual "return".
            if self.current_state in ("listening", "speaking"):
                ring_offsets = (0.0, 0.333, 0.666)

                for offset in ring_offsets:
                    progress = (
                        self.pulse_phase + offset
                    ) % 1.0

                    # Radius is based on base_radius, NOT the breathing core.
                    # Therefore every visible ring is monotonically outward.
                    ring_radius = base_radius * (
                        0.98
                        + (progress * 1.08)
                    )

                    # Fade all the way to zero before the ring wraps back to
                    # the core. This makes the reset read as a fresh emission.
                    fade = max(
                        0.0,
                        1.0 - progress
                    )
                    fade = fade ** 1.55

                    alpha = fade * (
                        0.30
                        + (self.pulse_energy * 0.62)
                    )

                    ring_width = (
                        0.85
                        + (fade * 1.55)
                    )

                    if alpha > 0.012:
                        Color(
                            self.status_color[0],
                            self.status_color[1],
                            self.status_color[2],
                            min(0.82, alpha)
                        )
                        Line(
                            circle=(
                                cx,
                                cy,
                                ring_radius
                            ),
                            width=ring_width
                        )

            else:
                # Calm static rings while idle/thinking/error.
                for ring_radius, alpha, width in (
                    (radius * 1.66, 0.16, 1.25),
                    (radius * 1.34, 0.34, 1.45),
                    (radius * 1.10, 0.70, 1.80),
                ):
                    Color(
                        self.status_color[0],
                        self.status_color[1],
                        self.status_color[2],
                        alpha
                    )
                    Line(
                        circle=(cx, cy, ring_radius),
                        width=width
                    )

            # Main luminous voice core.
            Color(
                self.status_color[0],
                self.status_color[1],
                self.status_color[2],
                0.18
            )
            Ellipse(
                pos=(cx - radius * 1.06, cy - radius * 1.06),
                size=(radius * 2.12, radius * 2.12)
            )

            Color(*self.status_color)
            Ellipse(
                pos=(cx - radius * 0.86, cy - radius * 0.86),
                size=(radius * 1.72, radius * 1.72)
            )

            # Subtle upper highlight.
            Color(1, 1, 1, 0.16)
            Ellipse(
                pos=(cx - radius * 0.50, cy + radius * 0.18),
                size=(radius * 0.62, radius * 0.30)
            )

            # Live waveform bars in the center.
            Color(1, 1, 1, 0.96)
            bar_gap = radius * 0.22
            base_heights = (0.42, 0.78, 1.12, 0.78, 0.42)

            if self.wave_bars is not None:
                live_bars = self.wave_bars
            else:
                # Microphone gives one real RMS value. Use the pulse phase to
                # distribute that real energy across all five lines so they
                # visibly dance while still following the user's loudness.
                phase = self.pulse_phase * 6.283185307179586
                patterns = (
                    0.62 + (0.38 * abs(math.sin(phase + 0.20))),
                    0.58 + (0.42 * abs(math.sin(phase + 1.25))),
                    0.55 + (0.45 * abs(math.sin(phase + 2.15))),
                    0.58 + (0.42 * abs(math.sin(phase + 3.05))),
                    0.62 + (0.38 * abs(math.sin(phase + 4.10))),
                )
                live_bars = tuple(
                    min(
                        1.0,
                        (level * 1.55) * pattern
                    )
                    for pattern in patterns
                )

            for index, height_scale in enumerate(base_heights):
                x = cx + (index - 2) * bar_gap

                # All five bars now have stronger travel; the middle three
                # remain the most expressive.
                emphasis = (0.92, 1.15, 1.34, 1.15, 0.92)[index]
                live_scale = (
                    0.20
                    + (
                        live_bars[index]
                        * 1.95
                        * emphasis
                    )
                )

                half_h = min(
                    radius * 0.73,
                    (
                        radius
                        * height_scale
                        * 0.36
                        * live_scale
                    )
                )

                Line(
                    points=[x, cy - half_h, x, cy + half_h],
                    width=3.0
                )


# =========================================================
# CHAT MESSAGE ROW
# =========================================================

class ChatMessageRow(FloatLayout):
    """One independently rendered conversation message."""

    def __init__(
        self,
        app_ref,
        text,
        role="assistant",
        **kwargs
    ):
        super().__init__(
            size_hint_y=None,
            height=dp(70),
            **kwargs
        )

        self.app_ref = app_ref
        self.role = (
            role
            if role in (
                "user",
                "assistant",
                "system"
            )
            else "assistant"
        )
        self.raw_text = clean_unicode(text)
        self._render_event = None

        if self.role == "user":
            width_hint = 0.84
            position_hint = {
                "right": 0.98,
                "top": 1
            }
            background_color = (
                0.035,
                0.26,
                0.48,
                1.0
            )
            self.text_color = (
                0.97,
                0.985,
                1.0,
                1.0
            )
            self.native_text_rgb = (
                247,
                251,
                255
            )
        elif self.role == "system":
            width_hint = 0.90
            position_hint = {
                "x": 0.02,
                "top": 1
            }
            background_color = (
                0.22,
                0.14,
                0.035,
                1.0
            )
            self.text_color = (
                1.0,
                0.86,
                0.58,
                1.0
            )
            self.native_text_rgb = (
                255,
                222,
                158
            )
        else:
            width_hint = 0.90
            position_hint = {
                "x": 0.02,
                "top": 1
            }
            background_color = (
                0.07,
                0.085,
                0.12,
                1.0
            )
            self.text_color = (
                0.88,
                0.91,
                0.96,
                1.0
            )
            self.native_text_rgb = (
                224,
                232,
                245
            )

        self.bubble = FloatLayout(
            size_hint=(
                width_hint,
                None
            ),
            height=dp(66),
            pos_hint=position_hint
        )

        with self.bubble.canvas.before:
            Color(*background_color)
            self.background_shape = RoundedRectangle(
                pos=self.bubble.pos,
                size=self.bubble.size,
                radius=[dp(16)]
            )

        self.bubble.bind(
            pos=self._sync_background,
            size=self._sync_background,
            width=self._schedule_render
        )

        self.fallback_label = Label(
            text=fix_text(
                self._display_text(),
                wrap_at=26
            ),
            font_name=self.app_ref.arabic_font,
            font_size="16sp",
            color=self.text_color,
            size_hint=(1, None),
            height=self.bubble.height,
            pos_hint={"top": 1},
            halign="right",
            valign="top",
            padding=(
                dp(12),
                dp(14)
            ),
            markup=False
        )

        self.message_image = Image(
            size_hint=(1, None),
            height=self.bubble.height,
            pos_hint={"top": 1},
            allow_stretch=True,
            keep_ratio=False,
            opacity=0
        )

        self.bubble.add_widget(
            self.fallback_label
        )
        self.bubble.add_widget(
            self.message_image
        )
        self.add_widget(
            self.bubble
        )

        self.fallback_label.bind(
            width=self._update_fallback_width,
            texture_size=self._update_fallback_height
        )

        Clock.schedule_once(
            lambda dt:
            self._render_native(),
            0.08
        )

    def _display_text(self):
        if self.role == "user":
            prefix = "أنت:"
        elif self.role == "system":
            prefix = "تنبيه:"
        else:
            prefix = "811:"

        return (
            prefix
            + "\n"
            + self.raw_text
        ).strip()

    def update_text(self, text):
        self.raw_text = clean_unicode(text)
        self.fallback_label.text = fix_text(
            self._display_text(),
            wrap_at=26
        )
        self._schedule_render()

    def cancel_render(self):
        if self._render_event is not None:
            try:
                self._render_event.cancel()
            except Exception:
                pass
        self._render_event = None

    def _sync_background(self, *args):
        self.background_shape.pos = self.bubble.pos
        self.background_shape.size = self.bubble.size

    def _update_fallback_width(
        self,
        instance,
        width
    ):
        instance.text_size = (
            max(
                dp(70),
                width - dp(24)
            ),
            None
        )

    def _update_fallback_height(
        self,
        instance,
        texture_size
    ):
        if self.message_image.opacity > 0:
            return

        self._apply_height(
            texture_size[1] + dp(24)
        )

    def _apply_height(self, content_height):
        height = max(
            dp(66),
            float(content_height)
        )

        self.bubble.height = height
        self.fallback_label.height = height
        self.message_image.height = height
        self.height = height + dp(3)

    def _schedule_render(self, *args):
        self.cancel_render()
        self._render_event = Clock.schedule_once(
            lambda dt:
            self._render_native(),
            0.08
        )

    def _render_native(self):
        self._render_event = None

        if (
            platform != "android"
            or self.app_ref._native_chat_failed
        ):
            self.show_fallback()
            return

        width = int(
            max(
                2,
                self.bubble.width
            )
        )

        if width <= 2:
            self._schedule_render()
            return

        try:
            png_bytes, bitmap_height = (
                self.app_ref
                ._render_android_text_to_png(
                    self._display_text(),
                    width,
                    text_rgb=self.native_text_rgb
                )
            )

            if not png_bytes:
                raise RuntimeError(
                    "Android chat message renderer returned empty image"
                )

            core_image = CoreImage(
                BytesIO(png_bytes),
                ext="png"
            )
            texture = core_image.texture

            if texture is None:
                raise RuntimeError(
                    "Kivy could not create the chat message texture"
                )

            self.message_image.texture = texture
            self._apply_height(bitmap_height)
            self.message_image.opacity = 1
            self.fallback_label.opacity = 0

            Clock.schedule_once(
                self.app_ref._scroll_chat_to_bottom,
                0
            )

            print(
                "811: Chat message rendered:",
                self.role,
                width,
                "x",
                bitmap_height
            )

        except Exception as exc:
            self.app_ref._native_chat_failed = True
            print(
                "811: Native chat message renderer failed:",
                repr(exc)
            )
            self.app_ref._show_all_chat_fallback()

    def show_fallback(self):
        self.fallback_label.text = fix_text(
            self._display_text(),
            wrap_at=26
        )
        self.message_image.opacity = 0
        self.fallback_label.opacity = 1
        self._apply_height(
            self.fallback_label.texture_size[1]
            + dp(24)
        )


# =========================================================
# MAIN APP
# =========================================================

class VoiceAssistantApp(App):

    def build(self):
        self.title = "VOICE ASSISTANT 811"

        # -------------------------
        # Core state
        # -------------------------

        self.processing = False
        self.ai_engine = None

        # Phase 1 background core service.
        # This does not listen for the wake word yet. It only proves that a
        # dedicated Android foreground service can remain alive independently
        # of the Kivy activity while preserving the stable Build #140 UI.
        self.background_core_started = False
        self._background_core_start_attempt = 0
        self._background_core_max_start_attempts = 10
        self._app_is_foreground = True

        # Phase 2B diagnostic: once per app session, when the app first moves
        # safely to the background, ask the service itself to speak a short
        # Arabic phrase. This proves TTS can run independently from Kivy.
        self._background_tts_probe_sent = False
        self._background_command_serial = 0

        # Hands-free conversation mode.
        # One manual Talk press starts a session; after each successful 811
        # reply finishes speaking, listening starts again automatically.
        # Clear, manual listening stop, or an error ends the session safely.
        self.handsfree_active = False
        self._handsfree_generation = 0

        # Incremented whenever a new AI request starts or Clear cancels work.
        # Late replies from an older background request are ignored safely.
        self._request_serial = 0

        # -------------------------
        # TTS
        # -------------------------

        self.tts = None
        self.tts_ready = False
        self.tts_language_ready = False
        self.tts_init_error = ""
        self.tts_last_result = None
        self.tts_media_volume = None
        self.tts_media_volume_max = None
        self.tts_is_speaking = False
        self._tts_pending_text = ""
        self._tts_listener = None
        self._tts_watch_generation = 0

        # Real output-audio visualizer used only while 811 is speaking.
        # It listens to Android's output mix (audio session 0) and never
        # changes the TTS playback path. If a device blocks Visualizer,
        # TTS continues normally and only the visual reaction is skipped.
        self._tts_output_visualizer = None
        self._tts_output_visualizer_listener = None

        # -------------------------
        # SpeechRecognizer
        # -------------------------

        self.speech_recognizer = None
        self.speech_recognizer_ready = False
        self.is_listening = False

        self._speech_listener = None
        self._speech_autoclass = None
        self._last_ui_runnable = None

        self.speech_init_error = ""
        self.speech_last_error_code = 0
        self.speech_last_error_name = ""
        self._ignore_next_speech_error = False

        # Prefer Iraqi Arabic, then Saudi Arabic, then generic Arabic,
        # and finally allow Android to use its own default language.
        self.speech_languages = [
            "ar-IQ",
            "ar-SA",
            "ar",
            None
        ]
        self.speech_language_index = 0

        # One automatic recovery is allowed for transient recognizer
        # states such as ERROR_CLIENT / ERROR_RECOGNIZER_BUSY.
        self.speech_recovery_attempts = 0
        self.speech_max_recovery_attempts = 1

        # -------------------------
        # UI
        # -------------------------

        self.arabic_font = ARABIC_FONT

        # -------------------------
        # Conversation messages
        # -------------------------

        self._initial_chat_text = (
            "مرحباً\n"
            "أنا 811\n"
            "جاهز للعمل معك."
        )
        self._chat_rows = []
        self._active_user_row = None
        self._native_chat_failed = False

        request_android_permissions()

        # =================================================
        # AI
        # =================================================

        try:
            self.ai_engine = AIClient()
        except Exception as exc:
            print(
                "811: AIClient init error:",
                repr(exc)
            )
            self.ai_engine = None

        # =================================================
        # ROOT
        # =================================================

        root = BoxLayout(
            orientation="vertical"
        )

        with root.canvas.before:
            Color(
                0.025,
                0.030,
                0.045,
                1.0
            )

            root.background_rect = RoundedRectangle(
                pos=root.pos,
                size=root.size,
                radius=[0]
            )

        root.bind(
            pos=lambda instance, value:
            setattr(
                root.background_rect,
                "pos",
                value
            )
        )

        root.bind(
            size=lambda instance, value:
            setattr(
                root.background_rect,
                "size",
                value
            )
        )

        # =================================================
        # MAIN
        # =================================================

        main = BoxLayout(
            orientation="vertical",
            padding=(
                dp(16),
                dp(16),
                dp(16),
                dp(14)
            ),
            spacing=dp(10)
        )

        # =================================================
        # HEADER
        # =================================================

        header = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            spacing=dp(3)
        )

        self.title_label = Label(
            text="VOICE ASSISTANT 811",
            font_name="Roboto",
            font_size="23sp",
            bold=True,
            color=(
                0.95,
                0.97,
                1.0,
                1.0
            ),
            halign="center",
            valign="middle"
        )

        self.subtitle_label = Label(
            text=fix_text(
                "مساعدك الشخصي الذكي"
            ),
            font_name=self.arabic_font,
            font_size="14sp",
            color=(
                0.55,
                0.65,
                0.78,
                1.0
            ),
            halign="center",
            valign="middle"
        )

        header.add_widget(
            self.title_label
        )

        header.add_widget(
            self.subtitle_label
        )

        main.add_widget(
            header
        )

        # =================================================
        # AI API KEY (Groq / Gemini)
        # =================================================

        key_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            padding=dp(4)
        )

        self.key_input = TextInput(
            hint_text="AI API Key (Groq / Gemini)",
            multiline=False,
            password=True,
            font_size="14sp",
            font_name="Roboto",
            foreground_color=(
                0.90,
                0.93,
                0.98,
                1.0
            ),
            background_color=(
                0.08,
                0.10,
                0.14,
                1.0
            ),
            cursor_color=(
                0.25,
                0.65,
                1.0,
                1.0
            ),
            padding=(
                dp(14),
                dp(12)
            )
        )

        self.key_input.bind(
            focus=self._on_api_key_focus
        )

        key_container.add_widget(
            self.key_input
        )

        main.add_widget(
            key_container
        )

        # Restore the key from Android private app storage. The key never goes
        # into GitHub/source code and remains hidden by password=True.
        Clock.schedule_once(
            lambda dt:
            self._load_saved_api_key(),
            0.35
        )

        # =================================================
        # STATUS
        # =================================================

        status_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(205),
            spacing=dp(2)
        )

        self.status_orb = StatusOrb()

        status_container.add_widget(
            self.status_orb
        )

        self.status_label = Label(
            text=fix_text(
                "جاهز"
            ),
            font_name=self.arabic_font,
            font_size="19sp",
            bold=True,
            color=(
                0.30,
                0.75,
                1.0,
                1.0
            ),
            size_hint_y=None,
            height=dp(42),
            halign="center",
            valign="middle"
        )

        self.status_label.bind(
            width=lambda instance, value:
            setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        status_container.add_widget(
            self.status_label
        )

        main.add_widget(
            status_container
        )

        # =================================================
        # CHAT
        # =================================================

        chat_panel = BoxLayout(
            orientation="vertical",
            padding=dp(3)
        )

        self.scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=dp(4),
            scroll_type=[
                "bars",
                "content"
            ]
        )

        self.chat_messages = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(8),
            padding=(
                0,
                dp(6),
                0,
                dp(6)
            )
        )

        self.chat_messages.bind(
            minimum_height=
            self.chat_messages.setter(
                "height"
            )
        )

        self.scroll.add_widget(
            self.chat_messages
        )

        # New conversation messages appear at the bottom.
        self.scroll.scroll_y = 0

        chat_panel.add_widget(
            self.scroll
        )

        main.add_widget(
            chat_panel
        )

        # =================================================
        # BUTTONS
        # =================================================

        buttons = BoxLayout(
            size_hint_y=None,
            height=dp(60),
            spacing=dp(9)
        )

        self.speak_btn = Button(
            size_hint_x=0.78,
            text=fix_text(
                "اضغط للتحدث"
            ),
            font_name=self.arabic_font,
            font_size="18sp",
            bold=True,
            background_normal="",
            background_down="",
            background_color=(
                0.08,
                0.45,
                0.90,
                1.0
            ),
            color=(
                1,
                1,
                1,
                1
            )
        )

        self.speak_btn.bind(
            on_press=self.on_speak_click
        )

        self.clear_btn = Button(
            size_hint_x=0.22,
            text=fix_text(
                "مسح"
            ),
            font_name=self.arabic_font,
            font_size="16sp",
            background_normal="",
            background_down="",
            background_color=(
                0.12,
                0.14,
                0.19,
                1.0
            ),
            color=(
                0.85,
                0.88,
                0.93,
                1.0
            )
        )

        self.clear_btn.bind(
            on_press=self.on_clear_click
        )

        buttons.add_widget(
            self.speak_btn
        )

        buttons.add_widget(
            self.clear_btn
        )

        main.add_widget(
            buttons
        )

        # =================================================
        # FOOTER
        # =================================================

        self.footer_label = Label(
            text=(
                "Speech Recognition • "
                "Native TTS • "
                "Cairo Arabic • "
                "Groq AI"
            ),
            font_name="Roboto",
            font_size="11sp",
            color=(
                0.38,
                0.43,
                0.52,
                1.0
            ),
            size_hint_y=None,
            height=dp(22),
            halign="center",
            valign="middle"
        )

        self.footer_label.bind(
            width=lambda instance, value:
            setattr(
                instance,
                "text_size",
                (value, None)
            )
        )

        main.add_widget(
            self.footer_label
        )

        root.add_widget(
            main
        )

        self.set_state(
            "ready"
        )

        # Create the initial assistant message after Kivy measures the panel.
        Clock.schedule_once(
            lambda dt:
            self._set_chat_text(
                self._initial_chat_text,
                role="assistant"
            ),
            0.20
        )

        if platform == "android":
            Clock.schedule_once(
                lambda dt:
                self.init_native_tts(),
                1.0
            )

            # Give the permission dialog a little more time before
            # creating SpeechRecognizer.
            Clock.schedule_once(
                lambda dt:
                self.init_native_speech(),
                2.0
            )

            # Start the Phase 1 background core while the Activity is still
            # visible. This is important for modern Android foreground-service
            # restrictions, especially for the future microphone wake-word
            # phase. No wake-word capture is enabled in this build yet.
            Clock.schedule_once(
                lambda dt:
                self.start_background_core(),
                3.0
            )

        return root

    # =====================================================
    # NATIVE ANDROID ARABIC RENDERER
    # =====================================================

    def _render_android_text_to_png(
        self,
        text,
        bitmap_width,
        text_rgb=(
            224,
            230,
            242
        )
    ):
        """Use Android's shaping engine (StaticLayout) without creating a View."""
        from jnius import (
            autoclass,
            cast
        )

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )
        TextPaint = autoclass(
            "android.text.TextPaint"
        )
        Paint = autoclass(
            "android.graphics.Paint"
        )
        StaticLayout = autoclass(
            "android.text.StaticLayout"
        )
        StaticLayoutBuilder = autoclass(
            "android.text.StaticLayout$Builder"
        )
        LayoutAlignment = autoclass(
            "android.text.Layout$Alignment"
        )
        TextDirectionHeuristics = autoclass(
            "android.text.TextDirectionHeuristics"
        )
        Bitmap = autoclass(
            "android.graphics.Bitmap"
        )
        BitmapConfig = autoclass(
            "android.graphics.Bitmap$Config"
        )
        BitmapCompressFormat = autoclass(
            "android.graphics.Bitmap$CompressFormat"
        )
        Canvas = autoclass(
            "android.graphics.Canvas"
        )
        AndroidColor = autoclass(
            "android.graphics.Color"
        )
        Typeface = autoclass(
            "android.graphics.Typeface"
        )
        ByteArrayOutputStream = autoclass(
            "java.io.ByteArrayOutputStream"
        )
        JavaString = autoclass(
            "java.lang.String"
        )
        BuildVersion = autoclass(
            "android.os.Build$VERSION"
        )

        activity = PythonActivity.mActivity
        if activity is None:
            raise RuntimeError(
                "Android Activity unavailable for text renderer"
            )

        metrics = (
            activity.getResources()
            .getDisplayMetrics()
        )

        density = float(metrics.density)
        scaled_density = float(metrics.scaledDensity)

        pad_h = int(
            round(12.0 * density)
        )
        pad_v = int(
            round(18.0 * density)
        )

        content_width = int(
            max(
                1,
                bitmap_width - (pad_h * 2)
            )
        )

        flags = int(
            Paint.ANTI_ALIAS_FLAG
        )

        try:
            flags |= int(
                Paint.SUBPIXEL_TEXT_FLAG
            )
        except Exception:
            pass

        paint = TextPaint(flags)
        paint.setColor(
            AndroidColor.rgb(
                int(text_rgb[0]),
                int(text_rgb[1]),
                int(text_rgb[2])
            )
        )
        paint.setTextSize(
            17.0 * scaled_density
        )
        paint.setTypeface(
            Typeface.create(
                "sans-serif",
                Typeface.NORMAL
            )
        )

        java_text = JavaString(
            clean_unicode(text)
        )
        char_sequence = cast(
            "java.lang.CharSequence",
            java_text
        )

        if int(BuildVersion.SDK_INT) >= 23:
            builder = StaticLayoutBuilder.obtain(
                char_sequence,
                0,
                java_text.length(),
                paint,
                content_width
            )

            builder.setAlignment(
                LayoutAlignment.ALIGN_NORMAL
            )
            builder.setTextDirection(
                TextDirectionHeuristics.FIRSTSTRONG_RTL
            )
            builder.setIncludePad(False)
            builder.setLineSpacing(
                0.0,
                1.18
            )

            layout = builder.build()
        else:
            # API 21-22 compatibility. StaticLayout still uses Android's
            # native bidi/shaping engine; the first strong Arabic character
            # determines RTL paragraph direction on these versions.
            layout = StaticLayout(
                char_sequence,
                paint,
                content_width,
                LayoutAlignment.ALIGN_NORMAL,
                1.18,
                0.0,
                False
            )

        layout_height = int(
            max(
                1,
                layout.getHeight()
            )
        )

        bitmap_height = int(
            max(
                1,
                layout_height + (pad_v * 2)
            )
        )

        # Guard against accidental runaway memory usage from a malformed reply.
        # Normal assistant replies are far below this limit.
        max_height = 8192
        if bitmap_height > max_height:
            raise RuntimeError(
                "Arabic response is too tall to render safely: "
                + str(bitmap_height)
            )

        bitmap = Bitmap.createBitmap(
            int(bitmap_width),
            int(bitmap_height),
            BitmapConfig.ARGB_8888
        )
        bitmap.eraseColor(
            AndroidColor.TRANSPARENT
        )

        canvas = Canvas(bitmap)
        canvas.translate(
            float(pad_h),
            float(pad_v)
        )
        layout.draw(canvas)

        output = ByteArrayOutputStream()

        try:
            ok = bitmap.compress(
                BitmapCompressFormat.PNG,
                100,
                output
            )

            if not ok:
                raise RuntimeError(
                    "Android Bitmap.compress returned false"
                )

            java_bytes = output.toByteArray()
            png_bytes = bytes(
                (int(value) & 0xFF)
                for value in java_bytes
            )

        finally:
            try:
                output.close()
            except Exception:
                pass

            try:
                bitmap.recycle()
            except Exception:
                pass

        return png_bytes, bitmap_height

    # =====================================================
    # CONVERSATION MESSAGES
    # =====================================================

    def _scroll_chat_to_bottom(
        self,
        *args
    ):
        if hasattr(self, "scroll"):
            self.scroll.scroll_y = 0

    def _show_all_chat_fallback(
        self
    ):
        for row in list(self._chat_rows):
            row.show_fallback()

        Clock.schedule_once(
            self._scroll_chat_to_bottom,
            0
        )

    def _clear_chat_messages(
        self
    ):
        for row in list(self._chat_rows):
            row.cancel_render()

        self._chat_rows = []
        self._active_user_row = None

        if hasattr(self, "chat_messages"):
            self.chat_messages.clear_widgets()

    def _add_chat_message(
        self,
        text,
        role="assistant"
    ):
        text = clean_unicode(text)

        if not text:
            return None

        row = ChatMessageRow(
            app_ref=self,
            text=text,
            role=role
        )

        self._chat_rows.append(row)
        self.chat_messages.add_widget(row)

        Clock.schedule_once(
            self._scroll_chat_to_bottom,
            0.05
        )

        return row

    def _set_chat_text(
        self,
        text,
        role="assistant"
    ):
        """Reset the conversation to one independently rendered message."""
        self._clear_chat_messages()
        return self._add_chat_message(
            text,
            role=role
        )

    def _append_chat_text(
        self,
        text,
        role="assistant"
    ):
        return self._add_chat_message(
            text,
            role=role
        )

    def _update_user_draft(
        self,
        text
    ):
        text = clean_unicode(text)

        if not text:
            return

        if self._active_user_row is None:
            self._active_user_row = (
                self._add_chat_message(
                    text,
                    role="user"
                )
            )
        else:
            self._active_user_row.update_text(
                text
            )

        Clock.schedule_once(
            self._scroll_chat_to_bottom,
            0
        )

    def _commit_user_message(
        self,
        text
    ):
        text = clean_unicode(text)

        if not text:
            return

        if self._active_user_row is None:
            self._add_chat_message(
                text,
                role="user"
            )
        else:
            self._active_user_row.update_text(
                text
            )

        self._active_user_row = None

        Clock.schedule_once(
            self._scroll_chat_to_bottom,
            0
        )

    # =====================================================
    # STATES
    # =====================================================

    def set_state(
        self,
        state,
        message=None
    ):
        states = {
            "ready": {
                "text": "جاهز",
                "color": (
                    0.30,
                    0.75,
                    1.0,
                    1.0
                )
            },
            "listening": {
                "text": "جاري الاستماع...",
                "color": (
                    0.10,
                    0.85,
                    0.90,
                    1.0
                )
            },
            "thinking": {
                "text": "جاري التفكير...",
                "color": (
                    1.0,
                    0.65,
                    0.12,
                    1.0
                )
            },
            "speaking": {
                "text": "811 يتحدث الآن",
                "color": (
                    0.20,
                    0.85,
                    0.35,
                    1.0
                )
            },
            "error": {
                "text": "حدث خطأ",
                "color": (
                    1.0,
                    0.28,
                    0.30,
                    1.0
                )
            }
        }

        current = states.get(
            state,
            states["ready"]
        )

        self.status_label.text = fix_text(
            current["text"]
        )

        self.status_label.color = (
            current["color"]
        )

        self.status_orb.set_state(
            state
        )

        # Listening and thinking details already appear in the status area.
        # Only durable errors become conversation messages, so the chat stays
        # clean and preserves the real user/assistant exchange.
        if message is not None and state == "error":
            self._append_chat_text(
                message,
                role="system"
            )

        if state == "listening":
            self.speak_btn.text = fix_text(
                "إيقاف الاستماع"
            )

            self.speak_btn.background_color = (
                0.08,
                0.60,
                0.70,
                1.0
            )

        elif state == "thinking":
            self.speak_btn.text = fix_text(
                "جاري التفكير..."
            )

            self.speak_btn.background_color = (
                0.75,
                0.45,
                0.05,
                1.0
            )

        elif state == "speaking":
            self.speak_btn.text = fix_text(
                "يتحدث 811..."
            )

            self.speak_btn.background_color = (
                0.10,
                0.65,
                0.24,
                1.0
            )

        elif state == "error":
            self.speak_btn.text = fix_text(
                "حاول مرة أخرى"
            )

            self.speak_btn.background_color = (
                0.70,
                0.15,
                0.18,
                1.0
            )

        else:
            self.speak_btn.text = fix_text(
                "اضغط للتحدث"
            )

            self.speak_btn.background_color = (
                0.08,
                0.45,
                0.90,
                1.0
            )

    # =====================================================
    # ANDROID MAIN THREAD HELPER
    # =====================================================

    def _run_on_android_ui(
        self,
        func
    ):
        if platform != "android":
            func()
            return

        try:
            from jnius import (
                PythonJavaClass,
                java_method,
                autoclass
            )

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                print(
                    "811: Android Activity unavailable "
                    "for runOnUiThread"
                )
                return

            class UiRunnable(
                PythonJavaClass
            ):
                __javainterfaces__ = [
                    "java/lang/Runnable"
                ]
                __javacontext__ = "app"

                @java_method("()V")
                def run(self):
                    try:
                        func()
                    except Exception as exc:
                        print(
                            "811: Android UI Runnable error:",
                            repr(exc)
                        )

            runnable = UiRunnable()

            # Keep a strong reference while Java may still use it.
            self._last_ui_runnable = runnable

            activity.runOnUiThread(
                runnable
            )

        except Exception as exc:
            print(
                "811: runOnUiThread error:",
                repr(exc)
            )

    # =====================================================
    # PRIVATE AI KEY STORAGE
    # =====================================================

    def _api_preferences(
        self
    ):
        if platform != "android":
            return None

        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            activity = (
                PythonActivity.mActivity
            )

            if activity is None:
                return None

            return (
                activity
                .getSharedPreferences(
                    "voice_assistant_811_private",
                    0
                )
            )

        except Exception as exc:
            print(
                "811: API preferences error:",
                repr(exc)
            )
            return None

    def _provider_for_key(
        self,
        api_key
    ):
        try:
            return (
                AIClient
                .identify_provider(
                    api_key
                )
            )
        except Exception:
            key = str(
                api_key or ""
            ).strip()

            if key.lower().startswith(
                "gsk_"
            ):
                return "groq"

            return (
                "gemini"
                if key
                else ""
            )

    def _load_saved_api_key(
        self
    ):
        prefs = (
            self._api_preferences()
        )

        if prefs is None:
            return

        try:
            saved_key = str(
                prefs.getString(
                    "ai_api_key",
                    ""
                )
                or ""
            ).strip()

            if not saved_key:
                return

            self.key_input.text = (
                saved_key
            )

            provider = (
                self._provider_for_key(
                    saved_key
                )
            )

            if (
                self.ai_engine
                is not None
            ):
                self.ai_engine.set_api_key(
                    saved_key
                )

            print(
                "811: Saved AI key restored | provider:",
                provider or "unknown"
            )

        except Exception as exc:
            print(
                "811: Saved AI key load error:",
                repr(exc)
            )

    def _save_api_key(
        self,
        api_key
    ):
        key = str(
            api_key or ""
        ).strip()

        if not key:
            return False

        prefs = (
            self._api_preferences()
        )

        if prefs is None:
            return False

        try:
            provider = (
                self._provider_for_key(
                    key
                )
            )

            editor = prefs.edit()

            editor.putString(
                "ai_api_key",
                key
            )

            editor.putString(
                "ai_provider",
                provider
            )

            editor.apply()

            if (
                self.ai_engine
                is not None
            ):
                self.ai_engine.set_api_key(
                    key
                )

            print(
                "811: AI key saved privately | provider:",
                provider or "unknown"
            )

            return True

        except Exception as exc:
            print(
                "811: AI key save error:",
                repr(exc)
            )
            return False

    def _on_api_key_focus(
        self,
        instance,
        focused
    ):
        if focused:
            return

        key = (
            self.key_input
            .text
            .strip()
        )

        if key:
            self._save_api_key(
                key
            )

    # =====================================================
    # PHASE 1 BACKGROUND CORE SERVICE
    # =====================================================

    def _background_core_control_path(
        self
    ):
        if platform != "android":
            return None

        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                return None

            files_dir = str(
                activity
                .getFilesDir()
                .getAbsolutePath()
            )

            return os.path.join(
                files_dir,
                "811_background_core_control.txt"
            )

        except Exception as exc:
            print(
                "811: Background control path error:",
                repr(exc)
            )
            return None

    def _background_core_command_path(
        self
    ):
        control_path = (
            self._background_core_control_path()
        )

        if not control_path:
            return None

        return os.path.join(
            os.path.dirname(control_path),
            "811_background_core_command.json"
        )

    def _send_background_core_command(
        self,
        action,
        **payload
    ):
        """
        Send a one-shot command to the separate Background Core process.

        Commands are written atomically to the app-private files directory.
        The service ignores command IDs it has already handled.
        """
        if platform != "android":
            return False

        path = (
            self._background_core_command_path()
        )

        if not path:
            return False

        try:
            self._background_command_serial += 1

            command = {
                "id": (
                    str(int(time.time() * 1000))
                    + "-"
                    + str(self._background_command_serial)
                ),
                "action": str(action),
                "created_at": time.time(),
            }

            command.update(
                payload
            )

            temp_path = path + ".tmp"

            with open(
                temp_path,
                "w",
                encoding="utf-8"
            ) as handle:
                json.dump(
                    command,
                    handle,
                    ensure_ascii=False
                )

            os.replace(
                temp_path,
                path
            )

            print(
                "811: Background command sent:",
                action
            )

            return True

        except Exception as exc:
            print(
                "811: Background command write error:",
                repr(exc)
            )
            return False

    def _set_background_wake_capture(
        self,
        enabled,
        reason
    ):
        """
        Tell the separate background service whether it may own the microphone.

        Phase 2A uses a tiny private control file because the service runs in a
        separate Android process. This avoids competing with the existing
        SpeechRecognizer while the Kivy Activity is active.
        """
        if platform != "android":
            return

        path = self._background_core_control_path()

        if not path:
            return

        try:
            temp_path = path + ".tmp"

            payload = (
                ("capture" if enabled else "pause")
                + "\n"
                + str(reason)
                + "\n"
                + str(time.time())
                + "\n"
            )

            with open(
                temp_path,
                "w",
                encoding="utf-8"
            ) as handle:
                handle.write(
                    payload
                )

            os.replace(
                temp_path,
                path
            )

            print(
                "811: Background wake capture:",
                "ON" if enabled else "PAUSED",
                "|",
                reason
            )

        except Exception as exc:
            print(
                "811: Background control write error:",
                repr(exc)
            )

    def start_background_core(
        self
    ):
        """
        Start the dedicated Android foreground service.

        Phase 1 deliberately does NOT open the microphone or implement the
        811 wake word. The service is only the persistent background shell
        that later phases will build on.
        """
        if platform != "android":
            return

        if self.background_core_started:
            return

        # The service is declared with foregroundServiceType=microphone so the
        # next wake-word phase can use the same stable service architecture.
        # On modern Android, start it only after RECORD_AUDIO is granted and
        # while this Activity is visible.
        if not self._has_record_audio_permission():
            self._background_core_start_attempt += 1

            if (
                self._background_core_start_attempt
                <= self._background_core_max_start_attempts
            ):
                print(
                    "811: Background core waiting for RECORD_AUDIO permission; "
                    "attempt",
                    self._background_core_start_attempt
                )

                Clock.schedule_once(
                    lambda dt:
                    self.start_background_core(),
                    1.0
                )
            else:
                print(
                    "811: Background core not started because "
                    "RECORD_AUDIO permission was not granted"
                )

            return

        self._run_on_android_ui(
            self._start_background_core_on_ui
        )

    def _start_background_core_on_ui(
        self
    ):
        if self.background_core_started:
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                raise RuntimeError(
                    "Android Activity unavailable for Background Core"
                )

            # Generated automatically by python-for-android from:
            # backgroundcore:background_core.py
            ServiceBackgroundcore = autoclass(
                "org.test.voiceassistant811."
                "ServiceBackgroundcore"
            )

            # Empty icon name = use the application's normal icon.
            # The notification is intentionally simple in Phase 1.
            ServiceBackgroundcore.start(
                activity,
                "",
                "Voice Assistant 811",
                "811 Background Core ACTIVE",
                "phase1"
            )

            self.background_core_started = True
            self._background_core_start_attempt = 0

            # The foreground Activity owns the voice pipeline. Keep the
            # background AudioRecord paused until the app goes to background.
            self._set_background_wake_capture(
                False,
                "app_foreground"
            )

            print(
                "811: Background Core foreground service STARTED"
            )

        except Exception as exc:
            self.background_core_started = False

            print(
                "811: Background Core start error:",
                repr(exc)
            )

    # =====================================================
    # NATIVE TTS
    # =====================================================

    def init_native_tts(
        self
    ):
        if platform != "android":
            return

        self._run_on_android_ui(
            self._init_native_tts_on_ui
        )

    def _init_native_tts_on_ui(
        self
    ):
        try:
            from jnius import (
                autoclass,
                PythonJavaClass,
                java_method
            )

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            TextToSpeech = autoclass(
                "android.speech.tts.TextToSpeech"
            )

            Locale = autoclass(
                "java.util.Locale"
            )

            Context = autoclass(
                "android.content.Context"
            )

            AudioManager = autoclass(
                "android.media.AudioManager"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                self.tts_ready = False
                self.tts_language_ready = False
                self.tts_init_error = (
                    "Android Activity unavailable"
                )
                print(
                    "811: TTS init failed:",
                    self.tts_init_error
                )
                return

            if self.tts is not None:
                try:
                    self.tts.stop()
                except Exception:
                    pass

                try:
                    self.tts.shutdown()
                except Exception:
                    pass

                self.tts = None

            self.tts_ready = False
            self.tts_language_ready = False
            self.tts_init_error = ""

            outer = self

            class TTSInitListener(
                PythonJavaClass
            ):
                __javainterfaces__ = [
                    "android/speech/tts/"
                    "TextToSpeech$OnInitListener"
                ]
                __javacontext__ = "app"

                @java_method("(I)V")
                def onInit(
                    self,
                    status
                ):
                    try:
                        if (
                            status
                            != TextToSpeech.SUCCESS
                        ):
                            outer.tts_ready = False
                            outer.tts_language_ready = False
                            outer.tts_init_error = (
                                "TextToSpeech initialization failed "
                                "with status "
                                + str(status)
                            )

                            print(
                                "811: TTS initialization failed:",
                                status
                            )
                            return

                        outer.tts_ready = True
                        outer.tts_language_ready = False
                        outer.tts_init_error = ""

                        locales = [
                            Locale(
                                "ar",
                                "IQ"
                            ),
                            Locale(
                                "ar",
                                "SA"
                            ),
                            Locale(
                                "ar",
                                "AE"
                            ),
                            Locale(
                                "ar",
                                "EG"
                            ),
                            Locale(
                                "ar"
                            )
                        ]

                        for locale in locales:
                            try:
                                available = (
                                    outer.tts
                                    .isLanguageAvailable(
                                        locale
                                    )
                                )

                                if (
                                    available
                                    < TextToSpeech.LANG_AVAILABLE
                                ):
                                    continue

                                result = (
                                    outer.tts
                                    .setLanguage(
                                        locale
                                    )
                                )

                                if (
                                    result
                                    >= TextToSpeech.LANG_AVAILABLE
                                ):
                                    outer.tts_language_ready = True

                                    print(
                                        "811: Arabic TTS ready:",
                                        locale
                                    )
                                    break

                            except Exception as lang_exc:
                                print(
                                    "811: TTS locale error:",
                                    repr(lang_exc)
                                )

                        if not outer.tts_language_ready:
                            outer.tts_init_error = (
                                "No Arabic TTS voice is installed "
                                "or enabled on this device."
                            )

                            print(
                                "811:",
                                outer.tts_init_error
                            )
                            return

                        try:
                            outer.tts.setSpeechRate(
                                0.95
                            )

                            outer.tts.setPitch(
                                1.0
                            )
                        except Exception as voice_exc:
                            print(
                                "811: TTS voice tuning error:",
                                repr(voice_exc)
                            )

                        try:
                            audio_manager = (
                                activity.getSystemService(
                                    Context.AUDIO_SERVICE
                                )
                            )

                            outer.tts_media_volume = (
                                audio_manager
                                .getStreamVolume(
                                    AudioManager.STREAM_MUSIC
                                )
                            )

                            outer.tts_media_volume_max = (
                                audio_manager
                                .getStreamMaxVolume(
                                    AudioManager.STREAM_MUSIC
                                )
                            )

                            print(
                                "811: Media volume:",
                                outer.tts_media_volume,
                                "/",
                                outer.tts_media_volume_max
                            )

                        except Exception as volume_exc:
                            print(
                                "811: Media volume check error:",
                                repr(volume_exc)
                            )

                        pending = outer._tts_pending_text

                        if pending:
                            outer._tts_pending_text = ""

                            outer._run_on_android_ui(
                                lambda:
                                outer._speak_on_android_ui(
                                    pending
                                )
                            )

                    except Exception as exc:
                        outer.tts_ready = False
                        outer.tts_language_ready = False
                        outer.tts_init_error = (
                            type(exc).__name__
                            + ": "
                            + str(exc)
                        )

                        print(
                            "811: TTS callback error:",
                            repr(exc)
                        )

            self._tts_listener = (
                TTSInitListener()
            )

            self.tts = TextToSpeech(
                activity,
                self._tts_listener
            )

            print(
                "811: Native Android TTS created"
            )

        except Exception as exc:
            self.tts = None
            self.tts_ready = False
            self.tts_language_ready = False
            self.tts_init_error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            print(
                "811: Native TTS init error:",
                repr(exc)
            )

    def _start_tts_output_visualizer(
        self
    ):
        """Start real-time analysis of the audio mix while 811 speaks."""
        if platform != "android":
            return

        self._run_on_android_ui(
            self._start_tts_output_visualizer_on_ui
        )

    def _start_tts_output_visualizer_on_ui(
        self
    ):
        # Always release a previous instance first.
        self._stop_tts_output_visualizer_on_ui()

        try:
            from jnius import (
                autoclass,
                PythonJavaClass,
                java_method
            )

            Visualizer = autoclass(
                "android.media.audiofx.Visualizer"
            )

            outer = self

            class OutputCaptureListener(
                PythonJavaClass
            ):
                __javainterfaces__ = [
                    "android/media/audiofx/"
                    "Visualizer$OnDataCaptureListener"
                ]
                __javacontext__ = "app"

                @java_method(
                    "(Landroid/media/audiofx/"
                    "Visualizer;[BI)V"
                )
                def onWaveFormDataCapture(
                    self,
                    visualizer,
                    waveform,
                    sampling_rate
                ):
                    try:
                        if waveform is None:
                            return

                        count = len(waveform)
                        if count <= 0:
                            return

                        sum_sq = 0.0
                        peak = 0.0

                        for value in waveform:
                            # Android Visualizer waveform is unsigned 8-bit
                            # PCM centered at 128. Pyjnius exposes Java bytes
                            # as signed values, so normalize with & 0xFF.
                            sample = (
                                (int(value) & 0xFF)
                                - 128
                            ) / 128.0

                            absolute = abs(sample)
                            sum_sq += sample * sample

                            if absolute > peak:
                                peak = absolute

                        rms = (
                            sum_sq
                            / float(count)
                        ) ** 0.5

                        # Blend RMS with peak so speech consonants remain lively
                        # without making quiet background noise pulse the orb.
                        raw_level = (
                            rms * 0.78
                            + peak * 0.22
                        )

                        level = (
                            raw_level - 0.018
                        ) / 0.30

                        level = max(
                            0.0,
                            min(1.0, level)
                        )

                        # Split the real output waveform into five short
                        # time slices. Each slice gets its own amplitude so
                        # the center bars move independently with 811's speech.
                        bars = []
                        bucket_count = 5

                        for bucket in range(bucket_count):
                            start = (
                                count * bucket
                            ) // bucket_count
                            end = (
                                count * (bucket + 1)
                            ) // bucket_count

                            bucket_sum_sq = 0.0
                            bucket_peak = 0.0
                            bucket_samples = max(1, end - start)

                            for sample_index in range(start, end):
                                bucket_sample = (
                                    (int(waveform[sample_index]) & 0xFF)
                                    - 128
                                ) / 128.0

                                absolute = abs(bucket_sample)
                                bucket_sum_sq += (
                                    bucket_sample
                                    * bucket_sample
                                )

                                if absolute > bucket_peak:
                                    bucket_peak = absolute

                            bucket_rms = (
                                bucket_sum_sq
                                / float(bucket_samples)
                            ) ** 0.5

                            bucket_raw = (
                                bucket_rms * 0.76
                                + bucket_peak * 0.24
                            )

                            bucket_level = (
                                bucket_raw - 0.012
                            ) / 0.22

                            bars.append(
                                max(
                                    0.0,
                                    min(1.0, bucket_level)
                                )
                            )

                        outer.on_tts_output_waveform(
                            level,
                            tuple(bars)
                        )

                    except Exception as exc:
                        print(
                            "811: TTS output waveform error:",
                            repr(exc)
                        )

                @java_method(
                    "(Landroid/media/audiofx/"
                    "Visualizer;[BI)V"
                )
                def onFftDataCapture(
                    self,
                    visualizer,
                    fft,
                    sampling_rate
                ):
                    # Waveform data is enough for real loudness reaction.
                    pass

            visualizer = Visualizer(0)

            capture_range = (
                Visualizer.getCaptureSizeRange()
            )

            min_capture = int(
                capture_range[0]
            )
            max_capture = int(
                capture_range[1]
            )

            capture_size = max(
                min_capture,
                min(512, max_capture)
            )

            visualizer.setCaptureSize(
                capture_size
            )

            capture_rate = int(
                Visualizer.getMaxCaptureRate()
            )

            listener = OutputCaptureListener()

            result = visualizer.setDataCaptureListener(
                listener,
                capture_rate,
                True,
                False
            )

            # Visualizer.SUCCESS is 0. Treat any other result as unavailable.
            if int(result) != 0:
                try:
                    visualizer.release()
                except Exception:
                    pass

                print(
                    "811: TTS output Visualizer listener unavailable:",
                    result
                )
                return

            visualizer.setEnabled(
                True
            )

            # Keep strong references while Android callbacks are active.
            self._tts_output_visualizer = visualizer
            self._tts_output_visualizer_listener = listener

            print(
                "811: Real TTS output visualizer started"
            )

        except Exception as exc:
            self._tts_output_visualizer = None
            self._tts_output_visualizer_listener = None

            # This feature is optional. A device/ROM may block output-mix
            # Visualizer access; never let that break the working TTS path.
            print(
                "811: Real TTS output visualizer unavailable:",
                repr(exc)
            )

    def _stop_tts_output_visualizer(
        self
    ):
        if platform != "android":
            self._tts_output_visualizer = None
            self._tts_output_visualizer_listener = None
            return

        self._run_on_android_ui(
            self._stop_tts_output_visualizer_on_ui
        )

    def _stop_tts_output_visualizer_on_ui(
        self
    ):
        visualizer = self._tts_output_visualizer

        self._tts_output_visualizer = None
        self._tts_output_visualizer_listener = None

        if visualizer is None:
            return

        try:
            visualizer.setEnabled(
                False
            )
        except Exception:
            pass

        try:
            visualizer.release()
        except Exception:
            pass

        print(
            "811: TTS output visualizer stopped"
        )

    @mainthread
    def on_tts_output_waveform(
        self,
        level,
        bars
    ):
        """Drive the green orb and center bars from the real TTS output."""
        if not self.tts_is_speaking:
            return

        self.status_orb.set_tts_waveform(
            level,
            bars
        )

    def speak(
        self,
        text
    ):
        if platform != "android":
            print(
                "811 [Desktop TTS]:",
                text
            )
            return

        text = clean_for_speech(
            text
        )

        if not text:
            return

        self._tts_pending_text = text

        self._run_on_android_ui(
            lambda:
            self._speak_on_android_ui(
                text
            )
        )

    def _speak_on_android_ui(
        self,
        text
    ):
        try:
            from jnius import (
                autoclass,
                cast
            )

            TextToSpeech = autoclass(
                "android.speech.tts.TextToSpeech"
            )

            Bundle = autoclass(
                "android.os.Bundle"
            )

            AudioManager = autoclass(
                "android.media.AudioManager"
            )

            JavaString = autoclass(
                "java.lang.String"
            )

            HashMap = autoclass(
                "java.util.HashMap"
            )

            if (
                self.tts is None
                or not self.tts_ready
                or not self.tts_language_ready
            ):
                print(
                    "811: TTS not ready; reinitializing."
                )

                self._tts_pending_text = text
                self._init_native_tts_on_ui()
                return

            utterance_id = (
                "811_utterance_"
                + str(
                    abs(
                        hash(text)
                    )
                )
            )

            queue_mode = int(
                TextToSpeech.QUEUE_FLUSH
            )

            # -------------------------------------------------
            # Android API 21+ modern overload:
            # speak(CharSequence, int, Bundle, String)
            #
            # Pyjnius does not always up-cast a Python string
            # to java.lang.CharSequence automatically.  That
            # was the exact runtime failure seen on the phone.
            # Force the Java types explicitly.
            # -------------------------------------------------

            modern_error = None
            result = None

            try:
                params = Bundle()

                try:
                    params.putInt(
                        TextToSpeech.Engine.KEY_PARAM_STREAM,
                        AudioManager.STREAM_MUSIC
                    )

                    params.putFloat(
                        TextToSpeech.Engine.KEY_PARAM_VOLUME,
                        1.0
                    )
                except Exception as params_exc:
                    print(
                        "811: TTS params warning:",
                        repr(params_exc)
                    )

                java_text = cast(
                    "java.lang.CharSequence",
                    JavaString(text)
                )

                java_utterance_id = JavaString(
                    utterance_id
                )

                result = self.tts.speak(
                    java_text,
                    queue_mode,
                    params,
                    java_utterance_id
                )

                print(
                    "811: TTS modern speak overload used"
                )

            except Exception as exc:
                modern_error = exc

                print(
                    "811: TTS modern speak overload failed:",
                    repr(exc)
                )

            # -------------------------------------------------
            # Defensive fallback:
            # speak(String, int, HashMap)
            #
            # This overload is deprecated by Android but is
            # still present and is very reliable through
            # Pyjnius because every argument has an exact Java
            # class rather than an interface type.
            # -------------------------------------------------

            if result is None:
                legacy_params = HashMap()

                try:
                    legacy_params.put(
                        TextToSpeech.Engine.KEY_PARAM_STREAM,
                        JavaString(
                            str(
                                AudioManager.STREAM_MUSIC
                            )
                        )
                    )

                    legacy_params.put(
                        TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID,
                        JavaString(
                            utterance_id
                        )
                    )
                except Exception as legacy_params_exc:
                    print(
                        "811: TTS legacy params warning:",
                        repr(legacy_params_exc)
                    )

                try:
                    result = self.tts.speak(
                        JavaString(text),
                        queue_mode,
                        legacy_params
                    )

                    print(
                        "811: TTS legacy speak fallback used"
                    )

                except Exception as legacy_exc:
                    self.tts_is_speaking = False
                    self.tts_init_error = (
                        "TTS-02: تعذر استدعاء محرك النطق على هذا الجهاز."
                    )

                    print(
                        "811: TTS legacy speak fallback failed:",
                        repr(legacy_exc)
                    )

                    if modern_error is not None:
                        print(
                            "811: TTS modern failure was:",
                            repr(modern_error)
                        )

                    Clock.schedule_once(
                        lambda dt:
                        self._show_tts_error(),
                        0
                    )
                    return

            self.tts_last_result = int(
                result
            )

            if int(result) == int(
                TextToSpeech.ERROR
            ):
                self.tts_is_speaking = False
                self.tts_init_error = (
                    "TTS-03: محرك Android رفض تشغيل الرد الصوتي."
                )

                print(
                    "811: TTS speak returned ERROR"
                )

                Clock.schedule_once(
                    lambda dt:
                    self._show_tts_error(),
                    0
                )
                return

            self._tts_pending_text = ""
            self.tts_is_speaking = True
            self.tts_init_error = ""

            print(
                "811: TTS speak queued successfully"
            )

            # Analyze the actual audio output while this utterance plays.
            # Failure is non-fatal: speech remains untouched.
            self._start_tts_output_visualizer()

            self._tts_watch_generation += 1
            watch_generation = self._tts_watch_generation

            Clock.schedule_once(
                lambda dt:
                self._watch_tts_completion(
                    dt,
                    watch_generation
                ),
                0.35
            )

        except Exception as exc:
            self.tts_is_speaking = False
            self.tts_init_error = (
                "TTS-01: تعذر تجهيز الرد الصوتي."
            )

            print(
                "811: TTS speak error:",
                repr(exc)
            )

            Clock.schedule_once(
                lambda dt:
                self._show_tts_error(),
                0
            )

    def _watch_tts_completion(
        self,
        dt,
        watch_generation
    ):
        # A Clear/interrupt increments the generation, invalidating old watchers.
        if watch_generation != self._tts_watch_generation:
            return

        if platform != "android":
            self.tts_is_speaking = False
            return

        try:
            if (
                self.tts is not None
                and self.tts.isSpeaking()
            ):
                self.tts_is_speaking = True

                Clock.schedule_once(
                    lambda next_dt:
                    self._watch_tts_completion(
                        next_dt,
                        watch_generation
                    ),
                    0.30
                )
                return

        except Exception as exc:
            print(
                "811: TTS isSpeaking check error:",
                repr(exc)
            )

        self.tts_is_speaking = False
        self._stop_tts_output_visualizer()

        # Successful turn complete: either continue the hands-free dialogue
        # or return to the normal one-shot ready state.
        self._schedule_handsfree_resume()

    def stop_speaking(
        self
    ):
        """Immediately stop queued/current Android TTS without shutting it down."""
        self._tts_pending_text = ""
        self.tts_is_speaking = False
        self._tts_watch_generation += 1
        self._stop_tts_output_visualizer()

        if platform != "android":
            return

        if self.tts is None:
            return

        self._run_on_android_ui(
            self._stop_speaking_on_android_ui
        )

    def _stop_speaking_on_android_ui(
        self
    ):
        try:
            if self.tts is not None:
                result = self.tts.stop()
                print("811: TTS stopped by user; result:", result)
        except Exception as exc:
            print("811: TTS stop error:", repr(exc))

    def _show_tts_error(
        self
    ):
        self._disable_handsfree()
        self._stop_tts_output_visualizer()
        self.processing = False
        self.speak_btn.disabled = False

        details = (
            self.tts_init_error
            or "TTS-00: تعذر تشغيل الرد الصوتي."
        )

        if (
            self.tts_media_volume is not None
            and self.tts_media_volume <= 0
        ):
            details += (
                "\n"
                "مستوى صوت الوسائط في الهاتف يساوي صفر."
            )

        self.status_label.text = fix_text(
            "تعذر تشغيل الرد الصوتي"
        )

        self.status_label.color = (
            1.0,
            0.28,
            0.30,
            1.0
        )

        self.status_orb.set_state(
            "error"
        )

        self._append_chat_text(
            "تشخيص الصوت:\n"
            + details,
            role="system"
        )

    # =====================================================
    # MICROPHONE PERMISSION
    # =====================================================

    def _has_record_audio_permission(
        self
    ):
        if platform != "android":
            return False

        try:
            from android.permissions import (
                check_permission,
                Permission
            )

            return bool(
                check_permission(
                    Permission.RECORD_AUDIO
                )
            )

        except Exception as exc:
            print(
                "811: RECORD_AUDIO permission check error:",
                repr(exc)
            )
            return False

    def _request_record_audio_permission(
        self
    ):
        if platform != "android":
            return

        try:
            from android.permissions import (
                request_permissions,
                Permission
            )

            request_permissions(
                [
                    Permission.RECORD_AUDIO
                ]
            )

            print(
                "811: RECORD_AUDIO permission requested"
            )

        except Exception as exc:
            print(
                "811: RECORD_AUDIO permission request error:",
                repr(exc)
            )

    # =====================================================
    # SPEECH ERROR MAP
    # =====================================================

    def _speech_error_info(
        self,
        error_code
    ):
        errors = {
            1: (
                "ERROR_NETWORK_TIMEOUT",
                "انتهت مهلة اتصال خدمة التعرف على الكلام."
            ),
            2: (
                "ERROR_NETWORK",
                "حدث خطأ في شبكة خدمة التعرف على الكلام."
            ),
            3: (
                "ERROR_AUDIO",
                "حدث خطأ أثناء تسجيل الصوت من الميكروفون."
            ),
            4: (
                "ERROR_SERVER",
                "خادم التعرف على الكلام أعاد خطأ."
            ),
            5: (
                "ERROR_CLIENT",
                "أوقف Android جلسة التعرف من جهة التطبيق."
            ),
            6: (
                "ERROR_SPEECH_TIMEOUT",
                "لم يتم اكتشاف كلام خلال المهلة المحددة."
            ),
            7: (
                "ERROR_NO_MATCH",
                "تم سماع صوت لكن لم يتم التعرف على كلمات مطابقة."
            ),
            8: (
                "ERROR_RECOGNIZER_BUSY",
                "محرك التعرف على الكلام مشغول حالياً."
            ),
            9: (
                "ERROR_INSUFFICIENT_PERMISSIONS",
                "صلاحية الميكروفون غير متاحة للتطبيق."
            ),
            10: (
                "ERROR_TOO_MANY_REQUESTS",
                "تم إرسال طلبات كثيرة إلى محرك التعرف."
            ),
            11: (
                "ERROR_SERVER_DISCONNECTED",
                "انقطع الاتصال بخدمة التعرف على الكلام."
            ),
            12: (
                "ERROR_LANGUAGE_NOT_SUPPORTED",
                "لغة التعرف المطلوبة غير مدعومة على هذا الجهاز."
            ),
            13: (
                "ERROR_LANGUAGE_UNAVAILABLE",
                "لغة التعرف المطلوبة مدعومة لكنها غير متاحة حالياً."
            ),
            14: (
                "ERROR_CANNOT_CHECK_SUPPORT",
                "تعذر التحقق من دعم محرك التعرف."
            ),
            15: (
                "ERROR_CANNOT_LISTEN_TO_DOWNLOAD_EVENTS",
                "تعذر الاستماع إلى أحداث تنزيل نموذج اللغة."
            )
        }

        return errors.get(
            int(error_code),
            (
                "ERROR_UNKNOWN",
                "حدث خطأ غير معروف في التعرف على الكلام."
            )
        )

    def _current_speech_language(
        self
    ):
        if (
            self.speech_language_index < 0
            or self.speech_language_index
            >= len(self.speech_languages)
        ):
            self.speech_language_index = 0

        return self.speech_languages[
            self.speech_language_index
        ]

    def _speech_language_label(
        self
    ):
        language = (
            self._current_speech_language()
        )

        if language is None:
            return "SYSTEM_DEFAULT"

        return language

    # =====================================================
    # SPEECH RECOGNIZER INITIALIZATION
    # =====================================================

    def init_native_speech(
        self
    ):
        if platform != "android":
            return

        self._run_on_android_ui(
            self._init_native_speech_on_ui
        )

    def _init_native_speech_on_ui(
        self
    ):
        try:
            from jnius import (
                autoclass,
                PythonJavaClass,
                java_method
            )

            self._speech_autoclass = (
                autoclass
            )

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            SpeechRecognizer = autoclass(
                "android.speech.SpeechRecognizer"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                self.speech_recognizer_ready = False
                self.speech_init_error = (
                    "Android Activity unavailable"
                )

                print(
                    "811:",
                    self.speech_init_error
                )
                return

            available = (
                SpeechRecognizer
                .isRecognitionAvailable(
                    activity
                )
            )

            print(
                "811: SpeechRecognizer availability:",
                bool(available)
            )

            if not available:
                self.speech_recognizer_ready = False
                self.speech_init_error = (
                    "No RecognitionService available"
                )

                print(
                    "811:",
                    self.speech_init_error
                )
                return

            outer = self

            class RecognitionListener(
                PythonJavaClass
            ):
                __javainterfaces__ = [
                    "android/speech/"
                    "RecognitionListener"
                ]
                __javacontext__ = "app"

                @java_method(
                    "(Landroid/os/Bundle;)V"
                )
                def onReadyForSpeech(
                    self,
                    params
                ):
                    outer.on_speech_ready()

                @java_method(
                    "()V"
                )
                def onBeginningOfSpeech(
                    self
                ):
                    outer.on_speech_begin()

                @java_method(
                    "(F)V"
                )
                def onRmsChanged(
                    self,
                    rmsdB
                ):
                    outer.on_speech_rms(
                        float(rmsdB)
                    )

                @java_method(
                    "([B)V"
                )
                def onBufferReceived(
                    self,
                    buffer
                ):
                    pass

                @java_method(
                    "()V"
                )
                def onEndOfSpeech(
                    self
                ):
                    outer.on_speech_end()

                @java_method(
                    "(I)V"
                )
                def onError(
                    self,
                    error
                ):
                    outer.on_speech_error(
                        int(error)
                    )

                @java_method(
                    "(Landroid/os/Bundle;)V"
                )
                def onResults(
                    self,
                    results
                ):
                    # Important:
                    # Extract Java Bundle data inside the Java callback.
                    # Only a normal Python string crosses to Kivy's thread.
                    text = (
                        outer
                        ._extract_speech_results(
                            results
                        )
                    )

                    outer.on_speech_results_text(
                        text
                    )

                @java_method(
                    "(Landroid/os/Bundle;)V"
                )
                def onPartialResults(
                    self,
                    results
                ):
                    text = (
                        outer
                        ._extract_speech_results(
                            results
                        )
                    )

                    outer.on_speech_partial_text(
                        text
                    )

                @java_method(
                    "(ILandroid/os/Bundle;)V"
                )
                def onEvent(
                    self,
                    event_type,
                    params
                ):
                    pass

            self._speech_listener = (
                RecognitionListener()
            )

            recognizer = (
                SpeechRecognizer
                .createSpeechRecognizer(
                    activity
                )
            )

            if recognizer is None:
                self.speech_recognizer_ready = False
                self.speech_init_error = (
                    "createSpeechRecognizer returned null"
                )

                print(
                    "811:",
                    self.speech_init_error
                )
                return

            self.speech_recognizer = recognizer

            self.speech_recognizer.setRecognitionListener(
                self._speech_listener
            )

            self.speech_recognizer_ready = True
            self.speech_init_error = ""

            print(
                "811: SpeechRecognizer READY"
            )

        except Exception as exc:
            self.speech_recognizer = None
            self.speech_recognizer_ready = False

            self.speech_init_error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            print(
                "811: SpeechRecognizer init FAILED:"
            )

            print(
                "811:",
                self.speech_init_error
            )

    # =====================================================
    # START LISTENING
    # =====================================================

    def start_listening(
        self
    ):
        if platform != "android":
            self.set_state(
                "error",
                "الاستماع الصوتي متاح على Android فقط."
            )
            return

        if self.processing:
            return

        if self.is_listening:
            return

        if not self._has_record_audio_permission():
            self._request_record_audio_permission()

            self.set_state(
                "error",
                "صلاحية الميكروفون غير مفعلة.\n"
                "تم طلب صلاحية RECORD_AUDIO.\n"
                "وافق عليها ثم اضغط للتحدث مرة أخرى."
            )
            return

        if not self.speech_recognizer_ready:
            message = (
                "محرك التعرف على الكلام غير جاهز."
            )

            if self.speech_init_error:
                message += (
                    "\n\n"
                    + self.speech_init_error
                )

            self.set_state(
                "error",
                message
            )

            # Try initialization one more time in case permissions
            # were granted after app startup.
            self.init_native_speech()
            return

        self.speech_recovery_attempts = 0
        self._active_user_row = None

        self._run_on_android_ui(
            self._start_listening_on_ui
        )

    def _start_listening_on_ui(
        self
    ):
        try:
            from jnius import autoclass

            Intent = autoclass(
                "android.content.Intent"
            )

            RecognizerIntent = autoclass(
                "android.speech.RecognizerIntent"
            )

            intent = Intent(
                RecognizerIntent
                .ACTION_RECOGNIZE_SPEECH
            )

            intent.putExtra(
                RecognizerIntent
                .EXTRA_LANGUAGE_MODEL,
                RecognizerIntent
                .LANGUAGE_MODEL_FREE_FORM
            )

            language = (
                self._current_speech_language()
            )

            if language:
                intent.putExtra(
                    RecognizerIntent
                    .EXTRA_LANGUAGE,
                    language
                )

            intent.putExtra(
                RecognizerIntent
                .EXTRA_PARTIAL_RESULTS,
                True
            )

            intent.putExtra(
                RecognizerIntent
                .EXTRA_MAX_RESULTS,
                3
            )

            intent.putExtra(
                RecognizerIntent
                .EXTRA_PROMPT,
                "تحدث الآن"
            )

            print(
                "811: startListening language:",
                self._speech_language_label()
            )

            self.speech_recognizer.startListening(
                intent
            )

            self.is_listening = True

            Clock.schedule_once(
                lambda dt:
                self.set_state(
                    "listening",
                    "جاري الاستماع...\n"
                    "اللغة: "
                    + self._speech_language_label()
                ),
                0
            )

            print(
                "811: startListening OK"
            )

        except Exception as exc:
            self.is_listening = False

            print(
                "811: startListening FAILED:",
                repr(exc)
            )

            message = (
                "تعذر بدء الاستماع.\n"
                + type(exc).__name__
                + ": "
                + str(exc)
            )

            Clock.schedule_once(
                lambda dt:
                self.set_state(
                    "error",
                    message
                ),
                0
            )

    # =====================================================
    # STOP LISTENING
    # =====================================================

    def stop_listening(
        self
    ):
        if self.speech_recognizer is None:
            return

        self._run_on_android_ui(
            self._stop_listening_on_ui
        )

    def _stop_listening_on_ui(
        self
    ):
        try:
            self.speech_recognizer.stopListening()
        except Exception as exc:
            print(
                "811: stopListening error:",
                repr(exc)
            )

        self.is_listening = False

        if not self.processing:
            Clock.schedule_once(
                lambda dt:
                self.set_state(
                    "ready"
                ),
                0
            )

    def cancel_listening(
        self
    ):
        """Cancel SpeechRecognizer without accepting a final result."""
        self.is_listening = False

        if self.speech_recognizer is None:
            return

        self._ignore_next_speech_error = True
        self._run_on_android_ui(
            self._cancel_listening_on_ui
        )

        # Android commonly reports ERROR_CLIENT after cancel(). Ignore only
        # that immediate callback; clear the guard if no callback arrives.
        Clock.schedule_once(
            self._clear_speech_cancel_guard,
            1.0
        )

    def _cancel_listening_on_ui(
        self
    ):
        try:
            if self.speech_recognizer is not None:
                self.speech_recognizer.cancel()
                print("811: SpeechRecognizer cancelled by user")
        except Exception as exc:
            print("811: SpeechRecognizer cancel error:", repr(exc))

    def _clear_speech_cancel_guard(
        self,
        dt
    ):
        self._ignore_next_speech_error = False

    # =====================================================
    # SPEECH RESULTS
    # =====================================================

    def _extract_speech_results(
        self,
        results
    ):
        if results is None:
            return ""

        try:
            SpeechRecognizer = (
                self._speech_autoclass(
                    "android.speech."
                    "SpeechRecognizer"
                )
            )

            matches = (
                results
                .getStringArrayList(
                    SpeechRecognizer
                    .RESULTS_RECOGNITION
                )
            )

            if matches is None:
                return ""

            if matches.size() == 0:
                return ""

            return str(
                matches.get(0)
            )

        except Exception as exc:
            print(
                "811: speech result error:",
                repr(exc)
            )
            return ""

    # =====================================================
    # SPEECH CALLBACKS
    # =====================================================

    @mainthread
    def on_speech_rms(
        self,
        rms_db
    ):
        """Drive the visualizer from real microphone loudness while listening."""
        if not self.is_listening:
            return

        try:
            rms_db = float(rms_db)
        except Exception:
            return

        # Android SpeechRecognizer commonly reports roughly -2..10+ dB.
        # Clamp it into a stable visual 0..1 range and ignore tiny room noise.
        level = (rms_db + 2.0) / 12.0
        level = max(0.0, min(1.0, level))

        if level < 0.08:
            level = 0.0

        self.status_orb.set_voice_level(
            level
        )

    @mainthread
    def on_speech_ready(
        self
    ):
        if not self.processing:
            self.set_state(
                "listening"
            )

    @mainthread
    def on_speech_begin(
        self
    ):
        self.set_state(
            "listening"
        )

    @mainthread
    def on_speech_end(
        self
    ):
        if self.is_listening:
            self.set_state(
                "thinking"
            )

    @mainthread
    def on_speech_partial_text(
        self,
        text
    ):
        text = clean_unicode(
            text
        )

        if text:
            self._update_user_draft(
                text
            )

    @mainthread
    def on_speech_results_text(
        self,
        text
    ):
        self.is_listening = False
        self.speech_recovery_attempts = 0

        text = clean_unicode(
            text
        )

        if not text:
            self._disable_handsfree()
            self.processing = False
            self.speak_btn.disabled = False

            self.set_state(
                "error",
                "لم أتمكن من فهم الكلام."
            )

            Clock.schedule_once(
                lambda dt:
                self._return_to_ready(),
                2.0
            )
            return

        self._commit_user_message(
            text
        )

        api_key = (
            self.key_input
            .text
            .strip()
        )

        if not api_key:
            self._disable_handsfree()
            self.processing = False
            self.speak_btn.disabled = False

            self.set_state(
                "error",
                "أدخل مفتاح AI أولاً."
            )
            return

        self._save_api_key(
            api_key
        )

        self.processing = True
        self.speak_btn.disabled = True
        self._request_serial += 1
        request_serial = self._request_serial

        self.set_state(
            "thinking"
        )

        threading.Thread(
            target=self.process_user_text,
            args=(
                text,
                api_key,
                request_serial
            ),
            daemon=True
        ).start()

    @mainthread
    def on_speech_error(
        self,
        error_code
    ):
        self.is_listening = False

        error_code = int(
            error_code
        )

        if self._ignore_next_speech_error:
            self._ignore_next_speech_error = False
            print(
                "811: Ignored SpeechRecognizer error after user cancel:",
                error_code
            )
            return

        error_name, description = (
            self._speech_error_info(
                error_code
            )
        )

        self.speech_last_error_code = (
            error_code
        )

        self.speech_last_error_name = (
            error_name
        )

        print(
            "811 SpeechRecognizer error:",
            error_code,
            error_name,
            "| language:",
            self._speech_language_label()
        )

        # -------------------------------------------------
        # Automatic language fallback
        # -------------------------------------------------

        if error_code in (12, 13):
            next_index = (
                self.speech_language_index + 1
            )

            if next_index < len(
                self.speech_languages
            ):
                old_language = (
                    self._speech_language_label()
                )

                self.speech_language_index = (
                    next_index
                )

                new_language = (
                    self._speech_language_label()
                )

                self.set_state(
                    "listening",
                    "لغة التعرف "
                    + old_language
                    + " غير متاحة.\n"
                    + "أجرب تلقائياً: "
                    + new_language
                )

                print(
                    "811: Speech language fallback:",
                    old_language,
                    "->",
                    new_language
                )

                Clock.schedule_once(
                    lambda dt:
                    self._run_on_android_ui(
                        self._start_listening_on_ui
                    ),
                    0.35
                )
                return

        # -------------------------------------------------
        # Permission recovery
        # -------------------------------------------------

        if error_code == 9:
            self._request_record_audio_permission()
            self._disable_handsfree()

            self.processing = False
            self.speak_btn.disabled = False

            self.set_state(
                "error",
                "SpeechRecognizer Error "
                + str(error_code)
                + "\n"
                + error_name
                + "\n\n"
                + description
                + "\n\n"
                + "تم طلب صلاحية الميكروفون مرة أخرى."
            )
            return

        # -------------------------------------------------
        # One safe automatic recognizer recovery
        # -------------------------------------------------

        if (
            error_code in (5, 8, 11)
            and self.speech_recovery_attempts
            < self.speech_max_recovery_attempts
        ):
            self.speech_recovery_attempts += 1

            self.set_state(
                "listening",
                "SpeechRecognizer Error "
                + str(error_code)
                + "\n"
                + error_name
                + "\n\n"
                + "أعيد تهيئة محرك الصوت مرة واحدة..."
            )

            Clock.schedule_once(
                lambda dt:
                self._run_on_android_ui(
                    self._recreate_speech_and_retry_on_ui
                ),
                0.45
            )
            return

        # -------------------------------------------------
        # Final diagnostic error shown on screen
        # -------------------------------------------------

        self._disable_handsfree()
        self.processing = False
        self.speak_btn.disabled = False

        diagnostic_message = (
            "SpeechRecognizer Error "
            + str(error_code)
            + "\n"
            + error_name
            + "\n\n"
            + description
            + "\n\n"
            + "Language: "
            + self._speech_language_label()
        )

        self.set_state(
            "error",
            diagnostic_message
        )

        # Keep the diagnostic visible longer so it can be
        # photographed or copied.
        Clock.schedule_once(
            lambda dt:
            self._return_to_ready(),
            6.0
        )

    # =====================================================
    # SPEECH RECOVERY
    # =====================================================

    def _recreate_speech_and_retry_on_ui(
        self
    ):
        try:
            if self.speech_recognizer is not None:
                try:
                    self.speech_recognizer.cancel()
                except Exception:
                    pass

                try:
                    self.speech_recognizer.destroy()
                except Exception:
                    pass

            self.speech_recognizer = None
            self.speech_recognizer_ready = False
            self._speech_listener = None

            print(
                "811: Recreating SpeechRecognizer..."
            )

            self._init_native_speech_on_ui()

            if not self.speech_recognizer_ready:
                message = (
                    "فشلت إعادة تهيئة SpeechRecognizer.\n"
                    + self.speech_init_error
                )

                Clock.schedule_once(
                    lambda dt:
                    self.set_state(
                        "error",
                        message
                    ),
                    0
                )
                return

            self._start_listening_on_ui()

        except Exception as exc:
            print(
                "811: SpeechRecognizer recovery failed:",
                repr(exc)
            )

            message = (
                "فشلت إعادة تهيئة محرك الصوت.\n"
                + type(exc).__name__
                + ": "
                + str(exc)
            )

            Clock.schedule_once(
                lambda dt:
                self.set_state(
                    "error",
                    message
                ),
                0
            )

    # =====================================================
    # HANDS-FREE SESSION
    # =====================================================

    def _enable_handsfree(
        self
    ):
        self._handsfree_generation += 1
        self.handsfree_active = True

        print(
            "811: Hands-free session enabled"
        )

    def _disable_handsfree(
        self
    ):
        self._handsfree_generation += 1
        self.handsfree_active = False

        print(
            "811: Hands-free session disabled"
        )

    def _schedule_handsfree_resume(
        self
    ):
        """Restart listening shortly after a successful TTS turn."""
        if not self.handsfree_active:
            self._return_to_ready()
            return

        generation = self._handsfree_generation

        # Brief natural gap after 811 finishes so the phone speaker/TTS tail
        # cannot be picked up by SpeechRecognizer as the user's next phrase.
        self._return_to_ready()

        Clock.schedule_once(
            lambda dt:
            self._resume_handsfree_listening(
                generation
            ),
            0.55
        )

    def _resume_handsfree_listening(
        self,
        generation
    ):
        if not self.handsfree_active:
            return

        if generation != self._handsfree_generation:
            return

        if self.processing:
            return

        if self.is_listening:
            return

        if self.tts_is_speaking:
            return

        if self._tts_pending_text:
            return

        print(
            "811: Hands-free restarting listening"
        )

        self.start_listening()

    # =====================================================
    # BUTTON
    # =====================================================

    def on_speak_click(
        self,
        instance
    ):
        if self.processing:
            return

        if self.is_listening:
            # Manual stop means the user wants to end the automatic dialogue.
            self._disable_handsfree()
            self.stop_listening()
            return

        # Prevent repeated Talk presses while 811 is still speaking.
        if self.tts_is_speaking or self._tts_pending_text:
            return

        api_key = (
            self.key_input
            .text
            .strip()
        )

        if not api_key:
            self._disable_handsfree()
            self.set_state(
                "error",
                "يرجى إدخال مفتاح AI أولاً."
            )
            return

        self._save_api_key(
            api_key
        )

        # One press begins the hands-free conversation session.
        self._enable_handsfree()
        self.start_listening()

    # =====================================================
    # AI PIPELINE
    # =====================================================

    def process_user_text(
        self,
        user_text,
        api_key,
        request_serial
    ):
        try:
            if request_serial != self._request_serial:
                return

            if self.ai_engine is None:
                self.update_error(
                    "تعذر تهيئة محرك الذكاء الاصطناعي.",
                    request_serial
                )
                return

            provider = (
                self.ai_engine
                .set_api_key(
                    api_key
                )
            )

            print(
                "811: AI provider for request:",
                provider or "unknown"
            )

            response = (
                self.ai_engine
                .get_response(
                    user_text
                )
            )

            response = (
                ""
                if response is None
                else str(response).strip()
            )

            if not response:
                response = (
                    "لم يصلني رد من "
                    "الذكاء الاصطناعي."
                )

            if request_serial != self._request_serial:
                print("811: Ignored stale AI response after Clear/interrupt")
                return

            self.update_voice_conversation(
                user_text,
                response,
                request_serial
            )

        except Exception as exc:
            print(
                "811: AI pipeline error:",
                repr(exc)
            )

            self.update_error(
                "حدث خطأ أثناء معالجة طلبك.",
                request_serial
            )

    @mainthread
    def update_voice_conversation(
        self,
        user_text,
        response,
        request_serial
    ):
        if request_serial != self._request_serial:
            return

        self.processing = False
        self.speak_btn.disabled = False

        self._append_chat_text(
            response,
            role="assistant"
        )

        self.set_state(
            "speaking"
        )

        self.speak(
            clean_for_speech(
                response
            )
        )

        # The TTS watcher returns the UI to ready when playback ends.

    @mainthread
    def update_error(
        self,
        message,
        request_serial=None
    ):
        if (
            request_serial is not None
            and request_serial != self._request_serial
        ):
            return

        self._disable_handsfree()
        self.processing = False
        self.speak_btn.disabled = False

        self.set_state(
            "error",
            message
        )

        Clock.schedule_once(
            lambda dt:
            self._return_to_ready(),
            2.5
        )

    # =====================================================
    # READY
    # =====================================================

    def _return_to_ready(
        self,
        *args
    ):
        if self.processing:
            return

        if self.is_listening:
            return

        self.set_state(
            "ready"
        )

    # =====================================================
    # CLEAR
    # =====================================================

    def on_clear_click(
        self,
        instance
    ):
        # Clear is an emergency stop as well as a conversation reset.
        # It must work while listening, thinking, speaking, or waiting for the
        # next automatic hands-free turn.
        self._disable_handsfree()
        self._request_serial += 1
        self.processing = False
        self.speak_btn.disabled = False

        if self.is_listening:
            self.cancel_listening()

        self.stop_speaking()

        self._set_chat_text(
            "تم مسح الشاشة.\n"
            "أنا 811.\n"
            "جاهز.",
            role="assistant"
        )

        if self.ai_engine is not None:
            try:
                self.ai_engine.clear_history()
            except Exception as exc:
                print(
                    "811: clear_history error:",
                    repr(exc)
                )

        self.set_state(
            "ready"
        )

        self.key_input.focus = False

    # =====================================================
    # APP BACKGROUND / FOREGROUND
    # =====================================================

    def on_pause(
        self
    ):
        self._app_is_foreground = False

        # Phase 2A only gives the service the microphone when there is no
        # active hands-free/voice turn. This protects the stable recognizer.
        safe_to_capture = (
            not self.handsfree_active
            and not self.processing
            and not self.is_listening
            and not self.tts_is_speaking
            and not self._tts_pending_text
        )

        self._set_background_wake_capture(
            safe_to_capture,
            (
                "app_background_idle"
                if safe_to_capture
                else "app_background_voice_session"
            )
        )

        # Phase 2B: one controlled proof that the SERVICE can speak while the
        # Kivy Activity is paused. It runs only once per app session and only
        # when no foreground voice turn is active.
        if (
            safe_to_capture
            and not self._background_tts_probe_sent
        ):
            sent = self._send_background_core_command(
                "tts_probe",
                text=(
                    "أنا 811. "
                    "التشغيل في الخلفية جاهز."
                )
            )

            if sent:
                self._background_tts_probe_sent = True

        # Returning True lets Kivy pause normally while keeping the Android
        # foreground service alive.
        return True

    def on_resume(
        self
    ):
        self._app_is_foreground = True

        # Release the service microphone before the user interacts with the
        # foreground SpeechRecognizer.
        self._set_background_wake_capture(
            False,
            "app_foreground"
        )

    # =====================================================
    # STOP
    # =====================================================

    def on_stop(
        self
    ):
        self._disable_handsfree()

        try:
            if self.speech_recognizer is not None:
                self._run_on_android_ui(
                    self._destroy_speech_on_ui
                )

        except Exception as exc:
            print(
                "811: SpeechRecognizer destroy error:",
                repr(exc)
            )

        try:
            if self.tts is not None:
                self.tts.stop()
                self.tts.shutdown()

        except Exception as exc:
            print(
                "811: TTS shutdown error:",
                repr(exc)
            )

        self._app_is_foreground = False
        self._set_background_wake_capture(
            True,
            "app_stopped"
        )

        super().on_stop()

    def _destroy_speech_on_ui(
        self
    ):
        try:
            if self.speech_recognizer is not None:
                try:
                    self.speech_recognizer.cancel()
                except Exception:
                    pass

                self.speech_recognizer.destroy()
                self.speech_recognizer = None
                self.speech_recognizer_ready = False
                self._speech_listener = None

                print(
                    "811: SpeechRecognizer destroyed"
                )

        except Exception as exc:
            print(
                "811: SpeechRecognizer shutdown error:",
                repr(exc)
            )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    VoiceAssistantApp().run()
