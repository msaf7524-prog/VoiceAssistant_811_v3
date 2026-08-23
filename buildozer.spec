[app]

# (str) Title of your application
title = Voice Assistant 811

# (str) Package name
package.name = voiceassistant811

# (str) Package domain
package.domain = org.test

# (str) Source code where main.py lives
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas,ttf,xml

# (str) Application version
version = 0.2

# (list) Python requirements
requirements = python3,kivy,requests,pyjnius,arabic_reshaper,python-bidi,android,openssl,certifi

# (list) Android permissions
android.permissions = RECORD_AUDIO,INTERNET,ACCESS_NETWORK_STATE,MODIFY_AUDIO_SETTINGS,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_CONNECT,BLUETOOTH_SCAN

# (list) Supported architectures
android.archs = arm64-v8a,armeabi-v7a

# (str) Orientation
orientation = portrait

# (bool) Fullscreen
fullscreen = 0

# Android API
android.api = 33

# Minimum Android API
android.minapi = 21

# Accept SDK licenses
android.accept_sdk_license = True

# Extra Android manifest entries
android.extra_manifest_xml = ./src/android/extra_manifest.xml


[buildozer]

# Log level
log_level = 2

# Warn when running as root
warn_on_root = 1
