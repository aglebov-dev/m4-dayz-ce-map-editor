[app]

# title of your application
title = M4 DayZ CE Map Editor

# project root directory. default = The parent directory of input_file
project_dir = .

# source file entry point path. default = main.py
input_file = app.py

# directory where the executable output is generated
exec_directory = D:\dayz-repositories\M4.DayZ.CE.Map.Editor\dist

# path to the project file relative to project_dir
project_file = 

# application icon
icon = D:\dayz-repositories\M4.DayZ.CE.Map.Editor\app_icon_high.ico

[python]

# python path
python_path = D:\dayz-repositories\M4.DayZ.CE.Map.Editor\.venv\Scripts\python.exe

# python packages to install
packages = Nuitka==4.0

# buildozer = for deploying Android application
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]

# paths to required qml files. comma separated
# normally all the qml files required by the project are added automatically
# design studio projects include the qml files using qt resources
qml_files = 

# excluded qml plugin binaries
excluded_qml_plugins = 

# qt modules used. comma separated
modules = Core,Gui,Widgets

# qt plugins used by the application. only relevant for desktop deployment
# for qt plugins used in android application see [android][plugins]
plugins = accessiblebridge,egldeviceintegrations,generic,iconengines,imageformats,platforminputcontexts,platforms,platforms/darwin,platformthemes,styles,wayland-decoration-client,wayland-graphics-integration-client,wayland-shell-integration,xcbglintegrations

[android]

# path to pyside wheel
wheel_pyside = 

# path to shiboken wheel
wheel_shiboken = 

# plugins to be copied to libs folder of the packaged application. comma separated
plugins = 

[nuitka]

# usage description for permissions requested by the app as found in the info.plist file
# of the app bundle. comma separated
# eg = extra_args = --show-modules --follow-stdlib
macos.permissions = 

# mode of using nuitka. accepts standalone or onefile. default = onefile
# onefile — один .exe (распаковывается во временную папку при запуске). Для onedir-сборки
# (быстрее старт, ассеты рядом лежат файлами) поставь standalone.
mode = onefile

# specify any extra nuitka arguments
#  --include-data-dir=SRC=DEST — кладём ассеты в бандл (читаются через core.paths):
#     i18n (тексты интерфейса) и buildings (footprint-датасет) — маленькие и обязательные.
#     Тайлы подложки (assets/tiles ~108 МБ) НЕ бандлим: пользователь распаковывает их из
#     игры в %LOCALAPPDATA%/M4DayZCEMapEditor/tiles (или кладёт туда готовую пирамиду).
#  --include-package=paramiko — чтобы работала загрузка через SFTP (иначе вкладка отключена).
extra_args = --quiet --noinclude-qt-translations --windows-console-mode=disable --assume-yes-for-downloads --include-data-dir=D:/dayz-repositories/M4.DayZ.CE.Map.Editor/assets/i18n=assets/i18n --include-data-dir=D:/dayz-repositories/M4.DayZ.CE.Map.Editor/assets/buildings=assets/buildings --include-package=paramiko

[buildozer]

# build mode
# possible values = ["aarch64", "armv7a", "i686", "x86_64"]
# release creates a .aab, while debug creates a .apk
mode = debug

# path to pyside6 and shiboken6 recipe dir
recipe_dir = 

# path to extra qt android .jar files to be loaded by the application
jars_dir = 

# if empty, uses default ndk path downloaded by buildozer
ndk_path = 

# if empty, uses default sdk path downloaded by buildozer
sdk_path = 

# other libraries to be loaded at app startup. comma separated.
local_libs = 

# architecture of deployed platform
arch = 

