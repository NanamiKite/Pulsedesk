import asyncio
import json
import os
import threading
import time
import websockets
from bleak import BleakClient, BleakScanner

# ----------------- 配置区域 -----------------
WATCH_MAC = ""  # 你的华米手表 MAC 地址
PORT = 8765
# --------------------------------------------

HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# OBS 挂件界面 HTML
HTML_CONTENT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>OBS 华米心率挂件</title>
    <style>
        :root { --text-color: #ffffff; --heart-color: #ff3b30; --font-size: 52px; }
        body {
            margin: 0; padding: 0; background: transparent;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            height: 100vh; overflow: hidden; color: var(--text-color);
        }
        .hr-container {
            display: flex; align-items: center; gap: 12px; padding: 10px 22px;
            border-radius: 16px; background: rgba(18, 18, 20, 0.55);
            backdrop-filter: blur(12px); box-shadow: 0 8px 24px rgba(0,0,0,0.25);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .heart-icon {
            width: calc(var(--font-size) * 0.9); height: calc(var(--font-size) * 0.9);
            fill: var(--heart-color); filter: drop-shadow(0 0 8px rgba(255, 59, 48, 0.4));
        }
        @keyframes pulse {
            0% { transform: scale(1); }
            14% { transform: scale(1.22); }
            28% { transform: scale(1); }
            42% { transform: scale(1.12); }
            70% { transform: scale(1); }
        }
        .beating { animation: pulse var(--beat-duration, 1s) infinite ease-in-out; transform-origin: center; }
        .hr-value { font-size: var(--font-size); font-weight: 800; font-variant-numeric: tabular-nums; }
        .unit { font-size: calc(var(--font-size) * 0.35); font-weight: 600; opacity: 0.8; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background-color: #ff9500; display: inline-block; }
        .status-dot.online { background-color: #34c759; }
        .status-dot.offline { background-color: #ff3b30; }
        .controls {
            position: absolute; bottom: 10px; display: flex; align-items: center; gap: 12px;
            background: rgba(0, 0, 0, 0.85); padding: 8px 14px; border-radius: 8px; font-size: 12px; transition: opacity 0.3s;
        }
        .controls:hover { opacity: 1 !important; }
        input { cursor: pointer; }
    </style>
</head>
<body>
    <div class="hr-container">
        <svg class="heart-icon" id="heart" viewBox="0 0 24 24">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
        </svg>
        <span class="hr-value" id="hr-text">--</span>
        <span class="unit">BPM</span>
    </div>
    <div class="controls" id="controls">
        <span id="dot" class="status-dot offline"></span>
        <label>文字: <input type="color" id="text-color-picker" value="#ffffff"></label>
        <label>心脏: <input type="color" id="heart-color-picker" value="#ff3b30"></label>
        <label>字号: <input type="range" id="size-picker" min="28" max="96" value="52"></label>
    </div>
    <script>
        const hrText = document.getElementById('hr-text');
        const heart = document.getElementById('heart');
        const dot = document.getElementById('dot');

        document.getElementById('text-color-picker').addEventListener('input', (e) => document.documentElement.style.setProperty('--text-color', e.target.value));
        document.getElementById('heart-color-picker').addEventListener('input', (e) => document.documentElement.style.setProperty('--heart-color', e.target.value));
        document.getElementById('size-picker').addEventListener('input', (e) => document.documentElement.style.setProperty('--font-size', e.target.value + 'px'));
        setTimeout(() => { document.getElementById('controls').style.opacity = '0.25'; }, 5000);

        function connectWS() {
            const ws = new WebSocket('ws://localhost:8765');
            ws.onopen = () => { dot.className = "status-dot online"; };
            ws.onmessage = (event) => {
                const rate = JSON.parse(event.data).hr;
                hrText.textContent = rate;
                if (rate > 0) {
                    document.documentElement.style.setProperty('--beat-duration', `${(60 / rate).toFixed(2)}s`);
                    if (!heart.classList.contains('beating')) heart.classList.add('beating');
                } else heart.classList.remove('beating');
            };
            ws.onclose = () => {
                dot.className = "status-dot offline"; hrText.textContent = "--";
                heart.classList.remove('beating'); setTimeout(connectWS, 1500);
            };
            ws.onerror = () => ws.close();
        }
        connectWS();
    </script>
</body>
</html>
"""

CONNECTED_CLIENTS = set()
MAIN_LOOP = None

async def ws_handler(websocket, *args):
    CONNECTED_CLIENTS.add(websocket)
    print("📺 OBS 挂件已连接！")
    try:
        await websocket.wait_closed()
    finally:
        CONNECTED_CLIENTS.remove(websocket)

async def notify_clients(hr_value):
    if CONNECTED_CLIENTS:
        message = json.dumps({"hr": hr_value})
        await asyncio.gather(*[client.send(message) for client in CONNECTED_CLIENTS], return_exceptions=True)

def on_hr_data_received(sender, data: bytearray):
    flags = data[0]
    hr = int.from_bytes(data[1:3], byteorder='little') if (flags & 0x01) else data[1]
    print(f"❤️ [实时心率] {hr} BPM")
    if MAIN_LOOP and MAIN_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(notify_clients(hr), MAIN_LOOP)

async def robust_bluetooth_loop():
    print(f"🔍 启动稳定型蓝牙引擎，目标: {WATCH_MAC}")
    
    while True:
        try:
            # 采用 5.0 秒全局扫描确保 Windows 能够真正搜寻到广播数据包
            print("正在搜索手表信号...")
            device = await BleakScanner.find_device_by_address(WATCH_MAC, timeout=5.0)
            
            if not device:
                print("⚠️ 未搜到手表信号，请确认：1.手表戴在手上 2.已开启心率广播 3.手机蓝牙已关闭")
                await asyncio.sleep(1.0)
                continue

            disconnected_event = asyncio.Event()

            def on_disconnect(client):
                print("⚠️ 物理信号中断，重新建立连接...")
                disconnected_event.set()

            print(" 发现手表，正在建立通信通道...")
            # 将握手超时延长到 15 秒，容忍信号抖动
            async with BleakClient(device, disconnected_callback=on_disconnect, timeout=15.0) as client:
                print("✅ 成功连接！心率数据同步中...")
                await client.start_notify(HR_MEASUREMENT_UUID, on_hr_data_received)
                await disconnected_event.wait()

        except Exception as e:
            print(f"⚠️ 蓝牙协议层异常: {e}，1 秒后重试...")
            await asyncio.sleep(1.0)

def start_backend_service():
    global MAIN_LOOP
    MAIN_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(MAIN_LOOP)

    async def main_coro():
        async with websockets.serve(ws_handler, "localhost", PORT):
            await robust_bluetooth_loop()

    MAIN_LOOP.run_until_complete(main_coro())

if __name__ == "__main__":
    html_file = os.path.join(SCRIPT_DIR, "obs_heart_rate.html")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)

    print("==========================================")
    print(" 华米心率 OBS 服务已启动")
    print(f" 挂件 HTML 文件: {html_file}")
    print("==========================================")

    backend_thread = threading.Thread(target=start_backend_service, daemon=True)
    backend_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n程序已正常退出。")