import ctypes
import os
import re
import threading
import time

from kivy.clock import Clock
from kivy.utils import platform


class LocalQwenClient:
    """
    Local Qwen3.5 client for Voice Assistant 811.

    Android path:
        Kivy/Python
        -> Android document picker
        -> selected content URI
        -> one-time import to app-private storage
        -> real local GGUF filesystem path
        -> ctypes
        -> libqwen811.so
        -> llama.cpp
        -> Qwen3.5 2B GGUF

    No HTTP server, browser, Termux, remote API fallback, or GGUF inside
    the APK is used.
    """

    SYSTEM_PROMPT = (
        "أنت 811، مساعد شخصي ذكي باللغة العربية. "
        "أجب بوضوح ودقة وبأسلوب طبيعي ومختصر ما لم يطلب المستخدم التفصيل. "
        "لا تخترع معلومات أو هوية أو شركة أو مطوراً غير معروف. "
        "لا تعرض التفكير الداخلي أو وسوم <think> في الرد."
    )

    CONTEXT_SIZE = 2048
    THREADS = 4
    MAX_TOKENS = 256
    ABI_VERSION = 1

    PICK_MODEL_REQUEST_CODE = 8113
    PREFS_NAME = "voice_assistant_811_private"
    PREF_MODEL_URI = "local_qwen_model_uri"
    PREF_MODEL_NAME = "local_qwen_model_name"
    PREF_MODEL_PATH = "local_qwen_model_path"

    def __init__(self):
        self.model_path = ""
        self.model_loaded = False
        self.history = []

        self._lib = None
        self._handle = None
        self._native_path = ""
        self._lock = threading.RLock()

        self._android_activity_module = None
        self._activity_result_bound = False
        self._last_ui_runnable = None

        self._model_pfd = None
        self._model_uri = ""
        self._model_name = ""
        self._model_private_path = ""

        self._loading = False
        self._picker_open = False
        self._picker_declined = False
        self._last_provider_choice = ""

        self._provider_watch_event = None

        if platform == "android":
            Clock.schedule_once(
                lambda dt: self._initialize_android_picker(),
                0.80
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

    def native_engine_available(self):
        try:
            self._ensure_native_library()
            return True
        except Exception:
            return False

    def get_native_library_path(self):
        try:
            self._ensure_native_library()
            return self._native_path
        except Exception:
            return ""

    def get_model_name(self):
        return self._model_name or os.path.basename(
            self.model_path or ""
        )

    # =====================================================
    # ANDROID PICKER INITIALIZATION
    # =====================================================

    def _initialize_android_picker(self):
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

            print("811: Local Qwen document picker READY")

        except Exception as exc:
            print(
                "811: Local Qwen picker init error:",
                repr(exc)
            )

        if self._provider_watch_event is None:
            self._provider_watch_event = Clock.schedule_interval(
                self._watch_provider_choice,
                0.60
            )

    def _watch_provider_choice(self, dt):
        if platform != "android":
            return False

        provider = self._read_provider_choice()

        if provider != self._last_provider_choice:
            if provider != "local_qwen":
                self._picker_declined = False

            self._last_provider_choice = provider

        if provider != "local_qwen":
            return True

        if self.is_available():
            return True

        if self._loading or self._picker_open:
            return True

        saved_path = self._load_saved_model_path()

        if saved_path:
            self._start_private_path_load(
                saved_path
            )
            return True

        saved_uri = self._load_saved_model_uri()

        if saved_uri:
            # Migration/fallback: older test builds only saved the URI.
            # Import it once into app-private storage before llama.cpp loads it.
            self._start_uri_load(
                saved_uri,
                persist=True
            )
            return True

        if not self._picker_declined:
            self.request_model_picker()

        return True

    def request_model_picker(self):
        """
        Open Android's system document picker.

        This method is safe to call repeatedly; only one picker can be open.
        """
        if platform != "android":
            return False

        if self._picker_open:
            return True

        self._picker_open = True

        self._notify_app(
            "ready",
            "اختر ملف Qwen3.5 2B Q4_K_M بصيغة GGUF."
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
                    "811: Local Qwen GGUF picker opened"
                )

            except Exception as exc:
                self._picker_open = False
                self._picker_declined = True

                print(
                    "811: Local Qwen picker open error:",
                    repr(exc)
                )

                self._notify_app(
                    "error",
                    "تعذر فتح نافذة اختيار ملف Local Qwen."
                )

        self._run_on_android_ui(
            open_picker_on_ui
        )

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
                    "لم يتم اختيار نموذج Local Qwen."
                )

                print(
                    "811: Local Qwen picker cancelled"
                )
                return

            uri = data.getData()

            if uri is None:
                raise RuntimeError(
                    "Document picker returned no URI"
                )

            uri_string = str(
                uri.toString()
            )

            model_name = self._query_uri_name(
                uri
            )

            if (
                not model_name
                or not model_name.lower().endswith(
                    ".gguf"
                )
            ):
                self._picker_declined = True

                self._notify_app(
                    "error",
                    "الملف المختار ليس ملف GGUF."
                )
                return

            self._take_persistable_read_permission(
                data,
                uri
            )

            self._model_name = model_name
            self._picker_declined = False

            self._start_uri_load(
                uri_string,
                persist=True
            )

        except Exception as exc:
            self._picker_declined = True

            print(
                "811: Local Qwen picker result error:",
                repr(exc)
            )

            self._notify_app(
                "error",
                "تعذر قراءة ملف Local Qwen المختار."
            )

    # =====================================================
    # CONTENT URI / PRIVATE MODEL IMPORT
    # =====================================================

    def _start_uri_load(
        self,
        uri_string,
        persist
    ):
        if self._loading:
            return

        self._loading = True

        self._notify_app(
            "thinking",
            "جاري تحميل Local Qwen من ذاكرة الهاتف..."
        )

        threading.Thread(
            target=self._load_from_uri_worker,
            args=(
                str(uri_string),
                bool(persist)
            ),
            daemon=True
        ).start()

    def _load_from_uri_worker(
        self,
        uri_string,
        persist
    ):
        try:
            private_path, model_name = (
                self._import_uri_to_private_file(
                    uri_string
                )
            )

            with self._lock:
                self._close_model_descriptor_locked()
                self._model_uri = uri_string
                self._model_private_path = private_path

                if model_name:
                    self._model_name = model_name

                self._destroy_locked()
                self.model_path = private_path
                self.history = []

            self._notify_app(
                "thinking",
                "تم تجهيز ملف النموذج. جاري تشغيل Local Qwen..."
            )

            result = self.load_model()

            if result.get(
                "success"
            ):
                if persist:
                    self._save_model_uri(
                        uri_string,
                        self._model_name,
                        private_path
                    )

                self._notify_app(
                    "ready",
                    (
                        "Local Qwen جاهز للعمل بدون إنترنت.\n"
                        + (
                            self._model_name
                            or "Qwen3.5 2B"
                        )
                    )
                )

                print(
                    "811: Local Qwen model LOADED:",
                    self._model_name,
                    self.model_path
                )

            else:
                self._clear_saved_model_uri()
                self._picker_declined = True

                message = str(
                    result.get(
                        "message",
                        "تعذر تحميل Local Qwen."
                    )
                )

                self._notify_app(
                    "error",
                    message
                )

                print(
                    "811: Local Qwen model load failed:",
                    message
                )

        except Exception as exc:
            self._clear_saved_model_uri()
            self._picker_declined = True

            print(
                "811: Local Qwen import/load error:",
                repr(exc)
            )

            self._notify_app(
                "error",
                (
                    "تعذر تجهيز ملف Local Qwen.\n"
                    + str(exc)
                )
            )

        finally:
            self._loading = False

    def _start_private_path_load(
        self,
        model_path
    ):
        if self._loading:
            return

        model_path = str(
            model_path or ""
        ).strip()

        if (
            not model_path
            or not os.path.isfile(
                model_path
            )
        ):
            self._clear_saved_model_uri()
            return

        self._loading = True

        self._notify_app(
            "thinking",
            "جاري تشغيل Local Qwen من الملف المحلي..."
        )

        threading.Thread(
            target=self._load_private_path_worker,
            args=(model_path,),
            daemon=True
        ).start()

    def _load_private_path_worker(
        self,
        model_path
    ):
        try:
            with self._lock:
                self._destroy_locked()
                self.model_path = str(
                    model_path
                )
                self._model_private_path = (
                    self.model_path
                )
                self.history = []

            result = self.load_model()

            if result.get(
                "success"
            ):
                self._notify_app(
                    "ready",
                    (
                        "Local Qwen جاهز للعمل بدون إنترنت.\n"
                        + (
                            self._model_name
                            or "Qwen3.5 2B"
                        )
                    )
                )

                print(
                    "811: Local Qwen restored from private file:",
                    self.model_path
                )

            else:
                self._clear_saved_model_uri()
                self._picker_declined = True

                self._notify_app(
                    "error",
                    str(
                        result.get(
                            "message",
                            "تعذر تحميل Local Qwen."
                        )
                    )
                )

        except Exception as exc:
            self._clear_saved_model_uri()
            self._picker_declined = True

            print(
                "811: Local Qwen private-path load error:",
                repr(exc)
            )

            self._notify_app(
                "error",
                (
                    "تعذر تشغيل ملف Local Qwen المحلي.\n"
                    + str(exc)
                )
            )

        finally:
            self._loading = False

    def _import_uri_to_private_file(
        self,
        uri_string
    ):
        """
        Copy the selected Android document into app-private storage.

        llama.cpp's mmap loader needs a real regular filesystem file. Passing
        /proc/self/fd/<n> from a document provider can fail even when the phone
        has plenty of RAM, so the picker URI is used only as the import source.
        """
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
        uri = Uri.parse(
            str(uri_string)
        )

        model_name = self._query_uri_name(
            uri
        )

        if (
            not model_name
            or not model_name.lower().endswith(
                ".gguf"
            )
        ):
            raise RuntimeError(
                "الملف المختار ليس ملف GGUF."
            )

        pfd = resolver.openFileDescriptor(
            uri,
            "r"
        )

        if pfd is None:
            raise RuntimeError(
                "تعذر فتح ملف النموذج المختار."
            )

        source_fd = -1
        source_copy_fd = -1

        try:
            source_fd = int(
                pfd.getFd()
            )

            if source_fd < 0:
                raise RuntimeError(
                    "تعذر قراءة ملف النموذج المختار."
                )

            try:
                source_size = int(
                    pfd.getStatSize()
                )
            except Exception:
                source_size = -1

            files_dir = str(
                activity
                .getFilesDir()
                .getAbsolutePath()
            )

            private_dir = os.path.join(
                files_dir,
                "local_qwen"
            )

            os.makedirs(
                private_dir,
                exist_ok=True
            )

            final_path = os.path.join(
                private_dir,
                "qwen3_5_2b_q4_k_m.gguf"
            )
            temp_path = (
                final_path
                + ".part"
            )

            if source_size > 0:
                try:
                    stats = os.statvfs(
                        private_dir
                    )
                    free_bytes = (
                        int(stats.f_bavail)
                        * int(stats.f_frsize)
                    )

                    required_bytes = (
                        source_size
                        + (96 * 1024 * 1024)
                    )

                    if free_bytes < required_bytes:
                        raise RuntimeError(
                            "المساحة التخزينية غير كافية لنسخ نموذج Local Qwen."
                        )
                except RuntimeError:
                    raise
                except Exception:
                    pass

            self._notify_app(
                "thinking",
                (
                    "جاري استيراد ملف Local Qwen إلى مساحة التطبيق...\n"
                    "قد يستغرق ذلك دقيقة أو أكثر في المرة الأولى."
                )
            )

            try:
                if os.path.exists(
                    temp_path
                ):
                    os.remove(
                        temp_path
                    )
            except Exception:
                pass

            source_copy_fd = os.dup(
                source_fd
            )

            copied = 0
            chunk_size = (
                4 * 1024 * 1024
            )

            with os.fdopen(
                source_copy_fd,
                "rb",
                buffering=0
            ) as source:
                source_copy_fd = -1

                with open(
                    temp_path,
                    "wb",
                    buffering=0
                ) as target:
                    while True:
                        chunk = source.read(
                            chunk_size
                        )

                        if not chunk:
                            break

                        target.write(
                            chunk
                        )
                        copied += len(
                            chunk
                        )

                    target.flush()

                    try:
                        os.fsync(
                            target.fileno()
                        )
                    except Exception:
                        pass

            if copied <= 0:
                raise RuntimeError(
                    "تم اختيار ملف فارغ."
                )

            if (
                source_size > 0
                and copied != source_size
            ):
                raise RuntimeError(
                    "لم يكتمل نسخ ملف النموذج. حاول مرة أخرى."
                )

            with open(
                temp_path,
                "rb"
            ) as check:
                magic = check.read(
                    4
                )

            if magic != b"GGUF":
                raise RuntimeError(
                    "الملف المختار ليس نموذج GGUF صالحاً."
                )

            os.replace(
                temp_path,
                final_path
            )

            self._model_private_path = (
                final_path
            )

            print(
                "811: Local Qwen model imported:",
                final_path,
                copied,
                "bytes"
            )

            return (
                final_path,
                model_name
            )

        finally:
            if source_copy_fd >= 0:
                try:
                    os.close(
                        source_copy_fd
                    )
                except Exception:
                    pass

            try:
                pfd.close()
            except Exception:
                pass

    def _query_uri_name(
        self,
        uri
    ):
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

            resolver = (
                activity.getContentResolver()
            )

            cursor = resolver.query(
                uri,
                None,
                None,
                None,
                None
            )

            if (
                cursor is not None
                and cursor.moveToFirst()
            ):
                index = cursor.getColumnIndex(
                    OpenableColumns.DISPLAY_NAME
                )

                if index >= 0:
                    value = cursor.getString(
                        index
                    )

                    if value is not None:
                        return str(value)

        except Exception as exc:
            print(
                "811: Local Qwen URI name error:",
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

            flags = (
                granted_flags
                & read_flag
            )

            if not flags:
                flags = read_flag

            activity.getContentResolver().takePersistableUriPermission(
                uri,
                flags
            )

            print(
                "811: Local Qwen URI permission persisted"
            )

        except Exception as exc:
            # Current-session access can still work even when a provider does
            # not support persistable URI permissions.
            print(
                "811: Persistable URI permission warning:",
                repr(exc)
            )

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

    def _read_provider_choice(self):
        prefs = self._get_preferences()

        if prefs is None:
            return ""

        try:
            return str(
                prefs.getString(
                    "ai_provider_choice",
                    ""
                )
                or ""
            ).strip().lower()

        except Exception:
            return ""

    def _save_model_uri(
        self,
        uri_string,
        model_name,
        model_path=""
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
                str(
                    model_path
                    or self._model_private_path
                    or ""
                )
            )

            editor.apply()

        except Exception as exc:
            print(
                "811: Local Qwen selection save error:",
                repr(exc)
            )

    def _load_saved_model_path(self):
        prefs = self._get_preferences()

        if prefs is None:
            return ""

        try:
            saved_path = str(
                prefs.getString(
                    self.PREF_MODEL_PATH,
                    ""
                )
                or ""
            ).strip()

            saved_name = str(
                prefs.getString(
                    self.PREF_MODEL_NAME,
                    ""
                )
                or ""
            ).strip()

            if saved_name:
                self._model_name = saved_name

            if (
                saved_path
                and os.path.isfile(
                    saved_path
                )
            ):
                self._model_private_path = (
                    saved_path
                )
                return saved_path

            return ""

        except Exception:
            return ""

    def _load_saved_model_uri(self):
        prefs = self._get_preferences()

        if prefs is None:
            return ""

        try:
            uri_string = str(
                prefs.getString(
                    self.PREF_MODEL_URI,
                    ""
                )
                or ""
            ).strip()

            saved_name = str(
                prefs.getString(
                    self.PREF_MODEL_NAME,
                    ""
                )
                or ""
            ).strip()

            if saved_name:
                self._model_name = saved_name

            return uri_string

        except Exception:
            return ""

    def _clear_saved_model_uri(self):
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
    # MODEL PATH / LIFECYCLE
    # =====================================================

    def set_model_path(self, model_path):
        """
        Regular filesystem-path entry point kept for non-URI callers/tests.
        Android's normal flow imports the picker URI into app-private storage.
        """
        model_path = str(
            model_path or ""
        ).strip()

        if not model_path:
            return False

        if not model_path.lower().endswith(
            ".gguf"
        ):
            return False

        with self._lock:
            if (
                self.model_loaded
                and self.model_path == model_path
            ):
                return True

            self._destroy_locked()
            self.model_path = model_path
            self.history = []

        return True

    def load_model(self):
        """
        Load Qwen3.5 2B Q4_K_M.

        Heavy native work: call only from a worker thread.
        """
        with self._lock:
            if not self.model_path:
                return {
                    "success": False,
                    "message": (
                        "لم يتم اختيار ملف Qwen بصيغة GGUF بعد."
                    )
                }

            if not os.path.exists(
                self.model_path
            ):
                return {
                    "success": False,
                    "message": (
                        "تعذر الوصول إلى ملف النموذج. "
                        "اختر ملف GGUF مرة أخرى."
                    )
                }

            try:
                self._ensure_native_library()

            except Exception as exc:
                self.model_loaded = False

                return {
                    "success": False,
                    "message": (
                        "تعذر تشغيل محرك Local Qwen داخل التطبيق.\n"
                        + str(exc)
                    )
                }

            self._destroy_locked()

            path_bytes = self.model_path.encode(
                "utf-8",
                errors="strict"
            )

            handle_value = self._lib.qwen811_load(
                path_bytes,
                int(self.CONTEXT_SIZE),
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
            self.history = []

            return {
                "success": True,
                "message": (
                    "تم تحميل Qwen3.5 2B محلياً بنجاح. "
                    "يمكنك استخدام Local Qwen بدون إنترنت."
                )
            }

    def unload_model(self):
        with self._lock:
            self._destroy_locked()
            self._close_model_descriptor_locked()
            self.history = []

    def close(self):
        self.unload_model()

        if self._provider_watch_event is not None:
            try:
                self._provider_watch_event.cancel()
            except Exception:
                pass

            self._provider_watch_event = None

        if (
            self._activity_result_bound
            and self._android_activity_module
            is not None
        ):
            try:
                self._android_activity_module.unbind(
                    on_activity_result=self._on_activity_result
                )
            except Exception:
                pass

            self._activity_result_bound = False

    # =====================================================
    # CHAT
    # =====================================================

    def get_response(self, user_text):
        user_text = self._clean_text(
            user_text
        )

        if not user_text:
            return "لم أستلم نصاً واضحاً."

        if not self.is_available():
            if platform == "android":
                if not self._loading:
                    saved_uri = (
                        self._load_saved_model_uri()
                    )

                    if saved_uri:
                        self._start_uri_load(
                            saved_uri,
                            persist=False
                        )
                    elif not self._picker_open:
                        Clock.schedule_once(
                            lambda dt:
                            self.request_model_picker(),
                            0
                        )

            if self._loading:
                return (
                    "جاري تحميل Local Qwen. "
                    "انتظر قليلاً ثم تحدث مرة أخرى."
                )

            if self._picker_open:
                return (
                    "اختر ملف Qwen3.5 2B Q4_K_M "
                    "من نافذة الملفات أولاً."
                )

            return (
                "Local Qwen غير محمّل بعد. "
                "اختر ملف Qwen3.5 2B Q4_K_M بصيغة GGUF."
            )

        with self._lock:
            self._sync_history_with_visible_chat()

            prompt, fitted_history = (
                self._fit_prompt_to_context(
                    user_text
                )
            )

            if not prompt:
                return (
                    "الرسالة أكبر من سعة الذاكرة النصية المحلية. "
                    "اختصرها ثم حاول مرة أخرى."
                )

            output_ptr = ctypes.c_void_p()

            cancel_watch_stop = (
                threading.Event()
            )

            request_serial = (
                self._current_app_request_serial()
            )

            cancel_watch = threading.Thread(
                target=self._cancel_watchdog,
                args=(
                    request_serial,
                    cancel_watch_stop
                ),
                daemon=True
            )
            cancel_watch.start()

            try:
                status = self._lib.qwen811_generate(
                    self._handle,
                    prompt.encode(
                        "utf-8",
                        errors="strict"
                    ),
                    int(self.MAX_TOKENS),
                    ctypes.byref(
                        output_ptr
                    )
                )

            finally:
                cancel_watch_stop.set()

            if status != 0:
                native_error = (
                    self._last_native_error()
                )

                if status == 2:
                    return "تم إيقاف توليد الرد."

                if status == 3:
                    return (
                        "المحادثة تجاوزت سعة Local Qwen. "
                        "امسح المحادثة أو اختصر الرسالة ثم حاول مرة أخرى."
                    )

                return self._friendly_native_error(
                    native_error
                )

            if not output_ptr.value:
                return (
                    "لم يُرجع Local Qwen نصاً."
                )

            try:
                raw = ctypes.string_at(
                    output_ptr.value
                ).decode(
                    "utf-8",
                    errors="replace"
                )

            finally:
                self._lib.qwen811_free_text(
                    output_ptr
                )

            response = self.clean_model_output(
                raw
            )

            if not response:
                response = (
                    "لم يُرجع Local Qwen رداً واضحاً."
                )

            self.history = (
                list(fitted_history)
                + [
                    {
                        "role": "user",
                        "content": user_text
                    },
                    {
                        "role": "assistant",
                        "content": response
                    }
                ]
            )

            self._trim_history_turns(
                max_turns=6
            )

            return response

    def clear_history(self):
        with self._lock:
            self.history = []

    def cancel(self):
        """
        Native cancellation is lock-free by design.
        """
        lib = self._lib
        handle = self._handle

        if (
            lib is None
            or not handle
        ):
            return

        try:
            lib.qwen811_cancel(
                handle
            )
        except Exception:
            pass

    # =====================================================
    # MAIN-APP COOPERATION WITHOUT MODIFYING main.py
    # =====================================================

    def _current_app_request_serial(self):
        try:
            from kivy.app import App

            app = App.get_running_app()

            if app is None:
                return None

            return int(
                getattr(
                    app,
                    "_request_serial",
                    0
                )
            )

        except Exception:
            return None

    def _cancel_watchdog(
        self,
        request_serial,
        stop_event
    ):
        if request_serial is None:
            return

        while not stop_event.wait(
            0.10
        ):
            try:
                from kivy.app import App

                app = App.get_running_app()

                if app is None:
                    continue

                current = int(
                    getattr(
                        app,
                        "_request_serial",
                        request_serial
                    )
                )

                if current != int(
                    request_serial
                ):
                    self.cancel()
                    return

            except Exception:
                return

    def _sync_history_with_visible_chat(self):
        """
        The existing main.py Clear button resets visible chat but does not yet
        know about LocalQwenClient.clear_history(). Detect the first visible
        turn after a reset so local history is reset too, without touching the
        stable main.py.
        """
        try:
            from kivy.app import App

            app = App.get_running_app()

            if app is None:
                return

            rows = getattr(
                app,
                "_chat_rows",
                None
            )

            if (
                rows is not None
                and len(rows) <= 2
            ):
                self.history = []

        except Exception:
            pass

    def _notify_app(
        self,
        state,
        message
    ):
        message = str(
            message or ""
        )

        def apply_state(dt):
            try:
                from kivy.app import App

                app = App.get_running_app()

                if (
                    app is not None
                    and hasattr(
                        app,
                        "set_state"
                    )
                ):
                    app.set_state(
                        state,
                        message
                    )

            except Exception as exc:
                print(
                    "811: Local Qwen UI notify error:",
                    repr(exc)
                )

        Clock.schedule_once(
            apply_state,
            0
        )

    # =====================================================
    # QWEN3.5 TEXT CHAT TEMPLATE
    # =====================================================

    def _format_prompt(
        self,
        user_text,
        history=None
    ):
        if history is None:
            history = self.history

        parts = [
            "<|im_start|>system\n",
            self.SYSTEM_PROMPT,
            "<|im_end|>\n"
        ]

        for message in history:
            role = str(
                message.get(
                    "role",
                    ""
                )
            ).strip().lower()

            content = self._clean_text(
                message.get(
                    "content",
                    ""
                )
            )

            if (
                role not in (
                    "user",
                    "assistant"
                )
                or not content
            ):
                continue

            parts.extend(
                [
                    "<|im_start|>",
                    role,
                    "\n",
                    content,
                    "<|im_end|>\n"
                ]
            )

        parts.extend(
            [
                "<|im_start|>user\n",
                user_text,
                "<|im_end|>\n",
                "<|im_start|>assistant\n",
                "<think>\n\n</think>\n\n"
            ]
        )

        return "".join(
            parts
        )

    def _fit_prompt_to_context(
        self,
        user_text
    ):
        history = list(
            self.history
        )

        while True:
            prompt = self._format_prompt(
                user_text,
                history=history
            )

            token_count = (
                self._lib
                .qwen811_token_count(
                    self._handle,
                    prompt.encode(
                        "utf-8",
                        errors="strict"
                    )
                )
            )

            if token_count < 0:
                return None, []

            if (
                token_count
                + int(self.MAX_TOKENS)
                + 1
                <= int(self.CONTEXT_SIZE)
            ):
                return (
                    prompt,
                    history
                )

            if not history:
                return None, []

            history = (
                self._drop_oldest_turn(
                    history
                )
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
                "لم يتم العثور على libqwen811.so داخل التطبيق."
            )

        if not os.path.isfile(
            native_path
        ):
            raise RuntimeError(
                "مكتبة libqwen811.so غير موجودة في مسار Android الأصلي."
            )

        lib = ctypes.CDLL(
            native_path
        )

        lib.qwen811_abi_version.argtypes = []
        lib.qwen811_abi_version.restype = (
            ctypes.c_int
        )

        lib.qwen811_last_error.argtypes = []
        lib.qwen811_last_error.restype = (
            ctypes.c_char_p
        )

        lib.qwen811_load.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int
        ]
        lib.qwen811_load.restype = (
            ctypes.c_void_p
        )

        lib.qwen811_token_count.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p
        ]
        lib.qwen811_token_count.restype = (
            ctypes.c_int
        )

        lib.qwen811_generate.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.POINTER(
                ctypes.c_void_p
            )
        ]
        lib.qwen811_generate.restype = (
            ctypes.c_int
        )

        lib.qwen811_free_text.argtypes = [
            ctypes.c_void_p
        ]
        lib.qwen811_free_text.restype = None

        lib.qwen811_cancel.argtypes = [
            ctypes.c_void_p
        ]
        lib.qwen811_cancel.restype = None

        lib.qwen811_destroy.argtypes = [
            ctypes.c_void_p
        ]
        lib.qwen811_destroy.restype = None

        abi = int(
            lib.qwen811_abi_version()
        )

        if abi != int(
            self.ABI_VERSION
        ):
            raise RuntimeError(
                "إصدار محرك Local Qwen غير متوافق مع التطبيق."
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

                activity = (
                    PythonActivity.mActivity
                )

                if activity is not None:
                    native_dir = str(
                        activity
                        .getApplicationInfo()
                        .nativeLibraryDir
                    )

                    candidate = os.path.join(
                        native_dir,
                        "libqwen811.so"
                    )

                    if os.path.isfile(
                        candidate
                    ):
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
            "libqwen811.so"
        )

        if os.path.isfile(
            candidate
        ):
            return candidate

        return ""

    def _last_native_error(self):
        if self._lib is None:
            return ""

        try:
            raw = (
                self._lib
                .qwen811_last_error()
            )

            if not raw:
                return ""

            if isinstance(
                raw,
                bytes
            ):
                return raw.decode(
                    "utf-8",
                    errors="replace"
                ).strip()

            return str(
                raw
            ).strip()

        except Exception:
            return ""

    def _destroy_locked(self):
        if (
            self._lib is not None
            and self._handle
        ):
            try:
                self._lib.qwen811_destroy(
                    self._handle
                )
            except Exception:
                pass

        self._handle = None
        self.model_loaded = False

    def _close_model_descriptor_locked(self):
        pfd = self._model_pfd
        self._model_pfd = None

        if pfd is not None:
            try:
                pfd.close()
            except Exception:
                pass

        self.model_path = ""
        self._model_uri = ""

    # =====================================================
    # ANDROID UI THREAD
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
                        outer._picker_open = False

                        print(
                            "811: Local Qwen UI runnable error:",
                            repr(exc)
                        )

            runnable = UiRunnable()

            self._last_ui_runnable = (
                runnable
            )

            activity.runOnUiThread(
                runnable
            )

        except Exception as exc:
            self._picker_open = False

            print(
                "811: Local Qwen runOnUiThread error:",
                repr(exc)
            )

    # =====================================================
    # HISTORY
    # =====================================================

    def _drop_oldest_turn(
        self,
        history
    ):
        history = list(
            history
        )

        if not history:
            return []

        if (
            len(history) >= 2
            and history[0].get(
                "role"
            ) == "user"
            and history[1].get(
                "role"
            ) == "assistant"
        ):
            return history[2:]

        return history[1:]

    def _trim_history_turns(
        self,
        max_turns
    ):
        max_messages = max(
            0,
            int(max_turns) * 2
        )

        while len(
            self.history
        ) > max_messages:
            self.history = (
                self._drop_oldest_turn(
                    self.history
                )
            )

    # =====================================================
    # OUTPUT / ERRORS
    # =====================================================

    def clean_model_output(
        self,
        text
    ):
        text = str(
            text or ""
        )

        text = re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=(
                re.DOTALL
                | re.IGNORECASE
            )
        )

        text = text.replace(
            "<think>",
            ""
        ).replace(
            "</think>",
            ""
        )

        text = text.replace(
            "<|im_end|>",
            ""
        ).replace(
            "<|im_start|>",
            ""
        )

        return self._clean_text(
            text
        )

    def _friendly_native_error(
        self,
        native_error
    ):
        error = str(
            native_error or ""
        ).strip()

        lower = error.lower()

        if "qwen35 architecture" in lower:
            return (
                "الملف ليس نموذج Qwen3.5 الصحيح. "
                "اختر Qwen3.5 2B بصيغة GGUF."
            )

        if (
            "q4_k_m" in lower
            or "quantization" in lower
        ):
            return (
                "اختر نسخة Qwen3.5 2B بتكميم Q4_K_M."
            )

        if "2b model size" in lower:
            return (
                "اختر نموذج Qwen3.5 بحجم 2B."
            )

        if (
            "insufficient memory" in lower
            or "allocation failed" in lower
        ):
            return (
                "ذاكرة RAM المتاحة غير كافية لتحميل Local Qwen حالياً. "
                "أغلق التطبيقات الأخرى ثم حاول مرة أخرى."
            )

        if "gguf load failed" in lower:
            return (
                "تعذر فتح نموذج GGUF داخل المحرك. "
                "سيتم استخدام نسخة محلية داخل مساحة التطبيق في النسخة المصححة."
            )

        if "conversation exceeds context" in lower:
            return (
                "المحادثة طويلة على الذاكرة المحلية. "
                "امسح المحادثة أو اختصرها ثم حاول مرة أخرى."
            )

        if "cancelled" in lower:
            return "تم إيقاف توليد الرد."

        if error:
            return (
                "خطأ في Local Qwen:\n"
                + error
            )

        return (
            "حدث خطأ غير معروف داخل محرك Local Qwen."
        )

    def _clean_text(
        self,
        text
    ):
        if text is None:
            return ""

        text = str(
            text
        )

        text = text.replace(
            "\r\n",
            "\n"
        ).replace(
            "\r",
            "\n"
        )

        text = re.sub(
            r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]",
            "",
            text
        )

        lines = []

        for line in text.split(
            "\n"
        ):
            line = re.sub(
                r"[ \t]+",
                " ",
                line
            ).strip()

            if line:
                lines.append(
                    line
                )

        return "\n".join(
            lines
        ).strip()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
