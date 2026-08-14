[app]
title = Voice Assistant 811
package.name = voiceassistant811
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

requirements = python3,kivy,pyjnius,requests,urllib3,chardet,idna,certifi

orientation = portrait
osx.kivy_version = 2.0.0
fullscreen = 0

# أذونات الأندرويد المطلوبة للبلوتوث، المايك، ومنع خمول البطارية
android.permissions = RECORD_AUDIO, BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, WAKE_LOCK, FOREGROUND_SERVICE, INTERNET, ACCESS_NETWORK_STATE, MODIFY_AUDIO_SETTINGS

android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
