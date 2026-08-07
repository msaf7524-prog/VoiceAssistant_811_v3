[app]

# (str) Title of your application
title = Voice Assistant 811

# (str) Package name
package.name = voiceassistant811

# (str) Package domain (needed for android packaging)
package.domain = org.msaf

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas

# (list) Source files to exclude
source.exclude_exts = spec

# (list) List of directory to exclude
source.exclude_dirs = bin, .git, .github, __pycache__

# (str) Application versioning
version = 0.1

# (list) Application requirements
requirements = python3,kivy

# (list) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET, RECORD_AUDIO

# (int) Target Android API
android.api = 33

# (int) Minimum API support
android.minapi = 21

# (str) Android NDK version
android.ndk = 25b

# (bool) Private storage
android.private_storage = True

# (list) Android architecture to build for
android.archs = arm64-v8a

# (bool) Enable AndroidX support
android.androidx = True

# (str) python-for-android branch
p4a.branch = master

# (str) Packaging format
android.format = apk

[buildozer]

# (int) Log level
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1

# (str) Path to build directory
build_dir = .buildozer

# (str) Path to build output
bin_dir = ./bin
