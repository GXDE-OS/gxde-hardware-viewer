#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
                            QLabel, QGroupBox, QFormLayout, QGridLayout, QScrollArea,
                            QTableWidget, QTableWidgetItem, QProgressBar, QFrame,
                            QPushButton, QMenu, QMessageBox, QAbstractItemView, QDialog, QDialogButtonBox)
from PyQt6.QtCore import Qt, QTimer, QTranslator, QCoreApplication, QLocale, QSize
from PyQt6.QtGui import QIcon, QFont, QPixmap, QMovie

version = "2.4.0"

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

class HardwareManager(QMainWindow):
    def __init__(self):
        super().__init__()
    
        # 初始化变量
        self.cache = CacheManager()
        self.translator = QTranslator(self)
        self.current_lang = "en" 
        self.cpu_total_bar = None
        self.cpu_core_bars = []
        self.mem_total_bar = None
        self.swap_bar = None
        self.net_io_labels = {}
        self.disk_io_labels = {}
    
        # 初始化缩放因子
        self.init_scaling_factor()
    
        # 创建用户界面
        self.initUI()
    
        # 启动硬件监控
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(2000)
        self.monitor_timer.timeout.connect(self.update_hardware_info)
        self.monitor_timer.start()

    def init_scaling_factor(self):
        """初始化缩放因子，用于适配不同分辨率"""
        try:
            # 获取屏幕逻辑DPI
            screen = QApplication.primaryScreen()
            dpi = screen.logicalDotsPerInch()
            # 以96 DPI为基准计算缩放因子
            self.scaling_factor = dpi / 96.0
        except:
            self.scaling_factor = 1.0
            
    def scaled(self, value):
        """根据缩放因子缩放数值"""
        return int(value * self.scaling_factor)
        
    def initUI(self):
        # 设置窗口基本属性
        self.setWindowTitle(self.tr("GXDE Hardware Manager"))
        # 使用相对大小而非固定大小
        self.resize(self.scaled(900), self.scaled(600))
        
        # 创建主布局
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        
        # 创建侧边栏
        self.sidebar = QListWidget()
        # 侧边栏宽度根据缩放因子调整
        self.sidebar.setFixedWidth(self.scaled(180))
        self.sidebar.setStyleSheet(f"""
            QListWidget {{
                border-right: 1px solid #2CA7F8;
                padding-top: {self.scaled(10)}px;
            }}
            QListWidgetItem {{
                height: {self.scaled(36)}px;
                padding-left: {self.scaled(15)}px;
                font-size: {self.scaled(14)}px;
            }}
            QListWidget::item:selected {{
                color: #2CA7F8;
                border-left: 3px solid #2CA7F8;
            }}
        """)
        
        # 添加侧边栏项目
        self.add_sidebar_item(self.tr("System"), "system")
        self.add_sidebar_item(self.tr("CPU"), "cpu")
        self.add_sidebar_item(self.tr("Memory"), "memory")
        self.add_sidebar_item(self.tr("Storage"), "disk-quota")
        self.add_sidebar_item(self.tr("Network"), "network")
        self.add_sidebar_item(self.tr("Display"), "display")
        self.add_sidebar_item(self.tr("Sound"), "sound")
        self.add_sidebar_item(self.tr("Input Devices"), "dialog-input-devices")
        
        # 创建主内容区域
        self.stack = QStackedWidget()
        
        # 添加加载中的提示页面
        self.loading_page = self.create_loading_page()
        self.stack.addWidget(self.loading_page)
    
        # 连接侧边栏选择事件
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
    
        # 添加到主布局
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stack, 1)
    
        # 设置中心部件
        self.setCentralWidget(main_widget)
    
        # 默认显示加载页面，隐藏侧边栏
        self.sidebar.hide()
        self.stack.setCurrentIndex(0)

        # 添加各个页面
        self.stack.addWidget(self.create_system_info_page())
        self.stack.addWidget(self.create_cpu_page())
        self.stack.addWidget(self.create_memory_page())
        self.stack.addWidget(self.create_storage_page())
        self.stack.addWidget(self.create_network_page())
        self.stack.addWidget(self.create_display_page())
        self.stack.addWidget(self.create_sound_page())
        self.stack.addWidget(self.create_input_page())
        
        # 连接侧边栏选择事件
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        
        # 添加到主布局
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stack, 1)
        
        # 设置中心部件
        self.setCentralWidget(main_widget)
        
        # 默认选中第一个项目
        self.sidebar.setCurrentRow(0)
        
        # 添加右上角菜单按钮
        self.create_menu_button()
        
        # 应用字体缩放
        self.apply_font_scaling()

        self.setup_text_selection()

        QTimer.singleShot(100, self.load_real_pages)
    
    def create_loading_page(self):
        """创建加载页面"""
        widget = QWidget()

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
    
        layout.addStretch()

        # 创建GIF动画标签
        self.loading_gif_label = QLabel()
    
        gif_path = "/home/ocean/Downloads/loading.gif"
    
        self.loading_movie = QMovie(gif_path)
        self.loading_gif_label.setMovie(self.loading_movie)
        self.loading_movie.start()
        
        gif_size = self.scaled(150)
        self.loading_gif_label.setFixedSize(gif_size, gif_size)
        self.loading_movie.setScaledSize(QSize(gif_size, gif_size))

        gif_layout = QHBoxLayout()
        gif_layout.addStretch()
        gif_layout.addWidget(self.loading_gif_label)
        gif_layout.addStretch()
        layout.addLayout(gif_layout)

        layout.addStretch()
        return widget
    
    def load_real_pages(self):
        """加载实际页面"""
        QTimer.singleShot(1500, self.finish_loading)

    def finish_loading(self):
        """完成加载并显示主界面"""

        if hasattr(self, 'loading_movie'):
            self.loading_movie.stop()

        # 移除加载页面，显示实际内容
        self.stack.removeWidget(self.loading_page)
        self.loading_page.deleteLater()

        # 显示侧边栏并选中第一个项目
        self.sidebar.show()
        self.sidebar.setCurrentRow(0)

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
            table.customContextMenuRequested.connect(self.show_table_context_menu)  # 改为连接到一个显示菜单的函数

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
        
        # 窗口标题
        self.setWindowTitle(self.tr("GXDE Hardware Manager"))
    
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


    def create_menu_button(self):
        """创建右上角菜单按钮"""
        # 创建菜单按钮
        menu_button = QPushButton("☰")
        menu_button.setFixedSize(self.scaled(30), self.scaled(30))
        menu_button.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        
        # 创建菜单
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QMenu::item {
                padding: 5px 20px;
            }
        """)
        
        # 添加菜单项
        export_action = menu.addAction(self.tr("Export all information to desktop"))
        export_action.triggered.connect(self.export_all_info)
    
        about_action = menu.addAction(self.tr("About"))
        about_action.triggered.connect(self.show_about)
        # 设置按钮菜单
        menu_button.setMenu(menu)
        
        # 将按钮添加到窗口的右上角
        menu_button.setParent(self)
        menu_button.move(self.width() - menu_button.width() - 10, 30)
        
        # 保存按钮引用，以便在窗口大小改变时调整位置
        self.menu_button = menu_button

        QTimer.singleShot(100, self.update_menu_button_position)

    def update_menu_button_position(self):
        """更新菜单按钮位置"""
        if hasattr(self, 'menu_button') and self.menu_button:
            # 计算正确的位置
            x_pos = self.width() - self.menu_button.width() - 10
            y_pos = 10  # 距离顶部10像素
            self.menu_button.move(x_pos, y_pos)
            self.menu_button.raise_()  # 确保按钮在最上层
            self.menu_button.show()    # 确保按钮显示

    def resizeEvent(self, event):
        """重写窗口大小改变事件，确保菜单按钮始终在右上角"""
        super().resizeEvent(event)
        self.update_menu_button_position()

    def showEvent(self, event):
        """重写窗口显示事件，确保菜单按钮正确显示"""
        super().showEvent(event)
        # 窗口显示后更新菜单按钮位置
        QTimer.singleShot(100, self.update_menu_button_position)
        
    def resizeEvent(self, event):
        """重写窗口大小改变事件，确保菜单按钮始终在右上角"""
        super().resizeEvent(event)
        if hasattr(self, 'menu_button'):
            self.menu_button.move(self.width() - self.menu_button.width() - 10, 30)
        
    def export_all_info(self):
        """导出所有硬件信息到桌面"""
        # 清空缓存
        self.cache.clear()

        try:
            # 收集所有硬件信息
            info = {}
            
            # 系统信息
            uname = platform.uname()
            info[self.tr('System Information')] = {
                self.tr('System'): f"{uname.system} {uname.release} (GXDE)",
                self.tr('Host Name'): uname.node,
                self.tr("Kernel"): uname.version,
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
        
        # 更新CPU信息
        self.update_cpu_info()
        
        # 更新内存信息
        self.update_memory_info()
        
        # 如果在网络页面，更新网络信息
        if current_index == 4:
            self.update_network_info()
            
        # 如果在存储页面，更新磁盘IO信息
        if current_index == 3:
            self.update_disk_io_info()
            
        # 如果在系统信息页面，更新启动时间
        if current_index == 0:
            self.update_uptime()
            
        # 如果在显示页面，更新分辨率信息
        if current_index == 5:
            self.update_display_info()
    
    def add_sidebar_item(self, text, icon_name):
        """添加侧边栏项目"""
        item = QListWidgetItem(text)
        # 图标大小自适应
        icon = QIcon.fromTheme(icon_name, QIcon())
        item.setIcon(icon)
        self.sidebar.addItem(item)
        
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
            
        try:
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        # 去除引号和换行符
                        result = line.split('=')[1].strip().strip('"')
                        self.cache.set(cache_key, result, 3600)
                        return result
            result = self.tr("Unknown system version")
            self.cache.set(cache_key, result, 60)
            return result
        except FileNotFoundError:
            result = self.tr("Unable to get system version")
            self.cache.set(cache_key, result, 60)
            return result
        except Exception as e:
            result = self.tr("Failed to retrieve: {}").format(str(e))
            self.cache.set(cache_key, result, 60)
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
        uname = platform.uname()
        
        sys_layout.addRow(self.tr("Operating System:"), QLabel(self.get_os_version()))
        sys_layout.addRow(self.tr("Hostname:"), QLabel(uname.node))
        sys_layout.addRow(self.tr("Kernel Version:"), QLabel(uname.version))
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
        
        # 获取磁盘总容量
        disk_total = 0
        for part in psutil.disk_partitions():
            if 'cdrom' in part.opts or part.fstype == '':
                continue
            try:
                disk_usage = psutil.disk_usage(part.mountpoint)
                disk_total += disk_usage.total
            except PermissionError:
                continue
        
        hw_layout.addRow(self.tr("Total Disk Capacity:"), QLabel(self.format_size(disk_total)))

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
        return widget
        
    def create_cpu_page(self):
        """创建CPU信息页面"""
        widget = QScrollArea()
        widget.setWidgetResizable(True)
        
        content = QWidget()
        layout = QVBoxLayout(content)
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
        
        # CPU使用率
        cpu_usage = QWidget()
        cpu_usage_layout = QVBoxLayout()
        cpu_usage_layout.setSpacing(self.scaled(8))
        
        # 总体使用率
        self.cpu_total_bar = QProgressBar()
        self.cpu_total_bar.setFixedHeight(self.scaled(25))
        cpu_percent = psutil.cpu_percent(interval=0.1)
        self.cpu_total_bar.setValue(int(cpu_percent))
        self.cpu_total_bar.setFormat(self.tr("Total Usage: {}%").format(self.cpu_total_bar.value()))
        cpu_usage_layout.addWidget(self.cpu_total_bar)
        
        # 各核心使用率
        label = QLabel(self.tr("Core Usage:"))
        cpu_usage_layout.addWidget(label)
        
        self.core_usage_layout = QGridLayout()
        self.core_usage_layout.setSpacing(self.scaled(8))
        self.cpu_core_bars = []
        
        # 初始化核心进度条
        for i, percent in enumerate(psutil.cpu_percent(percpu=True, interval=0.1)):
            core_bar = QProgressBar()
            core_bar.setFixedHeight(self.scaled(25))
            core_bar.setValue(int(percent))
            core_bar.setFormat(self.tr("Core {}: {}%").format(i, core_bar.value()))
            self.core_usage_layout.addWidget(core_bar, i // 2, i % 2)
            self.cpu_core_bars.append(core_bar)
        
        cpu_usage_layout.addLayout(self.core_usage_layout)
        cpu_usage.setLayout(cpu_usage_layout)
        layout.addWidget(self.create_group_box(self.tr("CPU Usage"), cpu_usage))
        
        layout.addStretch()
        widget.setWidget(content)
        return widget
        
    def create_memory_page(self):
        """创建内存信息页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 内存使用情况
        mem_info = QWidget()
        mem_layout = QVBoxLayout()
        mem_layout.setSpacing(self.scaled(8))
        
        # 总内存信息
        mem = psutil.virtual_memory()
        
        self.mem_total_bar = QProgressBar()
        self.mem_total_bar.setFixedHeight(self.scaled(25))
        self.mem_total_bar.setValue(int(mem.percent))
        self.mem_total_bar.setFormat(self.tr("Memory Usage: {:.1f}% ({} / {})").format(mem.percent, self.format_size(mem.used), self.format_size(mem.total)))
        mem_layout.addWidget(self.mem_total_bar)
        
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
        
        self.swap_bar = QProgressBar()
        self.swap_bar.setFixedHeight(self.scaled(25))
        self.swap_bar.setValue(int(swap.percent))
        self.swap_bar.setFormat(self.tr("Swap Usage: {:.1f}% ({} / {})").format(swap.percent, self.format_size(swap.used), self.format_size(swap.total)))
        swap_layout.addWidget(self.swap_bar)
        
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
        widget = QScrollArea()
        widget.setWidgetResizable(True)
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 磁盘分区信息
        disk_table = QTableWidget()
        disk_table.setColumnCount(5)
        disk_table.setHorizontalHeaderLabels([self.tr("Device"), self.tr("Mount Point"), self.tr("File System"), self.tr("Total Capacity"), self.tr("Available Space")])
        disk_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # 设置表格字体
        font = disk_table.font()
        font.setPointSizeF(font.pointSizeF() * self.scaling_factor)
        disk_table.setFont(font)
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
        widget.setWidget(content)
        return widget
        
    def create_network_page(self):
        """创建网络信息页面"""
        widget = QScrollArea()
        widget.setWidgetResizable(True)
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 网络接口信息
        net_table = QTableWidget()
        net_table.setColumnCount(4)
        net_table.setHorizontalHeaderLabels([self.tr("Interface Name"), self.tr("IP Address"), self.tr("MAC Address"), self.tr("Status")])
        net_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # 设置表格字体
        font = net_table.font()
        font.setPointSizeF(font.pointSizeF() * self.scaling_factor)
        net_table.setFont(font)
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
        widget.setWidget(content)
        return widget
        
    def create_display_page(self):
        """创建显示信息页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(self.scaled(15), self.scaled(15), self.scaled(15), self.scaled(15))
        layout.setSpacing(self.scaled(10))
        
        # 显示设备信息
        self.display_info = QWidget()
        display_layout = QFormLayout()
        display_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        display_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        display_layout.setHorizontalSpacing(self.scaled(15))
        display_layout.setVerticalSpacing(self.scaled(8))
        
        # 获取显卡信息
        gpu_info = self.get_gpu_info()
        self.resolution_label = QLabel(self.get_screen_resolution())
        
        display_layout.addRow(self.tr("Graphics Card:"), QLabel(gpu_info))
        display_layout.addRow(self.tr("Resolution:"), self.resolution_label)
        display_layout.addRow(self.tr("Color Depth:"), QLabel(self.get_color_depth()))
        display_layout.addRow(self.tr("Refresh Rate:"), QLabel(self.get_refresh_rate()))

        self.display_info.setLayout(display_layout)
        layout.addWidget(self.create_group_box(self.tr("Display Devices"), self.display_info))
        
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
    
    def update_cpu_info(self):
        """更新CPU信息"""
        # 更新CPU总体使用率
        if self.cpu_total_bar:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_total_bar.setValue(int(cpu_percent))
            self.cpu_total_bar.setFormat(self.tr("Total Usage: {}%").format(int(cpu_percent)))
        
        # 更新各核心使用率
        if self.cpu_core_bars:
            core_percents = psutil.cpu_percent(percpu=True, interval=0.1)
            for i, (bar, percent) in enumerate(zip(self.cpu_core_bars, core_percents)):
                bar.setValue(int(percent))
                bar.setFormat(self.tr("Core {}: {}%").format(i, int(percent)))
        
        # 更新当前频率
        if hasattr(self, 'cpu_current_freq_label'):
            cpu_freq = psutil.cpu_freq()
            if cpu_freq and cpu_freq.current:
                self.cpu_current_freq_label.setText(f"{cpu_freq.current:.2f} MHz")
    
    def update_memory_info(self):
        """更新内存信息"""
        # 更新内存使用率
        if self.mem_total_bar:
            mem = psutil.virtual_memory()
            self.mem_total_bar.setValue(int(mem.percent))
            self.mem_total_bar.setFormat(self.tr("Memory Usage: {:.1f}% ({} / {})").format(mem.percent, self.format_size(mem.used), self.format_size(mem.total)))
            
            # 更新内存详细信息
            self.mem_used_label.setText(self.format_size(mem.used))
            self.mem_free_label.setText(self.format_size(mem.free))
            self.mem_available_label.setText(self.format_size(mem.available))
            self.mem_cache_label.setText(self.format_size(mem.total - mem.used - mem.free))
        
        # 更新交换分区信息
        if self.swap_bar:
            swap = psutil.swap_memory()
            self.swap_bar.setValue(int(swap.percent))
            self.swap_bar.setFormat(self.tr("Swap Usage: {:.1f}% ({} / {})").format(swap.percent, self.format_size(swap.used), self.format_size(swap.total)))
            
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
        if hasattr(self, 'resolution_label'):
            self.resolution_label.setText(self.get_screen_resolution())
    
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
            
            # 查找当前活跃的显示模式
            for line in output.split('\n'):
                if '*' in line and '+' in line:  # 包含*表示当前分辨率，+表示首选分辨率
                    parts = line.strip().split()
                    for part in parts:
                        if 'x' in part and part.replace('x', '').isdigit():
                            # 同时获取显示器名称
                            display_name = None
                            for l in output.split('\n'):
                                if ' connected' in l and part in output.split('\n')[output.split('\n').index(l)+1]:
                                    display_name = l.split()[0]
                                    break
                            if display_name:
                                return f"{display_name}: {part}"
                            else:
                                return part
            
            # Qt的方法备选
            screen_geometry = QApplication.primaryScreen().geometry()
            return f"{screen_geometry.width()} x {screen_geometry.height()}"
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
            # 通过xwininfo命令获取颜色深度
            result = subprocess.run(['xwininfo', '-root'], capture_output=True, text=True)
            output = result.stdout
            
            for line in output.split('\n'):
                if 'Depth' in line:
                    return self.tr("{} bits").format(line.split(':')[1].strip())
            
            # 备选方案
            return self.tr("32 bits")
        except:
            return self.tr("32 bits")
    
    def get_refresh_rate(self):
        """获取刷新率"""
        try:
            # 通过xrandr命令获取刷新率
            result = subprocess.run(['xrandr'], capture_output=True, text=True)
            output = result.stdout
            
            for line in output.split('\n'):
                if '*' in line:  # 当前活跃模式
                    parts = line.strip().split()
                    for part in parts:
                        if 'Hz' in part:
                            return part
            
            # 备选方案
            return "60 Hz"
        except:
            return "60 Hz"
        
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
            # 获取网络接口列表
            net_if_addrs = psutil.net_if_addrs()
            
            # 通过lspci获取网络设备信息
            result = subprocess.run(['lspci'], capture_output=True, text=True)
            output = result.stdout
            net_lines = [line for line in output.split('\n') if 'Ethernet controller' in line or 'Network controller' in line]
            
            # 处理每个网络接口
            for iface in net_if_addrs:
                device = {'interface': iface}
                
                # 查找匹配的PCI信息
                for line in net_lines:
                    iface_mac = None
                    for addr in net_if_addrs[iface]:
                        if hasattr(addr, 'family') and addr.family == psutil.AF_LINK:
                            iface_mac = addr.address.lower().replace(':', '')
                            break
                            
                    if iface_mac and iface_mac in line.lower():
                        device['model'] = line.split(': ', 2)[-1]
                        break
                else:
                    device['model'] = self.tr("Unknown")
                    
                # 获取驱动信息
                try:
                    result = subprocess.run(['ethtool', '-i', iface], capture_output=True, text=True)
                    for line in result.stdout.split('\n'):
                        if line.startswith('driver:'):
                            device['driver'] = line.split(':')[1].strip()
                            break
                except:
                    device['driver'] = self.tr("Unknown")
                    
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
                                    result = subprocess.run(['modinfo ' + driver_name + ' | grep version'], 
                                                           shell=True, capture_output=True, text=True)
                                    if result.stdout:
                                        version = result.stdout.split(': ')[1].strip()
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
        gxde_logo_path = "/home/ocean/Desktop/软件/hardware-viewer/gxde-logo/gxde-logo.svg"
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
                color: #2980b9;
                text-decoration: underline;
                font-size: 14px;
            }
            QPushButton:hover { color: #3498db; }
            QPushButton:pressed { color: #1f6391; }
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

    # 设置全局样式
    app.setStyle("Fusion")
    
    window = HardwareManager()
    window.show()
    
    sys.exit(app.exec())
