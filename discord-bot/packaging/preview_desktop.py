"""Development tool: opens the desktop app on a virtual display and saves screenshots of its pages (Linux, needs Xvfb + ImageMagick and a
Python with Tk and the app's dependencies).
    xvfb-run -a -s "-screen 0 1280x900x24" python packaging/preview_desktop.py <folder> [fresh|event|stopped]...
`fresh` is a first run (no token), `event` an event going on (the bot connected, the Activity open), `stopped` a configured app with the bot off.
Not shipped with the app."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("EVENTOS_HOME", tempfile.mkdtemp(prefix="eventos-preview-"))


def snap(app, out: Path, name: str, pause: float = 0.5) -> None:
    end = time.time() + pause
    while time.time() < end:
        app.update()
        time.sleep(0.02)
    target = out / f"{name}.png"
    subprocess.run(["import", "-window", "root", str(target)], check=True)
    print("saved", target)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    scenarios = sys.argv[2:] or ["fresh", "event", "stopped"]
    from eventos_app import paths, updates
    paths.seed_defaults()
    from desktop_fakes import connect
    from eventos_app.console_bridge import Segment
    from eventos_app.ui import App

    for scenario in scenarios:
        app = App()
        app.geometry("1120x780+0+0")
        if scenario == "event":
            connect(app)
            app.show_update(updates.Update("1.0.1", "https://github.com/Yendaxddd/eventos-app/releases/latest", "Panel del GM más rápido y copias de seguridad",
                                           "https://github.com/Yendaxddd/eventos-app/releases/latest/download/EventosApp-Setup.exe"))
            for text, color in (("✓ Servidor de la Actividad en el puerto 8765. Abriendo el túnel…", "#008000"), ("🌐 Actividad: Ana entró a la Actividad", None),
                                ("⚡ QTE HARD lanzado a Ana", None), ("⚠ Sin webhook para Ayudante: falta «Gestionar webhooks»", "#ffa500"),
                                ("💥 Rey de las Maldiciones recibió 40 de daño. HP: 640/1000", "#ff0000")):
                app._log_queue.append([Segment(text, color)])
        elif scenario == "stopped":
            app.settings.discord_token = "x" * 24
            app.settings.activity_enabled = True
        app.update()
        for name in app.pages:
            app.show_page(name)
            snap(app, out, f"{scenario}-{name}")
        for tab in ("send", "start"):                                   # the other tabs of the settings
            app.show_page("config", tab=tab)
            snap(app, out, f"{scenario}-config-{tab}")
        app.destroy()


if __name__ == "__main__":
    main()
