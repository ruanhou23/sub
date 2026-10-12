import sys
import os

# Set UTF-8 encoding for Windows standard IO
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure current project directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from ui.main_window import MainWindow

def main():
    try:
        app = MainWindow()
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
