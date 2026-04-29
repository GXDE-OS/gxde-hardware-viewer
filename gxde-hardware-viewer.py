#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
import platform
import psutil
import socket
import subprocess
import json
import os
import time
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QListWidget, QListWidgetItem, QStackedWidget,
                            QLabel, QGroupBox, QFormLayout, QTextEdit, QFileDialog, 
                            QTableWidget, QTableWidgetItem, QProgressBar, QFrame,
                            QPushButton, QMenu, QMessageBox, QAbstractItemView, QDialog, QDialogButtonBox, QScrollArea)
from PyQt6.QtCore import Qt, QTimer, QTranslator, QCoreApplication, QLocale, QThread, pyqtSignal, QProcess, QSettings, QRect, QRectF, QPoint, QEvent
from PyQt6.QtGui import QColor, QIcon, QFont, QPainter, QPalette, QPixmap, QImage, QFontMetrics, QPainterPath, QRegion

import dbus

version = "2.6.1-2"

uname = platform.uname()

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
        self.layout.setContentsMargins(self.scaled(12), self.scaled(8), self.scaled(12), self.scaled(8))
        self.layout.setSpacing(self.scaled(15))

        # 1.1 设定标题栏颜色
        self.lightBg = QColor("#FBFBFB")
        self.DarkBg = QColor("#050505")
        self.lightBorder = QColor(0, 0, 0, 25)
        self.darkBorder = QColor(255, 255, 255, 50)


        # 1.2 标题栏高度对齐文件管理器
        self.setFixedHeight(self.scaled(40))
        
        # 2. 左侧：窗口标题标签
        app_icon = QIcon.fromTheme("utilities-system-monitor")
        icon_size = self.scaled(24)
        icon_pixmap = app_icon.pixmap(icon_size, icon_size)

        self.title_icon_label = QLabel()
        self.title_icon_label.setPixmap(icon_pixmap)
        self.title_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_icon_label.setFixedSize(self.scaled(24), self.scaled(24))
        self.layout.addWidget(self.title_icon_label)
        self.layout.addStretch()
        
        # 3. 右侧：菜单按钮
        self.menu_button = QPushButton("☰")
        self.menu_button.setFixedSize(self.scaled(24), self.scaled(24))
        self.menu_button.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: {self.scaled(4)}px;
                background-color: transparent;
                font-size: {self.scaled(16)}px;
            }}
            QPushButton::menu-indicator {{
                image: none;
                width: 0px;
            }}
            QPushButton:hover {{
                background-color: grey;
            }}
            QPushButton:pressed {{
                color: white;
                background-color: #F380A6
            }}
        """)
        self.layout.addWidget(self.menu_button)
        
        # 4. 右侧：窗口控制按钮
        self.min_btn = self.create_gxde_control_btn("—")
        self.max_btn = self.create_gxde_control_btn("□")

        self.close_btn = self.create_gxde_control_btn("×")
        # 关闭按钮样式
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: {self.scaled(4)}px;
                background-color: transparent;
                font-size: {self.scaled(14)}px;
            }}
            QPushButton:hover {{
                background-color: #E6004C;
                color: white;
            }}
            QPushButton:pressed {{
                background-color: #cc0000;
            }}
        """)
        self.layout.addWidget(self.min_btn)
        self.layout.addWidget(self.max_btn)
        self.layout.addWidget(self.close_btn)
        
        # 5. 绑定窗口控制按钮事件
        self.min_btn.clicked.connect(self.parent.showMinimized)
        self.max_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.parent.close)

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
                background-color: #F380A6
            }}
        """)
        return btn 

    def toggle_maximize(self):
        """切换窗口最大化/还原"""
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.max_btn.setText("□")
        else:
            self.parent.showMaximized()
            self.max_btn.setText("▢")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.parent.windowHandle()
            if window is not None:
                # 如果窗口处于最大化状态，先还原再移动
                if self.parent.isMaximized():
                    self.parent.showNormal()
                window.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    # 6. 重载绘制函数
    #    模仿DTK2.0时代的标题栏
    def is_dark_mode(self) -> bool:
        # 需要Qt 6.5+
        scheme = QApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark

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

        # 主窗口已设置 WA_TranslucentBackground，需要自行填充背景色
        painter.fillPath(path, self.palette().color(QPalette.ColorRole.Window))

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

        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        item_padding = 13
        icon_size = 16
        icon_text_gap = 8
        check_mark_border = 3

        is_dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 100

        if self._is_checked:
            bg_color = QColor(44, 167, 248, 80) if is_dark else QColor(44, 167, 248, 60)
            text_color = QColor(96, 190, 255) if is_dark else QColor(44, 167, 248)
            painter.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        elif self._is_hovered:
            bg_color = QColor(255, 255, 255, 30) if is_dark else QColor(0, 0, 0, 20)
            text_color = QColor(220, 220, 220) if is_dark else QColor(0, 0, 0, 204)
            painter.setFont(QFont("Sans", 9))
        else:
            # Mod: 背景图片启用时，未选中时Item底色交由SideBar负责，不再由Item自行负责
            bg_color = QColor(0, 0, 0, 0)
            text_color = QColor(220, 220, 220) if is_dark else QColor(0, 0, 0, 204)
            painter.setFont(QFont("Sans", 9))

        if bg_color.alpha() > 0:
            painter.fillRect(self.rect(), bg_color)

        icon_top = (self.height() - icon_size) // 2
        icon_rect = QRect(item_padding, icon_top, icon_size, icon_size)
        icon = QIcon.fromTheme(self._icon_name)
        if not icon.isNull():
            pixmap = icon.pixmap(icon_size, icon_size)
            if self._is_checked:
                img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
                ip = QPainter(img)
                ip.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                ip.fillRect(img.rect(), text_color)
                ip.end()
                pixmap = QPixmap.fromImage(img)
            painter.drawPixmap(icon_rect, pixmap)

        painter.setPen(text_color)
        text_padding_left = item_padding + icon_size + icon_text_gap
        text_rect = QRect(text_padding_left, 0,
                          self.width() - text_padding_left - icon_text_gap,
                          self.height())
        fm = QFontMetrics(painter.font())
        elided = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        if self._is_checked:
            x = (self._width_override if self._width_override > 0 else self.width()) - check_mark_border
            painter.fillRect(x, 0, check_mark_border, self.height(), text_color)


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

        self._width_override = item_width_override if item_width_override > 0 else -1
        self._item_list = []
        self._bg_active = False  # Mod: 窗体背景启用状态

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

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
    def __init__(self):
        super().__init__()
    
        # 初始化变量
        self.cache = CacheManager()
        self.translator = QTranslator(self)
        self.current_lang = "en" 
        self.net_io_labels = {}
        self.disk_io_labels = {}
    
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

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            # 处理圆角
            self.update()
            for w in (getattr(self, 'gxde_title_bar', None),
                      getattr(self, 'sidebar', None),
                      self.centralWidget()):
                if w is not None:
                    w.update()
        super().changeEvent(event)

    def initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setWindowTitle(self.tr("GXDE Hardware Manager"))
        self.resize(self.scaled(900), self.scaled(600))
    
        # 创建中心部件
        central_widget = CentralWidget()
        self.setCentralWidget(central_widget)
    
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
        self.add_sidebar_item(self.tr("System"), "computer")
        self.add_sidebar_item(self.tr("CPU"), "cpu")
        self.add_sidebar_item(self.tr("Memory"), "memory")
        self.add_sidebar_item(self.tr("Storage"), "disk-quota")
        self.add_sidebar_item(self.tr("Network"), "network")
        self.add_sidebar_item(self.tr("Display"), "display")
        self.add_sidebar_item(self.tr("Sound"), "sound")
        self.add_sidebar_item(self.tr("Input Devices"), "dialog-input-devices")
        self.add_sidebar_item(self.tr("Driver Update"), "system-upgrade")
    
        # 5. 创建主内容区域
        self.stack = QStackedWidget()
    
        # 6. 添加所有页面
        self.stack.addWidget(self.create_system_info_page())
        self.stack.addWidget(self.create_cpu_page())
        self.stack.addWidget(self.create_memory_page())
        self.stack.addWidget(self.create_storage_page())
        self.stack.addWidget(self.create_network_page())
        self.stack.addWidget(self.create_display_page())
        self.stack.addWidget(self.create_sound_page())
        self.stack.addWidget(self.create_input_page())
        self.stack.addWidget(self.create_driver_update_page())
    
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
        
        # 侧边栏项目
        sidebar_texts = [
            self.tr("System"), self.tr("CPU"), self.tr("Memory"), 
            self.tr("Storage"), self.tr("Network"), self.tr("Display"), 
            self.tr("Sound"), self.tr("Input Devices")
        ]
        for i, text in enumerate(sidebar_texts):
            self.sidebar.item(i).setText(text)
    
        # 菜单项目
        menu = self.menu_button.menu()
        menu.actions()[1].setText(self.tr("Export all information to desktop"))
        menu.actions()[2].setText(self.tr("About"))
    
        # 重新创建所有页面（更新翻译后刷新页面）
        self.refresh_all_pages()
    
    def refresh_all_pages(self):
        """刷新所有页面以更新翻译"""
        current_index = self.stack.currentIndex()

        while self.stack.count() > 0:
            widget = self.stack.widget(0)  
            self.stack.removeWidget(widget) 
            widget.deleteLater() 

        # 重新添加所有页面
        self.stack.addWidget(self.create_system_info_page())
        self.stack.addWidget(self.create_cpu_page())
        self.stack.addWidget(self.create_memory_page())
        self.stack.addWidget(self.create_storage_page())
        self.stack.addWidget(self.create_network_page())
        self.stack.addWidget(self.create_display_page())
        self.stack.addWidget(self.create_sound_page())
        self.stack.addWidget(self.create_input_page())

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
            cpu_freq = psutil.cpu_freq()
            info[self.tr("CPU Info")] = {
                self.tr("Processor Model"): self.get_cpu_model(),
                self.tr("Architecture"): platform.machine(),
                self.tr("Physical Cores"): psutil.cpu_count(logical=False) or 0,
                self.tr("Logical Cores"): psutil.cpu_count(logical=True) or 0,
                self.tr("Current Frequency"): f"{cpu_freq.current:.2f} MHz" if cpu_freq and cpu_freq.current else "Unknown",
                self.tr("Maximum Frequency"): f"{cpu_freq.max:.2f} MHz" if cpu_freq and cpu_freq.max else "Unknown",
                self.tr("Minimum Frequency"): f"{cpu_freq.min:.2f} MHz" if cpu_freq and cpu_freq.min else "Unknown"
            }
            
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

        # 更新网络信息
        if current_index == 4:
            self.update_network_info()
            
        # 更新磁盘IO信息
        if current_index == 3:
            self.update_disk_io_info()
            
        # 更新启动时间
        if current_index == 0:
            self.update_uptime()
            
        # 更新分辨率信息
        if current_index == 5:
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
        
        # 获取CPU详细信息
        cpu_model = self.get_cpu_model()
        cpu_arch = platform.machine()
        cpu_count = psutil.cpu_count(logical=False) or 0
        logical_cpu = psutil.cpu_count(logical=True) or 0
        
        # 处理CPU频率信息
        cpu_freq = psutil.cpu_freq()
        current_freq = f"{cpu_freq.current:.2f} MHz" if cpu_freq and cpu_freq.current else self.tr("Unknown")
        max_freq = f"{cpu_freq.max:.2f} MHz" if cpu_freq and cpu_freq.max else self.tr("Unknown")
        min_freq = f"{cpu_freq.min:.2f} MHz" if cpu_freq and cpu_freq.min else self.tr("Unknown")
        
        # 保存当前频率标签引用以便更新
        self.cpu_current_freq_label = QLabel(current_freq)
        
        cpu_base_layout.addRow(self.tr("Processor Model:"), QLabel(cpu_model))
        cpu_base_layout.addRow(self.tr("Architecture:"), QLabel(cpu_arch))
        cpu_base_layout.addRow(self.tr("Physical Cores:"), QLabel(str(cpu_count)))
        cpu_base_layout.addRow(self.tr("Logical Cores:"), QLabel(str(logical_cpu)))
        cpu_base_layout.addRow(self.tr("Current Frequency:"), self.cpu_current_freq_label)
        cpu_base_layout.addRow(self.tr("Maximum Frequency:"), QLabel(max_freq))
        cpu_base_layout.addRow(self.tr("Minimum Frequency:"), QLabel(min_freq))
        
        cpu_base.setLayout(cpu_base_layout)
        layout.addWidget(self.create_group_box(self.tr("Basic Information"), cpu_base))
        
        # CPU驱动信息
        cpu_drivers = self.get_cpu_driver_info()
        driver_widget = QWidget()
        driver_layout = QFormLayout()
        driver_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        driver_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        driver_layout.setHorizontalSpacing(self.scaled(15))
        driver_layout.setVerticalSpacing(self.scaled(8))
        
        for key, value in cpu_drivers.items():
            driver_layout.addRow(f"{key}:", QLabel(value))
        
        driver_widget.setLayout(driver_layout)
        layout.addWidget(self.create_group_box(self.tr("CPU Driver Information"), driver_widget))
        
        layout.addStretch()
        return widget
        
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
            mem_driver_layout.addRow(f"{key}:", QLabel(value))
        
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
            driver_layout.addRow(f"{key}:", QLabel(value))
        
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
            driver_layout.addRow(f"{key}:", QLabel(value))
        
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

    def create_driver_update_page(self):
        """创建驱动更新页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        label1 = QLabel(self.tr(
            "⚠️ Warning: This feature will update drivers and the kernel. Please make sure you know what you are doing!\n"
            "In theory, we probably shouldn't encounter any strange problems (and even if we do, it shouldn't be a disaster).\n"
            "It is recommended to back up the system and data first.\n"
        ))

        font = label1.font()
        font.setPointSize(11) 
        font.setBold(True)
        label1.setFont(font)
        label1.setStyleSheet("color: #E6004C;")        
        layout.addWidget(label1)

        label2 = QLabel(self.tr('Please select the driver you want to update:'))
        font = label2.font()
        font.setBold(True)
        label2.setFont(font)
        layout.addWidget(label2)

        self.list_widget = QListWidget()
        self.list_widget.addItem(self.tr("Please click the 'Check for Updates' button to get available driver updates."))  
        layout.addWidget(self.list_widget)

        self.update_btn = QPushButton(self.tr("Update"))
        self.update_btn.clicked.connect(self.perform_update)
        self.update_btn.setFixedSize(100, 30)

        self.check_update_btn = QPushButton(self.tr("Check for updates"))
        self.check_update_btn.clicked.connect(self.on_check_updates_clicked)
        self.check_update_btn.setFixedSize(130, 30)

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
        self.checker = UpdateChecker()
        self.checker.finished.connect(self.on_update_check_finished)
        self.checker.start()

    def on_update_source_error(self, error_message):
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText(self.tr("Check for updates"))
        QMessageBox.critical(self, self.tr("Error"), error_message)

    def on_update_check_finished(self, driver_pkgs):
        """重新启用按钮"""
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText(self.tr("Check for updates"))

        # 更新列表
        self.list_widget.clear()
        if not driver_pkgs:
            self.list_widget.addItem(self.tr("All drivers and the kernel are up to date~"))
            return
        for name in driver_pkgs:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

    def perform_update(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())

        if not selected:
            QMessageBox.information(self, self.tr("Information"),
                                self.tr("Please select the driver or kernel to update first"))
            return

        self.update_btn.setEnabled(False)
        self.update_btn.setText(self.tr("Updating..."))

        dialog = UpdateProgressDialog(selected, self)
        dialog.exec()
        self.on_check_updates_clicked()   

        self.update_btn.setEnabled(True)
        self.update_btn.setText(self.tr("Update"))

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
                    if devtype == 'disk' and not name.startswith(('loop', 'ram')):
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

