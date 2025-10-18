const { app, BrowserWindow, ipcMain, Menu } = require("electron");
const path = require("path");



let win; // ✅ ADDED: make win global so IPC can access it

function createWindow() {
    win = new BrowserWindow({ // ✅ CHANGED: use global win
        width: 1000,
        height: 700,
        frame: false, // Keep this false for the custom title bar
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
        },
    });

    win.loadFile("index.html");

    // // Remove this in production starts
    // // --- Open DevTools automatically ---
    // win.webContents.openDevTools();
    // // Remove this in production ends

    // Define the menu template
    const template = [
        {
            label: 'File',
            submenu: [
                {
                    label: 'Exit',
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
                // ✅ CHANGED: remove role and add click to handle via IPC
                {
                    label: 'Toggle Fullscreen',
                    id: 'toggle-fullscreen-menu', // ✅ ADDED: give ID to reference
                    click: () => {
                        win.setFullScreen(!win.isFullScreen()); // ✅ ADDED: toggle fullscreen
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

    // Build the menu from the template
    const menu = Menu.buildFromTemplate(template);

    // Set the menu for the application
    Menu.setApplicationMenu(menu);

    // --- IPC listeners for toolbar buttons ---
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

    // ✅ ADDED: fullscreen IPC for toolbar fullscreen button
    ipcMain.on('toggle-fullscreen', () => {
        win.setFullScreen(!win.isFullScreen());
    });


    // // Remove this in production starts
    // // --- Renderer errors forwarded to terminal ---
    // ipcMain.on('renderer-error', (event, error) => {
    //     console.error('Renderer Error:', error);
    // });
    // // Remove this in production ends
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




// login process starts
const gotLock = app.requestSingleInstanceLock();

if (!gotLock) {
    app.quit();
} else {
    app.on('second-instance', (event, argv) => {
        const deeplinkUrl = argv.find(arg => arg.startsWith("scraper://"));
        if (deeplinkUrl && win) {  // ✅ changed mainWindow → win
            win.webContents.send("auth-token-received", deeplinkUrl);
            if (win.isMinimized()) win.restore();
            win.focus();
        }
    });

    app.whenReady().then(() => {
        app.setAsDefaultProtocolClient("scraper"); // register scraper:// protocol
        createWindow();
    });
}

// macOS deep link
app.on('open-url', (event, url) => {
    event.preventDefault();
    if (win) {  // ✅ changed mainWindow → win
        win.webContents.send("auth-token-received", url);
    }
});
// login process ends