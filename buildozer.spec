[app]
title = Voice Assistant 811
package.name = voiceassistant811
package.domain = org.voiceassistant
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.4
requirements = python3,kivy,pyjnius,plyer,requests,urllib3,certifi,charset_normalizer,idna,openssl
orientation = portrait
fullscreen = 0
android.permissions = INTERNET, RECORD_AUDIO
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
