// index.js - PRODUCTION VERSION
const { app, BrowserWindow, ipcMain, Menu, powerSaveBlocker } = require("electron");
const path = require("path");


app.commandLine.appendSwitch("disable-background-timer-throttling");
app.commandLine.appendSwitch("disable-backgrounding-occluded-windows");
app.commandLine.appendSwitch("disable-renderer-backgrounding");

let win; // Global reference to main window
let psbId = null;


// ✅ HEARTBEAT TIMERS (per crawl session)
const heartbeatTimers = new Map(); // sessionId -> intervalId
const pollTimers = new Map();

function startHeartbeat(sessionId, API_BASE_URL) {
    stopHeartbeat(sessionId); // avoid duplicates

    const intervalId = setInterval(async () => {
        try {
            await fetch(`${API_BASE_URL}/api/crawl-heartbeat/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: sessionId }),
            });
        } catch (err) {
            // silent failure is ok (network down etc)
        }
    }, 10000); // ✅ 10 seconds

    heartbeatTimers.set(sessionId, intervalId);
}

function stopHeartbeat(sessionId) {
    const intervalId = heartbeatTimers.get(sessionId);
    if (intervalId) {
        clearInterval(intervalId);
        heartbeatTimers.delete(sessionId);
    }
}

function startPolling(sessionId, API_BASE_URL, targetWebContentsId) {
    stopPolling(sessionId); // prevent duplicates

    const intervalId = setInterval(async () => {
        try {
            // ✅ fetch results from backend
            const res = await fetch(
                `${API_BASE_URL}/api/get-crawl-results/?session_id=${sessionId}&limit=200`
            );

            if (!res.ok) return;
            const data = await res.json();

            // ✅ send updates to renderer if window still exists
            const wc = BrowserWindow.fromWebContents(
                BrowserWindow.getAllWindows()
                    .map(w => w.webContents)
                    .find(wc => wc.id === targetWebContentsId)
            )?.webContents;

            if (wc && data?.results?.length) {
                wc.send("crawl-updates", { sessionId, updates: data.results, stats: data.stats });
            }

        } catch (err) {
            // ignore temporary errors
        }
    }, 500); // ✅ faster & stable even if minimized

    pollTimers.set(sessionId, intervalId);
}

function stopPolling(sessionId) {
    const intervalId = pollTimers.get(sessionId);
    if (intervalId) {
        clearInterval(intervalId);
        pollTimers.delete(sessionId);
    }
}



// // Remove this in production starts
// // --- Open DevTools automatically ---
ipcMain.on("open-devtools", (event) => {
    const wc = event.sender;

    if (!wc.isDevToolsOpened()) {
        wc.openDevTools({ mode: "detach" });
    }
});
// // Remove this in production ends


function createWindow() {
    win = new BrowserWindow({
        width: 1000,
        height: 700,
        frame: false,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            backgroundThrottling: false, // ✅ ADD THIS
        },
    });

    win.webContents.setBackgroundThrottling(false);

    win.loadFile("index.html");

    // // Remove this in production starts
    // // --- Open DevTools automatically ---
    win.webContents.openDevTools();
    // // Remove this in production ends
    
    // Define the menu template
    const template = [
        {
            label: 'File',
            submenu: [
                {
                    label: 'Exit',
                    accelerator: 'CmdOrCtrl+Q',
                    click: () => {
                        app.quit();
                    }
                }
            ]
        },
        {
            label: 'Edit',
            submenu: [
                { role: 'undo' },
                { role: 'redo' },
                { type: 'separator' },
                { role: 'cut' },
                { role: 'copy' },
                { role: 'paste' },
                { role: 'delete' },
                { type: 'separator' },
                { role: 'selectAll' }
            ]
        },
        {
            label: 'View',
            submenu: [
                { role: 'reload' },
                { role: 'forceReload' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
                { type: 'separator' },
                {
                    label: 'Toggle Fullscreen',
                    accelerator: 'F11',
                    click: () => {
                        win.setFullScreen(!win.isFullScreen());
                    }
                }
            ]
        },
        {
            label: 'Window',
            submenu: [
                { role: 'minimize' },
                { role: 'zoom' },
                { role: 'close' }
            ]
        }
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);

    // IPC listeners for toolbar buttons
    ipcMain.on('minimize-window', () => win.minimize());
    ipcMain.on('maximize-window', () => {
        if (win.isMaximized()) win.unmaximize();
        else win.maximize();
    });
    ipcMain.on('close-window', () => win.close());
    ipcMain.on('exit-app', () => app.quit());
    ipcMain.on('reload', () => win.reload());
    ipcMain.on('force-reload', () => win.webContents.reloadIgnoringCache());
    ipcMain.on('toggle-dev-tools', () => win.webContents.toggleDevTools());
    ipcMain.on('toggle-fullscreen', () => {
        win.setFullScreen(!win.isFullScreen());
    });

    // New window for URLs
    ipcMain.on("open-urls-window", () => {
        createUrlsWindow();
    });


    

    // // Remove this in production starts
    // // --- Renderer errors forwarded to terminal ---
    ipcMain.on('renderer-error', (event, error) => {
        console.error('Renderer Error:', error);
    });
    // // Remove this in production ends
}

// Function to create URLs window (PRODUCTION - NO DEVTOOLS)
function createUrlsWindow() {
    console.log("Creating URLs window...");
    
    const urlWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        show: false,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            backgroundThrottling: false, // ✅ IMPORTANT (no slowdown when minimized)
        },
    });

    urlWindow.webContents.setBackgroundThrottling(false);

    urlWindow.loadFile("urls.html");

    urlWindow.once('ready-to-show', () => {
        urlWindow.show();
        urlWindow.focus();
    });

    urlWindow.setTitle("URL Краулер");
    
    // Menu for URLs window
    const menuTemplate = [
        {
            label: 'File',
            submenu: [
                {
                    label: 'Close Window',
                    accelerator: 'CmdOrCtrl+W',
                    click: () => {
                        urlWindow.close();
                    }
                }
            ]
        },
        {
            label: 'Edit',
            submenu: [
                { role: 'undo' },
                { role: 'redo' },
                { type: 'separator' },
                { role: 'cut' },
                { role: 'copy' },
                { role: 'paste' },
                { role: 'selectAll' }
            ]
        },
        {
            label: 'View',
            submenu: [
                { role: 'reload' },
                { role: 'forceReload' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
            ]
        },
        {
            label: 'Window',
            submenu: [
                { role: 'minimize' },
                { role: 'zoom' },
                { role: 'close' }
            ]
        }
    ];

    const menu = Menu.buildFromTemplate(menuTemplate);
    urlWindow.setMenu(menu);

    urlWindow.on('closed', () => {
        console.log("URLs window closed");
    });
}

// Function to create crawling window with URL pre-filled
function createCrawlingWindow(crawlData) {
    const crawlingWindow = new BrowserWindow({
        width: 1600,
        height: 1000,
        frame: false,
        show: false,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            backgroundThrottling: false, // ✅ IMPORTANT
        },
        backgroundColor: '#1a1a1a'
    });

    crawlingWindow.webContents.setBackgroundThrottling(false);

    crawlingWindow.loadFile("pages/urls.html");

    crawlingWindow.once('ready-to-show', () => {
        crawlingWindow.show();
        crawlingWindow.focus();
        
        // Send crawl data to the window
        crawlingWindow.webContents.on('did-finish-load', () => {
            setTimeout(() => {
                crawlingWindow.webContents.send('auto-start-crawl', crawlData);
            }, 1000);
        });
    });

    crawlingWindow.setTitle(`Crawling: ${crawlData.url || 'New Crawl'}`);

    // Menu for crawling window
    const menuTemplate = [
        {
            label: 'File',
            submenu: [
                {
                    label: 'Close Window',
                    accelerator: 'CmdOrCtrl+W',
                    click: () => {
                        crawlingWindow.close();
                    }
                }
            ]
        },
        {
            label: 'Edit',
            submenu: [
                { role: 'undo' },
                { role: 'redo' },
                { type: 'separator' },
                { role: 'cut' },
                { role: 'copy' },
                { role: 'paste' },
                { role: 'selectAll' }
            ]
        },
        {
            label: 'View',
            submenu: [
                { role: 'reload' },
                { role: 'forceReload' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
            ]
        },
        {
            label: 'Window',
            submenu: [
                { role: 'minimize' },
                { role: 'zoom' },
                { role: 'close' }
            ]
        }
    ];

    const menu = Menu.buildFromTemplate(menuTemplate);
    crawlingWindow.setMenu(menu);
}

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

// Single instance lock for deep linking
const gotLock = app.requestSingleInstanceLock();

if (!gotLock) {
    app.quit();
} else {
    app.on('second-instance', (event, argv) => {
        const deeplinkUrl = argv.find(arg => arg.startsWith("scraper://"));
        if (deeplinkUrl && win) {
            // 🔥 FORCE DEVTOOLS OPEN FOR DEBUGGING
            // // Remove this in production starts
            // // --- Open DevTools automatically ---
            if (!win.webContents.isDevToolsOpened()) {
                win.webContents.openDevTools({ mode: 'detach' });
            }
            // // Remove this in production ends

            win.webContents.send("auth-token-received", deeplinkUrl);
            if (win.isMinimized()) win.restore();
            win.focus();
        }
    });

    // ✅ HEARTBEAT IPC (must be registered once)
    ipcMain.on("heartbeat-start", (event, payload) => {
        const { sessionId, apiBaseUrl } = payload || {};
        if (!sessionId || !apiBaseUrl) return;
        startHeartbeat(sessionId, apiBaseUrl);
    });

    ipcMain.on("heartbeat-stop", (event, payload) => {
        const { sessionId } = payload || {};
        if (!sessionId) return;
        stopHeartbeat(sessionId);
    });

    ipcMain.on("poll-start", (event, payload) => {
        const { sessionId, apiBaseUrl } = payload || {};
        if (!sessionId || !apiBaseUrl) return;

        // ✅ the renderer that requested polling
        const targetWebContentsId = event.sender.id;

        startPolling(sessionId, apiBaseUrl, targetWebContentsId);
    });

    ipcMain.on("poll-stop", (event, payload) => {
        const { sessionId } = payload || {};
        if (!sessionId) return;
        stopPolling(sessionId);
    });

    app.whenReady().then(() => {
        console.log("App is ready, creating main window...");

        // ✅ START POWER SAVE BLOCKER HERE
        psbId = powerSaveBlocker.start("prevent-app-suspension");
        console.log("✅ PowerSaveBlocker ON:", psbId);

        app.setAsDefaultProtocolClient("scraper");
        createWindow();
    });
}

// macOS deep link handling
app.on('open-url', (event, url) => {
    event.preventDefault();
    if (win) {
        win.webContents.send("auth-token-received", url);
    }
});