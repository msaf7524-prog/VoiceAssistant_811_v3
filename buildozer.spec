[app]

# (str) Title of your application
title = Voice Assistant 811

# (str) Package name
package.name = voiceassistant811

# (str) Package domain (needed for android/ios packaging)
package.domain = org.test

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas,ttf

# (str) Application versioning
version = 0.1

# (list) Application requirements (تمت إضافة certifi و openssl لاستقرار الاتصال)
requirements = python3,kivy,requests,pyjnius,arabic_reshaper,python-bidi,android,openssl,certifi

# (list) Permissions
android.permissions = RECORD_AUDIO,INTERNET,ACCESS_NETWORK_STATE,MODIFY_AUDIO_SETTINGS,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_CONNECT

# (list) Supported architectures
android.archs = arm64-v8a, armeabi-v7a

# (str) Supported orientation
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (int) Target Android API
android.api = 33

# (int) Minimum API your APK will support
android.minapi = 21

# (bool) Accept SDK license automatically
android.accept_sdk_license = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
