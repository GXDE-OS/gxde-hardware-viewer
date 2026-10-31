#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
import platform
import configparser
import psutil
import socket
import subprocess
import json
import os
import glob
import time
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QScrollArea, QAbstractScrollArea, QAbstractButton, QVBoxLayout, QSizePolicy, 
                            QHBoxLayout, QListWidget, QListWidgetItem, QStackedWidget,
                            QLabel, QGroupBox, QFormLayout, QTextEdit, QFileDialog, 
                            QTableWidget, QTableWidgetItem, QProgressBar, QFrame,
                            QPushButton, QMenu, QMessageBox, QAbstractItemView, QDialog, QDialogButtonBox, QToolButton)
from PyQt6.QtWidgets import QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer, QTranslator, QCoreApplication, QLocale, QThread, pyqtSignal, QProcess, QSettings, QRect, QRectF, QPoint, QEvent, QSize
from PyQt6.QtGui import QColor, QIcon, QFont, QPainter, QPalette, QPixmap, QFontMetrics, QPainterPath, QPen, QCursor
from enum import Enum
import dbus

# 主板信息读取库（独立 py 库，便于复用与封装；安装后位于 /usr/share/gxde-hardware-viewer 下）
sys.path.append("/usr/share/gxde-hardware-viewer")
try:
    from hardware_info import BoardInfo, translate_board_text
except ImportError:
    BoardInfo = None
    translate_board_text = None

# 光驱信息读取库（独立 py 库，便于复用与封装；安装后位于 /usr/share/gxde-hardware-viewer 下）
try:
    from hardware_info import CdromInfo, translate_cdrom_text
except ImportError:
    CdromInfo = None
    translate_cdrom_text = None

# 处理器信息读取库（独立 py 库，便于复用与封装；安装后位于 /usr/share/gxde-hardware-viewer 下）
try:
    from hardware_info import CpuInfo, translate_cpu_text
except ImportError:
    CpuInfo = None
    translate_cpu_text = None

version = "2.7.2"

uname = platform.uname()

# ==================== 主题色板（UI 设计规范） ====================
# 全应用仅允许使用以下主题色，新增颜色必须先在此登记：
#   1. 主色 PRIMARY      —— 品牌品红：选中态 / 主按钮 / 链接 / 高亮等交互强调
#   2. 警示色 WARNING    —— 仅用于危险操作警示（如驱动安装页）
# 二者之外一律使用中性色（黑 / 白 / 灰及其透明叠加），不构成主题色。
class ThemeColor:
    # 主色及其亮变体（同一色相的明度变体，用于深色背景下保证对比度）
    PRIMARY = QColor(230, 0, 76)          # #E6004C 品牌品红
    PRIMARY_LIGHT = QColor(255, 95, 145)  # #FF5F91 主色亮变体（深色背景专用）
    WARNING = QColor(245, 63, 63)         # #F53F3F 警示红

    @staticmethod
    def primary(alpha: int) -> QColor:
        """主色的透明变体（同一主题色，仅透明度不同）"""
        color = QColor(ThemeColor.PRIMARY)
        color.setAlpha(alpha)
        return color

    @staticmethod
    def primary_light(alpha: int) -> QColor:
        """主色亮变体的透明形式"""
        color = QColor(ThemeColor.PRIMARY_LIGHT)
        color.setAlpha(alpha)
        return color

    @staticmethod
    def css(color: QColor) -> str:
        """转为 Qt 样式表可用的 CSS 颜色字符串（含透明度）"""
        r, g, b, a = color.getRgb()
        return f"rgba({r}, {g}, {b}, {a})"

def get_scaling_factor() -> float:
    """获取屏幕逻辑 DPI 对应的缩放因子（与主窗口 init_scaling_factor 一致）"""
    try:
        dpi = QApplication.primaryScreen().logicalDotsPerInch()
        return dpi / 96.0
    except Exception:
        return 1.0

class SettingsUtils():
    @staticmethod
    # 从GXDE设置获取窗口圆角设置；若获取失败或非GXDE则默认返回8
    def get_window_radius() -> int:
        try:
            bus = dbus.SessionBus()
            obj = bus.get_object(
                "com.gxde.daemon.personalization",
                "/com/gxde/daemon/personalization"
            )
            interface = dbus.Interface(obj, dbus_interface="com.gxde.daemon.personalization")
            resultGen = int(interface.Radius())
            print(f"GetWindowRadius: Captured window radius: {resultGen}.")
            return resultGen
        
        except Exception as e:
            print(f"D-Bus service: Failed to capture window radius: {e}")
            print(f"GetWindowRadius: As a result, 8 is returned as radius.")
            return 8

# 标题栏按钮类型
class TitleBarBtnType(Enum):
    MINIMIZE = 0
    MAXIMIZE = 1
    CLOSE = 2
    MENU = 3

# 标题栏按钮（最大化、最小化、关闭、菜单）
class TitleBarBtns(QWidget):
    _ICON_PREFIX = {
        TitleBarBtnType.MINIMIZE: "minimize",
        TitleBarBtnType.MAXIMIZE: "maximize",
        TitleBarBtnType.CLOSE: "close",
        TitleBarBtnType.MENU: "menu",
    }

    clicked = pyqtSignal()

    def __init__(self, parent=None, btnType=TitleBarBtnType.CLOSE):
        super().__init__(parent)
        self.parent = parent
        self.btnType = btnType
        self._menu = None

        # 初始化缩放因子
        self.scaling_factor = parent.scaling_factor if hasattr(parent, 'scaling_factor') else 1.0

        # 绘制局部
        self.setFixedSize(self.scaled(40), self.scaled(40))
        self.layoutGen = QHBoxLayout(self)
        self.layoutGen.setContentsMargins(0, 0, 0, 0)
        
        self.btn = QToolButton(self)
        self.btn.setAutoRaise(True)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setStyleSheet("QToolButton { border: none; background: transparent; }")
        self.layoutGen.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignCenter)

        self.btn.setFixedSize(self.scaled(40), self.scaled(40))
        self.btn.setIconSize(QSize(self.scaled(40), self.scaled(40)))

        # 状态跟踪，用以切换 default / hover / pressed 图标
        self._hovered = False
        self._pressed = False
        self.btn.installEventFilter(self)

        self._refresh_icon()

        # 系统主题切换时刷新图标
        QApplication.styleHints().colorSchemeChanged.connect(self._refresh_icon)

        # 行为绑定
        self.btn.clicked.connect(self._on_clicked)

    def scaled(self, value):
        return int(value * self.scaling_factor)

    def _is_dark(self) -> bool:
        return self.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def _icon_path(self, state: str) -> str:
        prefix = self._ICON_PREFIX[self.btnType]
        if (self.btnType == TitleBarBtnType.MAXIMIZE
                and self.window().isMaximized()):
            prefix = "unmaximize"
        theme = "dark" if self._is_dark() else "light"
        suffix = f"_{state}_{theme}" if state else f"_{theme}"
        filename = f"{prefix}{suffix}.svg"
        for base in (
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons"),
            "/usr/share/gxde-hardware-viewer/icons",
        ):
            path = os.path.join(base, filename)
            if os.path.exists(path):
                return path
        return ""

    def _refresh_icon(self):
        if self._pressed:
            state = "pressed"
        elif self._hovered:
            state = "hover"
        else:
            state = ""
        path = self._icon_path(state)
        if path:
            self.btn.setIcon(QIcon(path))
        self.update()

    def paintEvent(self, event):
        if self._pressed:
            bg = QColor(0, 0, 0, 25) if self._is_dark() else QColor(52, 52, 75, 25)
        elif self._hovered:
            bg = QColor(255, 255, 255, 38) if self._is_dark() else QColor(99, 99, 129, 25)
        else:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 关闭按钮位于标题栏右上角，需匹配窗口圆角
        if self.btnType == TitleBarBtnType.CLOSE:
            radius = SettingsUtils().get_window_radius()
            rect = QRectF(self.rect())
            path = QPainterPath()
            if radius > 0:
                path.moveTo(rect.left(), rect.top())
                path.lineTo(rect.right() - radius, rect.top())
                path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
                path.lineTo(rect.right(), rect.bottom())
                path.lineTo(rect.left(), rect.bottom())
                path.closeSubpath()
            else:
                path.addRect(rect)
            painter.fillPath(path, bg)
        else:
            painter.fillRect(self.rect(), bg)

    def eventFilter(self, obj, event):
        if obj is self.btn:
            t = event.type()
            if t == QEvent.Type.Enter:
                self._hovered = True
                self._refresh_icon()
            elif t == QEvent.Type.Leave:
                self._hovered = False
                self._pressed = False
                self._refresh_icon()
            elif t == QEvent.Type.MouseButtonPress:
                self._pressed = True
                self._refresh_icon()
            elif t == QEvent.Type.MouseButtonRelease:
                self._pressed = False
                self._refresh_icon()
        return super().eventFilter(obj, event)

    def setMenu(self, menu):
        self._menu = menu

    def menu(self):
        return self._menu

    def _on_clicked(self):
        win = self.window()
        if self.btnType == TitleBarBtnType.MINIMIZE:
            win.showMinimized()
        elif self.btnType == TitleBarBtnType.MAXIMIZE:
            if win.isMaximized():
                win.showNormal()
            else:
                win.showMaximized()
            self._refresh_icon()
        elif self.btnType == TitleBarBtnType.CLOSE:
            win.close()
        elif self.btnType == TitleBarBtnType.MENU:
            if self._menu is not None:
                pos = self.mapToGlobal(QPoint(0, self.height()))
                self._menu.exec(pos)
            self.clicked.emit()



class GXDETitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        
        # 初始化缩放因子
        self.scaling_factor = parent.scaling_factor if hasattr(parent, 'scaling_factor') else 1.0
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(
            self.scaled(8), self.scaled(4), 
            self.scaled(8), self.scaled(4)
        )
        self.layout.setSpacing(self.scaled(8))

        # 1. 设置标题栏布局
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(self.scaled(15))

        self.titleBarInnerLayout = QHBoxLayout(self)
        self.titleBarInnerLayout.setContentsMargins(self.scaled(12), self.scaled(8), self.scaled(12), self.scaled(8))
        self.layout.addLayout(self.titleBarInnerLayout)

        # 1.1 设定标题栏颜色
        self.lightBg = QColor("#FBFBFB")
        self.DarkBg = QColor("#050505")
        self.lightBorder = QColor(0, 0, 0, 25)
        self.darkBorder = QColor(255, 255, 255, 50)


        # 1.2 标题栏高度对齐文件管理器
        self.setFixedHeight(self.scaled(40))
        
        # 2. 左侧：窗口标题标签
        app_icon = QIcon("/usr/share/gxde-hardware-viewer/icons/gxde-hardware-viewer.svg")
        icon_size = self.scaled(24)
        icon_pixmap = app_icon.pixmap(icon_size, icon_size)

        self.title_icon_label = QLabel()
        self.title_icon_label.setPixmap(icon_pixmap)
        self.title_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_icon_label.setFixedSize(self.scaled(24), self.scaled(24))
        self.titleBarInnerLayout.addWidget(self.title_icon_label)
        self.titleBarInnerLayout.addStretch()
        
        # 3. 右侧：菜单按钮
        self.titleBarBtnLayout = QHBoxLayout()
        self.titleBarBtnLayout.setContentsMargins(0, 0, 0, 0)
        self.titleBarBtnLayout.setSpacing(0)

        self.menu_button = TitleBarBtns(self, TitleBarBtnType.MENU)
        self.titleBarBtnLayout.addWidget(self.menu_button)
        
        # 4. 右侧：窗口控制按钮
        self.min_btn = TitleBarBtns(self, TitleBarBtnType.MINIMIZE)
        self.max_btn = TitleBarBtns(self, TitleBarBtnType.MAXIMIZE)
        self.close_btn = TitleBarBtns(self, TitleBarBtnType.CLOSE)

        self.titleBarBtnLayout.addWidget(self.min_btn)
        self.titleBarBtnLayout.addWidget(self.max_btn)
        self.titleBarBtnLayout.addWidget(self.close_btn)
        self.layout.addLayout(self.titleBarBtnLayout)
        
        # 5. 绑定窗口控制按钮事件
        self.min_btn.clicked.connect(self.parent.showMinimized)
        self.max_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.parent.close)

        # 6. 允许在触屏上使用手指拖拽标题栏
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self._touch_drag_offset = None
        self._mouse_drag_start = None

    def scaled(self, value):
        """复用缩放逻辑"""
        return int(value * self.scaling_factor)

    def create_gxde_control_btn(self, text):
        """创建窗口控制按钮（最小化/最大化）"""
        btn = QPushButton(text)
        btn.setFixedSize(self.scaled(24), self.scaled(24))
        btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: {self.scaled(4)}px;
                background-color: transparent;
                font-size: {self.scaled(14)}px;
            }}
            QPushButton:hover {{
                background-color: grey;
            }}
            QPushButton:pressed {{
                color: white;
                background-color: {ThemeColor.css(ThemeColor.PRIMARY)}
            }}
        """)
        return btn 

    def toggle_maximize(self):
        """切换窗口最大化/还原"""
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()
        self.max_btn._refresh_icon()

    # 新的窗口移动实现
    # 目的是为了支持触摸屏上通过手指移动窗口
    def handleWindowMove(self):
        window = self.parent.windowHandle()
        if window is None:
            return False

        # 如果窗口处于最大化状态，先还原再移动
        if self.parent.isMaximized():
            self.parent.showNormal()
        window.startSystemMove()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_drag_start = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._mouse_drag_start is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            distance = (
                event.globalPosition().toPoint() - self._mouse_drag_start
            ).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._mouse_drag_start = None
                if self.handleWindowMove():
                    event.accept()
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_drag_start = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_drag_start = None
            self.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def event(self, e):
        # 注意到触屏下似乎无法正确驱动 startSystemMove
        # 现在手动trace触摸点位置，通过move()更新坐标得了
        et = e.type()
        if et == QEvent.Type.TouchBegin:
            pts = e.points()
            if pts:
                local_pos = pts[0].position().toPoint()
                # 标题栏按钮不应该响应拖拽，不然点不动
                if self.childAt(local_pos) is not None:
                    return super().event(e)
                if self.parent.isMaximized():
                    self.parent.showNormal()

                global_pos = pts[0].globalPosition().toPoint()
                self._touch_drag_offset = global_pos - self.parent.frameGeometry().topLeft()
                e.accept()
                return True

        elif et == QEvent.Type.TouchUpdate:
            if self._touch_drag_offset is not None:
                pts = e.points()
                if pts:
                    global_pos = pts[0].globalPosition().toPoint()
                    self.parent.move(global_pos - self._touch_drag_offset)
                e.accept()
                return True
        elif et in (QEvent.Type.TouchEnd, QEvent.Type.TouchCancel):
            if self._touch_drag_offset is not None:
                self._touch_drag_offset = None
                e.accept()
                return True
        return super().event(e)

    # 6. 重载绘制函数
    #    模仿DTK2.0时代的标题栏
    def is_dark_mode(self) -> bool:
        return self.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 处理背景色
        if self.is_dark_mode():
            bgColorGen = self.DarkBg
            borderColorGen = self.darkBorder
        else:
            bgColorGen = self.lightBg
            borderColorGen = self.lightBorder

        # 处理窗口圆角
        radius = SettingsUtils().get_window_radius()
        rect = QRectF(self.rect())
        path = QPainterPath()
        if radius > 0:
            path.moveTo(rect.left(), rect.bottom())
            path.lineTo(rect.left(), rect.top() + radius)
            path.quadTo(rect.left(), rect.top(), rect.left() + radius, rect.top())
            path.lineTo(rect.right() - radius, rect.top())
            path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
            path.lineTo(rect.right(), rect.bottom())
            path.closeSubpath()
        else:
            path.addRect(rect)

        painter.fillPath(path, bgColorGen)

        # 处理衬线
        painter.fillRect(0, self.height() - 1, self.width(), 1, borderColorGen)

class CacheManager:
    """缓存管理器"""
    def __init__(self, default_ttl=300):
        self.cache = {}
        self.default_ttl = default_ttl
    
    def get(self, key):
        """获取缓存值"""
        if key in self.cache:
            data, timestamp, ttl = self.cache[key]
            if time.time() - timestamp < ttl:
                return data
            else:
                # 缓存过期，删除
                del self.cache[key]
        return None
    
    def set(self, key, data, ttl=None):
        """设置缓存值"""
        if ttl is None:
            ttl = self.default_ttl
        self.cache[key] = (data, time.time(), ttl)
    
    def clear(self, key=None):
        """清除缓存"""
        if key:
            if key in self.cache:
                del self.cache[key]
        else:
            self.cache.clear()

def get_gxde_theme():
    """获取系统主题"""
    try:
        result = subprocess.run(
            ['gsettings', 'get', 'com.deepin.dde.appearance', 'gtk-theme'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            theme = result.stdout.strip().strip("'").strip('"')
            if 'dark' in theme.lower():
                return 'dark'
            else:
                return 'light'
    except Exception as e:
        print(f"Failed to get GXDE theme: {e}")
    return 'light'

class CentralWidget(QWidget):
    """支持背景图片和半透明遮罩的中央部件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_image_path = ""
        self.overlay_enabled = False

        self.setObjectName("centralWidget")
        self.cached_scaled_pixmap = None
        self.cached_size = None

        self.current_theme = get_gxde_theme()
        self.update_overlay_color()

    def set_background_image(self, path):
        """设置背景图片路径，传入空字符串表示清除背景"""
        self.bg_image_path = path
        self.overlay_enabled = bool(path and os.path.exists(path))
        self.cached_scaled_pixmap = None  
        self.cached_size = None
        self.update()

    def update_overlay_color(self):
        """根据当前主题设置遮罩颜色"""
        if self.current_theme == 'dark':
            self.overlay_color = QColor(0, 0, 0, 125)     
        else:
            self.overlay_color = QColor(255, 255, 255, 125)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 用窗口圆角裁剪绘制区域，实现抗锯齿圆角
        win = self.window()
        radius = win.corner_radius() if hasattr(win, 'corner_radius') else 0
        rect = QRectF(self.rect())
        path = QPainterPath()
        if radius > 0:
            path.addRoundedRect(rect, radius, radius)
        else:
            path.addRect(rect)
        painter.setClipPath(path)

        # 填充背景色
        if self.bg_image_path and os.path.exists(self.bg_image_path):
            painter.fillPath(path, self.palette().color(QPalette.ColorRole.Window))
        else:
            is_dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
            painter.fillPath(path, QColor("#202020") if is_dark else QColor("#FFFFFF"))

        if self.bg_image_path and os.path.exists(self.bg_image_path):
            # 获取当前控件的逻辑尺寸
            target_size = self.size()
            # 获取设备像素比
            dpr = self.devicePixelRatioF()
            # 检查是否需要重新缩放
            if self.cached_scaled_pixmap is None or self.cached_size != target_size:
                pixmap = QPixmap(self.bg_image_path)
                if not pixmap.isNull():
                    # 按物理像素尺寸缩放，避免模糊
                    physical_size = target_size * dpr
                    scaled = pixmap.scaled(
                        physical_size,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding, # 改为保持比例并填满
                        Qt.TransformationMode.SmoothTransformation
                    )
                    scaled.setDevicePixelRatio(dpr)
                    self.cached_scaled_pixmap = scaled
                    self.cached_size = target_size

            if self.cached_scaled_pixmap is not None:
                # 计算居中偏移量，使图片中心与控件中心对齐
                pixmap_size = self.cached_scaled_pixmap.size()
                pixmap_width = pixmap_size.width()
                pixmap_height = pixmap_size.height()
                x = (target_size.width() * dpr - pixmap_width) / 2
                y = (target_size.height() * dpr - pixmap_height) / 2
                painter.drawPixmap(int(x), int(y), self.cached_scaled_pixmap)

        # 绘制半透明遮罩层
        if self.overlay_enabled:
            painter.fillPath(path, self.overlay_color)


