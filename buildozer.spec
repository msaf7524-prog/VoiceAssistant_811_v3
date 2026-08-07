[app]
title = Voice Assistant
package.name = voiceassistant
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,otf
version = 0.2
requirements = python3,kivy,pyjnius,plyer
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.build_tools_version = 33.0.2
android.accept_sdk_license = True
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
