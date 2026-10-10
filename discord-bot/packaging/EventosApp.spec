# PyInstaller spec for the desktop app.  Build with:  pyinstaller packaging/EventosApp.spec
# (run from discord-bot/; see build_windows.ps1, which also copies assets/ and data/ next to the exe)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent  # discord-bot/
sys.path.insert(0, str(ROOT))
from eventos_app import APP_NAME, __version__  # noqa: E402

# File properties shown in Explorer / Task Manager. Windows only (needs `pefile`, which
# PyInstaller installs on Windows only).
version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )

    _v = tuple(int(x) for x in (__version__.split(".") + ["0", "0", "0"])[:3]) + (0,)
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=_v, prodvers=_v, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", ""),
                StringStruct("FileDescription", APP_NAME),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", "EventosApp"),
                StringStruct("OriginalFilename", "EventosApp.exe"),
                StringStruct("ProductName", APP_NAME),
                StringStruct("ProductVersion", __version__),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


# customtkinter ships theme .json files and fonts that must travel with the app
datas = collect_data_files("customtkinter")
datas += [(str(ROOT / "eventos_app" / "resources"), "eventos_app/resources")]

a = Analysis(
    [str(ROOT / "run_app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    # The bot is loaded with importlib (see eventos_app/runner.py), so PyInstaller can't see it;
    # naming it makes PyInstaller follow all of its imports too. `keyboard` is imported inside
    # try/except at the top of the bot, so it is named explicitly.
    hiddenimports=["advanced_qte_hp_system_debug"] + (["keyboard"] if sys.platform == "win32" else []),
    # never used by the app; keeps the build smaller
    excludes=["matplotlib", "numpy", "pandas", "scipy", "pytest", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EventosApp",
    console=False,  # a real windowed app: no terminal
    icon=str(ROOT / "eventos_app" / "resources" / "icon.ico"),
    version=version_info,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="EventosApp", upx=False)
