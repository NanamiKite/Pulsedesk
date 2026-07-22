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
        width: 300,
        height: 160,
        minWidth: 180,            // 允许拉伸的最小宽度
        minHeight: 100,           // 允许拉伸的最小高度
        transparent: true,        // 窗口背景透明
        frame: false,             // 无边框/无标题栏
        alwaysOnTop: true,        // 永远置顶
        resizable: true,          // 允许鼠标拖拽边缘自由调整大小
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

// 监听来自网页端 (HTML) 齿轮按钮的展开/收起通知，动态调整窗口高度
ipcMain.on('resize-window', (event, expanded) => {
    if (mainWindow) {
        const [w, h] = mainWindow.getSize();
        if (expanded) {
            mainWindow.setSize(w, Math.max(h, 280)); // 展开控制面板时放大高度
        } else {
            mainWindow.setSize(w, 160); // 收起控制面板时还原高度
        }
    }
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