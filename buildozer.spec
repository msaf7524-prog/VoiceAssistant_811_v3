[app]

title = Voice Assistant 811

package.name = voiceassistant811

package.domain = org.test

source.dir = .

source.include_exts = py,png,jpg,kv,atlas,ttf,xml

version = 0.2

requirements = python3,kivy,requests,pyjnius,arabic_reshaper,python-bidi,android,openssl,certifi

services = backgroundcore:background_core.py:foreground:sticky:foregroundServiceType=microphone

android.permissions = RECORD_AUDIO,INTERNET,ACCESS_NETWORK_STATE,MODIFY_AUDIO_SETTINGS,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_CONNECT,BLUETOOTH_SCAN,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_MICROPHONE

android.archs = arm64-v8a

orientation = portrait

fullscreen = 0

android.api = 35

android.minapi = 24

android.accept_sdk_license = True

android.enable_androidx = True

android.gradle_dependencies = dev.ffmpegkit-maintained:llama-android:0.1.1

android.extra_manifest_xml = extra_manifest.xml


[buildozer]

log_level = 2

warn_on_root = 1
