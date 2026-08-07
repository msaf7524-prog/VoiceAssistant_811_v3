[app]

# (str) Title of your application
title = Voice Assistant

# (str) Package name
package.name = voiceassistant

# (str) Package domain
package.domain = org.test

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas,ttf,otf

# (str) Application versioning
version = 0.2

# (list) Application requirements
requirements = python3,kivy,pyjnius,plyer

# (str) Supported orientation
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET

# (int) Target Android API
android.api = 33

# (int) Minimum API required
android.minapi = 21

# (str) Android NDK version
android.ndk = 25b

# (list) List of architectures to build for
android.archs = arm64-v8a

[buildozer]

# (int) Log level
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
