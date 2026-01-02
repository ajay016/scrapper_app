// scripts/urls-simple.js
console.log('📦 URL Module: Starting...');

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ URL Module: DOM ready');
    
    // Get elements
    const searchBtn = document.getElementById('search-url-btn');
    const urlInput = document.getElementById('url-input');
    
    console.log('🔍 URL Module: Elements found:', {
        searchBtn: !!searchBtn,
        urlInput: !!urlInput
    });
    
    if (!searchBtn) {
        console.error('❌ URL Module: search-url-btn NOT FOUND!');
        return;
    }
    
    console.log('✅ URL Module: Adding click handler...');
    
    // Add click handler - USE CAPTURE PHASE
    searchBtn.addEventListener('click', function(event) {
        console.log('🎯 URL Module: Button CLICKED!');
        event.preventDefault();
        event.stopPropagation();
        
        // Get URL value
        const url = urlInput ? urlInput.value.trim() : '';
        console.log('📝 URL Module: URL value:', url);
        
        if (!url) {
            alert('Пожалуйста, введите URL');
            return;
        }
        
        // Change button state
        const originalHtml = this.innerHTML;
        this.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Загрузка...';
        this.disabled = true;
        
        // Show simple result
        const resultsContainer = document.getElementById('results-container');
        if (resultsContainer) {
            resultsContainer.innerHTML = `
                <div class="alert alert-success">
                    <h5>🔄 Сканирование начато</h5>
                    <p><strong>URL:</strong> ${url}</p>
                    <p><strong>Глубина:</strong> ${document.getElementById('url-depth-input')?.value || 2}</p>
                    <p>Сканирование запущено успешно!</p>
                    <small class="text-muted">В реальном приложении здесь начнется сканирование сайта</small>
                </div>
            `;
        }
        
        // Reset button after 3 seconds
        setTimeout(() => {
            this.innerHTML = originalHtml;
            this.disabled = false;
            console.log('✅ URL Module: Button reset');
        }, 3000);
        
    }, true); // Use capture phase - IMPORTANT!
    
    console.log('✅ URL Module: Handler added successfully');
});

// Also add a global click handler as backup
window.addEventListener('click', function(event) {
    if (event.target.id === 'search-url-btn' || event.target.closest('#search-url-btn')) {
        console.log('🌐 GLOBAL: Button clicked via global handler');
    }
}, true);

console.log('✅ URL Module: Setup complete');