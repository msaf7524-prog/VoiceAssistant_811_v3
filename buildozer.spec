[app]

# (str) Title of your application
title = Voice Assistant 811

# (str) Package name
package.name = voiceassistant811

# (str) Package domain (needed for android/ios packaging)
package.domain = org.test

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas

# (str) Application versioning
version = 1.0

# (list) Application requirements
# تم إضافة مكتبات تشكيل اللغة العربية لإنهاء مشكلة المربعات XXXX
requirements = python3,kivy,pyjnius,requests,urllib3,chardet,idna,certifi,arabic_reshaper,python-bidi

# (str) Supported orientations
orientation = portrait

# (string) Kivy version to use
osx.kivy_version = 2.0.0

# (bool) Fullscreen or not
fullscreen = 0

# (list) Permissions required for Microphone, Bluetooth and Background processing
android.permissions = RECORD_AUDIO, BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, WAKE_LOCK, FOREGROUND_SERVICE, INTERNET, ACCESS_NETWORK_STATE, MODIFY_AUDIO_SETTINGS

# (int) Target Android API
android.api = 33

# (int) Minimum API your APK will support
android.minapi = 21

# (str) Android NDK version to use
android.ndk = 25b

# (bool) Accept SDK licenses automatically
android.accept_sdk_license = True

# (str) The Android arch to build for
android.archs = arm64-v8a, armeabi-v7a

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
