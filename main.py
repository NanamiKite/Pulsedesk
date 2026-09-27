import asyncio
import websockets
import json
import time
from pathlib import Path
from bleak import BleakClient

# ==================== 1. 配置项 ====================
DEVICE_CONFIG_PATH = Path(__file__).with_name("device_config.json")
try:
    with DEVICE_CONFIG_PATH.open(encoding="utf-8") as config_file:
        WATCH_MAC = json.load(config_file).get("watch_mac", "")
except FileNotFoundError:
    WATCH_MAC = ""
CHARACTERISTIC_UUID = "00002a37-0000-1000-8000-00805f9b34fb"  # 标准 BLE 心率特征 UUID
HOST = "127.0.0.1"  # 强制使用 127.0.0.1，避免 IPv6 端口占用冲突
PORT = 8765

latest_heart_rate = "--"
latest_reading_at = 0.0
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
            padding: 6px;
            width: max-content;
        }

        .overlay {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            width: max-content;
        }

        /* 1. 主胶囊挂件 */
        .hr-capsule {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            width: max-content;
            padding: 6px 10px;
            background: rgba(18, 18, 22, 0.75);
            backdrop-filter: blur(12px);
            border-radius: 40px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.25);
            -webkit-app-region: drag; /* 允许鼠标拖动窗口 */
            cursor: move;
            transform-origin: center top;
        }

        .hr-left {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        /* 按 BPM 播放的装饰波形，不代表真实心电数据。 */
        .heartbeat {
            --wave-color: #ff4d4d;
            width: 64px;
            height: 28px;
            flex-shrink: 0;
            color: #737780;
            transition: color 0.2s ease;
        }

        .heartbeat.is-live { color: var(--wave-color); }
        .wave-track { opacity: 0.45; }
        .heartbeat.is-live .wave-track { opacity: 1; }
        .reading { white-space: nowrap; }

        /* 心率数值与单位 */
        .hr-value { 
            font-size: 26px; 
            font-weight: 800; 
            font-variant-numeric: tabular-nums;
            color: #ffffff; 
            line-height: 1.2;
            transition: color 0.2s ease;
        }
        .unit { 
            font-size: 11px; 
            color: #aaaaaa; 
            font-weight: 600; 
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
            width: 240px;
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
    <div class="overlay" id="overlay">

    <!-- 主悬浮胶囊 -->
    <div class="hr-capsule" id="capsule">
        <div class="hr-left">
            <svg class="heartbeat" id="heartbeat" viewBox="0 0 64 28" role="img" aria-label="心跳波形：等待数据">
                <defs>
                    <linearGradient id="waveFade" x1="0" x2="64" gradientUnits="userSpaceOnUse">
                        <stop offset="0" stop-color="currentColor" stop-opacity="0.1"/>
                        <stop offset="0.5" stop-color="currentColor" stop-opacity="0.7"/>
                        <stop offset="1" stop-color="currentColor"/>
                    </linearGradient>
                </defs>
                <path id="wavePath" class="wave-track" d="M1 14 H63" fill="none" stroke="url(#waveFade)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div class="reading">
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
        <label>波形颜色: <input type="color" id="waveColor" value="#ff4d4d" oninput="updateStyles()"></label>
    </div>
    </div>

    <script>
        let ipcRenderer = null;
        try {
            ipcRenderer = require('electron').ipcRenderer;
        } catch (e) {
            console.log("Running in standard browser environment");
        }

        const hrEl = document.getElementById('hr');
        const heartbeat = document.getElementById('heartbeat');
        const unitEl = document.getElementById('unitText');
        const controls = document.getElementById('controls');
        const wavePath = document.getElementById('wavePath');
        const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
        let bpm = 60;
        let live = false;
        let frame = null;
        let previousFrame = null;
        let elapsed = 0;
        let sampleTime = 0;
        let phase = 0;
        const samples = [];
        const DATA_HOLD_MS = 30000; // 短暂断链时保留最后读数 30 秒。
        let lastHr = null;
        let lastReceivedAt = 0;
        let staleTimer;
        let holdTimer;

        // 每帧生成新采样点，历史波形持续向左移动；BPM 只决定波峰间隔。
        function drawWave(now) {
            frame = null;
            if (!live || reducedMotion.matches) return;
            const dt = previousFrame === null ? 0 : Math.min((now - previousFrame) / 1000, 0.1);
            previousFrame = now;
            elapsed += dt;
            while (sampleTime <= elapsed) {
                phase = (phase + bpm / 60 / 120) % 1;
                const bump = (center, width) => Math.exp(-0.5 * ((phase - center) / width) ** 2);
                const y = 14 - 2 * bump(0.16, 0.035) + 3 * bump(0.30, 0.016)
                    - 11 * bump(0.34, 0.015) + 9 * bump(0.39, 0.022) - 3 * bump(0.62, 0.065);
                samples.push({ time: sampleTime, y });
                sampleTime += 1 / 120;
            }
            while (samples.length && samples[0].time < elapsed - 1.5) samples.shift();
            wavePath.setAttribute('d', samples.map((point, index) =>
                (index ? 'L' : 'M') + (63 - (elapsed - point.time) * 44).toFixed(2)
                + ' ' + point.y.toFixed(2)).join(' '));
            frame = requestAnimationFrame(drawWave);
        }

        function startWave() {
            if (!live) {
                previousFrame = null;
            }
            live = true;
            if (frame === null && !reducedMotion.matches) frame = requestAnimationFrame(drawWave);
        }

        reducedMotion.addEventListener('change', () => {
            previousFrame = null;
            if (live && frame === null && !reducedMotion.matches) frame = requestAnimationFrame(drawWave);
        });

        // 测量实际内容，收起设置后不会留下透明的大窗口。
        const overlay = document.getElementById('overlay');
        new ResizeObserver(() => {
            const bounds = overlay.getBoundingClientRect();
            if (ipcRenderer) ipcRenderer.send('resize-window', {
                width: Math.ceil(bounds.width + 12), height: Math.ceil(bounds.height + 12)
            });
        }).observe(overlay);

        function showInactive(message) {
            clearTimeout(staleTimer);
            live = false;
            if (frame !== null) cancelAnimationFrame(frame);
            frame = null;
            heartbeat.classList.remove('is-live');
            heartbeat.setAttribute('aria-label', '心跳波形：' + message);
            const holding = lastHr !== null && Date.now() - lastReceivedAt < DATA_HOLD_MS;
            hrEl.textContent = holding ? lastHr : '--';
            hrEl.style.opacity = holding ? '0.65' : '1';
        }

        function connect() {
            const ws = new WebSocket('ws://127.0.0.1:8765');
            ws.onopen = () => showInactive('等待数据');
            ws.onmessage = (event) => {
                let data;
                try { data = JSON.parse(event.data); } catch { return; }
                const hr = data?.hr;
                if (!Number.isInteger(hr) || hr <= 0 || hr > 65535) {
                    showInactive('等待数据');
                    return;
                }
                hrEl.textContent = hr;
                hrEl.style.opacity = '1';
                lastHr = hr;
                lastReceivedAt = Date.now();
                heartbeat.classList.add('is-live');
                heartbeat.setAttribute('aria-label', '心跳波形：' + hr + ' BPM');
                bpm = hr;
                startWave();
                clearTimeout(staleTimer);
                staleTimer = setTimeout(() => showInactive('等待更新'), 10000);
                clearTimeout(holdTimer);
                holdTimer = setTimeout(() => {
                    lastHr = null;
                    samples.length = 0;
                    elapsed = sampleTime = phase = 0;
                    wavePath.setAttribute('d', 'M1 14 H63');
                    showInactive('暂无新数据');
                }, DATA_HOLD_MS);
            };
            ws.onerror = () => ws.close();
            ws.onclose = () => {
                showInactive('连接已断开');
                setTimeout(connect, 2000);
            };
        }
        connect();

        function toggleSettings(e) {
            e.stopPropagation();
            const isHidden = controls.style.display === 'none' || !controls.style.display;
            
            if (isHidden) {
                controls.style.display = 'block';
            } else {
                controls.style.display = 'none';
            }
        }

        // 波形与读数同步缩放，颜色仅用于有实时数据的波形。
        function updateStyles() {
            const scale = parseFloat(document.getElementById('sizeRange').value);
            
            // 1. 等比例调整字体和 SVG 尺寸
            hrEl.style.fontSize = (26 * scale) + 'px';
            unitEl.style.fontSize = (11 * scale) + 'px';
            
            heartbeat.style.width = (64 * scale) + 'px';
            heartbeat.style.height = (28 * scale) + 'px';

            // 2. 颜色更新
            hrEl.style.color = document.getElementById('textColor').value;
            heartbeat.style.setProperty('--wave-color', document.getElementById('waveColor').value);
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
        hr = latest_heart_rate if time.monotonic() - latest_reading_at < 10 else "--"
        await websocket.send(json.dumps({"hr": hr}))
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)

async def notify_clients(hr):
    global latest_heart_rate, latest_reading_at
    latest_heart_rate = hr
    latest_reading_at = time.monotonic()
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
        await notify_clients("--")
        try:
            if not WATCH_MAC:
                print("[BLE] 请在 device_config.json 中设置 watch_mac")
                await asyncio.sleep(2)
                continue
            print(f"[BLE] Searching for device: {WATCH_MAC}")
            # 1. 显式设定 timeout=12.0，避免 WinRT 驱动死锁/被动 Cancelled
            async with BleakClient(WATCH_MAC, timeout=12.0) as client:
                print(f"[BLE] Connected successfully!")
                
                # 2. 给手环 1 秒缓冲，避免连接后立马 start_notify 触发 WinError
                await asyncio.sleep(1.0)
                
                if not client.is_connected:
                    continue

                await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
                print("[BLE] Heart rate notification active!")

                while client.is_connected:
                    await asyncio.sleep(0.5)

        # 3. 核心修复：显式捕获 CancelledError 与 Exception，防止进程退出
        except (Exception, asyncio.CancelledError) as e:
            err_txt = str(e) if str(e) else "Connection timed out / cancelled by OS"
            print(f"[BLE Error]: {err_txt}, retrying in 2s...")
            await asyncio.sleep(2)
        # 4. 终极兜底：捕获所有 BaseException 级别的致命异常
        except BaseException as e:
            print(f"[BLE Fatal Error]: {e}, retrying in 2s...")
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
