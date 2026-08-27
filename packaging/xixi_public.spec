# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

import webview
from PyInstaller.utils.hooks import collect_all, collect_submodules


project = Path(SPECPATH).resolve().parent
staging = project / "packaging" / "staging"
offline_bundle = os.environ.get("XIXI_BUILD_OFFLINE_BUNDLE", "0") == "1"

datas = [
    (str(project / "studio"), "studio"),
    (str(staging / "persona.txt"), "."),
    (str(staging / "interest_profile.json"), "."),
    (str(project / "learning_sources.json"), "."),
    (str(project / "meme_lexicon.json"), "."),
    (str(project / "data" / "voice_assets" / "xixi_voice_reference_zh.mp3"), "data/voice_assets"),
    (str(project / "data" / "voice_assets" / "xixi_reference_zh.mp3"), "data/voice_assets"),
    (str(project / "data" / "voice_assets" / "xixi_reference_ja.ogg"), "data/voice_assets"),
    (str(project / "data" / "voice_assets" / "xixi_reference_emphatic.ogg"), "data/voice_assets"),
    (str(project / "data" / "voice_assets" / "xixi_reference_warm.ogg"), "data/voice_assets"),
    (str(project / "data" / "voice_assets" / "xixi_reference_playful.ogg"), "data/voice_assets"),
    (str(project / "data" / "voice_assets" / "xixi_reference_concerned.ogg"), "data/voice_assets"),
    (str(project / "packaging" / "xixi_voice_tts_infer.yaml"), "runtime/voice"),
    (str(staging / "voice_models"), "runtime/voice/package/models"),
    (str(staging / "voice_wheels"), "runtime/voice/package/wheels"),
    (str(staging / "voice_engine"), "runtime/voice/package/engine"),
    (str(staging / "voice_nltk_data"), "runtime/voice/package/nltk_data"),
    (str(staging / "install_tools"), "runtime/install_tools"),
    (str(staging / "napcat"), "runtime/components/NapCat"),
    (str(project / "packaging" / "README.txt"), "."),
    (str(project / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project / "third_party_licenses"), "third_party_licenses"),
]
if offline_bundle:
    datas.append((str(project / "whisper-small-full"), "whisper-small-full"))

# pywebview resolves these assemblies beside the frozen executable before its
# package data path. Keep root copies so an installed one-folder build starts
# independently of the source environment.
webview_lib = Path(webview.__file__).resolve().parent / "lib"
for dll_name in (
    "Microsoft.Web.WebView2.Core.dll",
    "Microsoft.Web.WebView2.WinForms.dll",
    "WebBrowserInterop.x64.dll",
    "WebBrowserInterop.x86.dll",
):
    datas.append((str(webview_lib / dll_name), "."))

hiddenimports = [
    "app.studio",
    "start_xixi_studio",
    "start_xixi_qq",
    "pystray._win32",
    "keyring.backends.Windows",
    "webview.platforms.edgechromium",
    "qrcode",
]
for package in ("faster_whisper", "ctranslate2", "huggingface_hub", "openai", "ollama", "edge_tts"):
    hiddenimports += collect_submodules(package)

extra_datas = []
extra_binaries = []
for package in ("faster_whisper", "ctranslate2", "sounddevice", "pygame", "dxcam", "comtypes", "mss"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    extra_datas += [
        item
        for item in package_datas
        if not any(
            part.casefold() in {"docs", "examples", "test", "tests"}
            for part in Path(item[0]).parts
        )
    ]
    extra_binaries += package_binaries
    hiddenimports += [
        name
        for name in package_hidden
        if not any(
            token in name.casefold()
            for token in (".docs", ".examples", ".test", ".tests")
        )
    ]

a = Analysis(
    [str(project / "start_xixi_desktop.py")],
    pathex=[str(project)],
    binaries=extra_binaries,
    datas=datas + extra_datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "unittest.mock", "pygame.tests", "comtypes.test"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Xixi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    contents_directory=".",
    icon=str(project / "studio" / "assets" / "xixi-v3.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Xixi",
)
