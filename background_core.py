"""
Voice Assistant 811 — Phase 2B Background TTS Bridge

This phase keeps every successful Phase 2A behavior and adds ONE capability:
the Background Core can speak Arabic through Android TextToSpeech even while
the Kivy Activity is paused or not visible.

Important:
- The service still does NOT call Groq.
- The service still does NOT run SpeechRecognizer.
- The service still does NOT implement the "811" wake-word model.
- AudioRecord is released before TTS speaks, then may resume afterward.
- The app sends a one-time "tts_probe" command when it first goes safely to
  background. The expected phrase is:
      "أنا 811. التشغيل في الخلفية جاهز."

This isolates and proves background TTS before the AI pipeline is moved into
the service in a later phase.
"""

import json
import os
import time

from jnius import (
    autoclass,
    PythonJavaClass,
    java_method,
)


SAMPLE_RATE = 16000
CHANNELS = 1
HEARTBEAT_INTERVAL_SECONDS = 3.0

HEARTBEAT_FILENAME = "811_background_core_heartbeat.json"
CONTROL_FILENAME = "811_background_core_control.txt"
COMMAND_FILENAME = "811_background_core_command.json"


def _service_instance():
    PythonService = autoclass(
        "org.kivy.android.PythonService"
    )
    return PythonService.mService


def _files_dir(service):
    return str(
        service
        .getFilesDir()
        .getAbsolutePath()
    )


def _heartbeat_path(service):
    return os.path.join(
        _files_dir(service),
        HEARTBEAT_FILENAME
    )


def _control_path(service):
    return os.path.join(
        _files_dir(service),
        CONTROL_FILENAME
    )


def _command_path(service):
    return os.path.join(
        _files_dir(service),
        COMMAND_FILENAME
    )


def _read_capture_command(path):
    """
    Missing/invalid control data always defaults to PAUSED for safety.
    """
    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as handle:
            first_line = (
                handle.readline()
                .strip()
                .lower()
            )

        return first_line == "capture"

    except FileNotFoundError:
        return False

    except Exception as exc:
        print(
            "811: Background control read error:",
            repr(exc)
        )
        return False


def _read_one_shot_command(
    path,
    last_command_id
):
    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as handle:
            command = json.load(
                handle
            )

        command_id = str(
            command.get(
                "id",
                ""
            )
        ).strip()

        if not command_id:
            return None

        if command_id == last_command_id:
            return None

        return command

    except FileNotFoundError:
        return None

    except Exception as exc:
        print(
            "811: Background command read error:",
            repr(exc)
        )
        return None


def _write_heartbeat(
    path,
    started_at,
    state,
    capture_blocks,
    last_read_bytes,
    audio_source,
    last_command_id,
    tts_ready,
    error=""
):
    payload = {
        "service": "811-background-core",
        "phase": "2B",
        "state": state,
        "pid": os.getpid(),
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "audio_source": audio_source,
        "capture_blocks": capture_blocks,
        "last_read_bytes": last_read_bytes,
        "last_command_id": last_command_id,
        "tts_ready": bool(tts_ready),
        "error": error,
        "started_at": started_at,
        "updated_at": time.time(),
    }

    temp_path = path + ".tmp"

    with open(
        temp_path,
        "w",
        encoding="utf-8"
    ) as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False
        )

    os.replace(
        temp_path,
        path
    )


def _release_recorder(recorder):
    if recorder is None:
        return

    try:
        recorder.stop()
    except Exception:
        pass

    try:
        recorder.release()
    except Exception:
        pass


