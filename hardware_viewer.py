import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import os
import platform
from datetime import datetime

class Linux硬件驱动查看器:
    def __init__(self, 主窗口):
        self.主窗口 = 主窗口
        # 软件基本信息
        self.软件名称 = "硬件查看器"
        self.版本号 = "v1.0"
        self.主窗口.title(f"{self.软件名称}")
        self.主窗口.geometry("1300x900")
        self.主窗口.minsize(1000, 600)
        
        # 定义明暗配色方案
        self.配色方案 = {
            "浅色": {
                "主背景": "#f0f2f5",
                "卡片背景": "#ffffff",
                "文本背景": "#f8f9fa",
                "文本颜色": "#2d3748",
                "按钮正常": "#4285f4",
                "按钮hover": "#3367d6",
                "标签页未选中": "#e8eaed",
                "标签页选中": "#4285f4",
                "标签页文字": "#333333",
                "标签页选中文字": "white",
                "状态文字": "#666666",
                "滚动条背景": "#e8eaed",
                "滚动条轨道": "#f8f9fa",
                "标题颜色": "#1a365d"
            },
            "深色": {
                "主背景": "#1a1a2e",
                "卡片背景": "#24243e",
                "文本背景": "#2e2e4d",
                "文本颜色": "#e0e0ff",
                "按钮正常": "#4a6cf7",
                "按钮hover": "#3a5bdb",
                "标签页未选中": "#2d2d4a",
                "标签页选中": "#4a6cf7",
                "标签页文字": "#e0e0ff",
                "标签页选中文字": "white",
                "状态文字": "#b0b0cc",
                "滚动条背景": "#3d3d66",
                "滚动条轨道": "#2e2e4d",
                "标题颜色": "#a0a0ff"
            }
        }
        
        # 当前主题模式
        self.当前模式 = tk.StringVar(value="跟随系统")
        self.系统深色模式 = self.检测系统深色模式()
        self.当前配色 = self.配色方案["深色"] if self.系统深色模式 else self.配色方案["浅色"]
        self.主窗口.configure(bg=self.当前配色["主背景"])

        # 检查系统是否为 Linux
        if platform.system() != "Linux":
            messagebox.showerror("错误", "该程序仅支持 Linux 系统！")
            self.主窗口.quit()
            return

        # 初始化UI
        self.创建界面()
        # 首次加载硬件信息
        self.刷新所有信息()

    def 检测系统深色模式(self):
        """检测Linux系统是否为深色模式"""
        try:
            # 读取GTK3设置
            gtk3_settings = os.path.expanduser("~/.config/gtk-3.0/settings.ini")
            if os.path.exists(gtk3_settings):
                with open(gtk3_settings, "r", encoding="utf-8") as f:
                    if "gtk-application-prefer-dark-theme=1" in f.read():
                        return True
            
            # 读取GTK4设置
            gtk4_settings = os.path.expanduser("~/.config/gtk-4.0/settings.ini")
            if os.path.exists(gtk4_settings):
                with open(gtk4_settings, "r", encoding="utf-8") as f:
                    if "gtk-application-prefer-dark-theme=1" in f.read():
                        return True
            
            # 检测主题名称
            result = subprocess.run(
                ["xdg-settings", "get", "gtk-theme"],
                capture_output=True, encoding="utf-8", timeout=3
            ).stdout.strip().lower()
            if any(keyword in result for keyword in ["dark", "black", "night", "oled"]):
                return True
            
            # 检测KDE主题
            kde_settings = os.path.expanduser("~/.config/kdeglobals")
            if os.path.exists(kde_settings):
                with open(kde_settings, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "[General]" in content and "ColorScheme=Breeze-Dark" in content:
                        return True
            
            return False
        except Exception:
            return False

    def 切换主题模式(self):
        """切换主题模式"""
        模式 = self.当前模式.get()
        if 模式 == "跟随系统":
            self.系统深色模式 = self.检测系统深色模式()
            self.当前配色 = self.配色方案["深色"] if self.系统深色模式 else self.配色方案["浅色"]
        elif 模式 == "浅色":
            self.当前配色 = self.配色方案["浅色"]
        elif 模式 == "深色":
            self.当前配色 = self.配色方案["深色"]
        
        self.更新界面配色()

    def 更新界面配色(self):
        """更新所有UI组件的配色"""
        # 主窗口背景
        self.主窗口.configure(bg=self.当前配色["主背景"])
        
        # 顶部控制栏
        self.控制框架.configure(bg=self.当前配色["主背景"])
        self.控制内层框架.configure(bg=self.当前配色["卡片背景"])
        
        # 刷新按钮
        self.刷新按钮.configure(
            bg=self.当前配色["按钮正常"],
            fg="white"
        )
        self.刷新按钮.bind("<Enter>", lambda e: self.刷新按钮.config(bg=self.当前配色["按钮hover"]))
        self.刷新按钮.bind("<Leave>", lambda e: self.刷新按钮.config(bg=self.当前配色["按钮正常"]))
        
        # 状态标签
        self.状态标签.configure(
            bg=self.当前配色["卡片背景"],
            fg=self.当前配色["状态文字"]
        )
        
        # 主题选择控件
        self.主题标签.configure(
            bg=self.当前配色["卡片背景"],
            fg=self.当前配色["文本颜色"]
        )
        for btn in self.主题单选按钮:
            btn.configure(
                bg=self.当前配色["卡片背景"],
                fg=self.当前配色["文本颜色"],
                selectcolor=self.当前配色["卡片背景"]
            )
        
        # 标签页样式
        self.样式.configure("TNotebook", background=self.当前配色["主背景"], borderwidth=0)
        self.样式.configure(
            "TNotebook.Tab",
            background=self.当前配色["标签页未选中"],
            foreground=self.当前配色["标签页文字"],
        )
        self.样式.map(
            "TNotebook.Tab",
            background=[("selected", self.当前配色["标签页选中"])],
            foreground=[("selected", self.当前配色["标签页选中文字"])]
        )
        
        # 所有标签页内容区域
        for 文本区域 in self.标签页.values():
            卡片框架 = 文本区域.master
            卡片框架.configure(bg=self.当前配色["卡片背景"])
            
            文本区域.configure(
                bg=self.当前配色["文本背景"],
                fg=self.当前配色["文本颜色"],
                insertbackground=self.当前配色["标签页选中"]
            )
            文本区域.vbar.configure(
                bg=self.当前配色["滚动条背景"],
                troughcolor=self.当前配色["滚动条轨道"],
                borderwidth=0
            )
        
        # 关于页面标题颜色更新
        self.标签页["关于"].tag_config("title", foreground=self.当前配色["标题颜色"])
        
        self.主窗口.update_idletasks()

    def 创建界面(self):
        """创建完整UI界面"""
        # 顶部控制面板
        self.控制框架 = ttk.Frame(self.主窗口, padding="15")
        self.控制框架.pack(fill=tk.X, side=tk.TOP, padx=20, pady=15)
        
        # 控制栏内层卡片
        self.控制内层框架 = tk.Frame(self.控制框架, bg=self.当前配色["卡片背景"], bd=0, relief=tk.RAISED)
        self.控制内层框架.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # 刷新按钮
        self.刷新按钮 = tk.Button(
            self.控制内层框架, 
            text="🔄 刷新硬件信息", 
            command=self.刷新所有信息,
            font=("微软雅黑", 11, "bold"),
            bg=self.当前配色["按钮正常"],
            fg="white",
            bd=0,
            relief=tk.FLAT,
            padx=20,
            pady=8,
            cursor="hand2"
        )
        self.刷新按钮.pack(side=tk.LEFT, padx=15, pady=8)

        # 主题切换控件组
        主题控制框架 = tk.Frame(self.控制内层框架, bg=self.当前配色["卡片背景"])
        主题控制框架.pack(side=tk.RIGHT, padx=15, pady=8)
        
        self.主题标签 = tk.Label(
            主题控制框架,
            text="主题模式：",
            font=("微软雅黑", 10),
            bg=self.当前配色["卡片背景"],
            fg=self.当前配色["文本颜色"]
        )
        self.主题标签.pack(side=tk.LEFT, padx=5)
        
        self.主题单选按钮 = []
        for 模式 in ["浅色", "深色", "跟随系统"]:
            btn = tk.Radiobutton(
                主题控制框架,
                text=模式,
                variable=self.当前模式,
                value=模式,
                command=self.切换主题模式,
                font=("微软雅黑", 10),
                bg=self.当前配色["卡片背景"],
                fg=self.当前配色["文本颜色"],
                selectcolor=self.当前配色["卡片背景"],
                bd=0
            )
            btn.pack(side=tk.LEFT, padx=5)
            self.主题单选按钮.append(btn)

        # 状态标签
        self.状态标签 = tk.Label(
            self.控制内层框架, 
            text=f"上次更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            font=("微软雅黑", 10),
            bg=self.当前配色["卡片背景"],
            fg=self.当前配色["状态文字"]
        )
        self.状态标签.pack(side=tk.RIGHT, padx=15, pady=8)

        # 标签页容器
        self.标签页容器 = ttk.Notebook(self.主窗口)
        self.标签页容器.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        self.设置样式()

        # 创建标签页（包含关于页）
        self.标签页 = {
            "系统概览": self.创建标签页("系统概览"),
            "CPU信息": self.创建标签页("CPU信息"),
            "内存信息": self.创建标签页("内存信息"),
            "磁盘信息": self.创建标签页("磁盘信息"),
            "网卡信息": self.创建标签页("网卡信息"),
            "PCI设备(驱动)": self.创建标签页("PCI设备(驱动)"),
            "USB设备(驱动)": self.创建标签页("USB设备(驱动)"),
            "显卡信息": self.创建标签页("显卡信息"),
            "关于": self.创建标签页("关于", is_about=True)  # 关于页特殊处理
        }

        # 初始化关于页面内容
        self.初始化关于页面()

    def 设置样式(self):
        """配置UI组件样式"""
        self.样式 = ttk.Style()
        self.样式.configure("TNotebook", background=self.当前配色["主背景"], borderwidth=0)
        self.样式.configure(
            "TNotebook.Tab",
            font=("微软雅黑", 11),
            padding=(20, 8),
            background=self.当前配色["标签页未选中"],
            foreground=self.当前配色["标签页文字"],
            borderwidth=0
        )
        self.样式.map(
            "TNotebook.Tab",
            background=[("selected", self.当前配色["标签页选中"])],
            foreground=[("selected", self.当前配色["标签页选中文字"])]
        )

    def 创建标签页(self, 标签页名称, is_about=False):
        """创建单个标签页（硬件页默认可编辑，关于页默认禁用编辑）"""
        标签页 = ttk.Frame(self.标签页容器)
        self.标签页容器.add(标签页, text=标签页名称)
        
        # 卡片式内层框架
        卡片框架 = tk.Frame(标签页, bg=self.当前配色["卡片背景"], bd=0, relief=tk.RAISED)
        卡片框架.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 滚动文本区域（硬件页默认可编辑，关于页默认禁用）
        文本区域 = scrolledtext.ScrolledText(
            卡片框架,
            font=("微软雅黑", 10),
            wrap=tk.WORD,
            bg=self.当前配色["文本背景"],
            fg=self.当前配色["文本颜色"],
            bd=0,
            relief=tk.FLAT,
            padx=15,
            pady=15,
            highlightthickness=0,
            insertbackground=self.当前配色["标签页选中"],
            state=tk.DISABLED if is_about else tk.NORMAL  # 关键修复：硬件页默认可编辑
        )
        # 滚动条美化
        文本区域.vbar.configure(
            bg=self.当前配色["滚动条背景"],
            troughcolor=self.当前配色["滚动条轨道"],
            borderwidth=0
        )
        文本区域.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        return 文本区域

    def 初始化关于页面(self):
        """初始化关于页面内容"""
        关于内容 = [
            f"{'='*60}\n",
            f"{self.软件名称} {self.版本号}\n",
            f"{'='*60}\n\n",
            
            "📝 软件描述：\n",
            "本工具专为Linux系统设计，提供硬件及驱动信息的可视化查看功能。\n",
            "支持系统概览、CPU、内存、磁盘、网卡、PCI设备、USB设备\n",
            "和显卡等硬件信息的展示，并提供明暗主题切换功能。\n\n",
            
            "✨ 功能特点：\n",
            "- 全面的硬件信息采集与展示\n",
            "- 自动检测系统主题并适配\n",
            "- 支持手动切换明暗主题\n",
            "- 信息实时刷新功能\n",
            "- 中文友好的界面与信息展示\n\n",
            
            "🙏 开源致谢：\n",
            "本软件基于以下开源技术构建：\n",
            "- Python 编程语言 (https://www.python.org/)\n",
            "- Tkinter GUI 库 (Python标准库)\n",
            "- Linux 系统工具 (lspci, lsusb, df 等)\n\n",
            
            "📄 开源协议：\n",
            "无 \n\n",
            
            "💡 使用提示：\n",
            "部分硬件信息需要管理员权限才能完整显示，\n",
            "建议使用 sudo 命令运行本程序以获取完整信息。\n",
            f"{'='*60}\n"
        ]
        
        # 关于页临时启用编辑状态插入内容
        self.标签页["关于"].config(state=tk.NORMAL)
        self.标签页["关于"].delete(1.0, tk.END)
        self.标签页["关于"].insert(tk.END, ''.join(关于内容))
        
        # 设置标题行样式
        self.标签页["关于"].tag_config("title", foreground=self.当前配色["标题颜色"], font=("微软雅黑", 12, "bold"))
        self.标签页["关于"].tag_add("title", "1.0", "2.0")  # 软件名称行
        self.标签页["关于"].tag_add("title", "4.0", "5.0")  # 软件描述标题
        self.标签页["关于"].tag_add("title", "9.0", "10.0") # 功能特点标题
        self.标签页["关于"].tag_add("title", "15.0", "16.0")# 开源致谢标题
        self.标签页["关于"].tag_add("title", "21.0", "22.0")# 开源协议标题
        self.标签页["关于"].tag_add("title", "24.0", "25.0")# 使用提示标题
        
        # 关于页重新禁用编辑
        self.标签页["关于"].config(state=tk.DISABLED)

    def 执行命令(self, 命令):
        """执行Linux系统命令"""
        try:
            结果 = subprocess.run(
                命令,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                timeout=10
            )
            return 结果.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"命令执行失败：{e.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return "命令执行超时"
        except Exception as e:
            return f"执行错误：{str(e)}"

    def 获取系统概览(self):
        """获取系统基础信息"""
        信息 = ["=" * 60, "📊 系统概览".center(60), "=" * 60]
        
        # 操作系统版本
        系统信息 = self.执行命令("cat /etc/os-release | grep -E 'PRETTY_NAME|VERSION_ID'")
        信息.append("💻 操作系统版本：")
        信息.append(系统信息.replace("PRETTY_NAME=", "系统名称：").replace("VERSION_ID=", "版本号："))
        
        # 内核版本
        信息.append(f"\n内核版本：{self.执行命令('uname -r')}")
        
        # 主机名
        信息.append(f"主机名：{self.执行命令('hostname')}")
        
        # 运行时间
        运行时间 = self.执行命令("uptime -p")
        信息.append(f"系统运行时间：{运行时间.replace('up ', '已运行 ')}")
        
        return "\n".join(信息)

    def 获取CPU信息(self):
        """获取CPU详细信息"""
        信息 = ["=" * 60, "CPU 详细信息".center(60), "=" * 60]
        
        cpu原始信息 = self.执行命令("cat /proc/cpuinfo")
        字段映射 = {
            "model name": "CPU型号",
            "cpu cores": "物理核心数",
            "siblings": "逻辑核心数",
            "vendor_id": "厂商ID",
            "cpu MHz": "主频（MHz）",
            "cache size": "缓存大小"
        }
        
        for 行 in cpu原始信息.split("\n"):
            行 = 行.strip()
            for 英文字段, 中文字段 in 字段映射.items():
                if 行.startswith(英文字段):
                    信息.append(行.replace(英文字段 + ":", f"🔧 {中文字段}："))
                    break
        
        # 去重
        唯一信息 = []
        已存在 = set()
        for 行 in 信息:
            if 行 not in 已存在:
                已存在.add(行)
                唯一信息.append(行)
        
        return "\n".join(唯一信息)

    def 获取内存信息(self):
        """获取内存信息"""
        信息 = ["=" * 60, "🧠 内存 详细信息".center(60), "=" * 60]
        
        内存原始信息 = self.执行命令("cat /proc/meminfo")
        字段映射 = {
            "MemTotal": "总内存",
            "MemFree": "空闲内存",
            "MemAvailable": "可用内存",
            "Buffers": "缓冲区大小",
            "Cached": "缓存大小",
            "SwapTotal": "交换分区总大小",
            "SwapFree": "交换分区空闲大小"
        }
        
        for 行 in 内存原始信息.split("\n"):
            行 = 行.strip()
            for 英文字段, 中文字段 in 字段映射.items():
                if 行.startswith(英文字段):
                    字段值 = 行.split(":", 1)[1].strip()
                    if "kB" in 字段值:
                        kb数值 = int(字段值.split()[0])
                        gb数值 = round(kb数值 / 1024 / 1024, 2)
                        信息.append(f"📝 {中文字段}：{gb数值} GB （原始：{字段值}）")
                    else:
                        信息.append(f"📝 {中文字段}：{字段值}")
                    break
        
        return "\n".join(信息)

    def 获取磁盘信息(self):
        """获取磁盘信息"""
        信息 = ["=" * 60, "💾 磁盘 详细信息".center(60), "=" * 60]
        
        # 磁盘分区列表
        信息.append("📂 一、磁盘分区列表：")
        磁盘分区信息 = self.执行命令("lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL")
        表头映射 = {"NAME": "设备名", "SIZE": "大小", "TYPE": "设备类型", "MOUNTPOINT": "挂载点", "MODEL": "设备型号"}
        分区行 = 磁盘分区信息.split("\n")
        if 分区行:
            分区行[0] = 分区行[0].strip()
            for 英文表头, 中文表头 in 表头映射.items():
                分区行[0] = 分区行[0].replace(英文表头, 中文表头)
            信息.append("\n".join(分区行))
        
        # 磁盘使用率
        信息.append("\n" + "=" * 40)
        信息.append("📊 二、磁盘使用率：")
        磁盘使用率 = self.执行命令("df -h --output=source,fstype,size,used,avail,pcent,target")
        使用率表头映射 = {"source": "设备路径", "fstype": "文件系统", "size": "总大小", "used": "已用空间", "avail": "可用空间", "pcent": "使用率", "target": "挂载点"}
        使用率行 = 磁盘使用率.split("\n")
        if 使用率行:
            使用率行[0] = 使用率行[0].strip()
            for 英文表头, 中文表头 in 使用率表头映射.items():
                使用率行[0] = 使用率行[0].replace(英文表头, 中文表头)
            信息.append("\n".join(使用率行))
        
        return "\n".join(信息)

    def 获取网卡信息(self):
        """获取网卡信息"""
        信息 = ["=" * 60, "📡 网卡 详细信息".center(60), "=" * 60]
        
        # 网卡设备列表
        信息.append("🔌 一、网卡设备列表：")
        信息.append(self.执行命令("cat /proc/net/dev | grep -v 'lo' | grep -v 'face'"))
        
        # IP地址与MAC地址
        信息.append("\n" + "=" * 40)
        信息.append("🌐 二、IP地址与MAC地址：")
        ip信息 = self.执行命令("ip addr show | grep -E 'inet |link/ether' | grep -v 'lo'")
        信息.append(ip信息.replace("inet ", "IP地址：").replace("link/ether ", "MAC地址："))
        
        # 网卡驱动信息
        信息.append("\n" + "=" * 40)
        信息.append("    三、网卡驱动信息：")
        if os.path.exists("/sys/class/net"):
            网卡目录 = [d for d in os.listdir("/sys/class/net") if d != "lo"]
            for 网卡名 in 网卡目录:
                驱动路径 = f"/sys/class/net/{网卡名}/device/driver/module"
                if os.path.exists(驱动路径) and os.path.islink(驱动路径):
                    驱动名称 = os.path.basename(os.readlink(驱动路径))
                    信息.append(f"网卡 {网卡名} → 使用驱动：{驱动名称}")
                else:
                    信息.append(f"网卡 {网卡名} → 驱动：未知")
        else:
            信息.append("无法获取网卡驱动目录")
        
        return "\n".join(信息)

    def 获取PCI设备信息(self):
        """获取PCI设备信息"""
        信息 = ["=" * 60, "🔌 PCI设备及驱动信息".center(60), "=" * 60]
        
        # 检查pciutils是否安装
        if self.执行命令("which lspci") == "":
            信息.append("错误：未安装 pciutils 工具！")
            信息.append("请在终端执行：sudo apt install -y pciutils （Ubuntu/Debian系列）")
            信息.append("或：sudo yum install -y pciutils （CentOS/RHEL系列）")
            信息.append("或：sudo dnf install -y pciutils （Fedora系列）")
            return "\n".join(信息)
        
        # 获取PCI设备及驱动
        pci原始信息 = self.执行命令("lspci -v | grep -E 'Device|Kernel driver in use'")
        行列表 = pci原始信息.split("\n")
        
        for i in range(0, len(行列表), 2):
            if i+1 < len(行列表):
                设备名 = 行列表[i].strip().replace("Device:", "设备名称：")
                驱动名 = 行列表[i+1].strip().replace("Kernel driver in use:", "使用驱动：")
                信息.append(f"\n{设备名}")
                信息.append(f"{驱动名}")
        
        return "\n".join(信息)

    def 获取USB设备信息(self):
        """获取USB设备信息"""
        信息 = ["=" * 60, "USB设备及驱动信息".center(60), "=" * 60]
        
        # 检查usbutils是否安装
        if self.执行命令("which lsusb") == "":
            信息.append("错误：未安装 usbutils 工具！")
            信息.append("请在终端执行：sudo apt install -y usbutils （Ubuntu/Debian系列）")
            信息.append("或：sudo yum install -y usbutils （CentOS/RHEL系列）")
            信息.append("或：sudo dnf install -y usbutils （Fedora系列）")
            return "\n".join(信息)
        
        # 获取USB设备关键信息
        usb原始信息 = self.执行命令("lsusb -v | grep -E 'Bus |Device Descriptor|idVendor|idProduct|iProduct|Driver='")
        usb原始信息 = usb原始信息.replace("Bus ", "总线：").replace("Device Descriptor:", "设备描述符：")
        usb原始信息 = usb原始信息.replace("idVendor", "厂商ID").replace("idProduct", "产品ID")
        usb原始信息 = usb原始信息.replace("iProduct", "产品名称").replace("Driver=", "驱动：")
        
        信息.append(usb原始信息)
        return "\n".join(信息)

    def 获取显卡信息(self):
        """获取显卡信息"""
        信息 = ["=" * 60, "显卡 详细信息".center(60), "=" * 60]
        
        # 检查pciutils是否安装
        if self.执行命令("which lspci") == "":
            信息.append("错误：未安装 pciutils 工具！")
            信息.append("请在终端执行：sudo apt install -y pciutils （Ubuntu/Debian系列）")
            信息.append("或：sudo yum install -y pciutils （CentOS/RHEL系列）")
            信息.append("或：sudo dnf install -y pciutils （Fedora系列）")
            return "\n".join(信息)
        
        # 显卡设备
        显卡设备 = self.执行命令("lspci | grep -iE 'vga|3d|display'")
        信息.append("一、显卡设备：")
        信息.append(显卡设备 if 显卡设备 else "未检测到独立显卡（可能使用核显）")
        
        # 显卡驱动
        信息.append("\n" + "=" * 40)
        信息.append("二、显卡驱动信息：")
        显卡驱动 = self.执行命令("lspci -v | grep -A 10 -iE 'vga|3d|display' | grep 'Kernel driver in use'")
        if 显卡驱动:
            信息.append(显卡驱动.replace("Kernel driver in use:", "使用的内核驱动："))
        else:
            信息.append("未获取到显卡驱动信息（尝试用 sudo 运行程序获取完整权限）")
        
        return "\n".join(信息)

    def 刷新所有信息(self):
        """刷新所有硬件信息（核心修复：确保内容可插入）"""
        # 更新最后更新时间
        当前时间 = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.状态标签.config(text=f"上次更新：{当前时间}")
        self.主窗口.update_idletasks()
        
        try:
            # 硬件标签页列表（排除关于页）
            硬件标签页 = [key for key in self.标签页 if key != "关于"]
            
            # 逐个更新硬件标签页内容
            self.标签页["系统概览"].delete(1.0, tk.END)
            self.标签页["系统概览"].insert(tk.END, self.获取系统概览())
            
            self.标签页["CPU信息"].delete(1.0, tk.END)
            self.标签页["CPU信息"].insert(tk.END, self.获取CPU信息())
            
            self.标签页["内存信息"].delete(1.0, tk.END)
            self.标签页["内存信息"].insert(tk.END, self.获取内存信息())
            
            self.标签页["磁盘信息"].delete(1.0, tk.END)
            self.标签页["磁盘信息"].insert(tk.END, self.获取磁盘信息())
            
            self.标签页["网卡信息"].delete(1.0, tk.END)
            self.标签页["网卡信息"].insert(tk.END, self.获取网卡信息())
            
            self.标签页["PCI设备(驱动)"].delete(1.0, tk.END)
            self.标签页["PCI设备(驱动)"].insert(tk.END, self.获取PCI设备信息())
            
            self.标签页["USB设备(驱动)"].delete(1.0, tk.END)
            self.标签页["USB设备(驱动)"].insert(tk.END, self.获取USB设备信息())
            
            self.标签页["显卡信息"].delete(1.0, tk.END)
            self.标签页["显卡信息"].insert(tk.END, self.获取显卡信息())
            
            # 硬件页内容插入后设置为只读（可选，防止误编辑）
            for 标签页名称 in 硬件标签页:
                self.标签页[标签页名称].config(state=tk.DISABLED)
            
        except Exception as e:
            messagebox.showerror("刷新失败", f"获取硬件信息时出错：{str(e)}")
            # 出错时恢复编辑状态，方便调试
            for 标签页名称 in 硬件标签页:
                self.标签页[标签页名称].config(state=tk.NORMAL)

if __name__ == "__main__":
    根窗口 = tk.Tk()
    应用 = Linux硬件驱动查看器(根窗口)
    根窗口.mainloop()