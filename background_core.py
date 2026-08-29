"""
Voice Assistant 811 — Phase 2A Background Microphone Core

Purpose of this phase:
- Keep the successful sticky foreground service from Build #142.
- Add REAL Android AudioRecord microphone ownership while the app is in the
  background.
- Do NOT implement the "811" wake-word model yet.
- Do NOT call Groq, SpeechRecognizer, or TTS from the service.

The Kivy app and this service run in separate Android processes. They coordinate
through a tiny private control file:
    capture  -> service may open AudioRecord
    pause    -> service releases AudioRecord

This prevents the background microphone from competing with the already-stable
foreground SpeechRecognizer.

The service writes a heartbeat JSON file for diagnostics.
"""

import json
import os
import time

from jnius import autoclass


SAMPLE_RATE = 16000
CHANNELS = 1
HEARTBEAT_INTERVAL_SECONDS = 3.0

HEARTBEAT_FILENAME = "811_background_core_heartbeat.json"
CONTROL_FILENAME = "811_background_core_control.txt"


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


def _write_heartbeat(
    path,
    started_at,
    state,
    capture_blocks,
    last_read_bytes,
    audio_source,
    error=""
):
    payload = {
        "service": "811-background-core",
        "phase": "2A",
        "state": state,
        "pid": os.getpid(),
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "audio_source": audio_source,
        "capture_blocks": capture_blocks,
        "last_read_bytes": last_read_bytes,
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

    # Give Android comfortable headroom while keeping latency low enough for
    # a future wake-word detector.
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

    recorder = None
    direct_buffer = None
    buffer_bytes = 0
    source_name = ""

    capture_blocks = 0
    last_read_bytes = 0

    state = "paused"
    last_error = ""
    last_heartbeat = 0.0

    print(
        "811: Background Core Phase 2A started"
    )
    print(
        "811: Background microphone waits for app background command"
    )

    while True:
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