def _create_audio_record():
    """
    Prefer VOICE_RECOGNITION for cleaner speech input.
    Fall back to the normal microphone source if the phone/ROM refuses it.
    """
    AudioRecord = autoclass(
        "android.media.AudioRecord"
    )
    AudioFormat = autoclass(
        "android.media.AudioFormat"
    )
    MediaRecorder = autoclass(
        "android.media.MediaRecorder"
    )
    ByteBuffer = autoclass(
        "java.nio.ByteBuffer"
    )

    channel_config = int(
        AudioFormat.CHANNEL_IN_MONO
    )
    encoding = int(
        AudioFormat.ENCODING_PCM_16BIT
    )

    min_buffer = int(
        AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            channel_config,
            encoding
        )
    )

    if min_buffer <= 0:
        min_buffer = 4096

    buffer_bytes = max(
        4096,
        min_buffer * 2
    )

    sources = [
        (
            int(
                MediaRecorder
                .AudioSource
                .VOICE_RECOGNITION
            ),
            "VOICE_RECOGNITION"
        ),
        (
            int(
                MediaRecorder
                .AudioSource
                .MIC
            ),
            "MIC"
        ),
    ]

    last_error = None

    for audio_source, source_name in sources:
        recorder = None

        try:
            recorder = AudioRecord(
                audio_source,
                SAMPLE_RATE,
                channel_config,
                encoding,
                buffer_bytes
            )

            if int(
                recorder.getState()
            ) != int(
                AudioRecord.STATE_INITIALIZED
            ):
                raise RuntimeError(
                    "AudioRecord was not initialized"
                )

            recorder.startRecording()

            if int(
                recorder.getRecordingState()
            ) != int(
                AudioRecord.RECORDSTATE_RECORDING
            ):
                raise RuntimeError(
                    "AudioRecord did not enter RECORDING state"
                )

            direct_buffer = (
                ByteBuffer.allocateDirect(
                    buffer_bytes
                )
            )

            print(
                "811: Background AudioRecord ready:",
                source_name,
                "| buffer:",
                buffer_bytes
            )

            return (
                recorder,
                direct_buffer,
                buffer_bytes,
                source_name
            )

        except Exception as exc:
            last_error = exc

            print(
                "811: AudioRecord source failed:",
                source_name,
                repr(exc)
            )

            _release_recorder(
                recorder
            )

    raise RuntimeError(
        "No Android microphone source could initialize: "
        + repr(last_error)
    )


