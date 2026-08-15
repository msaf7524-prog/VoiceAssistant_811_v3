[app]
title = Voice Assistant 811
package.name = voiceapp
package.domain = org.test.voiceapp
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1

requirements = python3,kivy,requests,urllib3,chardet,idna,arabic_reshaper,python-bidi,pyjnius

orientation = portrait
osx.kivy_version = 2.2.1

fullscreen = 0

# الأذونات الكاملة للمايك، البلوتوث، والخدمة الخلفية المستمرة
android.permissions = RECORD_AUDIO, INTERNET, FOREGROUND_SERVICE, BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, WAKE_LOCK, MODIFY_AUDIO_SETTINGS, ACCESS_NETWORK_STATE

android.api = 33
android.minapi = 21
android.ndk = 25b
android.private_storage = True
android.accept_sdk_license = True

p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
