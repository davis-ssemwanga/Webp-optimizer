"""WebP Optimizer - entry point.  Run with:  python main.py"""
import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed. Run:  pip install -r requirements.txt")
        return 1

    from gui.main_window import MainWindow

    if sys.platform == "win32":  # show our icon in the taskbar instead of Python's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WebPOptimizer.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("WebP Optimizer")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