class BackgroundTTS:
    """
    Small native Android TTS engine that belongs to the service process.
    """

    def __init__(
        self,
        service
    ):
        self.service = service
        self.tts = None
        self.listener = None

        self.ready = False
        self.language_ready = False
        self.error = ""

        self._create()

    def _create(
        self
    ):
        TextToSpeech = autoclass(
            "android.speech.tts.TextToSpeech"
        )
        Locale = autoclass(
            "java.util.Locale"
        )

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
                        int(status)
                        != int(TextToSpeech.SUCCESS)
                    ):
                        outer.ready = False
                        outer.language_ready = False
                        outer.error = (
                            "TextToSpeech init status "
                            + str(status)
                        )

                        print(
                            "811: Background TTS init failed:",
                            status
                        )
                        return

                    outer.ready = True
                    outer.language_ready = False
                    outer.error = ""

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
                        ),
                    ]

                    for locale in locales:
                        try:
                            available = int(
                                outer.tts
                                .isLanguageAvailable(
                                    locale
                                )
                            )

                            if (
                                available
                                < int(
                                    TextToSpeech
                                    .LANG_AVAILABLE
                                )
                            ):
                                continue

                            result = int(
                                outer.tts
                                .setLanguage(
                                    locale
                                )
                            )

                            if (
                                result
                                >= int(
                                    TextToSpeech
                                    .LANG_AVAILABLE
                                )
                            ):
                                outer.language_ready = True

                                print(
                                    "811: Background Arabic TTS ready:",
                                    locale
                                )
                                break

                        except Exception as lang_exc:
                            print(
                                "811: Background TTS locale error:",
                                repr(lang_exc)
                            )

                    if not outer.language_ready:
                        outer.error = (
                            "No Arabic TTS voice available"
                        )
                        print(
                            "811: Background TTS:",
                            outer.error
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
                            "811: Background TTS tuning warning:",
                            repr(voice_exc)
                        )

                except Exception as exc:
                    outer.ready = False
                    outer.language_ready = False
                    outer.error = (
                        type(exc).__name__
                        + ": "
                        + str(exc)
                    )

                    print(
                        "811: Background TTS callback error:",
                        repr(exc)
                    )

        self.listener = (
            TTSInitListener()
        )

        try:
            self.tts = TextToSpeech(
                self.service,
                self.listener
            )

            print(
                "811: Background native TTS created"
            )

        except Exception as exc:
            self.tts = None
            self.ready = False
            self.language_ready = False
            self.error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            print(
                "811: Background TTS creation error:",
                repr(exc)
            )

    def wait_until_ready(
        self,
        timeout_seconds=5.0
    ):
        deadline = (
            time.time()
            + float(timeout_seconds)
        )

        while time.time() < deadline:
            if (
                self.ready
                and self.language_ready
                and self.tts is not None
            ):
                return True

            if self.error:
                return False

            time.sleep(
                0.05
            )

        if not self.error:
            self.error = (
                "Background TTS initialization timeout"
            )

        return False

    def speak_blocking(
        self,
        text,
        timeout_seconds=15.0
    ):
        text = str(
            text or ""
        ).strip()

        if not text:
            return False

        if not self.wait_until_ready():
            print(
                "811: Background TTS not ready:",
                self.error
            )
            return False

        TextToSpeech = autoclass(
            "android.speech.tts.TextToSpeech"
        )
        JavaString = autoclass(
            "java.lang.String"
        )
        HashMap = autoclass(
            "java.util.HashMap"
        )

        utterance_id = (
            "811_bg_"
            + str(
                int(time.time() * 1000)
            )
        )

        params = HashMap()

        try:
            params.put(
                TextToSpeech
                .Engine
                .KEY_PARAM_UTTERANCE_ID,
                JavaString(
                    utterance_id
                )
            )
        except Exception:
            pass

        try:
            result = int(
                self.tts.speak(
                    JavaString(text),
                    int(
                        TextToSpeech.QUEUE_FLUSH
                    ),
                    params
                )
            )

        except Exception as exc:
            self.error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            print(
                "811: Background TTS speak error:",
                repr(exc)
            )
            return False

        if result == int(
            TextToSpeech.ERROR
        ):
            self.error = (
                "Background TTS speak returned ERROR"
            )

            print(
                "811:",
                self.error
            )
            return False

        print(
            "811: Background TTS phrase queued"
        )

        # Give Android a brief moment to transition to speaking.
        start_deadline = (
            time.time()
            + 1.5
        )

        while (
            time.time()
            < start_deadline
        ):
            try:
                if self.tts.isSpeaking():
                    break
            except Exception:
                break

            time.sleep(
                0.05
            )

        deadline = (
            time.time()
            + float(timeout_seconds)
        )

        while time.time() < deadline:
            try:
                if not self.tts.isSpeaking():
                    break
            except Exception:
                break

            time.sleep(
                0.08
            )

        return True

    def shutdown(
        self
    ):
        if self.tts is None:
            return

        try:
            self.tts.stop()
        except Exception:
            pass

        try:
            self.tts.shutdown()
        except Exception:
            pass


