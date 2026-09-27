const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn, execSync } = require('child_process');
const path = require('path');

let mainWindow = null;
let pythonProcess = null;

/**
 * 彻底清除残留 Python 进程与卡死的 8765 端口
 */
function cleanupPython() {
    if (process.platform === 'win32') {
        try {
            // 1. 带 /T 参数，强杀 python.exe 及其派生的所有子进程树
            execSync('taskkill /F /T /IM python.exe', { stdio: 'ignore' });
        } catch (e) {
            // 忽略没有 python.exe 运行时的报错
        }

        try {
            // 2. 查出占用 8765 端口的 PID 并直接强杀，解决 10048 端口残留卡死
            execSync('for /f "tokens=5" %a in (\'netstat -aon ^| findstr 8765\') do taskkill /F /T /PID %a', { stdio: 'ignore' });
        } catch (e) {
            // 忽略端口未被占用时的报错
        }
    }
}

/**
 * 启动 Python 后台服务
 */
function startPythonBackend() {
    // 启动前先做一次彻底清理
    cleanupPython();

    const scriptPath = path.join(__dirname, 'main.py');
    console.log('[Electron] 正在启动后台 Python 脚本:', scriptPath);

    pythonProcess = spawn('python', ['-u',scriptPath], {
        cwd: __dirname,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[Python]: ${data.toString('utf-8').trim()}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Python Err]: ${data.toString('utf-8').trim()}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`[Python] 进程已退出，退出码: ${code}`);
    });
}

/**
 * 创建 Electron 悬浮窗口
 */
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 220,
        height: 60,
        transparent: true,        // 窗口背景透明
        frame: false,             // 无边框/无标题栏
        alwaysOnTop: true,        // 永远置顶
        resizable: false,         // 根据页面内容和缩放设置自动调整
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false
        }
    });

    // 延迟 1 秒加载页面，等待 Python WebSocket 服务启动完成
    setTimeout(() => {
        mainWindow.loadFile(path.join(__dirname, 'obs_heart_rate.html'));
    }, 1000);

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// 使用页面的实际尺寸，避免胶囊外留下大块透明空白。
ipcMain.on('resize-window', (event, size) => {
    if (!mainWindow || event.sender !== mainWindow.webContents || !size) return;
    if (!Number.isFinite(size.width) || !Number.isFinite(size.height)) return;
    const width = Math.max(100, Math.min(600, Math.ceil(size.width)));
    const height = Math.max(40, Math.min(600, Math.ceil(size.height)));
    mainWindow.setContentSize(width, height);
});

// App 生命周期管理
app.whenReady().then(() => {
    startPythonBackend();
    createWindow();
});

// 退出应用前彻底杀干净后台
app.on('will-quit', () => {
    cleanupPython();
});

app.on('window-all-closed', () => {
    cleanupPython();
    if (process.platform !== 'darwin') {
        app.quit();
    }
});