class UpdateChecker(QThread):
    """更新检查"""
    finished = pyqtSignal(list)  # 传递驱动列表

    def run(self):
        # 获取可升级包列表
        result = subprocess.run(['aptss', 'list', '--upgradable'],
                                capture_output=True, text=True)
        lines = result.stdout.splitlines()
        print("Raw lines:", lines)
        packages = []
        pattern = re.compile(r'^(\S+)/')
        for line in lines:
            match = pattern.match(line)
            if match:
                pkg = match.group(1)
                packages.append(pkg)
        print("All upgradable packages:", packages)
        # 3. 过滤出驱动/内核相关的包
        keywords = ['linux', 'nvidia', 'firmware', 'microcode', 'bluez']
        exclude_pkgs = ['linuxqq']
        driver_pkgs = [p for p in packages if any(k in p for k in keywords) and not any(ex in p for ex in exclude_pkgs)]
        print("Filtered driver packages:", driver_pkgs)
        self.finished.emit(driver_pkgs)

class UpdateSourceProgressDialog(QDialog):

    finished_with_error = pyqtSignal(str)  

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Updating software sources"))
        self.setModal(True)
        self.resize(500, 300)

        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.handle_finished)

        cmd = ['pkexec', 'aptss', 'update']
        self.process.start(cmd[0], cmd[1:])

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.text_edit.append(data)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.text_edit.append(data)

    def handle_finished(self, exit_code, exit_status):
        if exit_code != 0:
            error_msg = self.tr("Failed to update the software source. The operation was canceled or you do not have sufficient permissions.")
            stderr = self.process.readAllStandardError().data().decode()
            if stderr:
                error_msg += f"\n\n{stderr}"
            self.finished_with_error.emit(error_msg)
        self.accept()   