def main():
    service = _service_instance()

    if service is None:
        raise RuntimeError(
            "PythonService.mService is unavailable"
        )

    started_at = time.time()

    heartbeat_path = _heartbeat_path(
        service
    )
    control_path = _control_path(
        service
    )
    command_path = _command_path(
        service
    )

    recorder = None
    direct_buffer = None
    buffer_bytes = 0
    source_name = ""

    capture_blocks = 0
    last_read_bytes = 0

    state = "paused"
    last_error = ""
    last_heartbeat = 0.0
    last_command_id = ""

    background_tts = BackgroundTTS(
        service
    )

    print(
        "811: Background Core Phase 2B started"
    )
    print(
        "811: Background mic + independent TTS bridge readying"
    )

    while True:
        # -------------------------------------------------
        # One-shot service commands are processed BEFORE mic capture.
        # -------------------------------------------------
        command = _read_one_shot_command(
            command_path,
            last_command_id
        )

        if command is not None:
            command_id = str(
                command.get(
                    "id",
                    ""
                )
            )

            action = str(
                command.get(
                    "action",
                    ""
                )
            ).strip()

            # Mark consumed before execution so a failed command cannot loop.
            last_command_id = command_id

            if action == "tts_probe":
                if recorder is not None:
                    _release_recorder(
                        recorder
                    )

                    recorder = None
                    direct_buffer = None
                    buffer_bytes = 0
                    source_name = ""

                state = "speaking"
                last_error = ""

                text = str(
                    command.get(
                        "text",
                        "أنا 811. التشغيل في الخلفية جاهز."
                    )
                )

                print(
                    "811: Background TTS probe received"
                )

                success = (
                    background_tts
                    .speak_blocking(
                        text
                    )
                )

                if success:
                    state = "paused"
                    print(
                        "811: Background TTS probe COMPLETED"
                    )
                else:
                    state = "tts_error"
                    last_error = (
                        background_tts.error
                    )

                    print(
                        "811: Background TTS probe FAILED:",
                        last_error
                    )

                # The loop will re-open AudioRecord on the next iteration if
                # the foreground app still requests background capture.
                continue

        capture_requested = (
            _read_capture_command(
                control_path
            )
        )

        if not capture_requested:
            if recorder is not None:
                _release_recorder(
                    recorder
                )

                recorder = None
                direct_buffer = None
                buffer_bytes = 0
                source_name = ""

                print(
                    "811: Background AudioRecord PAUSED/RELEASED"
                )

            state = "paused"
            last_error = ""

            now = time.time()

            if (
                now - last_heartbeat
                >= HEARTBEAT_INTERVAL_SECONDS
            ):
                try:
                    _write_heartbeat(
                        heartbeat_path,
                        started_at,
                        state,
                        capture_blocks,
                        last_read_bytes,
                        source_name,
                        last_command_id,
                        background_tts.ready
                        and background_tts.language_ready,
                        last_error
                    )
                except Exception as exc:
                    print(
                        "811: Background heartbeat error:",
                        repr(exc)
                    )

                last_heartbeat = now

            time.sleep(
                0.15
            )
            continue

        if recorder is None:
            try:
                (
                    recorder,
                    direct_buffer,
                    buffer_bytes,
                    source_name
                ) = _create_audio_record()

                state = "capturing"
                last_error = ""

            except Exception as exc:
                state = "audio_error"
                last_error = (
                    type(exc).__name__
                    + ": "
                    + str(exc)
                )

                print(
                    "811: Background microphone start error:",
                    repr(exc)
                )

                try:
                    _write_heartbeat(
                        heartbeat_path,
                        started_at,
                        state,
                        capture_blocks,
                        last_read_bytes,
                        source_name,
                        last_command_id,
                        background_tts.ready
                        and background_tts.language_ready,
                        last_error
                    )
                except Exception:
                    pass

                time.sleep(
                    1.0
                )
                continue

        try:
            direct_buffer.clear()

            count = int(
                recorder.read(
                    direct_buffer,
                    buffer_bytes
                )
            )

            if count < 0:
                raise RuntimeError(
                    "AudioRecord.read returned "
                    + str(count)
                )

            last_read_bytes = count

            if count > 0:
                capture_blocks += 1
                state = "capturing"

        except Exception as exc:
            state = "audio_error"
            last_error = (
                type(exc).__name__
                + ": "
                + str(exc)
            )

            print(
                "811: Background AudioRecord read error:",
                repr(exc)
            )

            _release_recorder(
                recorder
            )

            recorder = None
            direct_buffer = None
            buffer_bytes = 0
            source_name = ""

            time.sleep(
                0.5
            )

        now = time.time()

        if (
            now - last_heartbeat
            >= HEARTBEAT_INTERVAL_SECONDS
        ):
            try:
                _write_heartbeat(
                    heartbeat_path,
                    started_at,
                    state,
                    capture_blocks,
                    last_read_bytes,
                    source_name,
                    last_command_id,
                    background_tts.ready
                    and background_tts.language_ready,
                    last_error
                )
            except Exception as exc:
                print(
                    "811: Background heartbeat error:",
                    repr(exc)
                )

            last_heartbeat = now


if __name__ == "__main__":
    main()
