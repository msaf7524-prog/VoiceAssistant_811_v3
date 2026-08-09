[app]

# (str) Title of your application
title = Voice Assistant 811

# (str) Package name
package.name = voiceassistant811

# (str) Package domain (needed for android/ios packaging)
package.domain = org.voiceassistant

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (تضمين ملفات الخط ttf ضروري جداً)
source.include_exts = py,png,jpg,kv,atlas,ttf

# (list) Application requirements
# تمت إضافة arabic_reshaper و python-bidi
requirements = python3,kivy,pyjnius,plyer,openssl,requests,certifi,urllib3,arabic_reshaper,python-bidi

# (str) Application versioning
version = 0.1

# (list) Permissions
android.permissions = INTERNET, RECORD_AUDIO, BLUETOOTH, BLUETOOTH_CONNECT, BLUETOOTH_ADMIN

# (int) Target Android API
android.api = 33

# (int) Minimum API supported
android.minapi = 21

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) List of service to declare
# services = 

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = disable, 1 = enable)
warn_on_root = 1