# Mod: 顶层透明层，负责窗体衬线
class WindowBorderOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        win = self.window()
        if hasattr(win, 'isMaximized') and (win.isMaximized() or win.isFullScreen()):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = win.corner_radius() if hasattr(win, 'corner_radius') else 0
        isDark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        borderColor = QColor(255, 255, 255, 50) if isDark else QColor(0, 0, 0, 25)
        borderRect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        borderPath = QPainterPath()
        if radius > 0:
            innerRadius = max(radius - 0.5, 0.0)
            borderPath.addRoundedRect(borderRect, innerRadius, innerRadius)
        else:
            borderPath.addRect(borderRect)
        painter.setPen(QPen(borderColor, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(borderPath)


# SideBarItem类，移植自MarcusPy827/Curly
class SideBarItem(QWidget):
    itemClicked = pyqtSignal(int)

    def __init__(self, icon_name, text, index, width_override=-1, parent=None):
        super().__init__(parent)
        self._index = index
        self._text = text
        self._icon_name = icon_name
        self._width_override = width_override if width_override > 0 else -1
        self._is_checked = False
        self._is_hovered = False

        # Mod: 窗口自定义背景启用状态
        self._bg_active = False

        # 缩放因子，与主窗口保持一致（HiDPI 适配）
        self.scaling_factor = parent.scaling_factor if hasattr(parent, 'scaling_factor') else 1.0

        # 规范：侧边栏项全应用同一高度，且随屏幕缩放
        self.setFixedHeight(self.scaled(44))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def scaled(self, value):
        return int(value * self.scaling_factor)

    def setChecked(self, is_checked):
        self._is_checked = is_checked
        self.update()

    # Mod: 通过SideBar的信号驱动，告知是否启用自定义背景图
    def setBackgroundActive(self, active):
        if self._bg_active == bool(active):
            return
        self._bg_active = bool(active)
        self.update()

    def getIndex(self):
        return self._index

    def setText(self, text):
        self._text = text
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.itemClicked.emit(self._index)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    # Mod: 渲染内置图标，而不是走XDG Icon
    def renderTintedIcon(self, size, color):
        filename = f"{self._icon_name}.svg"
        path = ""
        for base in (
            "/usr/share/gxde-hardware-viewer/icons",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons"),
        ):
            candidate = os.path.join(base, filename)
            if os.path.exists(candidate):
                path = candidate
                break
        if not path:
            return None
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return None
        data = data.replace(b"currentColor", color.name().encode("ascii"))
        dpr = self.devicePixelRatioF()
        physical = max(1, int(round(size * dpr)))
        pixmap = QPixmap()
        if not pixmap.loadFromData(data, "svg"):
            return None
        if pixmap.width() != physical or pixmap.height() != physical:
            pixmap = pixmap.scaled(
                physical, physical,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 规范：布局度量随缩放因子等比缩放，保证不同 DPI 下视觉一致
        card_rect = QRectF(self.scaled(12), self.scaled(3),
                           self.width() - self.scaled(18), self.height() - self.scaled(6))
        card_radius = self.scaled(9)
        card_path = QPainterPath()
        card_path.addRoundedRect(card_rect, card_radius, card_radius)
        icon_left = self.scaled(27)
        icon_size = self.scaled(18)
        icon_text_gap = self.scaled(9)

        is_dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 100

        # 规范：选中态仅使用主题色（主色及其透明/亮变体），不使用其他色相
        font = QFont(self.font())
        font.setPointSizeF(9 * self.scaling_factor)
        if self._is_checked:
            bg_color = ThemeColor.primary(36) if is_dark else ThemeColor.primary(25)
            border_color = ThemeColor.primary_light(70) if is_dark else ThemeColor.primary(38)
            text_color = ThemeColor.PRIMARY_LIGHT if is_dark else ThemeColor.PRIMARY
            font.setWeight(QFont.Weight.DemiBold)
        elif self._is_hovered:
            bg_color = QColor(255, 255, 255, 18) if is_dark else QColor(99, 99, 129, 14)
            border_color = QColor(0, 0, 0, 0)
            text_color = QColor(220, 220, 220) if is_dark else QColor(0, 0, 0, 204)
        else:
            # Mod: 背景图片启用时，未选中时Item底色交由SideBar负责，不再由Item自行负责
            bg_color = QColor(0, 0, 0, 0)
            border_color = QColor(0, 0, 0, 0)
            text_color = QColor(220, 220, 220) if is_dark else QColor(0, 0, 0, 204)
        painter.setFont(font)

        if bg_color.alpha() > 0:
            painter.setPen(
                QPen(border_color, 1)
                if border_color.alpha() > 0
                else Qt.PenStyle.NoPen
            )
            painter.setBrush(bg_color)
            painter.drawPath(card_path)

        icon_top = (self.height() - icon_size) // 2
        icon_rect = QRect(icon_left, icon_top, icon_size, icon_size)
        pixmap = self.renderTintedIcon(icon_size, text_color)
        if pixmap is not None:
            painter.drawPixmap(icon_rect, pixmap)

        painter.setPen(text_color)
        text_padding_left = icon_left + icon_size + icon_text_gap
        text_rect = QRect(text_padding_left, 0,
                          self.width() - text_padding_left - self.scaled(20),
                          self.height())
        fm = QFontMetrics(painter.font())
        elided = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)


# Mod: 将 CentralWidget 的窗口背景图按当前 widget 在窗口中的位置绘制到 painter
def _paint_central_bg(widget, painter):
    window = widget.window()
    if window is None:
        return False
    central = window.centralWidget() if hasattr(window, "centralWidget") else None
    if not isinstance(central, CentralWidget):
        return False
    pixmap = getattr(central, "cached_scaled_pixmap", None)
    if pixmap is None or pixmap.isNull():
        return False
    target_size = central.size()
    dpr = central.devicePixelRatioF()
    pix_w = pixmap.width()
    pix_h = pixmap.height()
    cx = (target_size.width() * dpr - pix_w) / 2
    cy = (target_size.height() * dpr - pix_h) / 2
    tl = widget.mapTo(central, QPoint(0, 0))
    painter.drawPixmap(int(cx - tl.x()), int(cy - tl.y()), pixmap)
    if getattr(central, "overlay_enabled", False):
        painter.fillRect(widget.rect(), central.overlay_color)
    return True


# SideBar类，移植自MarcusPy827/Curly
class SideBar(QWidget):
    sideBarItemClicked = pyqtSignal(int)
    # Mod: 通知Item窗体背景已被设置
    backgroundActiveChanged = pyqtSignal(bool)

    def __init__(self, item_width_override=-1, parent=None):
        super().__init__(parent)

        # 缩放因子，与主窗口保持一致（HiDPI 适配）
        self.scaling_factor = parent.scaling_factor if hasattr(parent, 'scaling_factor') else 1.0

        self._width_override = item_width_override if item_width_override > 0 else -1
        self._item_list = []
        self._bg_active = False  # Mod: 窗体背景启用状态

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(self.scaled(2))
        self._layout.setContentsMargins(0, self.scaled(8), 0, self.scaled(8))
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    def scaled(self, value):
        return int(value * self.scaling_factor)

    # Mod: SideBar加入paintEvent重载以支持在自定义背景下实现半透明侧栏
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        is_dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128

        # 处理窗口圆角
        radius = SettingsUtils().get_window_radius()
        rect = QRectF(self.rect())
        path = QPainterPath()
        if radius > 0:
            path.moveTo(rect.left(), rect.top())
            path.lineTo(rect.right(), rect.top())
            path.lineTo(rect.right(), rect.bottom())
            path.lineTo(rect.left() + radius, rect.bottom())
            path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - radius)
            path.closeSubpath()
        else:
            path.addRect(rect)

        if self._bg_active:
            painter.save()
            painter.setClipPath(path)
            _paint_central_bg(self, painter)
            overlay = QColor(37, 37, 37, 102) if is_dark else QColor(249, 249, 250, 102)
            painter.fillPath(path, overlay)
            painter.restore()
        else:
            color = QColor("#222222") if is_dark else QColor("#FDFDFD")
            painter.fillPath(path, color)

        # 处理衬线
        borderColor = QColor(255, 255, 255, 50) if is_dark else QColor(0, 0, 0, 25)
        painter.fillRect(self.width() - 1, 0, 1, self.height(), borderColor)

        super().paintEvent(event)

    # Mod: 启用/关闭窗口背景模式，刷新自身和所有子Item
    def setBackgroundActive(self, active):
        active = bool(active)
        if self._bg_active == active:
            return
        self._bg_active = active
        self.update()
        self.backgroundActiveChanged.emit(active)

    def isBackgroundActive(self):
        return self._bg_active

    def addItem(self, icon_name, text, index):
        item = SideBarItem(icon_name, text, index, self._width_override, self)
        self._item_list.append(item)
        self._layout.addWidget(item)
        item.itemClicked.connect(lambda i, it=item: self._on_item_clicked(i, it))
        # Mod：设置状态跟随
        self.backgroundActiveChanged.connect(item.setBackgroundActive)
        item.setBackgroundActive(self._bg_active)

    def _on_item_clicked(self, index, item):
        self.setCurrentItem(item)
        self.sideBarItemClicked.emit(index)

    def setCurrentItem(self, item):
        for it in self._item_list:
            it.setChecked(it is item)

    def setCurrentIndex(self, index):
        for it in self._item_list:
            it.setChecked(it.getIndex() == index)

    def item(self, index):
        for it in self._item_list:
            if it.getIndex() == index:
                return it
        return None


class HardwareManager(QMainWindow):
    # 窗体阴影
    _SHADOW_RADIUS = 40
    _SHADOW_OFFSET = QPoint(0, 10)
    _SHADOW_BORDER = 1
    _SHADOW_ACTIVE_COLOR = QColor(0, 0, 0, int(255 * 0.30))
    _SHADOW_INACTIVE_COLOR = QColor(0, 0, 0, int(255 * 0.15))
    # 窗口边缘可拖拽调整大小的区域宽度（像素）
    _RESIZE_MARGIN = 8

    def __init__(self):
        super().__init__()
    
        # 初始化变量
        self.cache = CacheManager()
        self.translator = QTranslator(self)
        self.current_lang = "en"
        self.net_io_labels = {}
        self.disk_io_labels = {}
        # 主板信息读取器（独立库，带缓存）
        self.board_info_reader = BoardInfo() if BoardInfo is not None else None
        # 光驱信息读取器（独立库，带缓存）
        self.cdrom_reader = CdromInfo() if CdromInfo is not None else None
        # 处理器信息读取器（独立库，带缓存）
        self.cpu_reader = CpuInfo() if CpuInfo is not None else None
    
        # 初始化缩放因子
        self.init_scaling_factor()

        self.table_style = f"""
            QTableWidget {{
                gridline-color: palette(mid);
                selection-background-color: palette(highlight);
                selection-color: palette(highlighted-text);
                background-color: palette(base);
                color: palette(text);
                font-size: {self.scaled(12)}px;
                border: 1px solid palette(dark);
                border-radius: {self.scaled(4)}px;
            }}
            QHeaderView::section {{
                background-color: palette(window);
                color: palette(text);
                padding: {self.scaled(8)}px;
                border: 1px solid palette(dark);
                border-bottom: 2px solid palette(highlight);
                font-weight: bold;
                font-size: {self.scaled(12)}px;
            }}
            QTableWidget::item {{
                padding: {self.scaled(6)}px;
                border-bottom: 1px solid palette(alternate-base);
                color: palette(text);
                background-color: transparent;
            }}
            QTableWidget::item:selected {{
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }}
            QTableWidget::item:alternate {{
                background-color: palette(alternate-base);
            }}
            /* 确保在深色主题下有足够的对比度 */
            QTableWidget::item:hover {{
                background-color: palette(highlight).lighter(120);
            }}
        """
    
        # 创建用户界面
        self.initUI()

        # 启用鼠标拖拽窗口边缘/角落调整大小
        self.init_window_resize()
    
        # 启动硬件监控
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(2000)
        self.monitor_timer.timeout.connect(self.update_hardware_info)
        self.monitor_timer.start()

        settings = QSettings("GXDE", "HardwareViewer")
        saved_path = settings.value("background/image_path", "")
        if saved_path:
            self.apply_background_image(saved_path)

    def init_scaling_factor(self):
        """初始化缩放因子，用于适配不同分辨率"""
        self.scaling_factor = 1.0
        try:
            # 获取屏幕逻辑DPI
            screen = QApplication.primaryScreen()
            dpi = screen.logicalDotsPerInch()

            self.scaling_factor = dpi / 96.0
        except:
            self.scaling_factor = 1.0
            
    def scaled(self, value):
        """根据缩放因子缩放数值"""
        return int(value * self.scaling_factor)

    def corner_radius(self):
        """读取GXDE设置中的窗口圆角半径，最大化时则返回0"""
        if self.isMaximized() or self.isFullScreen():
            return 0
        return SettingsUtils().get_window_radius()

    def _normal_shadow_margins(self):
        extent = self._SHADOW_RADIUS + self._SHADOW_BORDER
        return (
            extent - self._SHADOW_OFFSET.x(),
            extent - self._SHADOW_OFFSET.y(),
            extent + self._SHADOW_OFFSET.x(),
            extent + self._SHADOW_OFFSET.y(),
        )

    def _update_window_shadow(self):
        effect = getattr(self, 'window_shadow', None)
        maximized = self.isMaximized() or self.isFullScreen()

        if maximized:
            self.setContentsMargins(0, 0, 0, 0)
            if effect is not None:
                effect.setEnabled(False)
            return

        self.setContentsMargins(*self._normal_shadow_margins())
        if effect is not None:
            effect.setColor(
                self._SHADOW_ACTIVE_COLOR
                if self.isActiveWindow()
                else self._SHADOW_INACTIVE_COLOR
            )
            effect.setEnabled(True)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_window_shadow()
            title_bar = getattr(self, 'gxde_title_bar', None)
            if title_bar is not None:
                title_bar.max_btn._refresh_icon()
            self.update()
            for w in (getattr(self, 'gxde_title_bar', None),
                      getattr(self, 'sidebar', None),
                      getattr(self, 'border_overlay', None),
                      self.centralWidget()):
                if w is not None:
                    w.update()
        elif event.type() == QEvent.Type.ActivationChange:
            self._update_window_shadow()
        super().changeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Mod: 更新顶层透明层尺寸
        overlay = getattr(self, 'border_overlay', None)
        cw = self.centralWidget()
        if overlay is not None and cw is not None:
            overlay.setGeometry(cw.rect())
            overlay.raise_()

    # ---------- 鼠标拖拽调整窗口大小 ----------

    def init_window_resize(self):
        """启用通过拖拽窗口边缘/角落调整窗口大小"""
        self._resize_edge = None
        self._resize_start_geom = None
        self._resize_start_pos = None
        self._resize_cursor = None

        # 避免窗口被缩得过小
        self.setMinimumSize(self.scaled(700), self.scaled(480))

        # 定时刷新光标形状：不依赖子控件是否开启 mouseTracking
        self._resize_cursor_timer = QTimer(self)
        self._resize_cursor_timer.setInterval(100)
        self._resize_cursor_timer.timeout.connect(self.refresh_resize_cursor)
        self._resize_cursor_timer.start()

        # 全局事件过滤：捕获边缘按下与拖拽过程
        QApplication.instance().installEventFilter(self)

    def _content_global_rect(self):
        """返回中央部件（可见内容区）的全局矩形。

        窗口四周有阴影留白，检测的边缘应是内容区边界而非窗口外框。
        """
        cw = self.centralWidget()
        if cw is None:
            return self.geometry()
        return QRect(cw.mapToGlobal(QPoint(0, 0)), cw.size())

    def resize_edges_at(self, global_pos):
        """判断鼠标全局位置处于窗口哪条边缘/角落；不在可调整区域时返回 None"""
        if self.isMaximized() or self.isFullScreen() or not self.isVisible():
            return None

        rect = self._content_global_rect()
        margin = self._RESIZE_MARGIN
        x, y = global_pos.x(), global_pos.y()

        edges = Qt.Edge(0)
        if abs(x - rect.left()) <= margin:
            edges |= Qt.Edge.LeftEdge
        elif abs(x - rect.right()) <= margin:
            edges |= Qt.Edge.RightEdge
        if abs(y - rect.top()) <= margin:
            edges |= Qt.Edge.TopEdge
        elif abs(y - rect.bottom()) <= margin:
            edges |= Qt.Edge.BottomEdge
        return edges if bool(edges) else None

    @staticmethod
    def cursor_for_edges(edges):
        """根据边缘方向返回对应的调整大小光标"""
        left = bool(edges & Qt.Edge.LeftEdge)
        right = bool(edges & Qt.Edge.RightEdge)
        top = bool(edges & Qt.Edge.TopEdge)
        bottom = bool(edges & Qt.Edge.BottomEdge)
        if (left and top) or (right and bottom):
            return Qt.CursorShape.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def _is_resize_blocked_widget(self, widget):
        """标题栏按钮等交互控件不参与边缘调整大小，避免抢走点击"""
        w = widget
        while isinstance(w, QWidget):
            if isinstance(w, (QAbstractButton, TitleBarBtns)):
                return True
            # 注意：GXDETitleBar/TitleBarBtns 把 self.parent 覆盖成了属性，
            # 因此必须用 parentWidget()，不能用 parent()
            w = w.parentWidget()
        return False

    def refresh_resize_cursor(self):
        """根据当前光标位置更新调整大小光标"""
        if (not self.isActiveWindow() or self.isMaximized()
                or self.isFullScreen()):
            cursor = None
        elif self._resize_edge is not None:
            cursor = self.cursor_for_edges(self._resize_edge)
        else:
            pos = QCursor.pos()
            widget = QApplication.widgetAt(pos)
            edges = None
            if not self._is_resize_blocked_widget(widget):
                edges = self.resize_edges_at(pos)
            cursor = self.cursor_for_edges(edges) if edges is not None else None

        if cursor != self._resize_cursor:
            self._resize_cursor = cursor
            if cursor is None:
                self.unsetCursor()
            else:
                self.setCursor(cursor)

    def _is_own_widget(self, obj):
        return isinstance(obj, QWidget) and (obj is self or self.isAncestorOf(obj))

    def start_window_resize(self, edges, global_pos):
        """优先交由窗口系统处理调整大小，失败时回退到手动调整"""
        handle = self.windowHandle()
        if handle is not None and handle.startSystemResize(edges):
            return
        self._resize_edge = edges
        self._resize_start_geom = self.geometry()
        self._resize_start_pos = global_pos

    def apply_manual_resize(self, global_pos):
        """手动调整窗口尺寸（窗口系统不支持时的回退方案）"""
        edges = self._resize_edge
        geom = self._resize_start_geom
        if edges is None or geom is None:
            return

        delta = global_pos - self._resize_start_pos
        x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
        min_w = max(self.minimumWidth(), self.scaled(600))
        min_h = max(self.minimumHeight(), self.scaled(400))

        if bool(edges & Qt.Edge.LeftEdge):
            dx = min(delta.x(), geom.width() - min_w)
            x, w = geom.x() + dx, geom.width() - dx
        elif bool(edges & Qt.Edge.RightEdge):
            w = max(min_w, geom.width() + delta.x())
        if bool(edges & Qt.Edge.TopEdge):
            dy = min(delta.y(), geom.height() - min_h)
            y, h = geom.y() + dy, geom.height() - dy
        elif bool(edges & Qt.Edge.BottomEdge):
            h = max(min_h, geom.height() + delta.y())

        self.setGeometry(x, y, w, h)

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress:
            if (event.button() == Qt.MouseButton.LeftButton
                    and self.isActiveWindow() and self._is_own_widget(obj)
                    and not self._is_resize_blocked_widget(obj)):
                edges = self.resize_edges_at(event.globalPosition().toPoint())
                if edges is not None:
                    self.start_window_resize(edges, event.globalPosition().toPoint())
                    return True
        elif etype == QEvent.Type.MouseMove:
            if self._resize_edge is not None:
                self.apply_manual_resize(event.globalPosition().toPoint())
                return True
        elif etype == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._resize_edge is not None:
                self._resize_edge = None
                self._resize_start_geom = None
                self._resize_start_pos = None
                return True
        return super().eventFilter(obj, event)

    def wrap_in_scroll(self, widget):
        """将页面内容包裹进可滚动区域，避免信息过长时撑大整个窗口。

        关闭横向滚动条，仅在垂直方向内容超出时显示滚动条。
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # 禁止 scroll area 根据内容自动调整自身大小，否则仍会撑大窗口
        scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        scroll.setContentsMargins(0, 0, 0, 0)
        return scroll

    def _page_creators(self):
        """按显示顺序返回全部页面定义（key、侧边栏图标、页面构造方法）。

        侧边栏与堆栈页面的顺序、翻译刷新、定时刷新索引均以此为准。
        光驱板块在机器没有光驱时自动隐藏（见 :meth:`_cdrom_available`）。
        """
        pages = [
            ("system", "system_information", self.create_system_info_page),
            ("motherboard", "motherboard", self.create_motherboard_page),
            ("cpu", "cpu", self.create_cpu_page),
            ("memory", "ram", self.create_memory_page),
            ("storage", "rom", self.create_storage_page),
            ("network", "network", self.create_network_page),
            ("display", "display", self.create_display_page),
            ("sound", "sound", self.create_sound_page),
            ("input", "input_device", self.create_input_page),
            ("cdrom", "cdrom", self.create_cdrom_page),
            ("driver", "driver_update", self.create_driver_manage_page),
        ]
        # 机器没有光驱时隐藏光驱板块
        if not self._cdrom_available():
            pages = [p for p in pages if p[0] != "cdrom"]
        return pages

    def _cdrom_available(self):
        """判断机器是否存在光驱（读取逻辑见独立库 hardware_info/cdrom_info.py）。"""
        if self.cdrom_reader is None:
            return False
        try:
            return bool(self.get_cdrom_info().get("devices"))
        except Exception:
            return False

    def _sidebar_titles(self):
        """侧边栏各页面的标题（key 对应 _page_creators）。"""
        return {
            "system": self.tr("System"),
            "motherboard": self.tr("Motherboard"),
            "cpu": self.tr("CPU"),
            "memory": self.tr("Memory"),
            "storage": self.tr("Storage"),
            "network": self.tr("Network"),
            "display": self.tr("Display"),
            "sound": self.tr("Sound"),
            "input": self.tr("Input Devices"),
            "cdrom": self.tr("Optical Drive"),
            "driver": self.tr("Driver Manage"),
        }

    def initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setWindowTitle(self.tr("GXDE Hardware Manager"))
        shadow_left, shadow_top, shadow_right, shadow_bottom = self._normal_shadow_margins()
        self.setContentsMargins(shadow_left, shadow_top, shadow_right, shadow_bottom)
        self.resize(
            self.scaled(900) + shadow_left + shadow_right,
            self.scaled(600) + shadow_top + shadow_bottom,
        )
    
        # 创建中心部件
        central_widget = CentralWidget()
        self.setCentralWidget(central_widget)

        self.window_shadow = QGraphicsDropShadowEffect(self)
        self.window_shadow.setBlurRadius(self._SHADOW_RADIUS)
        self.window_shadow.setOffset(
            self._SHADOW_OFFSET.x(), self._SHADOW_OFFSET.y()
        )
        self.window_shadow.setColor(self._SHADOW_INACTIVE_COLOR)
        central_widget.setGraphicsEffect(self.window_shadow)
    
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

    
        # 1. 创建并添加标题栏
        self.gxde_title_bar = GXDETitleBar(self)
        main_layout.addWidget(self.gxde_title_bar)
    
        # 2. 创建内容区域
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
    
        # 3. 创建侧边栏
        sidebar_width = self.scaled(200)
        self.sidebar = SideBar(sidebar_width, self)
        self.sidebar.setFixedWidth(sidebar_width)

        # 4. 添加侧边栏项目
        for key, icon_name, _creator in self._page_creators():
            self.add_sidebar_item(self._sidebar_titles()[key], icon_name)

        # 5. 创建主内容区域
        self.stack = QStackedWidget()

        # 6. 添加所有页面（包裹滚动区域，信息过长时出现垂直滚动条）
        for _key, _icon_name, creator in self._page_creators():
            self.stack.addWidget(self.wrap_in_scroll(creator()))
    
        # 7. 将侧边栏和堆栈窗口添加到内容布局
        content_layout.addWidget(self.sidebar)
        content_layout.addWidget(self.stack, 1)
    
        # 8. 将内容区域添加到主布局
        main_layout.addWidget(content_widget, 1)
    
        # 9. 连接信号
        self.sidebar.sideBarItemClicked.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentIndex(0)
        self.stack.setCurrentIndex(0)
    
        # 10. 设置菜单
        self.menu = QMenu()
        export_action = self.menu.addAction(self.tr("Export all information to desktop"))
        export_action.triggered.connect(self.export_all_info)
        background_action = self.menu.addAction(self.tr("Set Background Image"))
        background_action.triggered.connect(self.choose_background_image)
        remove_background_action = self.menu.addAction(self.tr("Remove Background"))
        remove_background_action.triggered.connect(self.remove_background_image)
        about_action = self.menu.addAction(self.tr("About"))
        about_action.triggered.connect(self.show_about)
        self.gxde_title_bar.menu_button.setMenu(self.menu)
    
        # 11. 应用字体缩放
        self.apply_font_scaling()
    
        # 12. 设置文本选择功能
        self.setup_text_selection()

        # Mod: 顶层透明层，负责窗体衬线，包住整个窗口
        self.border_overlay = WindowBorderOverlay(central_widget)
        self.border_overlay.setGeometry(central_widget.rect())
        self.border_overlay.raise_()
        self.border_overlay.show()

    def setup_text_selection(self):
        """设置文本选中复制功能"""
        for widget in self.findChildren(QLabel):
            if not isinstance(widget, (QProgressBar, QPushButton)):
                widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                widget.setCursor(Qt.CursorShape.IBeamCursor)
    
        for table in self.findChildren(QTableWidget):
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
            table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            table.customContextMenuRequested.connect(self.show_table_context_menu)

    def show_table_context_menu(self, pos):
        """显示表格右键菜单"""
        table = self.sender()
        if not table:
            return
    
        # 创建右键菜单
        menu = QMenu(self)
    
        # 添加复制选项
        copy_action = menu.addAction(self.tr("Copy"))
        copy_action.triggered.connect(lambda: self.copy_table_content(table))
    
        # 只有在有选中内容时才显示菜单
        if table.selectedItems():
            menu.exec(table.viewport().mapToGlobal(pos))

    def copy_table_content(self, table):
        """复制表格选中内容"""
        selected_items = table.selectedItems()
        if not selected_items:
            return
    
        # 获取选中的行和列范围
        rows = sorted(set(item.row() for item in selected_items))
        cols = sorted(set(item.column() for item in selected_items))
    
        # 构建复制的文本
        text = ""
        for row in rows:
            row_data = []
            for col in cols:
                item = table.item(row, col)
                if item:
                    row_data.append(item.text())
            text += "\t".join(row_data) + "\n"
    
        # 复制到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(text.strip())

    def switch_language(self, lang):
        """切换应用语言"""
        if self.current_lang == lang:
            return
        
        self.current_lang = lang
        # 移除现有翻译
        QCoreApplication.removeTranslator(self.translator)
    
        # 加载对应语言文件
        if lang == "zh":
            if self.translator.load("zh_CN", f"{programPath}/../share/gxde-hardware-viewer/translations/gxde-hardware-viewer_zh_CN.qm"):
                QCoreApplication.installTranslator(self.translator)
        else:  # 中文
            QCoreApplication.removeTranslator(self.translator)
    
        # 重新翻译所有界面元素
        self.retranslate_ui()

    def retranslate_ui(self):
        """重新翻译所有界面文本"""
        # 清除缓存
        self.cache.clear()

        # 侧边栏项目（顺序与 _page_creators 一致）
        titles = self._sidebar_titles()
        for i, (key, _icon_name, _creator) in enumerate(self._page_creators()):
            self.sidebar.item(i).setText(titles[key])

        # 菜单项目
        menu = self.gxde_title_bar.menu_button.menu()
        actions = menu.actions()
        if len(actions) >= 4:
            actions[0].setText(self.tr("Export all information to desktop"))
            actions[1].setText(self.tr("Set Background Image"))
            actions[2].setText(self.tr("Remove Background"))
            actions[3].setText(self.tr("About"))

        # 重新创建所有页面（更新翻译后刷新页面）
        self.refresh_all_pages()

    def refresh_all_pages(self):
        """刷新所有页面以更新翻译"""
        current_index = self.stack.currentIndex()

        while self.stack.count() > 0:
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()

        # 重新添加所有页面（顺序与 initUI 一致）
        for _key, _icon_name, creator in self._page_creators():
            self.stack.addWidget(self.wrap_in_scroll(creator()))

        # 恢复之前选中的页面
        if current_index < self.stack.count():
            self.stack.setCurrentIndex(current_index)
        else:
            self.stack.setCurrentIndex(0)  # 异常时默认选中第一个

    def export_all_info(self):
        """导出所有硬件信息到桌面"""
        # 清空缓存
        self.cache.clear()

        try:
            # 收集所有硬件信息
            info = {}
            
            # 系统信息
            # uname = platform.uname()
            info[self.tr('System Information')] = {
                self.tr('System'): self.get_os_version(),
                self.tr('Host Name'): uname.node,
                self.tr("Kernel"): uname.release,
                self.tr('Architecture'): uname.machine,
                self.tr("Boot Time"): self.get_uptime()
            }
            
            # CPU信息
            cpu_freq = self.get_cpu_freq_info()
            cpu_extra = self.get_cpu_info()
            cpu_info = {
                self.tr("Processor Model"): cpu_extra.get("name") or self.get_cpu_model(),
                self._cpu_tr("Vendor"): cpu_extra.get("vendor") or self.tr("Unknown"),
                self.tr("Architecture"): cpu_extra.get("architecture") or platform.machine(),
                self.tr("Physical Cores"): cpu_extra.get("cores") or psutil.cpu_count(logical=False) or 0,
                self.tr("Logical Cores"): cpu_extra.get("logical_cpus") or psutil.cpu_count(logical=True) or 0,
                self._cpu_tr("Threads"): cpu_extra.get("threads_per_core") or self.tr("Unknown"),
                self.tr("Current Frequency"): f"{cpu_freq['current']:.2f} MHz" if cpu_freq['current'] else self.tr("Unknown"),
                self.tr("Maximum Frequency"): f"{cpu_freq['max']:.2f} MHz" if cpu_freq['max'] else self.tr("Unknown"),
                self.tr("Minimum Frequency"): f"{cpu_freq['min']:.2f} MHz" if cpu_freq['min'] else self.tr("Unknown")
            }
            # 补充 deepin-devicemanager 处理器板块的其余条目
            for label, key in [
                ("CPU Family", "cpu_family"),
                ("Model", "model"),
                ("Virtualization", "virtualization"),
                ("Flags", "flags"),
                ("Extensions", "extensions"),
                ("Stepping", "stepping"),
            ]:
                value = cpu_extra.get(key) or ""
                if value:
                    cpu_info[self._cpu_tr(label)] = value
            info[self.tr("CPU Info")] = cpu_info
            
            # 内存信息
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            info[self.tr('Memory Information')] = {
                self.tr('Total Memory'): self.format_size(mem.total),
                self.tr('Used'): self.format_size(mem.used),
                self.tr('Free'): self.format_size(mem.free),
                self.tr('Available'): self.format_size(mem.available),
                self.tr('Cache'): self.format_size(mem.total - mem.used - mem.free),
                self.tr('Memory Usage'): f"{mem.percent}%",
                self.tr('Total Swap'): self.format_size(swap.total),
                self.tr('Used Swap'): self.format_size(swap.used),
                self.tr('Free Swap'): self.format_size(swap.free),
                self.tr('Swap Usage'): f"{swap.percent}%"
            }
            
            # 磁盘信息
            disks = []
            for part in psutil.disk_partitions():
                if 'cdrom' in part.opts or part.fstype == '':
                    continue
                try:
                    disk_usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        self.tr('Device'): part.device,
                        self.tr('Mount Point'): part.mountpoint,
                        self.tr('File System'): part.fstype,
                        self.tr('Total Capacity'): self.format_size(disk_usage.total),
                        self.tr('Available Space'): self.format_size(disk_usage.free)
                    })
                except PermissionError:
                    continue
            info[self.tr('Disk Information')] = disks
            
            # 网络信息
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            network_interfaces = []
            for iface in net_if_addrs:
                # 获取IP地址
                ip_address = self.tr("Empty")
                for addr in net_if_addrs[iface]:
                    if addr.family == socket.AF_INET:
                        ip_address = addr.address
                        break
                        
                # 获取MAC地址
                mac_address = self.tr("Empty")
                for addr in net_if_addrs[iface]:
                    if hasattr(addr, 'family') and addr.family == psutil.AF_LINK:
                        mac_address = addr.address
                        break

                status = self.tr("Unknown")
                if iface in net_if_stats:
                    status = self.tr("Connected") if net_if_stats[iface].isup else self.tr("Disconnected")

                network_interfaces.append({
                    self.tr('Interface Name'): iface,
                    self.tr('IP Address'): ip_address,
                    self.tr('MAC Address'): mac_address,
                    self.tr('Status'): status
                })
            info[self.tr('Network Information')] = network_interfaces

            
            # 显示信息
            info[self.tr('Display Information')] = {
                self.tr('Graphics Card'): self.get_gpu_info(),
                self.tr('Resolution'): self.get_screen_resolution(),
                self.tr('Color Depth'): self.get_color_depth(),
                self.tr('Refresh Rate'): self.get_refresh_rate()
            }

            # 主板信息
            info[self.tr('Motherboard Information')] = self._motherboard_export_info()

            # 光驱信息（机器无光驱时不导出）
            if self._cdrom_available():
                info[self.tr('Optical Drive Information')] = self._cdrom_export_info()

            # 获取桌面路径
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.exists(desktop_path):
                desktop_path = os.path.join(os.path.expanduser("~"), "桌面")

            # 创建文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.tr('Hardware Information')}_{timestamp}.json"
            filepath = os.path.join(desktop_path, filename)

            # 写入JSON文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=4)

            # 显示成功消息
            QMessageBox.information(self, self.tr("Export Successful"), self.tr("Hardware information has been successfully exported to:\n{}").format(filepath))

        except Exception as e:
            QMessageBox.critical(self, self.tr("Export Failed"), self.tr("An error occurred while exporting hardware information:\n{}").format(str(e)))

    def _motherboard_export_info(self):
        """主板信息导出数据（与主板板块展示内容一致）"""
        export = {}
        for title, rows in self._motherboard_groups(self.get_motherboard_info()):
            export[title] = {label: value for label, value in rows}
        return export

    def _cdrom_export_info(self):
        """光驱信息导出数据（与光驱板块展示内容一致）"""
        export = {}
        info = self.get_cdrom_info()
        for index, device in enumerate(info.get("devices") or []):
            if len(info.get("devices") or []) > 1:
                title = self._cdrom_tr("Optical Drive") + (f" {index + 1}" if index else "")
            else:
                title = self._cdrom_tr("Optical Drive")
            rows = []
            for label, key in [
                ("Name", "name"),
                ("Vendor", "vendor"),
                ("Model", "model"),
                ("Version", "version"),
                ("Bus Info", "bus_info"),
                ("Capabilities", "capabilities"),
                ("Driver", "driver"),
                ("Maximum Power", "max_power"),
                ("Speed", "speed"),
            ]:
                value = device.get(key) or ""
                if value:
                    rows.append((self._cdrom_tr(label), value))
            rows.extend((self._cdrom_tr(label), value) for label, value in device.get("other") or [])
            export[title] = {label: value for label, value in rows}
        return export

    def choose_background_image(self):
        """弹出文管对话框选择背景图片"""

        settings = QSettings("GXDE", "HardwareViewer")
        last_dir = settings.value("background/last_dir", os.path.expanduser("~"))
    
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Background Image"),
            last_dir,
            self.tr("Image Files (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)")
        )
    
        if file_path:
            # 保存目录
            settings.setValue("background/last_dir", os.path.dirname(file_path))
            # 保存图片路径
            settings.setValue("background/image_path", file_path)
            # 应用背景
            self.apply_background_image(file_path)

    def apply_background_image(self, path):
        """设置背景图片并保存设置"""
        if not path or not os.path.exists(path):
            return
        self.centralWidget().set_background_image(path)

        # Mod：发送信号通知SideBar背景变更
        self.sidebar.setBackgroundActive(True)

    def remove_background_image(self):
        """移除背景图片"""
        self.centralWidget().set_background_image("")

        # Mod：同步通知SideBar背景变更
        self.sidebar.setBackgroundActive(False)
        # 清除保存的设置
        settings = QSettings("GXDE", "HardwareViewer")
        settings.remove("background/image_path")
    
    def show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()
        
    def apply_font_scaling(self):
        """应用字体缩放"""
        default_font = QFont()
        default_font.setPointSizeF(default_font.pointSizeF() * self.scaling_factor)
        self.setFont(default_font)
        
    def init_timer(self):
        """初始化定时器用于实时更新信息"""
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(2000)  # 2秒更新一次
        self.monitor_timer.timeout.connect(self.update_hardware_info)
        self.monitor_timer.start()
        
    def update_hardware_info(self):
        """更新硬件信息"""
        current_index = self.stack.currentIndex()
        page_index = {key: i for i, (key, _icon_name, _creator) in enumerate(self._page_creators())}

        # 更新网络信息
        if current_index == page_index["network"]:
            self.update_network_info()

        # 更新磁盘IO信息
        if current_index == page_index["storage"]:
            self.update_disk_io_info()

        # 更新启动时间
        if current_index == page_index["system"]:
            self.update_uptime()

        # 更新分辨率信息
        if current_index == page_index["display"]:
            self.update_display_info()

        self.update_memory_info()
    
    def add_sidebar_item(self, text, icon_name):
        """添加侧边栏项目"""
        index = len(self.sidebar._item_list)
        self.sidebar.addItem(icon_name, text, index)
        
    def create_group_box(self, title, widget):
        """创建带标题的分组框"""
        group = QGroupBox(title)
        # 调整标题字体大小
        font = group.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * self.scaling_factor)
        group.setFont(font)
        
        layout = QVBoxLayout()
        # 添加内边距
        layout.setContentsMargins(self.scaled(10), self.scaled(10), self.scaled(10), self.scaled(10))
        layout.setSpacing(self.scaled(8))
        layout.addWidget(widget)
        group.setLayout(layout)
        return group

    def _create_collapsible(self, title, content_widget):
        """创建可点击展开的折叠分组。

        收起时只显示带粗略信息的标题，点击标题可展开/收起内容（隐藏而非禁用）。
        标题使用醒目的带箭头按钮，点击后箭头方向翻转。
        """
        container = QWidget()
        vlayout = QVBoxLayout(container)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(self.scaled(4))

        header = QToolButton()
        header.setText(title)
        header.setCheckable(True)
        header.setChecked(False)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        header.setArrowType(Qt.ArrowType.RightArrow)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        font = header.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * self.scaling_factor)
        header.setFont(font)
        header.setStyleSheet(
            "QToolButton { text-align: left; padding: %dpx %dpx; "
            "border: %dpx solid palette(mid); border-radius: 6px; "
            "background-color: palette(alternate-base); }"
            "QToolButton:hover { background-color: palette(highlight); "
            "color: palette(highlighted-text); }"
            % (self.scaled(10), self.scaled(12), max(1, self.scaled(1)))
        )
        content_widget.setHidden(True)

        def _toggle(checked):
            content_widget.setHidden(not checked)
            header.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

        header.toggled.connect(_toggle)
        _toggle(False)

        vlayout.addWidget(header)
        vlayout.addWidget(content_widget)
        return container

    def create_page_button(self, text):
        """创建页面标准按钮

        UI 设计规范：
        - 同类型按钮全应用仅此一种尺寸（120x32，随 DPI 缩放），绝不出现两种尺寸；
        - 仅使用主题色：主色描边/文字，悬停主色浅底，按下主色底白字。
        """
        btn = QPushButton(text)
        btn.setFixedSize(self.scaled(120), self.scaled(32))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                border: 1px solid {ThemeColor.css(ThemeColor.PRIMARY)};
                border-radius: {self.scaled(6)}px;
                padding: {self.scaled(4)}px {self.scaled(12)}px;
                background: transparent;
                color: {ThemeColor.css(ThemeColor.PRIMARY)};
            }}
            QPushButton:hover {{
                background: {ThemeColor.css(ThemeColor.primary(25))};
            }}
            QPushButton:pressed {{
                background: {ThemeColor.css(ThemeColor.PRIMARY)};
                color: white;
            }}
            QPushButton:disabled {{
                border-color: gray;
                color: gray;
            }}
        """)
        return btn

    def get_os_version(self):
        """获取操作系统版本信息"""
        cache_key = "os_version"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        name = ""
        version = ""
        try:
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if line.startswith('NAME='):
                            name = line.split('=', 1)[1].strip().strip('"')
                    elif line.startswith('VERSION='): 
                        version = line.split('=', 1)[1].strip().strip('"')
                    if name and version:
                        break
        except FileNotFoundError:
            result = self.tr("Unable to get system version")
            self.cache.set(cache_key, result, 60)
            return result
        except Exception as e:
            result = self.tr("Failed to retrieve: {}").format(str(e))
            self.cache.set(cache_key, result, 60)
            return result

        if name and version:
            result = f"{name} {version}"  
        else:
            result = self.tr("Unknown system version")

        self.cache.set(cache_key, result, 3600)  
        return result

    def get_system_codename(self):
        """读取系统代号及其中文名，返回 (代号, 中文名)，中文名可能为空字符串

        参考 dde-daemon 的 systeminfo/version.go：
        优先读取 /etc/deepin-version 中 [Addition] 分组的 Milestone，
        读取失败时回退到 /etc/lsb-release 的 DISTRIB_RELEASE。
        中文名取自同分组的 Milestone[zh_CN] 条目，不存在时为空。
        """
        cache_key = "system_codename"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        codename = ""
        cn_name = ""
        # 优先：/etc/deepin-version -> [Addition] Milestone / Milestone[zh_CN]
        try:
            config = configparser.ConfigParser(interpolation=None)
            config.read("/etc/deepin-version", encoding="utf-8")
            codename = config.get("Addition", "Milestone", fallback="").strip()
            cn_name = config.get("Addition", "Milestone[zh_CN]", fallback="").strip()
        except Exception:
            codename = ""
            cn_name = ""

        # 回退：/etc/lsb-release -> DISTRIB_RELEASE
        if not codename:
            try:
                with open("/etc/lsb-release", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("DISTRIB_RELEASE="):
                            codename = line.split("=", 1)[1].strip().strip('"').strip()
                            break
            except Exception:
                codename = ""

        result = (codename, cn_name)
        self.cache.set(cache_key, result, 3600)
        return result

    def format_system_codename(self, codename_info):
        """格式化系统代号：存在中文名时追加括号，如 Lizhi（荔枝）；否则只显示英文代号"""
        if isinstance(codename_info, tuple):
            codename, cn_name = codename_info
        else:
            codename, cn_name = codename_info, ""

        if not codename:
            return self.tr("Unknown")
        if cn_name:
            return f"{codename}（{cn_name}）"
        return codename
        
    def create_system_info_page(self):
        """创建系统信息页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 系统概览
        self.sys_info_widget = QWidget()
        sys_layout = QFormLayout()
        sys_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        sys_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sys_layout.setHorizontalSpacing(self.scaled(15))
        sys_layout.setVerticalSpacing(self.scaled(8))
        
        # 获取系统信息
        #uname = platform.uname()
        
        sys_layout.addRow(self.tr("Operating System:"), QLabel(self.get_os_version()))
        sys_layout.addRow(
            self.tr("System Codename:"),
            QLabel(self.format_system_codename(self.get_system_codename()))
        )
        sys_layout.addRow(self.tr("Hostname:"), QLabel(uname.node))
        sys_layout.addRow(self.tr("Kernel Version:"), QLabel(uname.release))
        sys_layout.addRow(self.tr("System Architecture:"), QLabel(uname.machine))
        
        # 启动时间标签
        self.uptime_label = QLabel(self.get_uptime())
        sys_layout.addRow(self.tr("Boot Time:"), self.uptime_label)
        
        self.sys_info_widget.setLayout(sys_layout)
        layout.addWidget(self.create_group_box(self.tr("System Overview"), self.sys_info_widget))
        
        # 硬件概览
        hw_info = QWidget()
        hw_layout = QFormLayout()
        hw_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        hw_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hw_layout.setHorizontalSpacing(self.scaled(15))
        hw_layout.setVerticalSpacing(self.scaled(8))
        
        # 获取硬件信息
        cpu_model = self.get_cpu_model()
        cpu_count = psutil.cpu_count(logical=False) or 0
        logical_cpu = psutil.cpu_count(logical=True) or 0
        mem_total = self.format_size(psutil.virtual_memory().total)
        
        hw_layout.addRow(self.tr("Processor:"), QLabel(self.tr("{} ({} cores {} threads)").format(cpu_model, cpu_count, logical_cpu)))
        hw_layout.addRow(self.tr("Total Memory:"), QLabel(mem_total))
        
        self.disk_list_label = QLabel()
        self.disk_list_label.setWordWrap(True)
        self.disk_list_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.disk_list_label.setCursor(Qt.CursorShape.IBeamCursor)
        hw_layout.addRow(self.tr("Disks: "), self.disk_list_label)

        hw_info.setLayout(hw_layout)
        layout.addWidget(self.create_group_box(self.tr("Hardware Overview"), hw_info))
        
        # 内核模块信息
        kernel_modules = self.get_kernel_modules()
        modules_widget = QWidget()
        modules_layout = QVBoxLayout(modules_widget)
        
        modules_list = QLabel(kernel_modules)
        modules_list.setWordWrap(True)
        modules_layout.addWidget(modules_list)
        
        layout.addWidget(self.create_group_box(self.tr("Loaded Kernel Modules"), modules_widget))
        
        layout.addStretch()

        self.update_physical_disks_label()
        return widget

    def create_motherboard_page(self):
        """创建主板信息页面（信息口径与 deepin-devicemanager 的主板板块一致）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))

        groups = self._motherboard_groups(self.get_motherboard_info())

        if not groups:
            layout.addWidget(QLabel(self.tr("Unable to get motherboard information")))

        for title, rows in groups:
            content = QWidget()
            form_layout = QFormLayout()
            form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            form_layout.setHorizontalSpacing(self.scaled(15))
            form_layout.setVerticalSpacing(self.scaled(8))

            self._add_info_rows(form_layout, rows)

            content.setLayout(form_layout)
            layout.addWidget(self.create_group_box(title, content))

        layout.addStretch()
        return widget

    def get_motherboard_info(self):
        """获取主板 DMI 信息（读取逻辑见独立库 hardware_info/board_info.py）"""
        empty = {"available": False, "source": "", "smbios_version": "", "chipset": "", "board": None, "sections": []}
        if self.board_info_reader is None:
            return empty
        try:
            return self.board_info_reader.get_all()
        except Exception as e:
            print(f"Get motherboard info failed: {e}")
            return empty

    def _board_tr(self, text):
        """翻译主板字段名/区块名（翻译条目位于 BoardInfo 上下文）"""
        if translate_board_text is not None:
            return translate_board_text(text)
        return text

    def _motherboard_groups(self, info):
        """把主板信息整理为 [(分组标题, [(名称, 值), ...]), ...]。

        分组与字段口径和 deepin-devicemanager 主板板块一致：
        主板自身信息（制造商/版本/芯片组 + 其余可展示字段），
        以及 BIOS / 系统 / 机箱 / 内存插槽信息各区块。
        """
        groups = []
        board = info.get("board")
        if board:
            rows = []
            if board.get("vendor"):
                rows.append((self._board_tr("Vendor"), board["vendor"]))
            if board.get("version"):
                rows.append((self._board_tr("Version"), board["version"]))
            chipset = info.get("chipset") or ""
            if chipset:
                rows.append((self._board_tr("Chipset"), chipset))
            rows.extend((self._board_tr(key), value) for key, value in board.get("fields") or [])
            if rows:
                groups.append((self._board_tr(board["title"]), rows))

        for section in info.get("sections") or []:
            rows = []
            if section.get("vendor"):
                rows.append((self._board_tr("Vendor"), section["vendor"]))
            if section.get("version"):
                rows.append((self._board_tr("Version"), section["version"]))
            rows.extend((self._board_tr(key), value) for key, value in section.get("fields") or [])
            if rows:
                groups.append((self._board_tr(section["title"]), rows))
        return groups

    def _add_info_rows(self, form_layout, rows):
        """向表单布局中添加“名称: 值”行（值过长时自动换行）"""
        for label, value in rows:
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setMinimumWidth(0)
            form_layout.addRow(f"{label}:", value_label)

    def create_cpu_page(self):
        """创建CPU信息页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # CPU基本信息
        cpu_base = QWidget()
        cpu_base_layout = QFormLayout()
        cpu_base_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        cpu_base_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cpu_base_layout.setHorizontalSpacing(self.scaled(15))
        cpu_base_layout.setVerticalSpacing(self.scaled(8))
        
        # 获取CPU详细信息（名称/架构/核数优先取独立库，读不到时回退原有方式）
        info = self.get_cpu_info()
        cpu_model = info.get("name") or self.get_cpu_model()
        cpu_arch = info.get("architecture") or platform.machine()
        cpu_count = info.get("cores") or psutil.cpu_count(logical=False) or 0
        logical_cpu = info.get("logical_cpus") or psutil.cpu_count(logical=True) or 0
        
        # 处理CPU频率信息
        cpu_freq = self.get_cpu_freq_info()
        current_freq = f"{cpu_freq['current']:.2f} MHz" if cpu_freq['current'] else self.tr("Unknown")
        max_freq = f"{cpu_freq['max']:.2f} MHz" if cpu_freq['max'] else self.tr("Unknown")
        min_freq = f"{cpu_freq['min']:.2f} MHz" if cpu_freq['min'] else self.tr("Unknown")
        
        # 保存当前频率标签引用以便更新
        self.cpu_current_freq_label = QLabel(current_freq)
        
        cpu_base_layout.addRow(self.tr("Processor Model:"), QLabel(cpu_model))
        cpu_base_layout.addRow(f"{self._cpu_tr('Vendor')}:", QLabel(info.get("vendor") or self.tr("Unknown")))
        cpu_base_layout.addRow(self.tr("Architecture:"), QLabel(cpu_arch))
        cpu_base_layout.addRow(self.tr("Physical Cores:"), QLabel(str(cpu_count)))
        cpu_base_layout.addRow(self.tr("Logical Cores:"), QLabel(str(logical_cpu)))
        cpu_base_layout.addRow(f"{self._cpu_tr('Threads')}:", QLabel(info.get("threads_per_core") or self.tr("Unknown")))
        cpu_base_layout.addRow(self.tr("Current Frequency:"), self.cpu_current_freq_label)
        cpu_base_layout.addRow(self.tr("Maximum Frequency:"), QLabel(max_freq))
        cpu_base_layout.addRow(self.tr("Minimum Frequency:"), QLabel(min_freq))
        
        cpu_base.setLayout(cpu_base_layout)
        layout.addWidget(self.create_group_box(self.tr("Basic Information"), cpu_base))

        # 缓存信息（L1/L2/L3，来自 lscpu）
        cache_rows = []
        for label, key in [
            ("L1 Instruction Cache", "l1i_cache"),
            ("L1 Data Cache", "l1d_cache"),
            ("L2 Cache", "l2_cache"),
            ("L3 Cache", "l3_cache"),
        ]:
            value = info.get(key) or ""
            if value:
                cache_rows.append((self._cpu_tr(label), value))
        if cache_rows:
            cache_widget = QWidget()
            cache_layout = QFormLayout()
            cache_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            cache_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            cache_layout.setHorizontalSpacing(self.scaled(15))
            cache_layout.setVerticalSpacing(self.scaled(8))
            self._add_info_rows(cache_layout, cache_rows)
            cache_widget.setLayout(cache_layout)
            layout.addWidget(self.create_group_box(self._cpu_tr("Cache Information"), cache_widget))

        # CPU详细信息（deepin-devicemanager 处理器板块中的其余条目）
        detail_rows = []
        for label, key in [
            ("CPU Family", "cpu_family"),
            ("Model", "model"),
            ("Virtualization", "virtualization"),
            ("Flags", "flags"),
            ("Extensions", "extensions"),
            ("Stepping", "stepping"),
        ]:
            value = info.get(key) or ""
            if value:
                detail_rows.append((self._cpu_tr(label), value))
        if detail_rows:
            detail_widget = QWidget()
            detail_layout = QFormLayout()
            detail_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            detail_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            detail_layout.setHorizontalSpacing(self.scaled(15))
            detail_layout.setVerticalSpacing(self.scaled(8))
            self._add_info_rows(detail_layout, detail_rows)
            detail_widget.setLayout(detail_layout)
            layout.addWidget(self.create_group_box(self.tr("CPU Details"), detail_widget))
        
        # CPU驱动信息
        cpu_drivers = self.get_cpu_driver_info()
        driver_widget = QWidget()
        driver_layout = QFormLayout()
        driver_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        driver_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        driver_layout.setHorizontalSpacing(self.scaled(15))
        driver_layout.setVerticalSpacing(self.scaled(8))
        
        for key, value in cpu_drivers.items():
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setMinimumWidth(0)
            driver_layout.addRow(f"{key}:", value_label)
        
        driver_widget.setLayout(driver_layout)
        layout.addWidget(self.create_group_box(self.tr("CPU Driver Information"), driver_widget))

        # 各核心详细信息（大小核等异质芯片逐核完整读取；统一折叠，点击一次性展开/收起全部核心）
        per_core_info = info.get("per_core_info") or []
        if per_core_info:
            core_title = f"{self._cpu_tr('Per-core Information')} (×{logical_cpu})"
            core_inner = QWidget()
            cv = QVBoxLayout(core_inner)
            cv.setContentsMargins(self.scaled(10), self.scaled(10), self.scaled(10), self.scaled(10))
            cv.setSpacing(self.scaled(12))

            for core in per_core_info:
                head = QLabel(f"{self._cpu_tr('Logical Processor')} {core.get('processor', '')}")
                head.setStyleSheet("font-weight: bold;")
                cv.addWidget(head)

                rows = []
                if core.get("model_name"):
                    rows.append((self._cpu_tr("Core Model"), core["model_name"]))
                if core.get("cpu_family"):
                    rows.append((self._cpu_tr("CPU Family"), core["cpu_family"]))
                if core.get("model"):
                    rows.append((self._cpu_tr("Model"), core["model"]))
                if core.get("stepping"):
                    rows.append((self._cpu_tr("Stepping"), core["stepping"]))
                if core.get("vendor"):
                    rows.append((self._cpu_tr("Vendor"), core["vendor"]))
                if core.get("frequency"):
                    rows.append((self._cpu_tr("Core Frequency"), core["frequency"]))
                if core.get("extensions"):
                    rows.append((self._cpu_tr("Extensions"), core["extensions"]))
                if core.get("flags"):
                    rows.append((self._cpu_tr("Flags"), core["flags"]))
                form = QFormLayout()
                form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
                form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                form.setHorizontalSpacing(self.scaled(15))
                form.setVerticalSpacing(self.scaled(8))
                self._add_info_rows(form, rows)
                cv.addLayout(form)

            layout.addWidget(self._create_collapsible(core_title, core_inner))

        layout.addStretch()
        return widget
        
    def get_cpu_info(self):
        """获取处理器信息（读取逻辑见独立库 hardware_info/cpu_info.py）"""
        empty = {
            "available": False, "source": "",
            "name": "", "vendor": "", "architecture": "", "cpu_family": "",
            "model": "", "stepping": "", "extensions": "", "virtualization": "",
            "flags": "", "threads_per_core": "",
            "cores": None, "logical_cpus": None,
            "per_core": [], "core_types": [],
            "base": [], "other": [],
        }
        if self.cpu_reader is None:
            return empty
        try:
            return self.cpu_reader.get_all()
        except Exception as e:
            print(f"Get cpu info failed: {e}")
            return empty

    def _cpu_tr(self, text):
        """翻译处理器字段名（翻译条目位于 CpuInfo 上下文）"""
        if translate_cpu_text is not None:
            return translate_cpu_text(text)
        return text

    def create_memory_page(self):
        """创建内存信息页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))

        mem = psutil.virtual_memory() 
        swap = psutil.swap_memory()
        
        # 内存使用情况
        mem_info = QWidget()
        mem_layout = QVBoxLayout()
        mem_layout.setSpacing(self.scaled(8))
        
        # 详细内存信息
        self.mem_details = QWidget()
        mem_details_layout = QFormLayout()
        mem_details_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        mem_details_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        mem_details_layout.setHorizontalSpacing(self.scaled(15))
        mem_details_layout.setVerticalSpacing(self.scaled(8))
        
        self.mem_used_label = QLabel(self.format_size(mem.used))
        self.mem_free_label = QLabel(self.format_size(mem.free))
        self.mem_available_label = QLabel(self.format_size(mem.available))
        self.mem_cache_label = QLabel(self.format_size(mem.total - mem.used - mem.free))
        
        mem_details_layout.addRow(self.tr("Total Memory:"), QLabel(self.format_size(mem.total)))
        mem_details_layout.addRow(self.tr("Used:"), self.mem_used_label)
        mem_details_layout.addRow(self.tr("Free:"), self.mem_free_label)
        mem_details_layout.addRow(self.tr("Available:"), self.mem_available_label)
        mem_details_layout.addRow(self.tr("Cache:"), self.mem_cache_label)
        
        self.mem_details.setLayout(mem_details_layout)
        mem_layout.addWidget(self.mem_details)
        
        mem_info.setLayout(mem_layout)
        layout.addWidget(self.create_group_box(self.tr("Memory Information"), mem_info))
        
        # 内存硬件和驱动信息
        mem_hw_info = self.get_memory_hardware_info()
        mem_driver_widget = QWidget()
        mem_driver_layout = QFormLayout()
        mem_driver_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        mem_driver_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        mem_driver_layout.setHorizontalSpacing(self.scaled(15))
        mem_driver_layout.setVerticalSpacing(self.scaled(8))
        
        for key, value in mem_hw_info.items():
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setMinimumWidth(0)
            mem_driver_layout.addRow(f"{key}:", value_label)
        
        mem_driver_widget.setLayout(mem_driver_layout)
        layout.addWidget(self.create_group_box(self.tr("Memory Hardware & Drivers"), mem_driver_widget))
        
        # 交换分区信息
        swap_info = QWidget()
        swap_layout = QVBoxLayout()
        swap_layout.setSpacing(self.scaled(8))
        
        swap = psutil.swap_memory()

        # 交换分区详细信息
        self.swap_details = QWidget()
        swap_details_layout = QFormLayout()
        swap_details_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        swap_details_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        swap_details_layout.setHorizontalSpacing(self.scaled(15))
        swap_details_layout.setVerticalSpacing(self.scaled(8))
        
        self.swap_used_label = QLabel(self.format_size(swap.used))
        self.swap_free_label = QLabel(self.format_size(swap.free))
        
        swap_details_layout.addRow(self.tr("Total Swap:"), QLabel(self.format_size(swap.total)))
        swap_details_layout.addRow(self.tr("Used:"), self.swap_used_label)
        swap_details_layout.addRow(self.tr("Free:"), self.swap_free_label)
        
        self.swap_details.setLayout(swap_details_layout)
        swap_layout.addWidget(self.swap_details)
        
        swap_info.setLayout(swap_layout)
        layout.addWidget(self.create_group_box(self.tr("Swap Information"), swap_info))
        
        # zram 压缩内存信息（动态刷新）
        self.zram_container = QWidget()
        self.zram_container_layout = QVBoxLayout(self.zram_container)
        self.zram_container_layout.setSpacing(self.scaled(8))
        self.zram_container.setLayout(self.zram_container_layout)
        self.zram_table = None
        self.zram_device_count = -1
        self.update_zram_info()
        layout.addWidget(self.create_group_box(self.tr("zram Compression Memory"), self.zram_container))
        
        layout.addStretch()
        return widget
        
    def create_storage_page(self):
        """创建存储信息页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 磁盘分区信息
        disk_table = QTableWidget()
        disk_table.setColumnCount(5)
        disk_table.setHorizontalHeaderLabels([self.tr("Device"), self.tr("Mount Point"), self.tr("File System"), self.tr("Total Capacity"), self.tr("Available Space")])
        disk_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        disk_table.setAlternatingRowColors(True)                    
        disk_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)  
        disk_table.verticalHeader().setVisible(False) 

        disk_table.setStyleSheet(self.table_style)

        # 设置表头高度
        header = disk_table.horizontalHeader()
        header.setMinimumHeight(self.scaled(25))
        
        # 获取磁盘信息
        disks = psutil.disk_partitions()
        disk_table.setRowCount(len(disks))
        
        for row, part in enumerate(disks):
            # 设置行高
            disk_table.setRowHeight(row, self.scaled(25))
            
            if 'cdrom' in part.opts or part.fstype == '':
                disk_table.setItem(row, 0, QTableWidgetItem(part.device))
                disk_table.setItem(row, 1, QTableWidgetItem(part.mountpoint))
                disk_table.setItem(row, 2, QTableWidgetItem(part.fstype))
                disk_table.setItem(row, 3, QTableWidgetItem("N/A"))
                disk_table.setItem(row, 4, QTableWidgetItem("N/A"))
                continue
                
            try:
                disk_usage = psutil.disk_usage(part.mountpoint)
            except PermissionError:
                disk_table.setItem(row, 0, QTableWidgetItem(part.device))
                disk_table.setItem(row, 1, QTableWidgetItem(part.mountpoint))
                disk_table.setItem(row, 2, QTableWidgetItem(part.fstype))
                disk_table.setItem(row, 3, QTableWidgetItem(self.tr("No Permission")))
                disk_table.setItem(row, 4, QTableWidgetItem(self.tr("No Permission")))
                continue
                
            disk_table.setItem(row, 0, QTableWidgetItem(part.device))
            disk_table.setItem(row, 1, QTableWidgetItem(part.mountpoint))
            disk_table.setItem(row, 2, QTableWidgetItem(part.fstype))
            disk_table.setItem(row, 3, QTableWidgetItem(self.format_size(disk_usage.total)))
            disk_table.setItem(row, 4, QTableWidgetItem(self.format_size(disk_usage.free)))
        
        disk_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.create_group_box(self.tr("Disk Partitions"), disk_table))
        
        # 存储设备和驱动信息
        storage_devices = self.get_storage_devices_info()
        storage_driver_widget = QWidget()
        storage_driver_layout = QVBoxLayout(storage_driver_widget)
        
        storage_table = QTableWidget()
        storage_table.setColumnCount(3)
        storage_table.setHorizontalHeaderLabels([self.tr("Device Name"), self.tr("Model"), self.tr("Driver Module")])
        storage_table.setRowCount(len(storage_devices))
        storage_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        storage_table.setAlternatingRowColors(True)                    
        storage_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)  
        storage_table.verticalHeader().setVisible(False) 

        storage_table.setStyleSheet(self.table_style)
        
        for row, device in enumerate(storage_devices):
            storage_table.setRowHeight(row, self.scaled(25))
            storage_table.setItem(row, 0, QTableWidgetItem(device.get('name', self.tr(''))))
            storage_table.setItem(row, 1, QTableWidgetItem(device.get('model', self.tr('Unknown'))))
            storage_table.setItem(row, 2, QTableWidgetItem(device.get('driver', self.tr('Unknown'))))
        
        storage_table.horizontalHeader().setStretchLastSection(True)
        storage_driver_layout.addWidget(storage_table)
        
        layout.addWidget(self.create_group_box(self.tr("Storage Devices & Drivers"), storage_driver_widget))
        
        # 磁盘IO信息
        self.disk_io_widget = QWidget()
        io_layout = QFormLayout()
        io_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        io_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        io_layout.setHorizontalSpacing(self.scaled(15))
        io_layout.setVerticalSpacing(self.scaled(8))
        
        disk_io = psutil.disk_io_counters()
        self.disk_io_labels['read_count'] = QLabel(str(disk_io.read_count))
        self.disk_io_labels['write_count'] = QLabel(str(disk_io.write_count))
        self.disk_io_labels['read_bytes'] = QLabel(self.format_size(disk_io.read_bytes))
        self.disk_io_labels['write_bytes'] = QLabel(self.format_size(disk_io.write_bytes))
        
        io_layout.addRow(self.tr("Read Count:"), self.disk_io_labels['read_count'])
        io_layout.addRow(self.tr("Write Count:"), self.disk_io_labels['write_count'])
        io_layout.addRow(self.tr("Read Bytes:"), self.disk_io_labels['read_bytes'])
        io_layout.addRow(self.tr("Write Bytes:"), self.disk_io_labels['write_bytes'])

        self.disk_io_widget.setLayout(io_layout)
        layout.addWidget(self.create_group_box(self.tr("Disk I/O Statistics"), self.disk_io_widget))
        
        layout.addStretch()
        return widget
        
    def create_network_page(self):
        """创建网络信息页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 网络接口信息
        net_table = QTableWidget()
        net_table.setColumnCount(4)
        net_table.setHorizontalHeaderLabels([self.tr("Interface Name"), self.tr("IP Address"), self.tr("MAC Address"), self.tr("Status")])
        net_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        net_table.setAlternatingRowColors(True)                    
        net_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)  
        net_table.verticalHeader().setVisible(False) 

        net_table.setStyleSheet(self.table_style)

        # 设置表头高度
        header = net_table.horizontalHeader()
        header.setMinimumHeight(self.scaled(25))
        
        # 获取网络接口信息
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()
        
        net_table.setRowCount(len(net_if_addrs))
        
        for row, iface in enumerate(net_if_addrs):
            # 设置行高
            net_table.setRowHeight(row, self.scaled(25))
            
            # 获取IP地址
            ip_address = self.tr("Empty")
            for addr in net_if_addrs[iface]:
                if addr.family == socket.AF_INET:
                    ip_address = addr.address
                    break
                    
            # 获取MAC地址
            mac_address = self.tr("Empty")
            for addr in net_if_addrs[iface]:
                if hasattr(addr, 'family') and addr.family == psutil.AF_LINK:
                    mac_address = addr.address
                    break
                    
            # 获取状态
            status = self.tr("Unknown")
            if iface in net_if_stats:
                status = self.tr("Connected") if net_if_stats[iface].isup else self.tr("Disconnected")
            
            net_table.setItem(row, 0, QTableWidgetItem(iface))
            net_table.setItem(row, 1, QTableWidgetItem(ip_address))
            net_table.setItem(row, 2, QTableWidgetItem(mac_address))
            net_table.setItem(row, 3, QTableWidgetItem(status))
        
        net_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.create_group_box(self.tr("Network Interfaces"), net_table))
        
        # 网络设备和驱动信息
        net_devices = self.get_network_devices_info()
        net_driver_widget = QWidget()
        net_driver_layout = QVBoxLayout(net_driver_widget)
        
        net_driver_table = QTableWidget()
        net_driver_table.setColumnCount(3)
        net_driver_table.setHorizontalHeaderLabels([self.tr("Interface Name"), self.tr("Device Model"), self.tr("Driver Module")])
        net_driver_table.setRowCount(len(net_devices))
        net_driver_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        net_driver_table.setAlternatingRowColors(True)
        net_driver_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        net_driver_table.verticalHeader().setVisible(False)

        net_driver_table.setStyleSheet(self.table_style)
        
        for row, device in enumerate(net_devices):
            net_driver_table.setRowHeight(row, self.scaled(25))
            net_driver_table.setItem(row, 0, QTableWidgetItem(device.get('interface', self.tr('Unknown'))))
            net_driver_table.setItem(row, 1, QTableWidgetItem(device.get('model', self.tr('Unknown'))))
            net_driver_table.setItem(row, 2, QTableWidgetItem(device.get('driver', self.tr('Unknown'))))
        
        net_driver_table.horizontalHeader().setStretchLastSection(True)
        net_driver_layout.addWidget(net_driver_table)
        
        layout.addWidget(self.create_group_box(self.tr("Network Devices & Drivers"), net_driver_widget))

        # 网络流量信息
        self.net_io_widget = QWidget()
        net_io_layout = QFormLayout()
        net_io_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        net_io_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        net_io_layout.setHorizontalSpacing(self.scaled(15))
        net_io_layout.setVerticalSpacing(self.scaled(8))
        
        net_counter = psutil.net_io_counters()
        self.net_io_labels['bytes_recv'] = QLabel(self.format_size(net_counter.bytes_recv))
        self.net_io_labels['bytes_sent'] = QLabel(self.format_size(net_counter.bytes_sent))
        self.net_io_labels['packets_recv'] = QLabel(str(net_counter.packets_recv))
        self.net_io_labels['packets_sent'] = QLabel(str(net_counter.packets_sent))
        self.net_io_labels['errin'] = QLabel(str(net_counter.errin))
        self.net_io_labels['errout'] = QLabel(str(net_counter.errout))
        
        net_io_layout.addRow(self.tr("Bytes Received:"), self.net_io_labels['bytes_recv'])
        net_io_layout.addRow(self.tr("Bytes Sent:"), self.net_io_labels['bytes_sent'])
        net_io_layout.addRow(self.tr("Packets Received:"), self.net_io_labels['packets_recv'])
        net_io_layout.addRow(self.tr("Packets Sent:"), self.net_io_labels['packets_sent'])
        net_io_layout.addRow(self.tr("Receive Errors:"), self.net_io_labels['errin'])
        net_io_layout.addRow(self.tr("Transmit Errors:"), self.net_io_labels['errout'])

        self.net_io_widget.setLayout(net_io_layout)
        layout.addWidget(self.create_group_box(self.tr("Network Traffic Statistics"), self.net_io_widget))
        
        layout.addStretch()
        return widget
        
    def create_display_page(self):
        """创建显示信息页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 显示设备信息
        self.display_info = QWidget()
        display_layout = QVBoxLayout()
        display_layout.setSpacing(self.scaled(10))
        
        # 显卡信息
        gpu_info = self.get_gpu_info()
        gpu_label = QLabel(f"<b>{self.tr('Graphics Card:')}</b> {gpu_info}")
        # 允许长文本（如多显卡信息）自动换行，避免超出窗口宽度
        gpu_label.setWordWrap(True)
        gpu_label.setMinimumWidth(0)
        # 这边我把样式表去掉，统一一下字体
        display_layout.addWidget(gpu_label)
        
        # VRAM信息
        total_vram, available_vram = self.get_vram_info()
        vram_layout = QHBoxLayout()
        vram_layout.setSpacing(self.scaled(20))
        
        total_vram_label = QLabel(f"<b>{self.tr('Total VRAM:')}</b> {self.format_size(total_vram)}")
        available_vram_label = QLabel(f"<b>{self.tr('Available VRAM:')}</b> {self.format_size(available_vram)}")
        # 同上

        vram_layout.addWidget(total_vram_label)
        vram_layout.addWidget(available_vram_label)
        vram_layout.addStretch()
        display_layout.addLayout(vram_layout)
        
        self.display_info.setLayout(display_layout)
        layout.addWidget(self.create_group_box(self.tr("Graphics Information"), self.display_info))
        
        # 多屏幕信息表格
        self.screens_table = QTableWidget()
        self.screens_table.setColumnCount(4)
        self.screens_table.setHorizontalHeaderLabels([
            self.tr("Screen Name"), 
            self.tr("Resolution"), 
            self.tr("Color Depth"), 
            self.tr("Refresh Rate")
        ])
        
        # 设置表格样式 - 支持深色主题
        self.screens_table.setStyleSheet(self.table_style)
        
        # 设置表格属性
        self.screens_table.setAlternatingRowColors(True)
        self.screens_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.screens_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.screens_table.horizontalHeader().setStretchLastSection(True)
        self.screens_table.verticalHeader().setVisible(False)
        
        # 填充屏幕数据
        self.update_screens_table()
        
        layout.addWidget(self.create_group_box(self.tr("Connected Displays"), self.screens_table))
        
        # 显示驱动信息
        display_drivers = self.get_display_driver_info()
        driver_widget = QWidget()
        driver_layout = QFormLayout()
        driver_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        driver_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        driver_layout.setHorizontalSpacing(self.scaled(15))
        driver_layout.setVerticalSpacing(self.scaled(8))
        
        for key, value in display_drivers.items():
            value_label = QLabel(value)
            # 允许长文本（如 OpenGL 供应商/渲染器）自动换行，避免超出窗口宽度
            value_label.setWordWrap(True)
            value_label.setMinimumWidth(0)
            driver_layout.addRow(f"{key}:", value_label)
        
        driver_widget.setLayout(driver_layout)
        layout.addWidget(self.create_group_box(self.tr("Display Driver Information"), driver_widget))
        
        layout.addStretch()
        return widget
        
    def create_sound_page(self):
        """创建声音设备页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 声音设备信息
        sound_info = self.get_sound_devices_info()
        sound_widget = QWidget()
        sound_layout = QVBoxLayout(sound_widget)
        sound_layout.setSpacing(self.scaled(6))
        
        # 输出设备
        label1 = QLabel(self.tr("Audio Output Devices:"))
        font = label1.font()
        font.setBold(True)
        label1.setFont(font)
        sound_layout.addWidget(label1)

        for device in sound_info.get('output', []):
            sound_layout.addWidget(QLabel(self.tr("  - {} (Driver: {})").format(device['name'], device['driver'])))
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        sound_layout.addWidget(line)
        
        # 输入设备
        label2 = QLabel(self.tr("Audio Input Devices:"))
        font = label2.font()
        font.setBold(True)
        label2.setFont(font)
        sound_layout.addWidget(label2)

        for device in sound_info.get('input', []):
            sound_layout.addWidget(QLabel(self.tr("  - {} (Driver: {})").format(device['name'], device['driver'])))

        sound_widget.setLayout(sound_layout)
        layout.addWidget(self.create_group_box(self.tr("Audio Devices & Drivers"), sound_widget))
        
        # 音频驱动信息
        audio_drivers = self.get_audio_driver_info()
        driver_widget = QWidget()
        driver_layout = QFormLayout()
        driver_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        driver_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        driver_layout.setHorizontalSpacing(self.scaled(15))
        driver_layout.setVerticalSpacing(self.scaled(8))
        
        for key, value in audio_drivers.items():
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setMinimumWidth(0)
            driver_layout.addRow(f"{key}:", value_label)
        
        driver_widget.setLayout(driver_layout)
        layout.addWidget(self.create_group_box(self.tr("Audio Driver Details"), driver_widget))
        
        layout.addStretch()
        return widget
        
    def create_input_page(self):
        """创建输入设备页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 输入设备信息
        input_devices = self.get_input_devices_info()
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setSpacing(self.scaled(6))
        
        # 键盘设备
        if input_devices.get('keyboard'):
            label1 = QLabel(self.tr("Keyboard:"))
            font = label1.font()
            font.setBold(True)
            label1.setFont(font)
            input_layout.addWidget(label1)
            
            for device in input_devices['keyboard']:
                input_layout.addWidget(QLabel(self.tr("  - {} (Driver: {})").format(device['name'], device['driver'])))
            
            line1 = QFrame()
            line1.setFrameShape(QFrame.Shape.HLine)
            line1.setFrameShadow(QFrame.Shadow.Sunken)
            input_layout.addWidget(line1)
        
        # 鼠标设备
        if input_devices.get('mouse'):
            label2 = QLabel(self.tr("Mouse:"))
            font = label2.font()
            font.setBold(True)
            label2.setFont(font)
            input_layout.addWidget(label2)

            for device in input_devices['mouse']:
                input_layout.addWidget(QLabel(self.tr("  - {} (Driver: {})").format(device['name'], device['driver'])))
            
            line2 = QFrame()
            line2.setFrameShape(QFrame.Shape.HLine)
            line2.setFrameShadow(QFrame.Shadow.Sunken)
            input_layout.addWidget(line2)
        
        # 其他输入设备
        if input_devices.get('other'):
            label3 = QLabel(self.tr("Other Input Devices:"))
            font = label3.font()
            font.setBold(True)
            label3.setFont(font)
            input_layout.addWidget(label3)
            
            for device in input_devices['other']:
                input_layout.addWidget(QLabel(self.tr("  - {} (Driver: {})").format(device['name'], device['driver'])))

        input_widget.setLayout(input_layout)
        layout.addWidget(self.create_group_box(self.tr("Input Devices & Drivers"), input_widget))
        
        layout.addStretch()
        return widget

    def create_cdrom_page(self):
        """创建光驱信息页面（信息口径与 deepin-devicemanager 的光驱板块一致）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))

        info = self.get_cdrom_info()
        devices = info.get("devices") or []

        if not devices:
            layout.addWidget(QLabel(self.tr("Unable to get optical drive information")))
            layout.addStretch()
            return widget

        for index, device in enumerate(devices):
            # 多光驱时给每个设备一个分组标题
            if len(devices) > 1:
                title = self._cdrom_tr("Optical Drive") + (f" {index + 1}" if index else "")
            else:
                title = self._cdrom_tr("Optical Drive")

            rows = []
            for label, key in [
                ("Name", "name"),
                ("Vendor", "vendor"),
                ("Model", "model"),
                ("Version", "version"),
                ("Bus Info", "bus_info"),
                ("Capabilities", "capabilities"),
                ("Driver", "driver"),
                ("Maximum Power", "max_power"),
                ("Speed", "speed"),
            ]:
                value = device.get(key) or ""
                if value:
                    rows.append((self._cdrom_tr(label), value))
            rows.extend((self._cdrom_tr(label), value) for label, value in device.get("other") or [])

            content = QWidget()
            form_layout = QFormLayout()
            form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            form_layout.setHorizontalSpacing(self.scaled(15))
            form_layout.setVerticalSpacing(self.scaled(8))

            self._add_info_rows(form_layout, rows)

            content.setLayout(form_layout)
            layout.addWidget(self.create_group_box(title, content))

        layout.addStretch()
        return widget

    def get_cdrom_info(self):
        """获取光驱信息（读取逻辑见独立库 hardware_info/cdrom_info.py）"""
        empty = {"available": False, "source": "", "devices": []}
        if self.cdrom_reader is None:
            return empty
        try:
            return self.cdrom_reader.get_all()
        except Exception as e:
            print(f"Get cdrom info failed: {e}")
            return empty

    def _cdrom_tr(self, text):
        """翻译光驱字段名/区块名（翻译条目位于 CdromInfo 上下文）"""
        if translate_cdrom_text is not None:
            return translate_cdrom_text(text)
        return text

    def create_driver_manage_page(self):
        """创建驱动管理页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        label1 = QLabel(self.tr(
            "⚠️ Warning: This feature will install or update drivers and the kernel.\n" 
            "Please make sure you know what you are doing!\n"
            "It is recommended to back up the system and data first.\n"
        ))

        # 规范：警示文字使用警示色，字号跟随全局缩放，不单独硬编码
        font = label1.font()
        font.setBold(True)
        label1.setFont(font)
        label1.setStyleSheet(f"color: {ThemeColor.css(ThemeColor.WARNING)};")        
        layout.addWidget(label1)

        label2 = QLabel(self.tr('Please select the driver you want to install or update:'))
        font = label2.font()
        font.setBold(True)
        label2.setFont(font)
        layout.addWidget(label2)

        self.list_widget = QListWidget()
        self.list_widget.addItem(self.tr("Please click the 'Check Driver' button to get available driver&driver updates."))  
        layout.addWidget(self.list_widget)

        # 规范：同类型按钮全应用同一尺寸（120x32，随缩放），绝不出现两种尺寸
        self.update_btn = self.create_page_button(self.tr("Apply"))
        self.update_btn.clicked.connect(self.perform_update)

        self.check_update_btn = self.create_page_button(self.tr("Check Driver"))
        self.check_update_btn.clicked.connect(self.on_check_updates_clicked)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.check_update_btn)
        button_layout.addWidget(self.update_btn)

        layout.addLayout(button_layout)
        layout.addStretch()
        return widget

    def on_check_updates_clicked(self):
        """禁用按钮"""
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText(self.tr("Checking..."))

        self.source_dialog = UpdateSourceProgressDialog(self)
        self.source_dialog.finished_with_error.connect(self.on_update_source_error)
        self.source_dialog.finished.connect(self.on_source_dialog_closed)  # 对话框关闭后启动检查
        self.source_dialog.open()


    def on_source_dialog_closed(self):
        # 仅在更新源成功时才继续检查驱动，否则恢复按钮状态
        if not getattr(self.source_dialog, '_succeeded', False):
            self.check_update_btn.setEnabled(True)
            self.check_update_btn.setText(self.tr("Check Driver"))
            return
        # 清理上一个尚未退出的 checker，避免线程泄漏
        if hasattr(self, 'checker') and self.checker is not None:
            if self.checker.isRunning():
                self.checker.wait(3000)
            self.checker.deleteLater()
        self.checker = DriverChecker(self)
        self.checker.finished.connect(self.on_update_check_finished)
        self.checker.start()

    def on_update_source_error(self, error_message):
        # 按钮状态由 on_source_dialog_closed 统一恢复，这里只负责提示错误
        QMessageBox.critical(self, self.tr("Error"), error_message)

    def on_update_check_finished(self, driver_list):
        """重新启用按钮"""
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText(self.tr("Check Driver"))

        # 更新列表
        self.list_widget.clear()
        if not driver_list:
            self.list_widget.addItem(self.tr("All drivers are already installed and up to date~"))
            return
        
        for pkg_name, status in driver_list:
            if status == "install":
                display_text = self.tr("[Install] {}").format(pkg_name)
            else:  # upgrade
                display_text = self.tr("[Upgrade] {}").format(pkg_name)

            item = QListWidgetItem(display_text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, pkg_name)
            self.list_widget.addItem(item)

    def perform_update(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                pkg_name = item.data(Qt.ItemDataRole.UserRole)
                if pkg_name:
                    selected.append(pkg_name)

        if not selected:
            QMessageBox.information(self, self.tr("Information"),
                                self.tr("Please select the driver or kernel first"))
            return

        self.update_btn.setEnabled(False)
        self.update_btn.setText(self.tr("Apply..."))

        dialog = ProgressDialog(selected, self)
        dialog.exec()

        self.update_btn.setEnabled(True)
        self.update_btn.setText(self.tr("Apply"))
        # 仅在安装成功时才自动重新检查，避免失败后反复弹窗
        if getattr(dialog, '_succeeded', False):
            QMessageBox.warning(
                self,
                self.tr("Restart Required"),
                self.tr(
                    "✅ Driver installation/upgrade completed successfully!\n\n"
                    "It is strongly recommended to restart your computer to ensure the new drivers and kernel take effect.\n\n"
                    "⚠️ WARNING: A system restart will close all running programs and lose any unsaved data.\n"
                    "Please save all your open documents before restarting the system."
                ),
                QMessageBox.StandardButton.Ok
            )
            self.on_check_updates_clicked()

    def update_memory_info(self):
        """更新内存信息"""
        # 更新内存详细信息
        mem = psutil.virtual_memory()
        self.mem_used_label.setText(self.format_size(mem.used))
        self.mem_free_label.setText(self.format_size(mem.free))
        self.mem_available_label.setText(self.format_size(mem.available))
        self.mem_cache_label.setText(self.format_size(mem.total - mem.used - mem.free))
        
        swap = psutil.swap_memory()
        # 更新交换分区详细信息
        self.swap_used_label.setText(self.format_size(swap.used))
        self.swap_free_label.setText(self.format_size(swap.free))
        
        # 更新 zram 压缩内存信息
        self.update_zram_info()
    
    def update_network_info(self):
        """更新网络信息"""
        if self.net_io_labels:
            net_counter = psutil.net_io_counters()
            self.net_io_labels['bytes_recv'].setText(self.format_size(net_counter.bytes_recv))
            self.net_io_labels['bytes_sent'].setText(self.format_size(net_counter.bytes_sent))
            self.net_io_labels['packets_recv'].setText(str(net_counter.packets_recv))
            self.net_io_labels['packets_sent'].setText(str(net_counter.packets_sent))
            self.net_io_labels['errin'].setText(str(net_counter.errin))
            self.net_io_labels['errout'].setText(str(net_counter.errout))
    
    def update_disk_io_info(self):
        """更新磁盘IO信息"""
        if self.disk_io_labels:
            disk_io = psutil.disk_io_counters()
            self.disk_io_labels['read_count'].setText(str(disk_io.read_count))
            self.disk_io_labels['write_count'].setText(str(disk_io.write_count))
            self.disk_io_labels['read_bytes'].setText(self.format_size(disk_io.read_bytes))
            self.disk_io_labels['write_bytes'].setText(self.format_size(disk_io.write_bytes))
    
    def update_zram_info(self):
        """更新 zram 压缩内存信息（动态刷新，每 2 秒调用一次）"""
        if not hasattr(self, 'zram_container_layout'):
            return
        
        devices = self.get_zram_info()
        layout = self.zram_container_layout
        
        # 无 zram 设备时显示提示
        if not devices:
            self.zram_device_count = 0
            self._rebuild_zram_container(layout, None)
            layout.addWidget(QLabel(self.tr("No zram device found")))
            return
        
        # 设备数量变化或表格尚未创建时重建表格结构
        if self.zram_device_count != len(devices) or self.zram_table is None:
            table = QTableWidget()
            table.setColumnCount(7)
            table.setHorizontalHeaderLabels([
                self.tr("Device"),
                self.tr("Disk Size"),
                self.tr("Algorithm"),
                self.tr("Data Size"),
                self.tr("Compressed"),
                self.tr("Memory Used"),
                self.tr("Compression Ratio"),
            ])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.verticalHeader().setVisible(False)
            table.setStyleSheet(self.table_style)
            
            header = table.horizontalHeader()
            header.setMinimumHeight(self.scaled(25))
            header.setStretchLastSection(True)
            
            table.setRowCount(len(devices))
            for row in range(len(devices)):
                table.setRowHeight(row, self.scaled(25))
            
            self._rebuild_zram_container(layout, table)
            self.zram_table = table
            self.zram_device_count = len(devices)
        
        # 仅更新单元格内容，避免重建造成闪烁
        for row, dev in enumerate(devices):
            ratio = (dev['orig_data_size'] / dev['compr_data_size']) if dev['compr_data_size'] else 0
            self.zram_table.setItem(row, 0, QTableWidgetItem(dev['name']))
            self.zram_table.setItem(row, 1, QTableWidgetItem(self.format_size(dev['disksize'])))
            self.zram_table.setItem(row, 2, QTableWidgetItem(dev['algorithm']))
            self.zram_table.setItem(row, 3, QTableWidgetItem(self.format_size(dev['orig_data_size'])))
            self.zram_table.setItem(row, 4, QTableWidgetItem(self.format_size(dev['compr_data_size'])))
            self.zram_table.setItem(row, 5, QTableWidgetItem(self.format_size(dev['mem_used_total'])))
            self.zram_table.setItem(row, 6, QTableWidgetItem(f"{ratio:.2f}x" if ratio else "-"))
    
    def _rebuild_zram_container(self, layout, new_widget):
        """清空 zram 容器布局并放入新控件"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if new_widget is not None:
            layout.addWidget(new_widget)
    
    def update_uptime(self):
        """更新系统运行时间"""
        if hasattr(self, 'uptime_label'):
            self.uptime_label.setText(self.get_uptime())
    
    def update_display_info(self):
        """更新显示信息"""
        if hasattr(self, 'screens_table'):
            self.update_screens_table()
    
    def update_screens_table(self):
        """更新屏幕信息表格"""
        try:
            # 获取屏幕数据
            resolutions = self.get_screen_resolution().split('\n')
            color_depths = self.get_color_depth().split('\n')
            refresh_rates = self.get_refresh_rate().split('\n')
            
            # 确定行数
            max_rows = max(len(resolutions), len(color_depths), len(refresh_rates))
            self.screens_table.setRowCount(max_rows)
            
            for row in range(max_rows):
                # 屏幕名称
                screen_name = ""
                if row < len(resolutions) and ':' in resolutions[row]:
                    screen_name = resolutions[row].split(':')[0].strip()
                elif row == 0:
                    screen_name = self.tr("Primary Screen")
                else:
                    screen_name = f"{self.tr('Screen')} {row + 1}"
                
                # 分辨率
                resolution = ""
                if row < len(resolutions):
                    if ':' in resolutions[row]:
                        resolution = resolutions[row].split(':', 1)[1].strip()
                    else:
                        resolution = resolutions[row].strip()
                
                # 颜色深度
                color_depth = ""
                if row < len(color_depths):
                    if ':' in color_depths[row]:
                        color_depth = color_depths[row].split(':', 1)[1].strip()
                    else:
                        color_depth = color_depths[row].strip()
                
                # 刷新率
                refresh_rate = ""
                if row < len(refresh_rates):
                    if ':' in refresh_rates[row]:
                        refresh_rate = refresh_rates[row].split(':', 1)[1].strip()
                    else:
                        refresh_rate = refresh_rates[row].strip()
                
                # 设置表格项
                self.screens_table.setItem(row, 0, QTableWidgetItem(screen_name))
                self.screens_table.setItem(row, 1, QTableWidgetItem(resolution))
                self.screens_table.setItem(row, 2, QTableWidgetItem(color_depth))
                self.screens_table.setItem(row, 3, QTableWidgetItem(refresh_rate))
            
            # 调整列宽
            self.screens_table.resizeColumnsToContents()
            self.screens_table.setColumnWidth(0, max(120, self.screens_table.columnWidth(0)))  # 屏幕名称列最小宽度
            self.screens_table.setColumnWidth(1, max(150, self.screens_table.columnWidth(1)))  # 分辨率列最小宽度
            self.screens_table.setColumnWidth(2, max(100, self.screens_table.columnWidth(2)))  # 颜色深度列最小宽度
            self.screens_table.setColumnWidth(3, max(100, self.screens_table.columnWidth(3)))  # 刷新率列最小宽度
            
        except Exception as e:
            print(f"Error updating screens table: {e}")
            # 如果出错，至少显示一个空行
            self.screens_table.setRowCount(1)
            self.screens_table.setItem(0, 0, QTableWidgetItem(self.tr("Unable to get screen information")))
            self.screens_table.setItem(0, 1, QTableWidgetItem(""))
            self.screens_table.setItem(0, 2, QTableWidgetItem(""))
            self.screens_table.setItem(0, 3, QTableWidgetItem(""))
    
    def get_cpu_model(self):
        """获取CPU型号"""
        cache_key = "cpu_model"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
            
        try:
            result = subprocess.run(
                ["/usr/libexec/dtk5/DCore/bin/deepin-os-release", "--cpu-model"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
        
            if result.returncode == 0:
                cpu_model = result.stdout.strip()
                final_result = cpu_model if cpu_model else self.tr("Unknown CPU Model")
            else:
                final_result = self.tr("Failed to retrieve: {}").format(result.stderr.strip())
            
            self.cache.set(cache_key, final_result, 3600)
            return final_result
            
        except FileNotFoundError:
            result = self.tr("Command does not exist, please check if the path is correct")
            self.cache.set(cache_key, result, 3600)
            return result
        except Exception as e:
            result = self.tr("Error getting CPU model: {}").format(str(e))
            self.cache.set(cache_key, result, 3600)
            return result

    def get_cpu_freq_info(self):
        """获取CPU频率信息（sysfs 需要 root 权限，优先通过 pkexec helper 读取）"""
        cache_key = "cpu_freq_info"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        freq = {"current": None, "min": None, "max": None}

        try:
            result = subprocess.run(
                ["gxde-hardware-viewer-helper", "cpu_freq"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and result.stdout:
                # helper 正常时只输出 JSON；这里容忍输出前后有额外提示文本
                start = result.stdout.rfind("{")
                end = result.stdout.rfind("}")
                if start != -1 and end > start:
                    data = json.loads(result.stdout[start:end + 1])
                    for key in freq:
                        value = data.get(key)
                        if isinstance(value, (int, float)):
                            freq[key] = float(value)
        except Exception:
            # helper 可能未安装、pkexec 被取消或输出异常，继续尝试 psutil 兜底
            pass

        if all(value is None for value in freq.values()):
            try:
                cpu_freq = psutil.cpu_freq()
                if cpu_freq:
                    freq["current"] = float(cpu_freq.current) if cpu_freq.current else None
                    freq["min"] = float(cpu_freq.min) if cpu_freq.min else None
                    freq["max"] = float(cpu_freq.max) if cpu_freq.max else None
            except Exception:
                pass

        self.cache.set(cache_key, freq, 10)
        return freq
    
    def get_physical_disks(self):
        """获取磁盘列表"""
        disks = []
        try:
            result = subprocess.run(
                ['lsblk', '-d', '-b', '-o', 'NAME,SIZE,TYPE,MODEL', '-n'],
                capture_output=True, text=True, check=True
            )
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.strip().split(maxsplit=3)
                if len(parts) >= 3:
                    name = parts[0]
                    size = int(parts[1])         
                    devtype = parts[2]
                    model = parts[3] if len(parts) > 3 else ''
                    if devtype == 'disk' and not name.startswith(('loop', 'ram', 'zram')):
                        disks.append({'name': name, 'size': size, 'model': model})
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
            print(f"Error running lsblk: {e}")
        return disks

    def update_physical_disks_label(self):
        """更新物理磁盘列表显示标签"""
        disks = self.get_physical_disks()
        if not disks:
            text = self.tr("No physical disks found (lsblk may not be available)")
        else:
            lines = []
            for disk in disks:
                size_str = self.format_size(disk['size'])  
                if disk['model']:
                    lines.append(f"{disk['name']} ({disk['model']}): {size_str}")
                else:
                    lines.append(f"{disk['name']}: {size_str}")
            text = "\n".join(lines)
        self.disk_list_label.setText(text)

    def get_gpu_info(self):
        """获取显卡信息"""
        cache_key = "gpu_info"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
            
        try:
            result = subprocess.run(['lspci'], capture_output=True, text=True, check=True)
            output = result.stdout
            
            gpu_lines = [line for line in output.split('\n') if 'VGA compatible controller' in line]
            
            if gpu_lines:
                gpu_info = [line.split(': ', 2)[-1] for line in gpu_lines]
                result = '; '.join(gpu_info)
            else:
                result = self.tr("Unknown graphics card (no VGA device detected)")
                
            self.cache.set(cache_key, result, 3600)
            return result
        except Exception as e:
            result = self.tr("Unknown graphics card (please ensure lspci command is available)")
            self.cache.set(cache_key, result, 3600)
            return result
    
    def get_screen_resolution(self):
        """获取屏幕分辨率"""
        try:
            # 尝试使用xrandr命令获取分辨率
            result = subprocess.run(['xrandr'], capture_output=True, text=True)
            output = result.stdout
            
            screens = []
            current_display = None
            
            for line in output.split('\n'):
                line = line.strip()
                if ' connected' in line:
                    # 找到连接的显示器
                    parts = line.split()
                    current_display = parts[0]
                elif current_display and '*' in line:
                    # 找到当前分辨率
                    parts = line.strip().split()
                    for part in parts:
                        if 'x' in part and part.replace('x', '').replace('+', '').isdigit():
                            resolution = part.split('+')[0]  # 移除+号
                            screens.append(f"{current_display}: {resolution}")
                            break
            
            if screens:
                return '\n'.join(screens)
            
            # Qt的方法备选 - 获取所有屏幕
            all_screens = []
            for i, screen in enumerate(QApplication.screens()):
                geometry = screen.geometry()
                name = screen.name() or f"Screen {i+1}"
                all_screens.append(f"{name}: {geometry.width()} x {geometry.height()}")
            
            return '\n'.join(all_screens) if all_screens else f"{QApplication.primaryScreen().geometry().width()} x {QApplication.primaryScreen().geometry().height()}"
        except Exception as e:
            print(self.tr("Failed to get resolution: {}").format(e))
            try:
                # 最后的备选方案
                screen_geometry = QApplication.primaryScreen().geometry()
                return f"{screen_geometry.width()} x {screen_geometry.height()}"
            except:
                return self.tr("Unknown resolution")
    
    def get_color_depth(self):
        """获取颜色深度"""
        try:
            # 通过xwininfo命令获取颜色深度（根窗口）
            result = subprocess.run(['xwininfo', '-root'], capture_output=True, text=True)
            output = result.stdout
            
            for line in output.split('\n'):
                if 'Depth' in line:
                    depth = line.split(':')[1].strip()
                    return self.tr("{} bits").format(depth)
            
            # 备选方案 - 尝试获取所有屏幕的颜色深度
            screens_info = []
            for i, screen in enumerate(QApplication.screens()):
                depth = screen.depth()
                name = screen.name() or f"Screen {i+1}"
                screens_info.append(f"{name}: {depth} bits")
            
            return '\n'.join(screens_info) if screens_info else self.tr("32 bits")
        except:
            return self.tr("32 bits")
    
    def get_refresh_rate(self):
        """获取刷新率"""
        try:
            # 通过xrandr命令获取刷新率
            result = subprocess.run(['xrandr'], capture_output=True, text=True)
            output = result.stdout
            
            refresh_rates = []
            current_display = None
            
            for line in output.split('\n'):
                line = line.strip()
                if ' connected' in line:
                    current_display = line.split()[0]
                elif current_display and '*' in line:
                    parts = line.strip().split()
                    for part in parts:
                        if 'Hz' in part:
                            refresh_rates.append(f"{current_display}: {part}")
                            break
            
            if refresh_rates:
                return '\n'.join(refresh_rates)
            
            # 备选方案 - Qt方法
            screens_info = []
            for i, screen in enumerate(QApplication.screens()):
                refresh = screen.refreshRate()
                name = screen.name() or f"Screen {i+1}"
                screens_info.append(f"{name}: {refresh:.1f} Hz")
            
            return '\n'.join(screens_info) if screens_info else "60 Hz"
        except:
            return "60 Hz"
    
    def get_vram_info(self):
        total = available = 0
        try:
            # 先nvidia
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.total,memory.used', '--format=csv,noheader,nounits'],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                parts = result.stdout.strip().split(',')
                if len(parts) >= 2:
                    total = int(parts[0]) * 1024 * 1024   
                    used = int(parts[1]) * 1024 * 1024
                    available = total - used
                    return total, available
        except:
            pass

        try:
            # 再尝试AMD
            with open('/sys/class/drm/card0/device/mem_info_vram_total', 'r') as f:
                total = int(f.read().strip())
            with open('/sys/class/drm/card0/device/mem_info_vram_used', 'r') as f:
                used = int(f.read().strip())
                available = total - used
                return total, available
        except:
            pass

        # 最后glxinfo
        try:
            out = subprocess.run(['glxinfo'], capture_output=True, text=True).stdout
            for line in out.splitlines():
                low = line.lower()
                if 'video memory:' in low:
                    parts = line.split(':', 1)[1].strip().split()
                    if parts:
                        total = self._convert_to_bytes(float(parts[0]), parts[1] if len(parts) > 1 else 'B')
                elif 'dedicated video memory' in low:
                    parts = line.split(':', 1)[1].strip().split()
                    if parts:
                        available = self._convert_to_bytes(float(parts[0]), parts[1] if len(parts) > 1 else 'B')
        except:
            pass

        return total, available

    def _convert_to_bytes(self, value, unit):
        unit = unit.upper()
        if unit == 'KB':
            return int(value * 1024)
        elif unit == 'MB':
            return int(value * 1024 * 1024)
        elif unit == 'GB':
            return int(value * 1024 * 1024 * 1024)
        elif unit == 'TB':
            return int(value * 1024 * 1024 * 1024 * 1024)
        else:
            return int(value)
            
    def format_size(self, size):
        """格式化字节大小为人类可读的形式"""
        if size <= 0:
            return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"
        
    def get_uptime(self):
        """获取系统运行时间"""
        try:
            uptime_seconds = psutil.boot_time()
            boot_time = datetime.fromtimestamp(uptime_seconds)
            now = datetime.now()
            delta = now - boot_time
            
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            return self.tr("{} days {} hours {} minutes").format(days, hours, minutes)
        except:
            return self.tr("Unknown")
    
    # 新增驱动和设备信息相关函数
    def get_kernel_modules(self):
        """获取加载的内核模块"""
        cache_key = "kernel_modules"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
            
        try:
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            output = result.stdout
            
            lines = output.split('\n')[1:11]
            modules = [line.split()[0] for line in lines if line.strip()]
            result = ", ".join(modules) + self.tr(" (only showing the first 10)")
            self.cache.set(cache_key, result, 300)
            return result
        except Exception as e:
            result = self.tr("Unable to get kernel module information")
            self.cache.set(cache_key, result, 60)
            return result
    

    def get_cpu_driver_info(self):
        """获取CPU驱动信息"""
        cache_key = "cpu_driver_info"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
            
        info = {}
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.strip().startswith('vendor_id'):
                        info[self.tr('Vendor')] = line.split(':')[1].strip()
                        break
            
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if line.strip().startswith('microcode'):
                            info[self.tr('Microcode Version')] = line.split(':')[1].strip()
                            break
            except:
                info[self.tr('Microcode Version')] = "Unknown"
            
            try:
                with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor', 'r') as f:
                    info[self.tr('Scheduler')] = f.read().strip()
            except:
                info[self.tr('Scheduler')] = "Unknown"
                
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            cpu_modules = [line.split()[0] for line in result.stdout.split('\n') 
                         if 'cpu' in line or 'processor' in line or 'intel' in line or 'amd' in line]
            info[self.tr('Related Driver Modules')] = ", ".join(cpu_modules[:5])
            
            self.cache.set(cache_key, info, 300)
            return info
        except Exception as e:
            info[self.tr('Driver Information')] = self.tr("Unable to retrieve")
            self.cache.set(cache_key, info, 60)
            return info
    
    def get_memory_hardware_info(self):
        """获取内存硬件信息"""
        info = {}
        try:
            # 内存控制器信息
            result = subprocess.run(['lspci'], capture_output=True, text=True)
            output = result.stdout
            mem_ctrl_lines = [line for line in output.split('\n') if 'Memory controller' in line]
            if mem_ctrl_lines:
                info[self.tr('Memory Controller')] = mem_ctrl_lines[0].split(': ', 2)[-1]
            else:
                info[self.tr('Memory Controller')] = self.tr("Unknown")
                
            # 内存类型和大小 (从dmidecode获取，需要root权限)
            try:
                result = subprocess.run(['gxde-hardware-viewer-helper', 'memory'], capture_output=True, text=True)
                output = result.stdout
                
                # 提取内存类型
                for line in output.split('\n'):
                    if 'Type:' in line and 'Unknown' not in line:
                        info[self.tr('Memory Type')] = line.split(':')[1].strip()
                        break
                
                # 提取内存速度
                for line in output.split('\n'):
                    if 'Speed:' in line and 'Unknown' not in line:
                        info[self.tr('Memory Speed')] = line.split(':')[1].strip()
                        break
            except:
                info[self.tr('Memory Type')] = self.tr("Requires root privileges to view")
                info[self.tr('Memory Speed')] = self.tr("Requires root privileges to view")
                
            # 内存驱动模块
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            mem_modules = [line.split()[0] for line in result.stdout.split('\n') 
                         if 'mem' in line or 'memory' in line or 'dram' in line]
            info[self.tr('Related Driver Modules')] = ", ".join(mem_modules[:5])
            
        except Exception as e:
            print(self.tr("Failed to get memory hardware information: {}").format(e))
            info[self.tr('Memory Information')] = self.tr("Unable to retrieve")
        
        return info
    
    def get_zram_info(self):
        """获取 zram 压缩内存设备信息（无需 root 权限，读取 sysfs）"""
        devices = []
        try:
            for dev_path in sorted(glob.glob('/sys/block/zram*')):
                dev_name = os.path.basename(dev_path)
                info = {
                    'name': dev_name,
                    'disksize': 0,
                    'algorithm': self.tr("Unknown"),
                    'orig_data_size': 0,
                    'compr_data_size': 0,
                    'mem_used_total': 0,
                }
                
                # 设备分配大小 (disksize)
                try:
                    with open(os.path.join(dev_path, 'disksize')) as f:
                        info['disksize'] = int(f.read().strip())
                except (OSError, ValueError):
                    pass
                
                # 当前压缩算法（sysfs 中以 [ ] 标记当前启用的算法）
                try:
                    with open(os.path.join(dev_path, 'comp_algorithm')) as f:
                        alg_text = f.read().strip()
                        match = re.search(r'\[([^\]]+)\]', alg_text)
                        info['algorithm'] = match.group(1) if match else (alg_text.split()[0] if alg_text else self.tr("Unknown"))
                except OSError:
                    pass
                
                # mm_stat: orig_data_size compr_data_size mem_used_total ...
                try:
                    with open(os.path.join(dev_path, 'mm_stat')) as f:
                        parts = f.read().split()
                        if len(parts) >= 3:
                            info['orig_data_size'] = int(parts[0])
                            info['compr_data_size'] = int(parts[1])
                            info['mem_used_total'] = int(parts[2])
                except OSError:
                    pass
                
                devices.append(info)
        except Exception as e:
            print(self.tr("Failed to get zram information: {}").format(e))
        
        return devices
    
    def get_storage_devices_info(self):
        """获取存储设备信息"""
        devices = []
        try:
            # 通过lsblk获取存储设备
            result = subprocess.run(['lsblk', '-o', 'NAME,TYPE,MODEL'], capture_output=True, text=True)
            output = result.stdout
            
            for line in output.split('\n')[1:]:  # 跳过表头
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] in ['disk', 'cdrom']:
                    device = {
                        'name': parts[0],
                        'model': parts[2] if len(parts) > 2 else 'Unknown'
                    }
                    
                    # 获取驱动信息
                    try:
                        with open(f'/sys/block/{parts[0]}/device/model', 'r') as f:
                            device['model'] = f.read().strip() or device['model']
                    except:
                        pass
                        
                    try:
                        with open(f'/sys/block/{parts[0]}/device/driver/module/drivers', 'r') as f:
                            driver_info = f.read().strip()
                            device['driver'] = driver_info.split('/')[-1] if driver_info else 'Unknown'
                    except:
                        device['driver'] = self.tr("Unknown")
                        
                    devices.append(device)
            
        except Exception as e:
            print(self.tr("Failed to get storage device information: {}").format(e))
            
        return devices
    
    def get_network_devices_info(self):
        """获取网络设备信息"""
        devices = []
        try:
            net_if_addrs = psutil.net_if_addrs()
        
            for iface in net_if_addrs:
                device = {'interface': iface}
            
                # 获取 MAC 地址（保留原逻辑）
                for addr in net_if_addrs[iface]:
                    if hasattr(addr, 'family') and addr.family == psutil.AF_LINK:
                        device['mac'] = addr.address
                        break
            
                # 获取驱动和型号
                driver = self.tr("Unknown")
                model = self.tr("Unknown")
                try:
                    result = subprocess.run(['ethtool', '-i', iface], capture_output=True, text=True, check=False)
                    if result.returncode == 0:
                        for line in result.stdout.splitlines():
                            if line.startswith('driver:'):
                                driver = line.split(':', 1)[1].strip()
                            elif line.startswith('bus-info:'):
                                bus_info = line.split(':', 1)[1].strip()
                                # 通过 PCI 地址查询型号
                                lspci = subprocess.run(['lspci', '-s', bus_info], capture_output=True, text=True, check=False)
                                if lspci.returncode == 0 and lspci.stdout.strip():
                                    model = lspci.stdout.split(':', 1)[1].strip()
                except (subprocess.SubprocessError, FileNotFoundError):
                    pass
            
                device['driver'] = driver
                device['model'] = model
                devices.append(device)
            
        except Exception as e:
            print(self.tr("Failed to get network device information: {}").format(e))
    
        return devices
    
    def get_display_driver_info(self):
        """获取显示驱动信息"""
        try:
            drivers = {}
            
            # 通过lspci获取显卡信息
            result = subprocess.run([r'lspci | grep -i "vga\|3d\|display"'], shell=True, capture_output=True, text=True)
            gpu_lines = result.stdout.splitlines()
            
            # 通过glxinfo获取OpenGL驱动信息（需要mesa-utils包）
            try:
                result = subprocess.run([r'glxinfo | grep "OpenGL vendor string\|OpenGL renderer string"'], 
                                       shell=True, capture_output=True, text=True)
                for line in result.stdout.splitlines():
                    if 'vendor' in line:
                        drivers[self.tr('OpenGL Vendor')] = line.split(': ')[1]
                    if 'renderer' in line:
                        drivers[self.tr('OpenGL Renderer')] = line.split(': ')[1]
            except:
                pass
            
            # 通过modinfo获取显卡驱动模块信息
            for i, line in enumerate(gpu_lines):
                parts = line.split()
                if len(parts) >= 1:
                    pci_id = parts[0]
                    try:
                        # 获取驱动模块
                        result = subprocess.run(['lspci -k -s ' + pci_id], shell=True, capture_output=True, text=True)
                        for l in result.stdout.splitlines():
                            if 'Kernel driver in use:' in l:
                                driver_name = l.split(': ')[1]
                                drivers[self.tr('Graphics Card {} Driver').format(i+1)] = driver_name
                                
                                # 获取驱动版本
                                try:
                                    if drivers.get('OpenGL Vendor') == 'NVIDIA Corporation':
                                        result = subprocess.run(['modinfo ' + driver_name + ' | grep version'], 
                                                            shell=True, capture_output=True, text=True)
                                        if result.stdout:
                                            version = result.stdout.split(': ')[1].strip()
                                            drivers[self.tr('Graphics Card {} Driver Version').format(i+1)] = version
                                    else:
                                        #uname = platform.uname()
                                        version = uname.release
                                        drivers[self.tr('Graphics Card {} Driver Version').format(i+1)] = version
                                except:
                                    pass
                    except:
                        pass
            
            if not drivers:
                drivers[self.tr('Status')] = self.tr('No display driver information detected')
                
            return drivers
        except Exception as e:
            return {self.tr('Error'): self.tr('Unable to get display driver information: {}').format(str(e))}
        
    def get_sound_devices_info(self):
        """获取声音设备信息"""
        devices = {'output': [], 'input': []}
        try:
            # 使用aplay获取输出设备
            try:
                result = subprocess.run(['aplay', '-l'], capture_output=True, text=True)
                output = result.stdout
                
                for line in output.split('\n'):
                    if 'card' in line and 'Device' in line:
                        parts = line.strip().split(': ')
                        if len(parts) >= 2:
                            device_name = parts[1]
                            driver = 'snd_hda_intel'  # 默认常见驱动
                            
                            # 尝试获取实际驱动
                            try:
                                card_id = parts[0].split()[1]
                                with open(f'/sys/class/sound/card{card_id}/device/driver/module/drivers', 'r') as f:
                                    driver_info = f.read().strip()
                                    driver = driver_info.split('/')[-1] if driver_info else driver
                            except:
                                pass
                                
                            devices['output'].append({
                                'name': device_name,
                                'driver': driver
                            })
            except:
                pass
                
            # 使用arecord获取输入设备
            try:
                result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
                output = result.stdout
                
                for line in output.split('\n'):
                    if 'card' in line and 'Device' in line:
                        parts = line.strip().split(': ')
                        if len(parts) >= 2:
                            device_name = parts[1]
                            driver = 'snd_hda_intel'  # 默认常见驱动
                            
                            # 尝试获取实际驱动
                            try:
                                card_id = parts[0].split()[1]
                                with open(f'/sys/class/sound/card{card_id}/device/driver/module/drivers', 'r') as f:
                                    driver_info = f.read().strip()
                                    driver = driver_info.split('/')[-1] if driver_info else driver
                            except:
                                pass
                                
                            devices['input'].append({
                                'name': device_name,
                                'driver': driver
                            })
            except:
                pass
                
        except Exception as e:
            print(self.tr("Failed to get audio device information: {}").format(e))
            
        # 如果没有获取到信息，使用默认值
        if not devices['output']:
            devices['output'].append({'name': self.tr('Built-in Speakers'), 'driver': 'snd_hda_intel'})
            devices['output'].append({'name': self.tr('HDMI Audio Output'), 'driver': 'snd_hda_intel'})
            
        if not devices['input']:
            devices['input'].append({'name': self.tr('Built-in Microphone'), 'driver': 'snd_hda_intel'})
            devices['input'].append({'name': self.tr('Headphone Microphone'), 'driver': 'snd_hda_intel'})
            
        return devices
    
    def get_audio_driver_info(self):
        """获取音频驱动信息"""
        info = {}
        try:
            # 音频服务
            try:
                result = subprocess.run(['pgrep', 'pulseaudio'], capture_output=True, text=True)
                if result.stdout:
                    info[self.tr('Audio Service')] = 'PulseAudio'
                else:
                    result = subprocess.run(['pgrep', 'pipewire'], capture_output=True, text=True)
                    info[self.tr('Audio Service')] = 'PipeWire' if result.stdout else self.tr('Unknown')
            except:
                info[self.tr('Audio Service')] = self.tr('Unknown')
                
            # 内核音频驱动
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            audio_modules = [line.split()[0] for line in result.stdout.split('\n') 
                           if 'snd' in line or 'audio' in line]
            info[self.tr('Kernel Audio Modules')] = ", ".join(audio_modules[:5])
            
        except Exception as e:
            print(self.tr("Failed to get audio driver information: {}").format(e))
            info[self.tr('Driver Information')] = self.tr("Unable to retrieve")
        
        return info
    
    def get_input_devices_info(self):
        """获取输入设备信息"""
        devices = {'keyboard': [], 'mouse': [], 'other': []}
        try:
            # 使用xinput列出输入设备
            result = subprocess.run(['xinput', 'list'], capture_output=True, text=True)
            output = result.stdout
            
            for line in output.split('\n'):
                if 'id=' in line and 'slave' in line:
                    # 提取设备名称
                    name = line.split('id=')[0].strip()
                    
                    # 提取设备ID
                    device_id = line.split('id=')[1].split()[0]
                    
                    # 获取驱动信息
                    driver = self.tr("Unknown")
                    try:
                        result = subprocess.run(['xinput', 'list-props', device_id], capture_output=True, text=True)
                        for prop_line in result.stdout.split('\n'):
                            if 'Device Driver' in prop_line:
                                driver = prop_line.split(':', 1)[1].strip()
                                break
                    except:
                        pass
                        
                    # 分类设备
                    if 'keyboard' in name.lower():
                        devices['keyboard'].append({'name': name, 'driver': driver})
                    elif 'mouse' in name.lower() or 'touchpad' in name.lower():
                        devices['mouse'].append({'name': name, 'driver': driver})
                    else:
                        devices['other'].append({'name': name, 'driver': driver})
            
        except Exception as e:
            print(self.tr("Failed to get input device information: {}").format(e))
            
        # 如果没有获取到信息，使用默认值
        if not devices['keyboard']:
            devices['keyboard'].append({'name': self.tr('Generic USB Keyboard'), 'driver': 'atkbd'})
            
        if not devices['mouse']:
            devices['mouse'].append({'name': self.tr('Generic USB Mouse'), 'driver': 'usbhid'})
            devices['mouse'].append({'name': self.tr('Touchpad'), 'driver': 'synaptics'})
            
        if not devices['other']:
            devices['other'].append({'name': self.tr('Webcam'), 'driver': 'uvcvideo'})
            
        return devices

class DriverChecker(QThread):
    """驱动检查"""
    finished = pyqtSignal(list)  # 传递驱动列表

    def __init__(self, hardware_manager, parent=None):
        super().__init__(parent)
        self.hardware_manager = hardware_manager

    def is_pkg_installed(self, pkg_name):
        """检查驱动是否已安装"""
        result = subprocess.run(
            ['dpkg-query', '-W', '-f=${Status}', pkg_name],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return False
        return 'install ok installed' in result.stdout

    def detect_nvidia_packages(self):
        """通过 nvidia-detect 检测推荐安装的 NVIDIA 驱动包"""
        try:
            result = subprocess.run(
                ['nvidia-detect'],
                capture_output=True, text=True, timeout=30
            )
            # 注意：nvidia-detect 在显卡仅被旧 legacy 驱动支持、且该驱动不在当前
            # Debian suite 中时（如 bookworm 下的 390 legacy），会输出提示信息但
            # 以退出码 1 结束（脚本默认 RET=1，仅找到可推荐包时才置 0）。
            # 因此不能仅凭 returncode 判定，必须解析输出内容以识别 legacy 驱动。
            output = result.stdout
            pkgs = []
            # "It is recommended to install the" 后下一行缩进输出包名
            lines = output.splitlines()
            recommend_found = False
            pkg_pattern = re.compile(r'nvidia[-\w]*driver[-\w]*')
            for i, line in enumerate(lines):
                if 'It is recommended to install' in line:
                    recommend_found = True
                    # 先尝试从当前行提取包名
                    m = pkg_pattern.search(line)
                    if m:
                        candidate = m.group(0).strip()
                        if candidate and candidate not in pkgs:
                            pkgs.append(candidate)
                        recommend_found = False
                    continue
                if recommend_found:
                    # 推荐语句下的第一行非空缩进行即为包名
                    stripped = line.strip()
                    if stripped:
                        m = pkg_pattern.search(stripped)
                        if m:
                            candidate = m.group(0).strip()
                            if candidate and candidate not in pkgs:
                                pkgs.append(candidate)
                        recommend_found = False
            # 整份输出中任何包含 nvidia-xxx-driver 的行兜底匹配
            if not pkgs:
                for line in lines:
                    for m in pkg_pattern.finditer(line):
                        candidate = m.group(0).strip()
                        # 过滤掉明显不是包名的纯描述词
                        if candidate in ('nvidia-driver',):
                            if candidate not in pkgs:
                                pkgs.append(candidate)
                            continue
                        if len(candidate) >= 10 and candidate not in pkgs:
                            pkgs.append(candidate)
            # legacy 驱动系列描述，如 "only supported by the 390 legacy drivers series"
            if not pkgs:
                legacy_match = re.search(r'only supported by the (\d+) legacy drivers series', output, re.IGNORECASE)
                if legacy_match:
                    version = legacy_match.group(1)
                    candidate = f'nvidia-legacy-{version}xx-driver'
                    if candidate not in pkgs:
                        pkgs.append(candidate)  
            return pkgs
        except FileNotFoundError:
            # 系统未安装 nvidia-detect，静默跳过
            return []
        except Exception:
            return []

    def run(self):
        try:
            # 获取可升级包列表
            result = subprocess.run(['apt', 'list', '--upgradable'],
                                    capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                self.finished.emit([])
                return
            lines = result.stdout.splitlines()
            packages = []
            pattern = re.compile(r'^(\S+)/')
            for line in lines:
                match = pattern.match(line)
                if match:
                    pkg = match.group(1)
                    packages.append(pkg)
            # 3. 过滤出驱动/内核相关的包
            keywords = ['linux', 'nvidia', 'firmware', 'microcode', 'bluez', 'broadcom']
            exclude_pkgs = ['linuxqq']
            driver_pkgs = [p for p in packages if any(k in p for k in keywords) and not any(ex in p for ex in exclude_pkgs)]
            # 新增对博通网卡的特别支持
            net_devices = self.hardware_manager.get_network_devices_info()
            broadcom_pkgs = ['broadcom-sta-dkms']
            for device in net_devices:
                model = (device.get('model') or '').lower()
                if 'broadcom' in model:
                    if 'ethernet' not in model:
                        for pkg in broadcom_pkgs:
                            if not self.is_pkg_installed(pkg) and pkg not in driver_pkgs:
                                driver_pkgs.append(pkg)
                        break
            # 新增对 NVIDIA 显卡驱动的特别支持：通过 nvidia-detect 精确匹配型号
            nvidia_pkgs = self.detect_nvidia_packages()
            for pkg in nvidia_pkgs:
                # 已安装的包如果在可升级列表里，上面已经加过了；
                # 未安装但显卡存在时，作为安装项加入
                if not self.is_pkg_installed(pkg) and pkg not in driver_pkgs:
                    driver_pkgs.append(pkg)

            result_list = []
            for pkg in driver_pkgs:
                if self.is_pkg_installed(pkg):
                    result_list.append((pkg, "upgrade"))
                else:
                    result_list.append((pkg, "install"))

            self.finished.emit(result_list)
        except Exception as e:
            # 任何异常都保证发出 finished 信号，避免按钮永久禁用
            print(self.tr("DriverChecker error: {}").format(e))
            self.finished.emit([])
        
class UpdateSourceProgressDialog(QDialog):

    finished_with_error = pyqtSignal(str)  

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Updating software sources"))
        self.setModal(True)
        # 与主窗口保持一致的 HiDPI 缩放
        self.scaling_factor = get_scaling_factor()
        self.resize(self.scaled(500), self.scaled(300))
        self._succeeded = False

        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.handle_finished)

        cmd = ['pkexec', 'apt', 'update']
        self.process.start(cmd[0], cmd[1:])

    def scaled(self, value):
        return int(value * self.scaling_factor)

    def closeEvent(self, event):
        # 进程运行时阻止关闭，避免半中断导致包管理状态不一致
        if self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(
                self, self.tr("Please Wait"),
                self.tr("The operation is still in progress. Please wait until it finishes."),
                QMessageBox.StandardButton.Ok
            )
            event.ignore()
        else:
            event.accept()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.text_edit.append(data)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.text_edit.append(data)

    def handle_finished(self, exit_code, exit_status):
        if exit_code == 0:
            self._succeeded = True
            self.accept()
        else:
            error_msg = self.tr("Failed to update the software source. The operation was canceled or you do not have sufficient permissions.")
            stderr = self.process.readAllStandardError().data().decode()
            if stderr:
                error_msg += f"\n\n{stderr}"
            self.finished_with_error.emit(error_msg)
            self.reject()

class ProgressDialog(QDialog):
    def __init__(self, packages, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Update&Install Progress"))
        self.setModal(True)
        # 与主窗口保持一致的 HiDPI 缩放
        self.scaling_factor = get_scaling_factor()
        self.resize(self.scaled(600), self.scaled(400))
        self._succeeded = False

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.close_btn = QPushButton(self.tr("Close"))
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.handle_finished)

        cmd = ['pkexec', 'apt', 'install', '-y'] + packages
        self.process.start(cmd[0], cmd[1:])

    def scaled(self, value):
        return int(value * self.scaling_factor)

    def closeEvent(self, event):
        # 安装进程运行时阻止关闭，避免 dpkg 中断导致包管理状态损坏
        if self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(
                self, self.tr("Please Wait"),
                self.tr("The installation is still in progress. Please wait until it finishes."),
                QMessageBox.StandardButton.Ok
            )
            event.ignore()
        else:
            event.accept()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.text_edit.append(data)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.text_edit.append(data)

    def handle_finished(self, exit_code, exit_status):
        if exit_code == 0:
            self._succeeded = True
            self.text_edit.append(self.tr("\n✅ Update successful！"))
        else:
            self.text_edit.append(self.tr("❌ Update failed. Please check the output. If the problem cannot be resolved,"
                                          "please paste the error onto the forum or QQ group.\n"
                                          "forum：https://bbs.spark-app.store/\n"
                                          "QQ group：712629637\n"))
        self.close_btn.setEnabled(True)

class AboutDialogContainer(QWidget):
    """关于对话框的圆角内容容器（外观参考 DAboutDialog）"""

    def __init__(self, parent=None, radius=8):
        super().__init__(parent)
        self.setObjectName("AboutContainer")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._radius = radius

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 抗锯齿圆角裁剪
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)

        # 对应 DAboutDialog 的半透明背景与细边框
        if self.palette().color(QPalette.ColorRole.Window).lightness() < 128:
            painter.fillPath(path, QColor(30, 31, 35, 219))   # rgba(30,31,35,0.86)
            border_color = QColor(255, 255, 255, 15)
        else:
            painter.fillPath(path, QColor(255, 255, 255, 204))  # rgba(255,255,255,0.80)
            border_color = QColor(0, 0, 0, 20)

        painter.setPen(QPen(border_color, 1))
        painter.drawPath(path)


class AboutDialog(QDialog):
    """关于对话框（UI 参考 dtk2widget-qt6 的 DAboutDialog）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("About GXDE Hardware Viewer"))
        self.setModal(True)

        # 缩放因子，与主窗口保持一致
        try:
            dpi = QApplication.primaryScreen().logicalDotsPerInch()
            self.scaling_factor = dpi / 96.0
        except Exception:
            self.scaling_factor = 1.0

        self._radius = SettingsUtils.get_window_radius()

        # 无边框 + 半透明背景 + 圆角
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 外层留白用于绘制阴影
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            self.scaled(20), self.scaled(20), self.scaled(20), self.scaled(20)
        )

        container = AboutDialogContainer(self, self._radius)
        # 让容器内的按钮也能拿到缩放因子
        container.scaling_factor = self.scaling_factor

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(self.scaled(24))
        shadow.setOffset(0, self.scaled(3))
        shadow.setColor(QColor(0, 0, 0, 80))
        container.setGraphicsEffect(shadow)
        outer.addWidget(container)

        # 主题相关配色（对应 DAboutDialog 的亮/暗色主题）
        is_dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        # 规范：链接仅使用主题色（深色背景下用主色亮变体保证对比度）
        link_color = ThemeColor.css(ThemeColor.PRIMARY_LIGHT if is_dark else ThemeColor.PRIMARY)
        desc_color = "#c0c0c0" if is_dark else "#1A1A1A"
        version_color = "#999999" if is_dark else "#666666"
        name_style = f"color: #f0f0f0;" if is_dark else ""

        container.setStyleSheet(f"""
            QLabel#ProductNameLabel {{
                font-size: {self.scaled(18)}px; {name_style}
            }}
            QLabel#VersionLabel {{
                font-size: {self.scaled(12)}px; color: {version_color};
            }}
            QLabel#WebsiteLabel {{
                font-size: {self.scaled(13)}px; color: {link_color};
            }}
            QLabel#AcknowledgementLabel {{
                font-size: {self.scaled(13)}px; color: {link_color};
            }}
            QLabel#DescriptionLabel {{
                font-size: {self.scaled(11)}px; color: {desc_color};
            }}
        """)

        # 主布局：对应 DAboutDialog 的 mainLayout（spacing 0，逐项手工间隔）
        main = QVBoxLayout(container)
        main.setContentsMargins(
            self.scaled(11), self.scaled(20), self.scaled(11), self.scaled(10)
        )
        main.setSpacing(0)

        # 右上角关闭按钮（与主窗口标题栏按钮同风格）
        self.close_btn = TitleBarBtns(container, TitleBarBtnType.CLOSE)
        self.close_btn.clicked.connect(self.close)

        # 应用图标
        logo_label = QLabel()
        logo_label.setContentsMargins(0, 0, 0, 0)
        icon = QIcon(self._app_icon_path())
        logo_label.setPixmap(icon.pixmap(self.scaled(80), self.scaled(80)))
        main.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignCenter)
        main.addSpacing(self.scaled(3))

        # 应用名称 18px，不加粗
        name_label = QLabel(self.tr("GXDE Hardware Viewer"))
        name_label.setObjectName("ProductNameLabel")
        main.addWidget(name_label, alignment=Qt.AlignmentFlag.AlignCenter)
        main.addSpacing(self.scaled(6))

        # 版本号 12px
        version_label = QLabel(self.tr("Version: ") + version)
        version_label.setObjectName("VersionLabel")
        main.addWidget(version_label, alignment=Qt.AlignmentFlag.AlignCenter)
        main.addSpacing(self.scaled(8))

        # 组织 Logo（宽幅 Logo，需限制宽度，否则会超出对话框）
        gxde_pixmap = QPixmap(self._gxde_logo_path())
        if not gxde_pixmap.isNull():
            company_logo_label = QLabel()
            # 按宽度上限等比缩放，保证不超出内容区（约 338px 可用宽度）
            company_logo_label.setPixmap(
                gxde_pixmap.scaled(
                    QSize(self.scaled(200), self.scaled(48)),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            main.addWidget(company_logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 官网链接
        website_label = QLabel(
            "<a href='https://www.gxde.top' style='text-decoration: none;'>www.gxde.top</a>"
        )
        website_label.setObjectName("WebsiteLabel")
        website_label.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        website_label.setFixedHeight(self.scaled(24))
        website_label.setOpenExternalLinks(True)
        main.addWidget(website_label, alignment=Qt.AlignmentFlag.AlignCenter)
        main.addSpacing(self.scaled(5))

        # 鸣谢入口（点击弹出鸣谢信息）
        ack_label = QLabel(
            f"<a href='#' style='text-decoration: none;'>{self.tr('Acknowledgments')}</a>"
        )
        ack_label.setObjectName("AcknowledgementLabel")
        ack_label.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        ack_label.setFixedHeight(self.scaled(24))
        ack_label.setOpenExternalLinks(False)
        ack_label.linkActivated.connect(self._show_acknowledgements)
        main.addWidget(ack_label, alignment=Qt.AlignmentFlag.AlignCenter)
        main.addSpacing(self.scaled(12))

        # 功能描述 11px，可换行
        desc_label = QLabel(self.tr("""
        GXDE Hardware Manager is a lightweight hardware information viewer specifically designed for the GXDE desktop environment
        """).strip())
        desc_label.setObjectName("DescriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        main.addWidget(desc_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.setFixedWidth(self.scaled(400))

        # 支持鼠标拖动移动窗口（无边框对话框需要自行实现）
        self._drag_start = None
        self._drag_origin = None
        self._drag_pending = False
        container.installEventFilter(self)
        for w in container.findChildren(QWidget):
            w.installEventFilter(self)

    def scaled(self, value):
        return int(value * self.scaling_factor)

    def _is_close_button(self, widget):
        """判断控件是否属于右上角关闭按钮（拖动需排除按钮）"""
        w = widget
        while isinstance(w, QWidget):
            if isinstance(w, TitleBarBtns):
                return True
            w = w.parentWidget()
        return False

    def eventFilter(self, obj, event):
        """对话框拖动移动：优先交给窗口系统，失败时回退手动移动"""
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress:
            if (event.button() == Qt.MouseButton.LeftButton
                    and not self._is_close_button(obj)):
                self._drag_start = event.globalPosition().toPoint()
                self._drag_origin = None
                self._drag_pending = True
        elif etype == QEvent.Type.MouseMove:
            if self._drag_start is None:
                return super().eventFilter(obj, event)
            buttons = event.buttons()
            if buttons & Qt.MouseButton.LeftButton:
                distance = event.globalPosition().toPoint() - self._drag_start
                if self._drag_pending:
                    if distance.manhattanLength() > self.scaled(6):
                        self._drag_pending = False
                        handle = self.windowHandle()
                        if handle is not None and handle.startSystemMove():
                            return True
                        # 窗口系统不支持时回退为手动移动
                        self._drag_origin = self.pos()
                        self.move(self._drag_origin + distance)
                        return True
                elif self._drag_origin is not None:
                    self.move(self._drag_origin + distance)
                    return True
        elif etype == QEvent.Type.MouseButtonRelease:
            self._drag_pending = False
            self._drag_origin = None
            self._drag_start = None
        return super().eventFilter(obj, event)

    def _app_icon_path(self):
        """应用图标路径，依次尝试安装目录与源码目录"""
        for path in (
            "/usr/share/gxde-hardware-viewer/icons/gxde-hardware-viewer.svg",
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "icons", "gxde-hardware-viewer.svg",
            ),
        ):
            if os.path.exists(path):
                return path
        return ""

    def _gxde_logo_path(self):
        """组织 Logo 路径，依次尝试安装目录与源码目录"""
        for path in (
            "/usr/share/gxde-hardware-viewer/gxde-logo_new.png",
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "gxde-logo_new.png"
            ),
        ):
            if os.path.exists(path):
                return path
        return ""

    def _show_acknowledgements(self, _link):
        QMessageBox.information(
            self,
            self.tr("Acknowledgments"),
            self.tr("Thanks to all the open source software we've used "
                    "and to you who are using it now"),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 将关闭按钮固定在容器右上角（对应 DAboutDialog 的 DAnchors 锚定）
        if hasattr(self, 'close_btn'):
            margin = self.scaled(6)
            btn = self.close_btn
            # 注意：TitleBarBtns 把 self.parent 覆盖成了属性，必须用 parentWidget()
            container = btn.parentWidget()
            if container is not None:
                btn.move(
                    container.width() - btn.width() - margin,
                    margin,
                )

    def keyPressEvent(self, event):
        # Esc 关闭（与 DAboutDialog 一致）
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # 固定宽度时按内容自适应高度（对应 DAboutDialog 的 showEvent 处理）
        self.resize(self.width(), self.heightForWidth(self.width()))



if __name__ == "__main__":

    app = QApplication(sys.argv)

    programPath = os.path.split(os.path.realpath(__file__))[0]

    translator = QTranslator()
    locale = QLocale.system().name()
    translator.load(f"{programPath}/../share/gxde-hardware-viewer/translations/gxde-hardware-viewer_{locale}.qm")
    if (os.path.exists(f"{programPath}/translations/gxde-hardware-viewer_{locale}.qm")):
        translator.load(f"{programPath}/translations/gxde-hardware-viewer_{locale}.qm")
    
    app.installTranslator(translator)


    
    palette = QPalette()

    palette.setColor(QPalette.ColorRole.Highlight, ThemeColor.PRIMARY)

    app.setPalette(palette)

    window = HardwareManager()
    window.show()
    
    sys.exit(app.exec())
