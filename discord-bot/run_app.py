"""Launcher used by PyInstaller (and handy for `python run_app.py`)."""
import sys

from eventos_app.main import main

if __name__ == "__main__":
    sys.exit(main())
