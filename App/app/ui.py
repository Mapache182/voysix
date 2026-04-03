from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSystemTrayIcon, QMenu, QTextEdit, QPushButton, QSpacerItem, QSizePolicy
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QRect
from PySide6.QtGui import QIcon, QPainter, QColor, QAction, QTextCursor, QPixmap, QLinearGradient
import sys
import os
import io
import ctypes
from app.i18n import tr, hlp
from app.utils import get_resource_path

class FloatingStatus(QWidget):
    geometry_changed = Signal()
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.ToolTip)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(100, 30)
        self.resize(160, 40)
        
        self.status = "idle" # "idle", "loading", "recording", "processing", "done"
        self.level = 0.0 # Audio level (0 to 1)
        self.drag_pos = QPoint()
        self.resizing = False
        self.resize_edge = None
        self.show_settings_callback = None
        self.ui_design = "waveform"
        self.level_history = [0.0] * 50
        
        self.status_labels = {
            "idle": tr("ready"),
            "loading": tr("loading"),
            "recording": tr("recording"),
            "processing": tr("processing"),
            "done": tr("done")
        }
        
        # UI Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 0)
        layout.setSpacing(5)
        
        # Status text in the middle
        self.label_widget = QLabel(self.status_labels["idle"])
        self.label_widget.setAlignment(Qt.AlignCenter)
        self.label_widget.setStyleSheet("color: white; font-weight: bold; border: none; background: transparent;")
        layout.addWidget(self.label_widget, 1) # Give it stretch
        
        # Settings button
        self.settings_btn = QPushButton("⚙", self)
        self.settings_btn.setFixedSize(20, 20)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(255, 255, 255, 120);
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                color: white;
                background: rgba(255, 255, 255, 40);
                border-radius: 10px;
            }
        """)
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self._on_settings_clicked)
        layout.addWidget(self.settings_btn)

        self.colors = {
            "idle": QColor(30, 30, 30, 230),       # Dark Grey
            "loading": QColor(255, 140, 0, 230),   # Dark Orange
            "recording": QColor(35, 35, 60, 235), # Premium Deep Navy/Slate
            "processing": QColor(0, 120, 215, 230),# Windows Blue
            "done": QColor(34, 139, 34, 230)       # Forest Green
        }

    def set_status(self, status):
        self.status = status
        # We don't reset level_history here to keep the transition smooth
        
        # In waveform design, hide text when recording
        if self.ui_design == "waveform" and status == "recording":
            self.label_widget.setText("") # Use empty text to keep layout spacing
        else:
            self.label_widget.setText(self.status_labels.get(status, status))
             
        self.update()
        if status == "done":
            QTimer.singleShot(2000, lambda: self.set_status("idle"))

    def set_level(self, level):
        self.level = level
        self.level_history.pop(0)
        self.level_history.append(level)
        self.update()

    def bring_to_front(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def set_always_on_top(self, on):
        geom = self.geometry()
        flags = Qt.FramelessWindowHint | Qt.ToolTip
        if on: flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setGeometry(geom)
        if on:
            try:
                hwnd = self.winId()
                if hwnd:
                    ctypes.windll.user32.SetWindowPos(int(hwnd), -1, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0040 | 0x0010)
            except: pass
        self.show()
        self.raise_()

    def _on_settings_clicked(self):
        if self.show_settings_callback:
            self.show_settings_callback()

    def resizeEvent(self, event):
        point_size = max(8, min(14, self.height() // 3))
        font = self.label_widget.font()
        font.setPointSize(point_size)
        self.label_widget.setFont(font)
        super().resizeEvent(event)

    def _get_resize_edge(self, pos):
        edge_size = 8
        rect = self.rect()
        at_right = pos.x() >= rect.width() - edge_size
        at_bottom = pos.y() >= rect.height() - edge_size
        if at_right and at_bottom: return "bottom_right"
        if at_right: return "right"
        if at_bottom: return "bottom"
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge = self._get_resize_edge(event.pos())
            if edge:
                self.resizing = True
                self.resize_edge = edge
            else:
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        if not event.buttons():
            edge = self._get_resize_edge(pos)
            if edge == "bottom_right": self.setCursor(Qt.SizeFDiagCursor)
            elif edge == "right": self.setCursor(Qt.SizeHorCursor)
            elif edge == "bottom": self.setCursor(Qt.SizeVerCursor)
            else: self.setCursor(Qt.ArrowCursor)
        elif event.buttons() & Qt.LeftButton:
            if self.resizing:
                if "right" in self.resize_edge:
                    self.resize(max(self.minimumWidth(), pos.x()), self.height())
                if "bottom" in self.resize_edge:
                    self.resize(self.width(), max(self.minimumHeight(), pos.y()))
            else:
                self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.resizing = False
        self.setCursor(Qt.ArrowCursor)
        self.geometry_changed.emit()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        color = self.colors.get(self.status, self.colors["idle"])
        
        # Pill/Rounded Rect shape
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        radius = min(self.height(), self.width()) // 2
        painter.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        
        # Volume meter
        if self.status == "recording":
            if self.ui_design == "waveform":
                # Draw Premium Waveform
                meter_h = self.height() * 0.7
                center_y = self.height() // 2
                samples = self.level_history
                n = len(samples)
                
                # Padding for rounded ends and button room
                x_start = 25
                x_end = self.width() - 35
                w_avail = x_end - x_start
                
                bar_count = n
                bar_spacing = 1
                bar_w = 2 
                max_bars = w_avail // (bar_w + bar_spacing)
                
                # Take only the LATEST samples that fit
                to_draw = samples[-max_bars:]
                num_to_draw = len(to_draw)
                
                # Center the bars in the available space
                actual_w = num_to_draw * (bar_w + bar_spacing)
                offset_x = (w_avail - actual_w) // 2
                
                # Gradient for bars
                gradient = QLinearGradient(0, center_y - meter_h/2, 0, center_y + meter_h/2)
                gradient.setColorAt(0, QColor(0, 255, 255, 255))   # Cyan top
                gradient.setColorAt(0.5, QColor(0, 200, 255, 180)) # Lighter cyan middle
                gradient.setColorAt(1, QColor(0, 255, 255, 255))   # Cyan bottom
                
                painter.setPen(Qt.NoPen)
                painter.setBrush(gradient)
                
                for i in range(num_to_draw):
                    # Scale and smooth value
                    val = to_draw[i] * 3.0 
                    if val > 1.0: val = 1.0
                    if val < 0.05: val = 0.05 
                    
                    h = int(val * meter_h)
                    x = x_start + offset_x + i * (bar_w + bar_spacing)
                    
                    painter.drawRoundedRect(
                        x, 
                        center_y - h // 2, 
                        bar_w, 
                        h,
                        bar_w // 2, bar_w // 2
                    )
            else:
                # Classic volume meter
                meter_h = max(2, self.height() // 10)
                meter_w = int(self.width() * min(self.level * 10, 0.7))
                if meter_w > 5:
                    painter.setBrush(QColor(0, 255, 150, 180))
                    painter.drawRoundedRect(
                        (self.width() - meter_w) // 2, 
                        self.height() - meter_h - 4, 
                        meter_w, 
                        meter_h,
                        2, 2
                    )



class LogWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Voysix {tr('show_logs')}")
        icon_path = get_resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: monospace;")
        layout.addWidget(self.text_edit)

    def append_log(self, text):
        self.text_edit.moveCursor(QTextCursor.End)
        self.text_edit.insertPlainText(text)
        self.text_edit.moveCursor(QTextCursor.End)

class LogHandler(io.TextIOBase):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def write(self, text):
        if text.strip():
            self.signal.emit(text)
        return len(text)

class AppTrayIcon(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        icon_path = get_resource_path(os.path.join("assets", "icon.png"))
            
        if os.path.exists(icon_path):
            self.setIcon(QIcon(icon_path))
        else:
            print(f"Warning: Icon file not found at: {icon_path}")
            self.setIcon(QIcon.fromTheme("audio-input-microphone"))
        
        self.menu = QMenu()
        self.settings_action = QAction(tr("settings"))
        self.log_action = QAction(tr("show_logs"))
        self.restart_action = QAction(tr("restart"))
        self.about_action = QAction(tr("about"))
        self.exit_action = QAction(tr("exit"))

        # Add icons to actions
        if os.path.exists(icon_path):
            # Same icon for all as a starting point, OR specific ones if we have them
            self.settings_action.setIcon(QIcon(icon_path))
            self.log_action.setIcon(QIcon(icon_path))
            self.restart_action.setIcon(QIcon(icon_path))
            self.about_action.setIcon(QIcon(icon_path))
            self.exit_action.setIcon(QIcon(icon_path))
        
        self.menu.addAction(self.settings_action)
        self.menu.addAction(self.log_action)
        self.menu.addAction(self.restart_action)
        self.menu.addAction(self.about_action)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_action)
        
        self.setContextMenu(self.menu)
