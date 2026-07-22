import asyncio
import threading
import websockets
import json
import os
from bleak import BleakClient

# ==================== 1. 配置项 ====================
WATCH_MAC = ""  #  请在此处替换为你手表的实际 MAC 地址
CHARACTERISTIC_UUID = "00002a37-0000-1000-8000-00805f9b34fb"  # 标准 BLE 心率特征 UUID
HOST = "127.0.0.1"  # 强制使用 127.0.0.1，避免 IPv6 端口占用冲突
PORT = 8765

latest_heart_rate = "--"
connected_clients = set()

# ==================== 2. 悬浮窗 HTML 界面模板 ====================
HTML_CONTENT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>PulseDesk Overlay</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background: transparent;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            overflow: hidden;
            user-select: none;
            padding: 10px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        /* 1. 主胶囊挂件 */
        .hr-capsule {
            display: inline-flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            width: 100%;
            padding: 8px 16px;
            background: rgba(18, 18, 22, 0.75);
            backdrop-filter: blur(12px);
            border-radius: 40px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
            -webkit-app-region: drag; /* 允许鼠标拖动窗口 */
            cursor: move;
            transition: all 0.2s ease;
            transform-origin: center top;
        }

        .hr-left {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        /* 🌟 SVG 心脏图标：支持平滑染色与动画 */
        .heart-svg {
            width: 22px;
            height: 22px;
            fill: #ff4d4d; /* 默认红色 */
            animation: pulse 1s infinite alternate;
            transition: fill 0.2s ease, width 0.1s ease, height 0.1s ease;
        }

        @keyframes pulse {
            0% { transform: scale(1); }
            100% { transform: scale(1.18); }
        }

        /* 心率数值与单位 */
        .hr-value { 
            font-size: 26px; 
            font-weight: 800; 
            color: #ffffff; 
            transition: font-size 0.1s ease, color 0.2s ease;
        }
        .unit { 
            font-size: 11px; 
            color: #aaaaaa; 
            font-weight: 600; 
            transition: font-size 0.1s ease;
        }

        /* ⚙️ 设置齿轮 */
        .settings-btn {
            opacity: 0;
            font-size: 14px;
            cursor: pointer;
            transition: opacity 0.2s ease, transform 0.2s ease;
            -webkit-app-region: no-drag;
            color: #ffffff;
        }
        .hr-capsule:hover .settings-btn { opacity: 0.8; }
        .settings-btn:hover { opacity: 1 !important; transform: rotate(45deg); }

        /* 2. 控制面板 */
        .controls-panel {
            display: none;
            width: 100%;
            margin-top: 8px;
            background: rgba(28, 28, 35, 0.92);
            backdrop-filter: blur(16px);
            padding: 10px 14px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            font-size: 12px;
            color: #ccc;
            -webkit-app-region: no-drag;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        }

        .controls-panel label {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 6px 0;
        }

        .controls-panel input[type="color"] {
            border: none;
            width: 22px;
            height: 22px;
            cursor: pointer;
            background: transparent;
        }

        .controls-panel input[type="range"] {
            width: 90px;
            cursor: pointer;
        }
    </style>
</head>
<body>

    <!-- 主悬浮胶囊 -->
    <div class="hr-capsule" id="capsule">
        <div class="hr-left">
            <!-- 🌟 用标准 SVG 替代 Emoji，完美支持 Fill 填充染色 -->
            <svg class="heart-svg" id="heartSvg" viewBox="0 0 24 24">
                <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
            <div>
                <span class="hr-value" id="hr">--</span>
                <span class="unit" id="unitText">BPM</span>
            </div>
        </div>
        <div class="settings-btn" title="设置" onclick="toggleSettings(event)">⚙️</div>
    </div>

    <!-- 控制面板 -->
    <div class="controls-panel" id="controls">
        <label>挂件大小: <input type="range" id="sizeRange" min="0.7" max="1.8" step="0.1" value="1" oninput="updateStyles()"></label>
        <label>文字颜色: <input type="color" id="textColor" value="#ffffff" onchange="updateStyles()"></label>
        <label>心脏颜色: <input type="color" id="heartColor" value="#ff4d4d" onchange="updateStyles()"></label>
    </div>

    <script>
        let ipcRenderer = null;
        try {
            ipcRenderer = require('electron').ipcRenderer;
        } catch (e) {
            console.log("Running in standard browser environment");
        }

        const ws = new WebSocket('ws://127.0.0.1:8765');
        const hrEl = document.getElementById('hr');
        const heartSvg = document.getElementById('heartSvg');
        const unitEl = document.getElementById('unitText');
        const controls = document.getElementById('controls');

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.hr) {
                hrEl.textContent = data.hr;
            }
        };

        function toggleSettings(e) {
            e.stopPropagation();
            const isHidden = controls.style.display === 'none' || !controls.style.display;
            
            if (isHidden) {
                controls.style.display = 'block';
                if (ipcRenderer) ipcRenderer.send('resize-window', true);
            } else {
                controls.style.display = 'none';
                if (ipcRenderer) ipcRenderer.send('resize-window', false);
            }
        }

        // 🌟 实时更新样式：SVG Fill 染色 + 等比例缩放大小
        function updateStyles() {
            const scale = parseFloat(document.getElementById('sizeRange').value);
            
            // 1. 等比例调整字体和 SVG 尺寸
            hrEl.style.fontSize = (26 * scale) + 'px';
            unitEl.style.fontSize = (11 * scale) + 'px';
            
            const svgSize = (22 * scale) + 'px';
            heartSvg.style.width = svgSize;
            heartSvg.style.height = svgSize;

            // 2. 颜色更新 (SVG 采用 fill 属性进行纯正染色)
            hrEl.style.color = document.getElementById('textColor').value;
            heartSvg.style.fill = document.getElementById('heartColor').value;
        }
    </script>
</body>
</html>
"""

# 写入 html 文件
with open("obs_heart_rate.html", "w", encoding="utf-8") as f:
    f.write(HTML_CONTENT)


# ==================== 3. 蓝牙与 WebSocket 逻辑 ====================

async def register(websocket):
    connected_clients.add(websocket)
    try:
        await websocket.send(json.dumps({"hr": latest_heart_rate}))
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)

async def notify_clients(hr):
    global latest_heart_rate
    latest_heart_rate = hr
    if connected_clients:
        message = json.dumps({"hr": hr})
        await asyncio.gather(*[client.send(message) for client in connected_clients], return_exceptions=True)

def notification_handler(sender, data):
    flags = data[0]
    hr = data[1] if (flags & 0x01) == 0 else int.from_bytes(data[1:3], byteorder='little')
    print(f"[HR]: {hr} BPM")
    asyncio.run_coroutine_threadsafe(notify_clients(hr), MAIN_LOOP)

async def robust_bluetooth_loop():
    while True:
        try:
            print(f"[BLE] Searching for device: {WATCH_MAC}")
            async with BleakClient(WATCH_MAC) as client:
                print(f"[BLE] Connected successfully!")
                await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
                while client.is_connected:
                    await asyncio.sleep(1)
        except Exception as e:
            print(f"[BLE Error]: {e}, retrying in 2s...")
            await asyncio.sleep(2)

async def main_coro():
    async with websockets.serve(register, HOST, PORT):
        print(f"[WebSocket] Server started at ws://{HOST}:{PORT}")
        await robust_bluetooth_loop()

def start_backend_service():
    global MAIN_LOOP
    MAIN_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(MAIN_LOOP)
    MAIN_LOOP.run_until_complete(main_coro())

if __name__ == "__main__":
    start_backend_service()