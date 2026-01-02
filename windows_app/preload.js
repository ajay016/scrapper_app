// preload.js
const { contextBridge, ipcRenderer } = require("electron");

console.log('🔌 Preload script loading...');

try {
    contextBridge.exposeInMainWorld("electronAPI", {
        openUrlsWindow: () => {
            console.log('🎯 openUrlsWindow called from renderer');
            return ipcRenderer.send("open-urls-window");
        }
    });
    
    console.log('✅ electronAPI exposed successfully');
} catch (error) {
    console.error('❌ Failed to expose electronAPI:', error);
}