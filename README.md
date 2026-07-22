# PulseDesk

PulseDesk 是一个基于 Electron + Python 开发的桌面心率悬浮挂件。直接连接蓝牙心率广播的手环或手表，将实时心率显示在桌面上，并同步支持 OBS 浏览器源接入，适合游戏玩家或主播在直播时展示实时心率。


## 环境要求

- **操作系统**：Windows 10 / 11（需要支持 BLE 蓝牙）
- **Node.js**：16.x 或以上版本
- **Python**：3.9 或以上版本

## 安装与配置

### 1. 克隆或下载本项目

```bash
git clone https://github.com/NanamiKite/Pulsedesk
cd Pulsedesk
```

### 2. 安装 Node.js 依赖

在项目根目录下执行：

```bash
npm install
```

### 3. 安装 Python 依赖

确保系统安装了 Python，并安装蓝牙与 WebSocket 相关依赖包：

```bash
pip install -r requirements.txt
```

### 4. 配置你的设备 MAC 地址

打开 `main.py` 文件，找到配置项，将 `WATCH_MAC` 修改为你自己手环/手表的蓝牙 MAC 地址：

```python
WATCH_MAC = "XX:XX:XX:XX:XX:XX"  # 替换为你手表的实际 MAC 地址
```

## 使用说明

在项目根目录下运行以下命令启动应用：

```bash
npm start
```

启动后：
1. 桌面会弹出一个透明的心率挂件。
2. Python 后台会自动搜寻并连接你设置的蓝牙设备。连接成功后，心率数字会实时刷新。
3. 鼠标悬停到挂件上点击齿轮图标，可以展开控制面板调整字体颜色、心脏颜色和挂件缩放比例。再次点击齿轮即可收起面板。

### 在 OBS 中使用(直接运行main.py即可)

1. 打开 OBS，在“来源”列表中添加一个 **浏览器** 来源。
2. 勾选“本地文件”，选择项目生成出来的 `obs_heart_rate.html`。
3. 宽度建议设置为 `300`，高度设置为 `200`，即可得到一个干净透明的心率挂件。

## 常见问题排查

- **提示端口被占用 (OSError: [Errno 10048])**：
  主程序在启动和退出时会自动清理 8765 端口。如果因异常崩溃导致端口依然被占用，可以打开 PowerShell 运行以下命令手动关闭残留进程：
  ```powershell
  taskkill /F /IM python.exe
  ```

- **搜寻不到蓝牙设备**：
  请确保电脑系统蓝牙已开启，且手环/手表已开启“心率广播”功能（例如在 Amazfit 手环设置中开启“运动心率广播”）。

## 许可协议

MIT License