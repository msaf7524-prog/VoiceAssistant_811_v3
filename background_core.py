"""
Voice Assistant 811 — Phase 1 Background Core

This service intentionally does NOT capture microphone audio yet.
Its only job in Phase 1 is to prove that python-for-android can keep a
dedicated sticky foreground process alive when the Kivy Activity is no longer
on screen. The next phase will add the local 811 wake-word detector here.

A small heartbeat file is written in the app's private files directory for
future diagnostics. No network requests, Groq calls, SpeechRecognizer calls,
or TTS calls are made from this service.
"""

import json
import os
import time

from jnius import autoclass


HEARTBEAT_INTERVAL_SECONDS = 15.0
HEARTBEAT_FILENAME = "811_background_core_heartbeat.json"


def _service_instance():
    PythonService = autoclass(
        "org.kivy.android.PythonService"
    )
    return PythonService.mService


def _heartbeat_path(service):
    files_dir = str(
        service.getFilesDir().getAbsolutePath()
    )
    return os.path.join(
        files_dir,
        HEARTBEAT_FILENAME
    )


def _write_heartbeat(path, started_at):
    payload = {
        "service": "811-background-core",
        "phase": 1,
        "state": "alive",
        "pid": os.getpid(),
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

    print(
        "811: Background Core Phase 1 started"
    )
    print(
        "811: Background Core heartbeat:",
        heartbeat_path
    )

    while True:
        try:
            _write_heartbeat(
                heartbeat_path,
                started_at
            )
        except Exception as exc:
            # Diagnostics must never terminate the service.
            print(
                "811: Background Core heartbeat error:",
                repr(exc)
            )

        time.sleep(
            HEARTBEAT_INTERVAL_SECONDS
        )


if __name__ == "__main__":
    main()