class UpdateProgressDialog(QDialog):
    def __init__(self, packages, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Update Progress"))
        self.setModal(True)
        self.resize(600, 400)

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

        cmd = ['pkexec', 'aptss', 'install', '--only-upgrade', '-y'] + packages
        self.process.start(cmd[0], cmd[1:])

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.text_edit.append(data)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.text_edit.append(data)

    def handle_finished(self, exit_code, exit_status):
        if exit_code == 0:
            self.text_edit.append(self.tr("\n✅ Update successful！"))
        else:
            self.text_edit.append(self.tr("❌ Update failed. Please check the output. If the problem cannot be resolved,"
                                          "please paste the error onto the forum or QQ group.\n" 
                                          "forum：https://bbs.spark-app.store/\n"
                                          "QQ group：712629637\n"))
        self.close_btn.setEnabled(True)

class AboutDialog(QDialog):
    """关于对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("About GXDE Hardware Viewer"))
        self.setFixedSize(400, 450)
        self.setModal(True)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 图标
        icon_label = QLabel()
        icon = QIcon.fromTheme("utilities-system-monitor")
        icon_label.setPixmap(icon.pixmap(128, 128))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # 软件名称
        name_label = QLabel(self.tr("GXDE Hardware Viewer"))
        name_font = QFont()
        name_font.setPointSize(10)
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        # 版本号
        version_label = QLabel(self.tr("Version: ") + version)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        # 系统徽标和官网
        gxde_vertical_layout = QVBoxLayout()
        gxde_vertical_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        gxde_icon_label = QLabel()
        gxde_logo_path = "/usr/share/gxde-hardware-viewer/gxde-logo_new.png"
        gxde_pixmap = QPixmap(gxde_logo_path)
        if not gxde_pixmap.isNull():
            scaled_pixmap = gxde_pixmap.scaled(
                128, 128,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            gxde_icon_label.setPixmap(scaled_pixmap)
            gxde_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gxde_vertical_layout.addWidget(gxde_icon_label)
        else:
            gxde_text_label = QLabel("GXDE")
            gxde_font = QFont()
            gxde_font.setPointSize(18)
            gxde_font.setBold(True)
            gxde_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gxde_vertical_layout.addWidget(gxde_text_label)

        url_label = QLabel('<a href="https://www.gxde.top">www.gxde.top</a>')
        url_label.setOpenExternalLinks(True)
        url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gxde_vertical_layout.addWidget(url_label)

        layout.addLayout(gxde_vertical_layout)

        # 鸣谢按钮
        thanks_button = QPushButton(self.tr("Acknowledgments"))
        thanks_button.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                color: #E6014C;
                text-decoration: underline;
                font-size: 14px;
            }
            QPushButton:hover { color: #F380A6; }
            QPushButton:pressed { color: #E6014C; }
        """)
        thanks_button.clicked.connect(lambda: QMessageBox.information(self, self.tr("Acknowledgments"), self.tr("Thanks to all the open source software we've used and to you who are using it now")))
        layout.addWidget(thanks_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # 功能说明
        desc_text = self.tr("""
        GXDE Hardware Manager is a lightweight hardware information viewer specifically designed for the GXDE desktop environment
        """)
        desc_label = QLabel(desc_text)
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("margin: 10px 20px;")
        layout.addWidget(desc_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)



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

    palette.setColor(QPalette.ColorRole.Highlight ,QColor("#F383A8"))

    app.setPalette(palette)

    window = HardwareManager()
    window.show()
    
    sys.exit(app.exec())
