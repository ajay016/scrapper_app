// index.js - PRODUCTION VERSION
const { app, BrowserWindow, ipcMain, Menu } = require("electron");
const path = require("path");

let win; // Global reference to main window



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
        },
    });

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
        },
    });

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
        },
        backgroundColor: '#1a1a1a'
    });

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
            if (!win.webContents.isDevToolsOpened()) {
                win.webContents.openDevTools({ mode: 'detach' });
            }

            win.webContents.send("auth-token-received", deeplinkUrl);
            if (win.isMinimized()) win.restore();
            win.focus();
        }
    });

    app.whenReady().then(() => {
        console.log("App is ready, creating main window...");
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