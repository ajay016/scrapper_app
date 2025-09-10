const { ipcRenderer, webFrame } = require("electron");

document.addEventListener('DOMContentLoaded', function () {
    // Toolbar buttons
    const buttons = [
        { id: 'minimize-btn', event: 'minimize-window' },
        { id: 'maximize-btn', event: 'maximize-window' },
        { id: 'close-btn', event: 'close-window' },
        { id: 'exit-app', event: 'exit-app' },
        { id: 'reload-btn', event: 'reload' },
        { id: 'force-reload-btn', event: 'force-reload' },
        { id: 'dev-tools-btn', event: 'toggle-dev-tools' },
        { id: 'fullscreen-btn', event: 'toggle-fullscreen' } // Toolbar fullscreen
    ];

    buttons.forEach(btn => {
        const el = document.getElementById(btn.id);
        if (el) el.addEventListener('click', () => ipcRenderer.send(btn.event));
    });

    // Zoom buttons
    document.getElementById('reset-zoom-btn')?.addEventListener('click', () => webFrame.setZoomFactor(1));
    document.getElementById('zoom-in-btn')?.addEventListener('click', () => webFrame.setZoomFactor(webFrame.getZoomFactor() + 0.1));
    document.getElementById('zoom-out-btn')?.addEventListener('click', () => webFrame.setZoomFactor(webFrame.getZoomFactor() - 0.1));

    // Menu items
    const menuEvents = {
        'minimize-window-menu': 'minimize-window',
        'zoom-window-menu': 'maximize-window',
        'close-window-menu': 'close-window',
        'fullscreen-btn-menu': 'toggle-fullscreen' // View menu fullscreen
    };

    Object.keys(menuEvents).forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('click', () => ipcRenderer.send(menuEvents[id]));
    });
});