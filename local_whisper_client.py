import ctypes
import os
import re
import threading
import time
from array import array

from kivy.clock import Clock
from kivy.utils import platform


class LocalWhisperClient:
    """
    Offline Arabic speech-to-text for Voice Assistant 811.

    Runtime:
        Android AudioRecord (16 kHz mono PCM)
        -> Python buffer
        -> ctypes
        -> libwhisper811.so
        -> whisper.cpp
        -> Arabic text

    The Whisper model is NOT stored in the APK. The user selects a multilingual
    ggml model once; it is imported into app-private storage and reused later.
    """

    ABI_VERSION = 1
    SAMPLE_RATE = 16000
    THREADS = 4

    PICK_MODEL_REQUEST_CODE = 8114

    PREFS_NAME = "voice_assistant_811_private"
    PREF_MODEL_URI = "local_whisper_model_uri"
    PREF_MODEL_NAME = "local_whisper_model_name"
    PREF_MODEL_PATH = "local_whisper_model_path"

    MAX_LISTEN_SECONDS = 20.0
    NO_SPEECH_TIMEOUT_SECONDS = 7.0
    END_SILENCE_SECONDS = 1.05

    def __init__(self):
        self.model_path = ""
        self.model_loaded = False

        self._lib = None
        self._handle = None
        self._native_path = ""

        self._model_lock = threading.RLock()
        self._inference_lock = threading.RLock()

        self._android_activity_module = None
        self._activity_result_bound = False
        self._last_ui_runnable = None

        self._model_uri = ""
        self._model_name = ""
        self._loading = False
        self._picker_open = False
        self._picker_declined = False

        self._recording = False
        self._transcribing = False
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._listen_thread = None
        self._audio_record = None

        if platform == "android":
            Clock.schedule_once(
                lambda dt: self._initialize_android(),
                1.15
            )

    # =====================================================
    # PUBLIC STATE
    # =====================================================

    def is_available(self):
        return bool(
            self.model_loaded
            and self._handle
            and self._lib is not None
        )

    def is_loading(self):
        return bool(self._loading)

    def is_recording(self):
        return bool(self._recording)

    def is_transcribing(self):
        return bool(self._transcribing)

    def get_model_name(self):
        return (
            self._model_name
            or os.path.basename(self.model_path or "")
        )

    def native_engine_available(self):
        try:
            self._ensure_native_library()
            return True
        except Exception:
            return False

    # =====================================================
    # ANDROID INIT / RESTORE
    # =====================================================

    def _initialize_android(self):
        if platform != "android":
            return

        try:
            from android import activity as android_activity

            self._android_activity_module = android_activity

            if not self._activity_result_bound:
                android_activity.bind(
                    on_activity_result=self._on_activity_result
                )
                self._activity_result_bound = True

            print("811: Local Whisper document picker READY")

        except Exception as exc:
            print(
                "811: Local Whisper picker init error:",
                repr(exc)
            )

        # Keep startup light. A previously selected Whisper model is restored
        # lazily on the first Local Qwen voice turn instead of consuming RAM
        # while the user is using Gemini or Groq.

    def ensure_model_or_pick(self):
        """
        Return True when Whisper is ready.
        If no model is ready, restore it or open the Android picker.
        """
        if self.is_available():
            return True

        if self._loading:
            self._notify_app(
                "thinking",
                "جاري تجهيز Whisper المحلي..."
            )
            return False

        saved_path = self._load_saved_model_path()

        if saved_path and os.path.isfile(saved_path):
            self._start_private_path_load(saved_path)
            return False

        self.request_model_picker()
        return False

    # =====================================================
    # MODEL PICKER
    # =====================================================

    def request_model_picker(self):
        if platform != "android":
            return False

        if self._picker_open:
            return True

        self._picker_open = True
        self._picker_declined = False

        self._notify_app(
            "ready",
            "اختر نموذج Whisper متعدد اللغات: ggml-base.bin"
        )

        def open_picker_on_ui():
            try:
                from jnius import autoclass

                PythonActivity = autoclass(
                    "org.kivy.android.PythonActivity"
                )
                Intent = autoclass(
                    "android.content.Intent"
                )

                activity = PythonActivity.mActivity

                if activity is None:
                    raise RuntimeError(
                        "Android Activity unavailable"
                    )

                intent = Intent(
                    Intent.ACTION_OPEN_DOCUMENT
                )
                intent.addCategory(
                    Intent.CATEGORY_OPENABLE
                )
                intent.setType("*/*")

                intent.addFlags(
                    Intent.FLAG_GRANT_READ_URI_PERMISSION
                )
                intent.addFlags(
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                )

                activity.startActivityForResult(
                    intent,
                    int(self.PICK_MODEL_REQUEST_CODE)
                )

                print(
                    "811: Local Whisper model picker opened"
                )

            except Exception as exc:
                self._picker_open = False
                self._picker_declined = True

                print(
                    "811: Local Whisper picker open error:",
                    repr(exc)
                )

                self._notify_app(
                    "error",
                    "تعذر فتح نافذة اختيار نموذج Whisper."
                )

        self._run_on_android_ui(open_picker_on_ui)
        return True

    def _on_activity_result(
        self,
        request_code,
        result_code,
        data
    ):
        if int(request_code) != int(
            self.PICK_MODEL_REQUEST_CODE
        ):
            return

        self._picker_open = False

        try:
            from jnius import autoclass

            Activity = autoclass(
                "android.app.Activity"
            )

            if (
                int(result_code)
                != int(Activity.RESULT_OK)
                or data is None
            ):
                self._picker_declined = True
                self._notify_app(
                    "ready",
                    "لم يتم اختيار نموذج Whisper."
                )
                return

            uri = data.getData()

            if uri is None:
                raise RuntimeError(
                    "Document picker returned no URI"
                )

            model_name = self._query_uri_name(uri)

            if not self._valid_model_name(model_name):
                self._picker_declined = True
                self._notify_app(
                    "error",
                    (
                        "اختر نموذج Whisper متعدد اللغات بصيغة .bin.\n"
                        "المقترح: ggml-base.bin\n"
                        "لا تختار ملف ينتهي بـ .en.bin"
                    )
                )
                return

            self._take_persistable_read_permission(
                data,
                uri
            )

            self._model_name = model_name
            self._model_uri = str(uri.toString())
            self._picker_declined = False

            self._start_uri_import_and_load(
                self._model_uri
            )

        except Exception as exc:
            self._picker_declined = True

            print(
                "811: Local Whisper picker result error:",
                repr(exc)
            )

            self._notify_app(
                "error",
                "تعذر قراءة نموذج Whisper المختار."
            )

    def _valid_model_name(self, model_name):
        name = str(model_name or "").strip().lower()

        if not name.endswith(".bin"):
            return False

        if name.endswith(".en.bin"):
            return False

        if "whisper" not in name and not name.startswith("ggml-"):
            return False

        return True

    # =====================================================
    # IMPORT MODEL TO APP-PRIVATE STORAGE
    # =====================================================

    def _start_uri_import_and_load(self, uri_string):
        if self._loading:
            return

        self._loading = True

        self._notify_app(
            "thinking",
            "جاري نسخ نموذج Whisper إلى مساحة التطبيق..."
        )

        threading.Thread(
            target=self._uri_import_load_worker,
            args=(str(uri_string),),
            daemon=True
        ).start()

    def _uri_import_load_worker(self, uri_string):
        try:
            private_path, model_name = (
                self._import_uri_to_private_file(
                    uri_string
                )
            )

            self.model_path = private_path
            self._model_name = (
                model_name
                or os.path.basename(private_path)
            )

            self._notify_app(
                "thinking",
                "تم تجهيز النموذج. جاري تشغيل Whisper المحلي..."
            )

            result = self.load_model()

            if result.get("success"):
                self._save_model_info(
                    uri_string,
                    self._model_name,
                    private_path
                )

                self._notify_app(
                    "ready",
                    (
                        "Whisper المحلي جاهز للعمل بدون إنترنت.\n"
                        + self._model_name
                    )
                )

                print(
                    "811: Local Whisper model LOADED:",
                    self._model_name,
                    private_path
                )

            else:
                self._clear_saved_model_info()
                self._notify_app(
                    "error",
                    str(
                        result.get(
                            "message",
                            "تعذر تشغيل Whisper المحلي."
                        )
                    )
                )

        except Exception as exc:
            self._clear_saved_model_info()

            print(
                "811: Local Whisper import/load error:",
                repr(exc)
            )

            self._notify_app(
                "error",
                (
                    "تعذر تجهيز نموذج Whisper.\n"
                    + str(exc)
                )
            )

        finally:
            self._loading = False

    def _start_private_path_load(self, model_path):
        if self._loading:
            return

        model_path = str(model_path or "").strip()

        if not model_path or not os.path.isfile(model_path):
            self._clear_saved_model_info()
            return

        self._loading = True

        threading.Thread(
            target=self._private_path_load_worker,
            args=(model_path,),
            daemon=True
        ).start()

    def _private_path_load_worker(self, model_path):
        try:
            self.model_path = str(model_path)

            result = self.load_model()

            if result.get("success"):
                print(
                    "811: Local Whisper restored:",
                    self.model_path
                )
            else:
                self._clear_saved_model_info()
                self._notify_app(
                    "error",
                    str(
                        result.get(
                            "message",
                            "تعذر تشغيل Whisper المحلي."
                        )
                    )
                )

        except Exception as exc:
            self._clear_saved_model_info()

            print(
                "811: Local Whisper restore error:",
                repr(exc)
            )

        finally:
            self._loading = False

    def _import_uri_to_private_file(self, uri_string):
        from jnius import autoclass

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )
        Uri = autoclass(
            "android.net.Uri"
        )

        activity = PythonActivity.mActivity

        if activity is None:
            raise RuntimeError(
                "Android Activity unavailable"
            )

        resolver = activity.getContentResolver()
        uri = Uri.parse(str(uri_string))

        model_name = self._query_uri_name(uri)

        if not self._valid_model_name(model_name):
            raise RuntimeError(
                "الملف ليس نموذج Whisper متعدد اللغات صالحاً."
            )

        pfd = resolver.openFileDescriptor(
            uri,
            "r"
        )

        if pfd is None:
            raise RuntimeError(
                "تعذر فتح نموذج Whisper المختار."
            )

        source_copy_fd = -1

        try:
            source_fd = int(pfd.getFd())

            if source_fd < 0:
                raise RuntimeError(
                    "Android returned invalid model file descriptor"
                )

            source_copy_fd = os.dup(source_fd)

            private_root = str(
                activity
                .getFilesDir()
                .getAbsolutePath()
            )

            model_dir = os.path.join(
                private_root,
                "local_whisper"
            )
            os.makedirs(
                model_dir,
                exist_ok=True
            )

            safe_name = re.sub(
                r"[^A-Za-z0-9._-]+",
                "_",
                os.path.basename(model_name)
            )

            if not safe_name.lower().endswith(".bin"):
                safe_name = "ggml-base.bin"

            destination = os.path.join(
                model_dir,
                safe_name
            )
            temp_path = destination + ".part"

            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

            copied = 0

            with os.fdopen(
                source_copy_fd,
                "rb",
                closefd=True
            ) as source:
                source_copy_fd = -1

                with open(
                    temp_path,
                    "wb"
                ) as target:
                    while True:
                        chunk = source.read(
                            1024 * 1024
                        )

                        if not chunk:
                            break

                        target.write(chunk)
                        copied += len(chunk)

                    target.flush()
                    os.fsync(
                        target.fileno()
                    )

            if copied < 1024 * 1024:
                raise RuntimeError(
                    "ملف نموذج Whisper صغير جداً أو غير مكتمل."
                )

            os.replace(
                temp_path,
                destination
            )

            return (
                destination,
                model_name
            )

        finally:
            if source_copy_fd >= 0:
                try:
                    os.close(source_copy_fd)
                except Exception:
                    pass

            try:
                pfd.close()
            except Exception:
                pass

    # =====================================================
    # MODEL LOAD
    # =====================================================

    def load_model(self):
        with self._model_lock:
            if not self.model_path:
                return {
                    "success": False,
                    "message": "لم يتم اختيار نموذج Whisper بعد."
                }

            if not os.path.isfile(self.model_path):
                return {
                    "success": False,
                    "message": "تعذر الوصول إلى نموذج Whisper المحلي."
                }

            try:
                self._ensure_native_library()

            except Exception as exc:
                return {
                    "success": False,
                    "message": (
                        "تعذر تشغيل libwhisper811.so.\n"
                        + str(exc)
                    )
                }

            self._destroy_model_locked()

            handle_value = self._lib.whisper811_load(
                self.model_path.encode(
                    "utf-8",
                    errors="strict"
                ),
                int(self.THREADS)
            )

            if not handle_value:
                self.model_loaded = False

                return {
                    "success": False,
                    "message": self._friendly_native_error(
                        self._last_native_error()
                    )
                }

            self._handle = ctypes.c_void_p(
                handle_value
            )
            self.model_loaded = True

            return {
                "success": True,
                "message": "Whisper المحلي جاهز."
            }

    # =====================================================
    # OFFLINE MICROPHONE LISTENING
    # =====================================================

    def listen_once(
        self,
        on_level=None,
        on_thinking=None,
        on_result=None,
        on_error=None
    ):
        """
        Record one utterance and transcribe it fully offline.

        Callbacks may be normal Python functions; they are marshalled to the
        Kivy thread before execution.
        """
        if platform != "android":
            self._callback(
                on_error,
                "Whisper المحلي متاح على Android فقط."
            )
            return False

        if not self.ensure_model_or_pick():
            self._callback(
                on_error,
                (
                    "Whisper المحلي غير جاهز بعد. "
                    "اختر ggml-base.bin وانتظر اكتمال التحميل."
                )
            )
            return False

        if self._recording or self._transcribing:
            return False

        self._stop_event.clear()
        self._cancel_event.clear()

        self._listen_thread = threading.Thread(
            target=self._listen_worker,
            args=(
                on_level,
                on_thinking,
                on_result,
                on_error
            ),
            daemon=True
        )
        self._listen_thread.start()

        return True

    def stop_listening(self):
        """
        Stop microphone capture and transcribe what was recorded.
        """
        self._stop_event.set()

    def cancel_listening(self):
        """
        Cancel microphone capture or native transcription.
        """
        self._cancel_event.set()
        self._stop_event.set()

        if (
            self._lib is not None
            and self._handle
        ):
            try:
                self._lib.whisper811_cancel(
                    self._handle
                )
            except Exception:
                pass

        audio_record = self._audio_record

        if audio_record is not None:
            try:
                audio_record.stop()
            except Exception:
                pass

    def _listen_worker(
        self,
        on_level,
        on_thinking,
        on_result,
        on_error
    ):
        record = None
        samples = array("f")

        speech_started = False
        silence_seconds = 0.0
        started_at = time.monotonic()

        try:
            from jnius import autoclass

            AudioRecord = autoclass(
                "android.media.AudioRecord"
            )
            AudioFormat = autoclass(
                "android.media.AudioFormat"
            )
            AudioSource = autoclass(
                "android.media.MediaRecorder$AudioSource"
            )

            channel_config = (
                AudioFormat.CHANNEL_IN_MONO
            )
            encoding = (
                AudioFormat.ENCODING_PCM_16BIT
            )

            min_buffer_bytes = int(
                AudioRecord.getMinBufferSize(
                    self.SAMPLE_RATE,
                    channel_config,
                    encoding
                )
            )

            if min_buffer_bytes <= 0:
                raise RuntimeError(
                    "Android AudioRecord buffer configuration failed"
                )

            buffer_bytes = max(
                min_buffer_bytes * 2,
                4096
            )
            buffer_samples = max(
                1024,
                buffer_bytes // 2
            )

            record = AudioRecord(
                AudioSource.VOICE_RECOGNITION,
                self.SAMPLE_RATE,
                channel_config,
                encoding,
                buffer_bytes
            )

            if int(
                record.getState()
            ) != int(
                AudioRecord.STATE_INITIALIZED
            ):
                raise RuntimeError(
                    "Android AudioRecord initialization failed"
                )

            # PyJNIus accepts normal Python lists for primitive Java arrays.
            # AudioRecord.read(short[], ...) updates the list in place because
            # PyJNIus passes arrays by reference by default.
            short_buffer = [
                0
            ] * buffer_samples

            self._audio_record = record
            self._recording = True

            record.startRecording()

            print(
                "811: Local Whisper AudioRecord STARTED"
            )

            while True:
                if self._cancel_event.is_set():
                    return

                if self._stop_event.is_set():
                    break

                elapsed = (
                    time.monotonic()
                    - started_at
                )

                if elapsed >= self.MAX_LISTEN_SECONDS:
                    break

                count = int(
                    record.read(
                        short_buffer,
                        0,
                        buffer_samples,
                        pass_by_reference=True
                    )
                )

                if count <= 0:
                    continue

                sum_sq = 0.0
                peak = 0.0

                for index in range(count):
                    value = float(
                        int(short_buffer[index])
                    ) / 32768.0

                    samples.append(value)

                    absolute = abs(value)
                    sum_sq += value * value

                    if absolute > peak:
                        peak = absolute

                rms = (
                    sum_sq / float(count)
                ) ** 0.5

                chunk_seconds = (
                    float(count)
                    / float(self.SAMPLE_RATE)
                )

                # Conservative thresholds tuned for normal phone microphones.
                # VOICE_RECOGNITION audio source already reduces room noise.
                speech_threshold = 0.018
                silence_threshold = 0.012

                if not speech_started:
                    if (
                        rms >= speech_threshold
                        or peak >= 0.075
                    ):
                        speech_started = True
                        silence_seconds = 0.0

                    elif (
                        elapsed
                        >= self.NO_SPEECH_TIMEOUT_SECONDS
                    ):
                        break

                else:
                    if (
                        rms < silence_threshold
                        and peak < 0.050
                    ):
                        silence_seconds += (
                            chunk_seconds
                        )
                    else:
                        silence_seconds = 0.0

                    if (
                        silence_seconds
                        >= self.END_SILENCE_SECONDS
                    ):
                        break

                level = (
                    rms - 0.004
                ) / 0.075

                level = max(
                    0.0,
                    min(1.0, level)
                )

                self._callback(
                    on_level,
                    level
                )

            if record is not None:
                try:
                    record.stop()
                except Exception:
                    pass

            self._recording = False
            self._audio_record = None

            if self._cancel_event.is_set():
                return

            if (
                not speech_started
                or len(samples)
                < int(self.SAMPLE_RATE * 0.25)
            ):
                self._callback(
                    on_error,
                    "لم أسمع كلاماً واضحاً."
                )
                return

            self._callback(
                on_level,
                0.0
            )
            self._callback(
                on_thinking
            )

            self._transcribing = True

            text = self._transcribe_samples(
                samples
            )

            self._transcribing = False

            if self._cancel_event.is_set():
                return

            if not text:
                self._callback(
                    on_error,
                    "لم أتمكن من تحويل الصوت إلى نص."
                )
                return

            self._callback(
                on_result,
                text
            )

        except Exception as exc:
            self._recording = False
            self._transcribing = False
            self._audio_record = None

            print(
                "811: Local Whisper listen error:",
                repr(exc)
            )

            if not self._cancel_event.is_set():
                self._callback(
                    on_error,
                    (
                        "خطأ في Whisper المحلي:\n"
                        + type(exc).__name__
                        + ": "
                        + str(exc)
                    )
                )

        finally:
            self._recording = False
            self._transcribing = False
            self._audio_record = None

            if record is not None:
                try:
                    record.release()
                except Exception:
                    pass

            self._callback(
                on_level,
                0.0
            )

    def _transcribe_samples(self, samples):
        if not self.is_available():
            raise RuntimeError(
                "Whisper model is not loaded"
            )

        if not samples:
            return ""

        if samples.itemsize != 4:
            raise RuntimeError(
                "Unexpected Python float array size"
            )

        with self._inference_lock:
            if self._cancel_event.is_set():
                return ""

            pcm_array = (
                ctypes.c_float
                * len(samples)
            ).from_buffer(samples)

            output_ptr = ctypes.c_void_p()

            status = self._lib.whisper811_transcribe(
                self._handle,
                pcm_array,
                int(len(samples)),
                b"ar",
                (
                    "اللهجة العراقية، العربية، "
                    "Voice Assistant 811"
                ).encode(
                    "utf-8"
                ),
                ctypes.byref(
                    output_ptr
                )
            )

            if status == 2:
                return ""

            if status == 3:
                return ""

            if status != 0:
                raise RuntimeError(
                    self._friendly_native_error(
                        self._last_native_error()
                    )
                )

            if not output_ptr.value:
                return ""

            try:
                text = ctypes.string_at(
                    output_ptr.value
                ).decode(
                    "utf-8",
                    errors="replace"
                )
            finally:
                self._lib.whisper811_free_text(
                    output_ptr
                )

            return self._clean_transcription(
                text
            )

    # =====================================================
    # NATIVE LIBRARY
    # =====================================================

    def _ensure_native_library(self):
        if self._lib is not None:
            return

        native_path = (
            self._resolve_native_library_path()
        )

        if not native_path:
            raise RuntimeError(
                "لم يتم العثور على libwhisper811.so داخل التطبيق."
            )

        lib = ctypes.CDLL(
            native_path
        )

        lib.whisper811_abi_version.argtypes = []
        lib.whisper811_abi_version.restype = (
            ctypes.c_int
        )

        lib.whisper811_sample_rate.argtypes = []
        lib.whisper811_sample_rate.restype = (
            ctypes.c_int
        )

        lib.whisper811_last_error.argtypes = []
        lib.whisper811_last_error.restype = (
            ctypes.c_char_p
        )

        lib.whisper811_load.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int
        ]
        lib.whisper811_load.restype = (
            ctypes.c_void_p
        )

        lib.whisper811_transcribe.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(
                ctypes.c_float
            ),
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(
                ctypes.c_void_p
            )
        ]
        lib.whisper811_transcribe.restype = (
            ctypes.c_int
        )

        lib.whisper811_free_text.argtypes = [
            ctypes.c_void_p
        ]
        lib.whisper811_free_text.restype = None

        lib.whisper811_cancel.argtypes = [
            ctypes.c_void_p
        ]
        lib.whisper811_cancel.restype = None

        lib.whisper811_destroy.argtypes = [
            ctypes.c_void_p
        ]
        lib.whisper811_destroy.restype = None

        abi = int(
            lib.whisper811_abi_version()
        )

        if abi != int(self.ABI_VERSION):
            raise RuntimeError(
                "إصدار محرك Whisper غير متوافق مع التطبيق."
            )

        sample_rate = int(
            lib.whisper811_sample_rate()
        )

        if sample_rate != int(self.SAMPLE_RATE):
            raise RuntimeError(
                "معدل أخذ عينات Whisper غير متوافق."
            )

        self._lib = lib
        self._native_path = native_path

    def _resolve_native_library_path(self):
        if platform == "android":
            try:
                from jnius import autoclass

                PythonActivity = autoclass(
                    "org.kivy.android.PythonActivity"
                )

                activity = PythonActivity.mActivity

                if activity is not None:
                    native_dir = str(
                        activity
                        .getApplicationInfo()
                        .nativeLibraryDir
                    )

                    candidate = os.path.join(
                        native_dir,
                        "libwhisper811.so"
                    )

                    if os.path.isfile(candidate):
                        return candidate

            except Exception:
                pass

        base_dir = os.path.dirname(
            os.path.abspath(__file__)
        )

        candidate = os.path.join(
            base_dir,
            "libs",
            "arm64-v8a",
            "libwhisper811.so"
        )

        if os.path.isfile(candidate):
            return candidate

        return ""

    def _destroy_model_locked(self):
        if (
            self._lib is not None
            and self._handle
        ):
            try:
                self._lib.whisper811_destroy(
                    self._handle
                )
            except Exception:
                pass

        self._handle = None
        self.model_loaded = False

    def _last_native_error(self):
        if self._lib is None:
            return ""

        try:
            raw = self._lib.whisper811_last_error()

            if not raw:
                return ""

            if isinstance(raw, bytes):
                return raw.decode(
                    "utf-8",
                    errors="replace"
                ).strip()

            return str(raw).strip()

        except Exception:
            return ""

    # =====================================================
    # PREFERENCES
    # =====================================================

    def _get_preferences(self):
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

            return activity.getSharedPreferences(
                self.PREFS_NAME,
                0
            )

        except Exception:
            return None

    def _save_model_info(
        self,
        uri_string,
        model_name,
        model_path
    ):
        prefs = self._get_preferences()

        if prefs is None:
            return

        try:
            editor = prefs.edit()

            editor.putString(
                self.PREF_MODEL_URI,
                str(uri_string or "")
            )
            editor.putString(
                self.PREF_MODEL_NAME,
                str(model_name or "")
            )
            editor.putString(
                self.PREF_MODEL_PATH,
                str(model_path or "")
            )

            editor.apply()

        except Exception as exc:
            print(
                "811: Local Whisper preference save error:",
                repr(exc)
            )

    def _load_saved_model_path(self):
        prefs = self._get_preferences()

        if prefs is None:
            return ""

        try:
            path = str(
                prefs.getString(
                    self.PREF_MODEL_PATH,
                    ""
                )
                or ""
            ).strip()

            name = str(
                prefs.getString(
                    self.PREF_MODEL_NAME,
                    ""
                )
                or ""
            ).strip()

            if name:
                self._model_name = name

            return path

        except Exception:
            return ""

    def _clear_saved_model_info(self):
        prefs = self._get_preferences()

        if prefs is None:
            return

        try:
            editor = prefs.edit()

            editor.remove(
                self.PREF_MODEL_URI
            )
            editor.remove(
                self.PREF_MODEL_NAME
            )
            editor.remove(
                self.PREF_MODEL_PATH
            )

            editor.apply()

        except Exception:
            pass

    # =====================================================
    # ANDROID URI HELPERS
    # =====================================================

    def _query_uri_name(self, uri):
        if platform != "android":
            return ""

        cursor = None

        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            OpenableColumns = autoclass(
                "android.provider.OpenableColumns"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                return ""

            cursor = (
                activity
                .getContentResolver()
                .query(
                    uri,
                    None,
                    None,
                    None,
                    None
                )
            )

            if (
                cursor is not None
                and cursor.moveToFirst()
            ):
                index = cursor.getColumnIndex(
                    OpenableColumns.DISPLAY_NAME
                )

                if index >= 0:
                    value = cursor.getString(index)

                    if value is not None:
                        return str(value)

        except Exception as exc:
            print(
                "811: Local Whisper URI name error:",
                repr(exc)
            )

        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass

        try:
            segment = uri.getLastPathSegment()

            if segment is not None:
                return str(segment)

        except Exception:
            pass

        return ""

    def _take_persistable_read_permission(
        self,
        data,
        uri
    ):
        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            Intent = autoclass(
                "android.content.Intent"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                return

            granted_flags = int(
                data.getFlags()
            )

            read_flag = int(
                Intent.FLAG_GRANT_READ_URI_PERMISSION
            )

            flags = granted_flags & read_flag

            if not flags:
                flags = read_flag

            (
                activity
                .getContentResolver()
                .takePersistableUriPermission(
                    uri,
                    flags
                )
            )

        except Exception as exc:
            print(
                "811: Local Whisper URI permission warning:",
                repr(exc)
            )

    # =====================================================
    # UI / CALLBACK HELPERS
    # =====================================================

    def _callback(self, callback, *args):
        if callback is None:
            return

        Clock.schedule_once(
            lambda dt: callback(*args),
            0
        )

    def _notify_app(self, state, message):
        def apply_state(dt):
            try:
                from kivy.app import App

                app = App.get_running_app()

                if (
                    app is not None
                    and hasattr(app, "set_state")
                ):
                    app.set_state(
                        state,
                        str(message or "")
                    )

            except Exception as exc:
                print(
                    "811: Local Whisper UI notify error:",
                    repr(exc)
                )

        Clock.schedule_once(
            apply_state,
            0
        )

    def _run_on_android_ui(self, func):
        if platform != "android":
            func()
            return

        try:
            from jnius import (
                PythonJavaClass,
                autoclass,
                java_method
            )

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            activity = PythonActivity.mActivity

            if activity is None:
                raise RuntimeError(
                    "Android Activity unavailable"
                )

            outer = self

            class UiRunnable(PythonJavaClass):
                __javainterfaces__ = [
                    "java/lang/Runnable"
                ]
                __javacontext__ = "app"

                @java_method("()V")
                def run(self):
                    try:
                        func()
                    except Exception as exc:
                        outer._picker_open = False

                        print(
                            "811: Local Whisper UI runnable error:",
                            repr(exc)
                        )

            runnable = UiRunnable()
            self._last_ui_runnable = runnable

            activity.runOnUiThread(
                runnable
            )

        except Exception as exc:
            self._picker_open = False

            print(
                "811: Local Whisper runOnUiThread error:",
                repr(exc)
            )

    # =====================================================
    # CLEANUP
    # =====================================================

    def _clean_transcription(self, text):
        text = str(text or "")

        text = re.sub(
            r"\[[^\]]*\]",
            " ",
            text
        )
        text = re.sub(
            r"\([^\)]*(?:music|applause|noise)[^\)]*\)",
            " ",
            text,
            flags=re.IGNORECASE
        )
        text = re.sub(
            r"\s+",
            " ",
            text
        )

        return text.strip()

    def _friendly_native_error(self, native_error):
        error = str(native_error or "").strip()
        lower = error.lower()

        if "multilingual" in lower:
            return (
                "اختر نموذج Whisper متعدد اللغات، "
                "ولا تختار نسخة .en."
            )

        if "model load failed" in lower:
            return (
                "تعذر تحميل نموذج Whisper. "
                "تأكد أن الملف كامل وصحيح."
            )

        if "cancelled" in lower:
            return "تم إيقاف Whisper."

        if error:
            return error

        return "حدث خطأ غير معروف داخل Whisper المحلي."

    def close(self):
        self.cancel_listening()

        worker = self._listen_thread

        if (
            worker is not None
            and worker.is_alive()
            and worker is not threading.current_thread()
        ):
            worker.join(timeout=1.5)

        with self._inference_lock:
            with self._model_lock:
                self._destroy_model_locked()

        if (
            self._activity_result_bound
            and self._android_activity_module is not None
        ):
            try:
                self._android_activity_module.unbind(
                    on_activity_result=self._on_activity_result
                )
            except Exception:
                pass

            self._activity_result_bound = False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
