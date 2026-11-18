"""Application stylesheet (light, neutral, readable on any OS theme)."""

APP_STYLE = """
QWidget { font-size: 13px; color: #1f2933; }
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget { background: #f4f6f8; }
QGroupBox {
    background: #ffffff; border: 1px solid #d9dee4; border-radius: 8px;
    margin-top: 14px; padding: 10px 10px 8px 10px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #334e68; }
QLabel { background: transparent; font-weight: normal; }
QLabel#hint { color: #627d98; font-size: 12px; }
QLabel#error { color: #b42318; }
QPushButton {
    background: #ffffff; border: 1px solid #bcccdc; border-radius: 6px; padding: 6px 14px;
}
QPushButton:hover { background: #eef2f6; }
QPushButton:disabled { color: #9aa5b1; background: #f0f2f5; }
QPushButton#primary { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; font-weight: 600; }
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton#primary:disabled { background: #a9bff0; border-color: #a9bff0; }
QPushButton#danger { color: #b42318; }
QLineEdit, QSpinBox, QComboBox { background: #ffffff; border: 1px solid #bcccdc; border-radius: 5px; padding: 4px 6px; }
QProgressBar { border: 1px solid #bcccdc; border-radius: 6px; text-align: center; height: 20px; background: #eef2f6; }
QProgressBar::chunk { background: #2563eb; border-radius: 5px; }
QTableWidget { background: #ffffff; border: 1px solid #d9dee4; gridline-color: #eef2f6; }
QHeaderView::section { background: #eef2f6; border: none; border-bottom: 1px solid #d9dee4; padding: 4px 6px; font-weight: 600; }
QLabel#previewImage { background: #eef2f6; border: 1px dashed #bcccdc; border-radius: 6px; }
"""
