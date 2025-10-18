// scripts/urls.js
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.__pages = root.__pages || {};
        root.__pages['urls'] = factory();
    }
}(this, function () {

    let selectedItems = new Set();
    let currentPage = 1;
    const itemsPerPage = 10;
    let paginatedResults = [];
    let allResults = [];
    let currentSessionId = null;
    let isCrawling = false;
    let resultsInterval = null;
    let statusInterval = null;

    function renderResults(results, baseIndex = 0) {
        if (!results || !results.length) return '';
        return results.map((r, index) => {
            const uniqueId = `${baseIndex + index}`;
            const isChecked = selectedItems.has(uniqueId);
            return `
                <div class="card my-2 p-2">
                    <div class="form-check">
                        <input class="form-check-input result-checkbox" type="checkbox" 
                            data-url="${r.url}" data-text="${r.text || r.url}" 
                            data-id="${uniqueId}" ${isChecked ? 'checked' : ''}>
                        <label class="form-check-label">
                            <a href="${r.url}" target="_blank" rel="noreferrer noopener" class="text-decoration-none">
                                ${r.text || r.url}
                            </a>
                            <span class="badge ${r.is_internal ? 'bg-primary' : 'bg-warning'} ms-2">
                                ${r.is_internal ? 'Internal' : 'External'}
                            </span>
                            ${r.depth !== undefined ? `<span class="badge bg-info ms-1">Depth: ${r.depth}</span>` : ''}
                            ${r.source_url ? `<small class="text-muted d-block mt-1">From: ${r.source_url}</small>` : ''}
                        </label>
                    </div>
                </div>
            `;
        }).join('');
    }

    function renderStatusMessage(message, type = 'info') {
        return `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
    }

    function renderRealTimeUpdate(update) {
        const statusContainer = document.getElementById('realtime-status');
        if (!statusContainer) return;

        let message = '';
        let type = 'info';
        let icon = '🔍';

        switch (update.type) {
            case 'processing':
                message = `Processing: ${update.url} (Depth ${update.depth})`;
                type = 'info';
                icon = '🔄';
                break;
            case 'link_found':
                message = `Found: ${update.link.text || update.link.url} (Total: ${update.total_found})`;
                type = 'success';
                icon = '✅';
                break;
            case 'info':
                message = update.message;
                type = 'info';
                icon = 'ℹ️';
                break;
            case 'warning':
                message = update.message;
                type = 'warning';
                icon = '⚠️';
                break;
            case 'error':
                message = `Error: ${update.message}`;
                type = 'danger';
                icon = '❌';
                break;
            case 'complete':
                message = `🎉 ${update.message}`;
                type = 'success';
                icon = '🎉';
                break;
        }

        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show mb-1`;
        alertDiv.innerHTML = `
            <small>${icon} ${message}</small>
            <button type="button" class="btn-close btn-close-sm" data-bs-dismiss="alert"></button>
        `;
        
        statusContainer.appendChild(alertDiv);
        
        // Auto-remove after 8 seconds for non-error messages
        if (type !== 'danger' && type !== 'warning') {
            setTimeout(() => {
                if (alertDiv.parentNode) {
                    alertDiv.remove();
                }
            }, 8000);
        }

        // Scroll to bottom
        statusContainer.scrollTop = statusContainer.scrollHeight;
    }

    function updateProgressStats(stats) {
        const statsContainer = document.getElementById('crawl-stats');
        if (!statsContainer) return;

        statsContainer.innerHTML = `
            <div class="row text-center">
                <div class="col">
                    <small class="text-muted">Pages Crawled</small>
                    <div class="h6 mb-0">${stats.pages_crawled || 0}</div>
                </div>
                <div class="col">
                    <small class="text-muted">Links Found</small>
                    <div class="h6 mb-0">${stats.total_found || 0}</div>
                </div>
                <div class="col">
                    <small class="text-muted">BS4 Success</small>
                    <div class="h6 mb-0">${stats.beautifulsoup_success || 0}</div>
                </div>
                <div class="col">
                    <small class="text-muted">Selenium Fallback</small>
                    <div class="h6 mb-0">${stats.selenium_fallback || 0}</div>
                </div>
            </div>
        `;
    }

    function updateProgressBar(found, total = 50) {
        const progressBar = document.getElementById('crawl-progress-bar');
        if (!progressBar) return;

        const percentage = Math.min((found / total) * 100, 100);
        progressBar.style.width = `${percentage}%`;
        progressBar.setAttribute('aria-valuenow', percentage);
        progressBar.textContent = `${found} links found`;
        
        if (found >= total) {
            progressBar.classList.remove('progress-bar-animated');
        }
    }

    function paginateResults(results, page, itemsPerPage) {
        const startIndex = (page - 1) * itemsPerPage;
        return results.slice(startIndex, startIndex + itemsPerPage);
    }

    function renderPagination(totalPages, currentPage) {
        const paginationContainer = document.getElementById('url-pagination');
        const paginationList = document.querySelector('.url-pagination-list');
        if (!paginationContainer || !paginationList) return;

        if (totalPages <= 1) {
            paginationContainer.classList.add('d-none');
            return;
        }
        
        paginationContainer.classList.remove('d-none');
        paginationList.innerHTML = '';

        const maxVisible = 7;
        let startPage = Math.max(currentPage - Math.floor(maxVisible / 2), 1);
        let endPage = startPage + maxVisible - 1;

        if (endPage > totalPages) {
            endPage = totalPages;
            startPage = Math.max(endPage - maxVisible + 1, 1);
        }

        const createPageItem = (page, text, disabled = false, active = false) => {
            const li = document.createElement('li');
            li.className = `page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link url-pagination-number" href="#" data-page="${page}">${text}</a>`;
            paginationList.appendChild(li);
        };

        // Prev button
        createPageItem(currentPage - 1, '« Prev', currentPage === 1);

        // First page if not in visible range
        if (startPage > 1) {
            createPageItem(1, '1');
            if (startPage > 2) {
                const li = document.createElement('li');
                li.className = 'page-item disabled';
                li.innerHTML = '<span class="page-link">...</span>';
                paginationList.appendChild(li);
            }
        }

        // Page numbers
        for (let i = startPage; i <= endPage; i++) {
            createPageItem(i, i, false, i === currentPage);
        }

        // Last page if not in visible range
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                const li = document.createElement('li');
                li.className = 'page-item disabled';
                li.innerHTML = '<span class="page-link">...</span>';
                paginationList.appendChild(li);
            }
            createPageItem(totalPages, totalPages);
        }

        // Next button
        createPageItem(currentPage + 1, 'Next »', currentPage === totalPages);

        // Click events
        paginationList.querySelectorAll('a.url-pagination-number').forEach(link => {
            link.addEventListener('click', e => {
                e.preventDefault();
                const page = parseInt(link.dataset.page);
                if (!isNaN(page) && page >= 1 && page <= totalPages && page !== currentPage) {
                    currentPage = page;
                    paginatedResults = paginateResults(allResults, currentPage, itemsPerPage);
                    document.getElementById('results-content').innerHTML = renderResults(paginatedResults, (currentPage - 1) * itemsPerPage);
                    renderPagination(totalPages, currentPage);
                    attachCheckboxHandlers();
                }
            });
        });
    }

    function attachCheckboxHandlers() {
        const markAllCheckbox = document.getElementById('mark-all-checkbox');
        const checkboxes = document.querySelectorAll('.result-checkbox');
        const actionButtonsContainer = document.getElementById('action-buttons-container');

        if (checkboxes.length > 0) {
            actionButtonsContainer.style.display = 'flex';
            actionButtonsContainer.innerHTML = `
                <button class="btn btn-primary btn-sm" id="save-selected-btn">
                    <i class="bi bi-save"></i> Save Selected
                </button>
                <button class="btn btn-outline-success btn-sm" id="export-selected-btn">
                    <i class="bi bi-download"></i> Export Selected
                </button>
                <div class="dropdown">
                    <button class="btn btn-outline-secondary btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                        <i class="bi bi-download"></i> Export All
                    </button>
                    <ul class="dropdown-menu">
                        <li><a class="dropdown-item export-all" href="#" data-format="csv"><i class="bi bi-filetype-csv"></i> CSV</a></li>
                        <li><a class="dropdown-item export-all" href="#" data-format="json"><i class="bi bi-filetype-json"></i> JSON</a></li>
                        <li><a class="dropdown-item export-all" href="#" data-format="txt"><i class="bi bi-filetype-txt"></i> Text</a></li>
                    </ul>
                </div>
            `;
            
            // Add event listeners for the new buttons
            document.getElementById('export-selected-btn').addEventListener('click', () => {
                if (!selectedItems.size) {
                    alert('Please select URLs to export');
                    return;
                }
                // Show format selection for selected items
                showExportFormatSelection('selected');
            });
            
            // Add event listeners for export all dropdown
            document.querySelectorAll('.export-all').forEach(item => {
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    const format = e.target.getAttribute('data-format');
                    exportUrls(format);
                });
            });
            
        } else {
            actionButtonsContainer.style.display = 'none';
        }

        checkboxes.forEach(cb => {
            cb.checked = selectedItems.has(cb.dataset.id);
            cb.onchange = () => {
                if (cb.checked) selectedItems.add(cb.dataset.id);
                else selectedItems.delete(cb.dataset.id);
                updateMarkAllCheckbox();
            };
        });

        if (markAllCheckbox) {
            markAllCheckbox.onchange = () => {
                const checked = markAllCheckbox.checked;
                checkboxes.forEach(cb => { 
                    cb.checked = checked; 
                    if (checked) selectedItems.add(cb.dataset.id);
                    else selectedItems.delete(cb.dataset.id);
                });
            };
            
            updateMarkAllCheckbox();
        }

        const saveBtn = document.getElementById('save-selected-btn');
        if (saveBtn) {
            saveBtn.onclick = () => {
                if (!selectedItems.size) return alert('Select at least one item');
                showSavePanel();
            };
        }
    }
    
    function updateMarkAllCheckbox() {
        const markAllCheckbox = document.getElementById('mark-all-checkbox');
        const checkboxes = document.querySelectorAll('.result-checkbox');
        
        if (!markAllCheckbox || checkboxes.length === 0) return;
        
        const allChecked = Array.from(checkboxes).every(c => c.checked);
        const someChecked = Array.from(checkboxes).some(c => c.checked);
        markAllCheckbox.checked = allChecked;
        markAllCheckbox.indeterminate = someChecked && !allChecked;
    }

    async function fetchCrawlResults(sessionId) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/get-crawl-results/?session_id=${sessionId}`);
            const data = await response.json();
            
            if (response.ok && data.results) {
                data.results.forEach(update => {
                    renderRealTimeUpdate(update);
                    
                    if (update.type === 'link_found') {
                        // Add new link to results
                        allResults.push(update.link);
                        
                        // Update results display
                        currentPage = 1;
                        paginatedResults = paginateResults(allResults, currentPage, itemsPerPage);
                        document.getElementById('results-content').innerHTML = renderResults(paginatedResults, (currentPage - 1) * itemsPerPage);
                        
                        const totalPages = Math.ceil(allResults.length / itemsPerPage);
                        renderPagination(totalPages, currentPage);
                        attachCheckboxHandlers();
                        
                        // Update progress
                        updateProgressBar(allResults.length);
                    }
                    
                    if (update.type === 'complete') {
                        stopCrawling();
                    }
                });

                // Update stats
                if (data.stats) {
                    updateProgressStats(data.stats);
                }
            }
        } catch (error) {
            console.error('Error fetching crawl results:', error);
        }
    }

    async function fetchCrawlStatus(sessionId) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/get-crawl-status/?session_id=${sessionId}`);
            const data = await response.json();
            
            if (response.ok) {
                // Update running time
                const runningTimeElem = document.getElementById('running-time');
                if (runningTimeElem) {
                    const minutes = Math.floor(data.running_time / 60);
                    const seconds = Math.floor(data.running_time % 60);
                    runningTimeElem.textContent = `${minutes}m ${seconds}s`;
                }
            }
        } catch (error) {
            console.error('Error fetching crawl status:', error);
        }
    }

    async function stopCrawling() {
        if (currentSessionId) {
            try {
                await fetch(`${API_BASE_URL}/api/stop-crawl/`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                    },
                    body: JSON.stringify({ session_id: currentSessionId })
                });
            } catch (error) {
                console.error('Error stopping crawl:', error);
            }
        }
        
        isCrawling = false;
        currentSessionId = null;
        
        if (resultsInterval) {
            clearInterval(resultsInterval);
            resultsInterval = null;
        }
        
        if (statusInterval) {
            clearInterval(statusInterval);
            statusInterval = null;
        }
        
        const searchBtn = document.getElementById("search-url-btn");
        const stopBtn = document.getElementById("stop-crawl-btn");
        
        if (searchBtn) {
            searchBtn.disabled = false;
            searchBtn.innerHTML = '<i class="bi bi-link-45deg"></i> Start Crawling';
        }
        
        if (stopBtn) {
            stopBtn.style.display = 'none';
        }

        // Update progress bar to complete
        const progressBar = document.getElementById('crawl-progress-bar');
        if (progressBar) {
            progressBar.classList.remove('progress-bar-animated');
            progressBar.classList.add('bg-success');
        }
    }

    function showSavePanel() {
        const savePanel = document.getElementById('save-panel');
        const overlay = document.getElementById('save-panel-overlay');
        
        fetch(`${API_BASE_URL}/api/project-list/`, {
            headers: { Authorization: `Bearer ${localStorage.getItem("accessToken")}` }
        })
        .then(res => res.json())
        .then(projects => {
            const projectSelect = document.getElementById("save-project-select");
            projectSelect.innerHTML = `<option value="">Select Project</option>`;
            projects.forEach(p => {
                projectSelect.innerHTML += `<option value="${p.id}">${p.name}</option>`;
            });
            
            savePanel.classList.add('show');
            overlay.classList.add('show');
        });
    }

    function hideSavePanel() {
        const savePanel = document.getElementById('save-panel');
        const overlay = document.getElementById('save-panel-overlay');
        savePanel.classList.remove('show');
        overlay.classList.remove('show');
    }

    function initSavePanel() {
        const closeBtn = document.getElementById('close-save-panel');
        const overlay = document.getElementById('save-panel-overlay');
        const confirmBtn = document.getElementById('confirm-save-btn');
        const projectSelect = document.getElementById('save-project-select');
        const folderSelect = document.getElementById('save-folder-select');
        
        if (closeBtn) closeBtn.addEventListener('click', hideSavePanel);
        if (overlay) overlay.addEventListener('click', hideSavePanel);
        
        if (projectSelect) {
            projectSelect.addEventListener('change', function() {
                const projectId = this.value;
                folderSelect.disabled = !projectId;
                
                if (!projectId) {
                    folderSelect.innerHTML = '<option value="">Select a Folder</option>';
                    return;
                }
                
                fetch(`${API_BASE_URL}/api/folder-list/?project_id=${projectId}`, {
                    headers: { Authorization: `Bearer ${localStorage.getItem("accessToken")}` }
                })
                .then(res => res.json())
                .then(folders => {
                    folderSelect.innerHTML = '<option value="">Select a Folder (Optional)</option>';
                    folders.forEach(f => {
                        folderSelect.innerHTML += `<option value="${f.id}">${f.name}</option>`;
                    });
                });
            });
        }
        
        if (confirmBtn) {
            confirmBtn.addEventListener('click', async () => {
                const projectId = projectSelect.value;
                const folderId = folderSelect.value || null;
                
                if (!projectId) return alert('Please select a project');
                
                const itemsToSave = Array.from(selectedItems).map(id => {
                    const idx = parseInt(id);
                    return allResults[idx];
                });
                
                try {
                    confirmBtn.disabled = true;
                    confirmBtn.textContent = 'Saving...';
                    
                    const res = await fetch(`${API_BASE_URL}/api/save-url-results/`, {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json', 
                            Authorization: `Bearer ${localStorage.getItem("accessToken")}` 
                        },
                        body: JSON.stringify({ 
                            items: itemsToSave, 
                            project_id: projectId,
                            folder_id: folderId,
                            source_url: document.getElementById('url-input').value
                        })
                    });
                    
                    const result = await res.json();
                    
                    if (res.ok) {
                        const messageContainer = document.getElementById('save-message-container');
                        messageContainer.innerHTML = `
                            <div class="alert alert-success alert-dismissible fade show" role="alert">
                                ${result.message}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        `;
                        hideSavePanel();
                        
                        selectedItems.clear();
                        document.querySelectorAll('.result-checkbox').forEach(cb => cb.checked = false);
                        updateMarkAllCheckbox();
                    } else {
                        alert(result.error || 'Save failed');
                    }
                } catch (err) {
                    console.error(err);
                    alert('Save failed');
                } finally {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = 'Save';
                }
            });
        }
    }

    // Export Functions
    function exportUrls(format) {
        if (!allResults.length) {
            alert('No URLs to export');
            return;
        }

        let content = '';
        let filename = '';
        const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
        
        switch (format) {
            case 'csv':
                content = 'URL,Text,Type,Depth,Source URL\n';
                allResults.forEach(item => {
                    const text = (item.text || '').replace(/"/g, '""');
                    const sourceUrl = (item.source_url || '').replace(/"/g, '""');
                    content += `"${item.url}","${text}","${item.is_internal ? 'Internal' : 'External'}","${item.depth || ''}","${sourceUrl}"\n`;
                });
                filename = `urls_${timestamp}.csv`;
                break;
                
            case 'json':
                content = JSON.stringify(allResults, null, 2);
                filename = `urls_${timestamp}.json`;
                break;
                
            case 'txt':
                allResults.forEach(item => {
                    content += `${item.url}\n`;
                    if (item.text) content += `Title: ${item.text}\n`;
                    content += `Type: ${item.is_internal ? 'Internal' : 'External'}\n`;
                    if (item.depth !== undefined) content += `Depth: ${item.depth}\n`;
                    if (item.source_url) content += `Source: ${item.source_url}\n`;
                    content += '---\n';
                });
                filename = `urls_${timestamp}.txt`;
                break;
        }
        
        downloadFile(content, filename, format);
    }

    function exportSelectedUrls(format) {
        if (!selectedItems.size) {
            alert('Please select URLs to export');
            return;
        }

        const itemsToExport = Array.from(selectedItems).map(id => {
            const idx = parseInt(id);
            return allResults[idx];
        });

        let content = '';
        let filename = '';
        const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
        
        switch (format) {
            case 'csv':
                content = 'URL,Text,Type,Depth,Source URL\n';
                itemsToExport.forEach(item => {
                    const text = (item.text || '').replace(/"/g, '""');
                    const sourceUrl = (item.source_url || '').replace(/"/g, '""');
                    content += `"${item.url}","${text}","${item.is_internal ? 'Internal' : 'External'}","${item.depth || ''}","${sourceUrl}"\n`;
                });
                filename = `selected_urls_${timestamp}.csv`;
                break;
                
            case 'json':
                content = JSON.stringify(itemsToExport, null, 2);
                filename = `selected_urls_${timestamp}.json`;
                break;
                
            case 'txt':
                itemsToExport.forEach(item => {
                    content += `${item.url}\n`;
                    if (item.text) content += `Title: ${item.text}\n`;
                    content += `Type: ${item.is_internal ? 'Internal' : 'External'}\n`;
                    if (item.depth !== undefined) content += `Depth: ${item.depth}\n`;
                    if (item.source_url) content += `Source: ${item.source_url}\n`;
                    content += '---\n';
                });
                filename = `selected_urls_${timestamp}.txt`;
                break;
        }
        
        downloadFile(content, filename, format);
    }

    function getMimeType(format) {
        const mimeTypes = {
            'csv': 'text/csv',
            'json': 'application/json',
            'txt': 'text/plain'
        };
        return mimeTypes[format] || 'text/plain';
    }

    function downloadFile(content, filename, format) {
        const blob = new Blob([content], { type: getMimeType(format) });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function showExportFormatSelection(type) {
        // Simple format selection - you could enhance this with a modal
        const format = prompt(`Select export format for ${type} URLs:\n\nEnter: csv, json, or txt`, 'csv');
        if (format) {
            const normalizedFormat = format.toLowerCase().trim();
            if (['csv', 'json', 'txt'].includes(normalizedFormat)) {
                if (type === 'selected') {
                    exportSelectedUrls(normalizedFormat);
                } else {
                    exportUrls(normalizedFormat);
                }
            } else {
                alert('Invalid format. Please enter: csv, json, or txt');
            }
        }
    }

    function init() {
        const searchBtn = document.getElementById("search-url-btn");
        const urlInput = document.getElementById("url-input");
        const depthInput = document.getElementById("url-depth-input");
        const resultsContainer = document.getElementById("results-container");
        const actionButtonsContainer = document.getElementById("action-buttons-container");
        const projectSelect = document.getElementById("project-select");

        if (!searchBtn) return;

        // Initialize save panel
        initSavePanel();

        // Add global export event listeners
        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('export-all') || e.target.parentElement.classList.contains('export-all')) {
                e.preventDefault();
                const target = e.target.classList.contains('export-all') ? e.target : e.target.parentElement;
                const format = target.getAttribute('data-format');
                exportUrls(format);
            }
            
            if (e.target.classList.contains('export-selected') || e.target.parentElement.classList.contains('export-selected')) {
                e.preventDefault();
                const target = e.target.classList.contains('export-selected') ? e.target : e.target.parentElement;
                const format = target.getAttribute('data-format');
                exportSelectedUrls(format);
            }
        });

        // Load projects
        fetch(`${API_BASE_URL}/api/project-list/`, {
            headers: { Authorization: `Bearer ${localStorage.getItem("accessToken")}` }
        })
        .then(res => res.json())
        .then(projects => {
            projectSelect.innerHTML = `<option value="">Select Project</option>`;
            projects.forEach(p => {
                projectSelect.innerHTML += `<option value="${p.id}">${p.name}</option>`;
            });
        });

        searchBtn.addEventListener("click", async () => {
            const url = (urlInput.value || '').trim();
            const depth = depthInput.value || 2;
            
            if (!url) {
                resultsContainer.innerHTML = `<div class="alert alert-danger">Please enter a URL</div>`;
                return;
            }

            if (isCrawling) {
                return alert('Crawling is already in progress');
            }

            // Reset state
            allResults = [];
            selectedItems.clear();
            currentPage = 1;
            isCrawling = true;

            // Update UI for crawling state
            searchBtn.disabled = true;
            searchBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Crawling...';
            
            // Add stop button if not exists
            let stopBtn = document.getElementById("stop-crawl-btn");
            if (!stopBtn) {
                stopBtn = document.createElement('button');
                stopBtn.id = 'stop-crawl-btn';
                stopBtn.className = 'btn btn-danger btn-sm ms-2';
                stopBtn.innerHTML = '<i class="bi bi-stop-fill"></i> Stop';
                stopBtn.onclick = stopCrawling;
                searchBtn.parentNode.appendChild(stopBtn);
            }
            stopBtn.style.display = 'inline-block';

            // Clear previous results and setup new UI
            resultsContainer.innerHTML = `
                <div class="mb-3">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0">Crawling Progress</h6>
                        <small class="text-muted">Running: <span id="running-time">0s</span></small>
                    </div>
                    <div class="progress mb-3">
                        <div id="crawl-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" 
                             role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                            Starting...
                        </div>
                    </div>
                    <div id="crawl-stats" class="mb-3"></div>
                </div>
                <div id="realtime-status" class="realtime-status mb-3" style="max-height: 300px; overflow-y: auto;"></div>
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0">Found Links <span class="badge bg-primary" id="total-links-badge">0</span></h6>
                    </div>
                    <div class="card-body">
                        <div id="results-content"></div>
                    </div>
                </div>
            `;

            actionButtonsContainer.style.display = 'none';

            try {
                // Start crawling session
                const response = await fetch(`${API_BASE_URL}/api/start-url-crawl/`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                    },
                    body: JSON.stringify({
                        url: url,
                        max_depth: depth,
                        max_pages: 100,
                        use_selenium: true // Enable Selenium fallback
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to start crawling');
                }

                currentSessionId = data.session_id;

                // Start polling for results
                resultsInterval = setInterval(() => {
                    fetchCrawlResults(currentSessionId);
                }, 1000);

                // Start polling for status
                statusInterval = setInterval(() => {
                    fetchCrawlStatus(currentSessionId);
                }, 2000);

            } catch (e) {
                console.error(e);
                resultsContainer.innerHTML = `<div class="alert alert-danger">Failed to start crawling: ${e.message}</div>`;
                stopCrawling();
            }
        });
    }

    return { 
        init, 
        exportUrls, 
        exportSelectedUrls,
        stopCrawling
    };
}));