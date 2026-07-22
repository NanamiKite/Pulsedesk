#  Amazfit OBS Heart Rate Overlay
> 华米（Amazfit）手环 / 手表 实时心率 OBS 直播挂件
适用于华米智能穿戴设备
基于 Python 的轻量级 OBS 心率挂件服务。通过蓝牙心率广播采集实时获取华米手表的实时心率数据推送给obs浏览源插件

## 🛠️ 环境准备

### 1. Python 环境
需安装 **Python 3.8+**。

### 2. 安装依赖库
在终端中运行以下命令安装必需的第三方库：

```bash
pip install bleak websockets