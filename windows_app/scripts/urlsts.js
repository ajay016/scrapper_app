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

    let lastRenderTime = 0;
    const RENDER_INTERVAL = 1000;
    
    // Filter variables
    let currentFilters = {
        linkType: 'all',
        depth: 'all',
        urlContains: '',
        urlExcludes: '',
        textContains: '',
        domain: '',
        regex: '',
        caseSensitive: false,
        invertFilter: false
    };
    
    let filteredResults = [];
    let isFilterActive = false;
    let isParsingWithFilters = false;

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
            case 'progress':
                message = update.message;
                type = 'info';
                icon = '📊';
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
                    <small class="text-muted">Просканированные страницы</small>
                    <div class="h6 mb-0">${stats.pages_crawled || 0}</div>
                </div>
                <div class="col">
                    <small class="text-muted">Ссылки найдены</small>
                    <div class="h6 mb-0">${stats.total_found || 0}</div>
                </div>
                <div class="col">
                    <small class="text-muted">Отфильтровано</small>
                    <div class="h6 mb-0">${stats.filtered_links || 0}</div>
                </div>
                <div class="col">
                    <small class="text-muted">BS4 Успех</small>
                    <div class="h6 mb-0">${stats.beautifulsoup_success || 0}</div>
                </div>
                <div class="col">
                    <small class="text-muted">Селен</small>
                    <div class="h6 mb-0">${stats.selenium_fallback || 0}</div>
                </div>
                <div class="col">
                    <small class="text-muted">Параллельно</small>
                    <div class="h6 mb-0">${stats.parallel_workers || 5}</div>
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
                    const resultsToShow = isFilterActive ? filteredResults : allResults;
                    paginatedResults = paginateResults(resultsToShow, currentPage, itemsPerPage);
                    document.getElementById('results-content').innerHTML = renderResults(paginatedResults, (currentPage - 1) * itemsPerPage);
                    renderPagination(totalPages, currentPage);
                    attachCheckboxHandlers();
                }
            });
        });
    }

    function attachCheckboxHandlers() {
        const actionButtonsContainer = document.getElementById('action-buttons-container');
        const checkboxes = document.querySelectorAll('.result-checkbox');

        if (checkboxes.length > 0) {
            actionButtonsContainer.style.display = 'flex';
            actionButtonsContainer.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="form-check me-3">
                        <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
                        <label class="form-check-label" for="mark-all-checkbox">Отметить все</label>
                    </div>
                    <button class="btn btn-success btn-sm me-2" id="save-selected-btn">
                        <i class="bi bi-save"></i> Сохранить выбранное
                    </button>
                    <button class="btn btn-outline-primary btn-sm me-2" id="export-selected-btn">
                        <i class="bi bi-download"></i> Экспортировать выбранное
                    </button>
                </div>
                <div class="d-flex align-items-center">
                    <span class="text-muted me-2 small" id="filtered-count">Показаны все результаты</span>
                    <button class="btn btn-outline-info btn-sm me-2" id="show-filters-btn">
                        <i class="bi bi-funnel"></i> URL-фильтры
                    </button>
                    <button class="btn btn-outline-warning btn-sm" id="parse-with-filters-btn">
                        <i class="bi bi-play-circle"></i> Анализ с помощью фильтров
                    </button>
                </div>
            `;
            
            // Add event listeners
            setTimeout(() => {
                // Export Selected button
                const exportSelectedBtn = document.getElementById('export-selected-btn');
                if (exportSelectedBtn) {
                    exportSelectedBtn.addEventListener('click', handleExportSelected);
                }
                
                // Parse with Filters button
                const parseWithFiltersBtn = document.getElementById('parse-with-filters-btn');
                if (parseWithFiltersBtn) {
                    parseWithFiltersBtn.addEventListener('click', startFilteredParsing);
                }
                
                // Show Filters button
                const showFiltersBtn = document.getElementById('show-filters-btn');
                if (showFiltersBtn) {
                    showFiltersBtn.addEventListener('click', toggleFilterPanel);
                }

                // Mark All checkbox
                const markAllCheckbox = document.getElementById('mark-all-checkbox');
                if (markAllCheckbox) {
                    markAllCheckbox.addEventListener('change', handleMarkAllChange);
                }

                // Save Selected button
                const saveSelectedBtn = document.getElementById('save-selected-btn');
                if (saveSelectedBtn) {
                    saveSelectedBtn.addEventListener('click', handleSaveSelected);
                }

            }, 0);
            
        } else {
            actionButtonsContainer.style.display = 'none';
        }

        // Individual checkbox handlers
        checkboxes.forEach(cb => {
            cb.addEventListener('change', function() {
                if (this.checked) {
                    selectedItems.add(this.dataset.id);
                } else {
                    selectedItems.delete(this.dataset.id);
                }
                updateMarkAllCheckbox();
            });
            
            // Auto-check all results by default
            cb.checked = true;
            selectedItems.add(cb.dataset.id);
        });

        updateMarkAllCheckbox();
    }

    // Event handler functions
    function handleExportSelected() {
        if (!selectedItems.size) {
            alert('Please select URLs to export');
            return;
        }
        exportSelectedUrls('csv');
    }

    function handleMarkAllChange(e) {
        const checked = e.target.checked;
        
        if (checked) {
            // Mark ALL results from ALL pages
            const allResultsToShow = isFilterActive ? filteredResults : allResults;
            selectedItems.clear();
            
            allResultsToShow.forEach((_, index) => {
                selectedItems.add(index.toString());
            });
            
            const checkboxes = document.querySelectorAll('.result-checkbox');
            checkboxes.forEach(cb => { 
                cb.checked = true;
            });
        } else {
            selectedItems.clear();
            
            const checkboxes = document.querySelectorAll('.result-checkbox');
            checkboxes.forEach(cb => { 
                cb.checked = false;
            });
        }
    }

    function handleSaveSelected() {
        if (!selectedItems.size) {
            alert('Please select at least one URL to save');
            return;
        }
        showSavePanel();
    }

    function updateMarkAllCheckbox() {
        const markAllCheckbox = document.getElementById('mark-all-checkbox');
        const allResultsToShow = isFilterActive ? filteredResults : allResults;
        
        if (!markAllCheckbox || allResultsToShow.length === 0) return;
        
        const allSelected = allResultsToShow.length === selectedItems.size;
        const someSelected = selectedItems.size > 0;
        
        markAllCheckbox.checked = allSelected;
        markAllCheckbox.indeterminate = someSelected && !allSelected;
    }

    async function fetchCrawlResults(sessionId) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/get-crawl-results/?session_id=${sessionId}`);
            const data = await response.json();

            if (response.ok && data.results) {
                let hasNewLinks = false;
                
                for (const update of data.results) {
                    renderRealTimeUpdate(update);

                    if (update.type === 'link_found') {
                        // Check if link already exists
                        const existingLink = allResults.find(r => r.url === update.link.url);
                        if (!existingLink) {
                            allResults.push(update.link);
                            hasNewLinks = true;
                        }
                    }

                    if (update.type === 'complete') {
                        handleCrawlComplete();
                    }
                }

                // Update UI if we have new links
                if (hasNewLinks && document.getElementById('results-content')) {
                    const now = Date.now();
                    const shouldRender = now - lastRenderTime > RENDER_INTERVAL;
                    
                    if (shouldRender) {
                        currentPage = 1;
                        const resultsToShow = isFilterActive ? filteredResults : allResults;
                        paginatedResults = paginateResults(resultsToShow, currentPage, itemsPerPage);
                        
                        const resultsContent = document.getElementById('results-content');
                        if (resultsContent) {
                            resultsContent.innerHTML = renderResults(paginatedResults, 0);
                            
                            const totalPages = Math.ceil(resultsToShow.length / itemsPerPage);
                            renderPagination(totalPages, currentPage);
                            attachCheckboxHandlers();
                            
                            // Update total links badge
                            const totalBadge = document.getElementById('total-links-badge');
                            if (totalBadge) totalBadge.textContent = allResults.length;
                            
                            // Auto-select all results
                            selectedItems.clear();
                            allResults.forEach((_, index) => {
                                selectedItems.add(index.toString());
                            });
                            
                            const checkboxes = document.querySelectorAll('.result-checkbox');
                            checkboxes.forEach(cb => {
                                cb.checked = true;
                            });
                            
                            updateMarkAllCheckbox();
                        }
                        
                        lastRenderTime = now;
                    }
                    
                    updateProgressBar(allResults.length);
                }

                if (data.stats) updateProgressStats(data.stats);
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
                
                // Handle completion
                if (data.status === 'completed' || data.status === 'stopped') {
                    handleCrawlComplete();
                }
            }
        } catch (error) {
            console.error('Error fetching crawl status:', error);
        }
    }

    async function handleCrawlComplete() {
        isCrawling = false;
        
        // Stop local intervals
        if (resultsInterval) {
            clearInterval(resultsInterval);
            resultsInterval = null;
        }
        
        if (statusInterval) {
            clearInterval(statusInterval);
            statusInterval = null;
        }
        
        // Stop background monitoring
        if (currentSessionId && window.__backgroundManager) {
            window.__backgroundManager.stopCrawl(currentSessionId);
        }
        
        const searchBtn = document.getElementById("search-url-btn");
        const stopBtn = document.getElementById("stop-crawl-btn");
        
        if (searchBtn) {
            searchBtn.disabled = false;
            searchBtn.innerHTML = '<i class="bi bi-link-45deg"></i> Начать сканировать';
        }
        
        if (stopBtn) {
            stopBtn.style.display = 'none';
        }

        // Update progress bar
        const progressBar = document.getElementById('crawl-progress-bar');
        if (progressBar) {
            progressBar.classList.remove('progress-bar-animated');
            progressBar.classList.add('bg-success');
        }

        // Show all results
        if (allResults.length) {
            currentPage = 1;
            paginatedResults = paginateResults(allResults, currentPage, itemsPerPage);
            document.getElementById('results-content').innerHTML = renderResults(paginatedResults, 0);

            const totalPages = Math.ceil(allResults.length / itemsPerPage);
            renderPagination(totalPages, currentPage);
            attachCheckboxHandlers();
            
            // Auto-select all results
            selectedItems.clear();
            allResults.forEach((_, index) => {
                selectedItems.add(index.toString());
            });
            
            const checkboxes = document.querySelectorAll('.result-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = true;
            });
            
            updateMarkAllCheckbox();
            
            // Show completion message
            const statusContainer = document.getElementById('realtime-status');
            if (statusContainer) {
                const completionDiv = document.createElement('div');
                completionDiv.className = 'alert alert-success alert-dismissible fade show mb-2';
                completionDiv.innerHTML = `
                    <strong>🎉 Crawling Completed!</strong><br>
                    <small>Found ${allResults.length} links from the crawl.</small>
                    <button type="button" class="btn-close btn-close-sm" data-bs-dismiss="alert"></button>
                `;
                statusContainer.appendChild(completionDiv);
            }
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
            
            // Stop background monitoring
            if (window.__backgroundManager) {
                window.__backgroundManager.stopCrawl(currentSessionId);
            }
        }
        
        isCrawling = false;
        currentSessionId = null;
        isParsingWithFilters = false;
        
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
            searchBtn.innerHTML = '<i class="bi bi-link-45deg"></i> Начать сканировать';
        }
        
        if (stopBtn) {
            stopBtn.style.display = 'none';
        }

        if (allResults.length) {
            currentPage = 1;
            paginatedResults = paginateResults(allResults, currentPage, itemsPerPage);
            document.getElementById('results-content').innerHTML = renderResults(paginatedResults, 0);

            const totalPages = Math.ceil(allResults.length / itemsPerPage);
            renderPagination(totalPages, currentPage);
            attachCheckboxHandlers();
            
            selectedItems.clear();
            allResults.forEach((_, index) => {
                selectedItems.add(index.toString());
            });
            
            const checkboxes = document.querySelectorAll('.result-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = true;
            });
            
            updateMarkAllCheckbox();
        }
    }

    // FILTER FUNCTIONS
    function getCurrentFilters() {
        return {
            linkType: document.getElementById('link-type-filter').value,
            depth: document.getElementById('depth-filter').value,
            urlContains: document.getElementById('url-contains-filter').value,
            urlExcludes: document.getElementById('url-excludes-filter').value,
            textContains: document.getElementById('text-contains-filter').value,
            domain: document.getElementById('domain-filter').value,
            regex: document.getElementById('regex-filter').value,
            caseSensitive: document.getElementById('case-sensitive').checked,
            invertFilter: document.getElementById('invert-filter').checked
        };
    }

    function applyDisplayFilters() {
        const filters = getCurrentFilters();
        currentFilters = filters;
        
        filteredResults = allResults.filter(item => {
            let matches = true;

            if (filters.linkType !== 'all') {
                if (filters.linkType === 'internal' && !item.is_internal) matches = false;
                if (filters.linkType === 'external' && !item.is_external) matches = false;
            }

            if (filters.depth !== 'all') {
                const depth = item.depth || 0;
                if (filters.depth === '3' && depth < 3) matches = false;
                else if (parseInt(filters.depth) !== depth) matches = false;
            }

            if (filters.urlContains) {
                const url = filters.caseSensitive ? item.url : item.url.toLowerCase();
                const search = filters.caseSensitive ? filters.urlContains : filters.urlContains.toLowerCase();
                if (!url.includes(search)) matches = false;
            }

            if (filters.urlExcludes) {
                const excludes = filters.urlExcludes.split(',').map(ex => ex.trim()).filter(ex => ex);
                const url = filters.caseSensitive ? item.url : item.url.toLowerCase();
                for (const exclude of excludes) {
                    const excludeTerm = filters.caseSensitive ? exclude : exclude.toLowerCase();
                    if (url.includes(excludeTerm)) {
                        matches = false;
                        break;
                    }
                }
            }

            if (filters.textContains) {
                const text = filters.caseSensitive ? (item.text || '') : (item.text || '').toLowerCase();
                const search = filters.caseSensitive ? filters.textContains : filters.textContains.toLowerCase();
                if (!text.includes(search)) matches = false;
            }

            if (filters.domain) {
                const domain = item.domain || new URL(item.url).hostname;
                const searchDomain = filters.caseSensitive ? filters.domain : filters.domain.toLowerCase();
                if (!domain.includes(searchDomain)) matches = false;
            }

            if (filters.regex) {
                try {
                    const regex = new RegExp(filters.regex, filters.caseSensitive ? '' : 'i');
                    if (!regex.test(item.url)) matches = false;
                } catch (e) {
                    console.error('Invalid regex pattern:', e);
                    matches = false;
                }
            }

            if (filters.invertFilter) {
                matches = !matches;
            }

            return matches;
        });

        isFilterActive = Object.values(filters).some(value => 
            value !== 'all' && value !== '' && value !== false
        );

        currentPage = 1;
        const resultsToShow = isFilterActive ? filteredResults : allResults;
        paginatedResults = paginateResults(resultsToShow, currentPage, itemsPerPage);
        
        const resultsContent = document.getElementById('results-content');
        if (resultsContent) {
            resultsContent.innerHTML = renderResults(paginatedResults, (currentPage - 1) * itemsPerPage);
            
            const totalPages = Math.ceil(resultsToShow.length / itemsPerPage);
            renderPagination(totalPages, currentPage);
            attachCheckboxHandlers();
        }
        
        updateFilteredCount();
    }

    function updateFilteredCount() {
        const filteredCount = document.getElementById('filtered-count');
        if (!filteredCount) return;

        if (isFilterActive) {
            filteredCount.textContent = `Showing ${filteredResults.length} of ${allResults.length} results`;
            filteredCount.className = 'text-info me-2 small fw-bold';
        } else {
            filteredCount.textContent = `Showing all ${allResults.length} results`;
            filteredCount.className = 'text-muted me-2 small';
        }
    }

    function clearFilters() {
        document.getElementById('link-type-filter').value = 'all';
        document.getElementById('depth-filter').value = 'all';
        document.getElementById('url-contains-filter').value = '';
        document.getElementById('url-excludes-filter').value = '';
        document.getElementById('text-contains-filter').value = '';
        document.getElementById('domain-filter').value = '';
        document.getElementById('regex-filter').value = '';
        document.getElementById('case-sensitive').checked = false;
        document.getElementById('invert-filter').checked = false;

        currentFilters = {
            linkType: 'all',
            depth: 'all',
            urlContains: '',
            urlExcludes: '',
            textContains: '',
            domain: '',
            regex: '',
            caseSensitive: false,
            invertFilter: false
        };

        isFilterActive = false;
        applyDisplayFilters();
    }

    function toggleFilterPanel() {
        const filterPanel = document.getElementById('filter-controls');
        if (filterPanel.style.display === 'none') {
            filterPanel.style.display = 'block';
        } else {
            filterPanel.style.display = 'none';
        }
    }

    async function startFilteredParsing() {
        const url = document.getElementById('url-input').value.trim();
        const depth = document.getElementById('url-depth-input').value || 2;
        const filters = getCurrentFilters();
        
        if (!url) {
            alert('Please enter a URL');
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
        isParsingWithFilters = true;

        // Update UI
        const searchBtn = document.getElementById("search-url-btn");
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Crawling with Filters...';
        
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

        // Show control panels
        document.getElementById('control-panel').style.display = 'block';
        document.getElementById('console-stats').style.display = 'block';
        document.getElementById('filter-controls').style.display = 'block';

        // Setup UI
        const resultsContainer = document.getElementById('results-container');
        resultsContainer.innerHTML = `
            <div class="mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0">Filtered Прогресс сканирования</h6>
                    <small class="text-muted">Бег: <span id="running-time">0s</span></small>
                </div>
                <div class="progress mb-3">
                    <div id="crawl-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated bg-warning" 
                         role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                        Начинаем фильтрованное сканирование...
                    </div>
                </div>
                <div id="crawl-stats" class="mb-3"></div>
            </div>
            <div id="realtime-status" class="realtime-status mb-3" style="max-height: 300px; overflow-y: auto;"></div>
            <div class="card">
                <div class="card-header">
                    <h6 class="mb-0">Найденные ссылки (Filtered) <span class="badge bg-warning" id="total-links-badge">0</span></h6>
                </div>
                <div class="card-body">
                    <div id="results-content"></div>
                </div>
            </div>
        `;

        document.getElementById('action-buttons-container').style.display = 'none';

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
                    use_selenium: true,
                    filters: filters,
                    max_workers: 5
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to start filtered crawling');
            }

            currentSessionId = data.session_id;

            // Register with background manager
            if (window.__backgroundManager) {
                window.__backgroundManager.startNewCrawl(currentSessionId, url, depth, filters);
            }

            // Add status message
            const statusContainer = document.getElementById('realtime-status');
            const filterInfo = document.createElement('div');
            filterInfo.className = 'alert alert-info alert-dismissible fade show mb-2';
            filterInfo.innerHTML = `
                <strong>Filtered Crawling Started</strong><br>
                <small>Crawl will continue even if you navigate away from this page.</small>
                <button type="button" class="btn-close btn-close-sm" data-bs-dismiss="alert"></button>
            `;
            statusContainer.appendChild(filterInfo);

            // Start local polling
            resultsInterval = setInterval(() => {
                fetchCrawlResults(currentSessionId);
            }, 1000);

            statusInterval = setInterval(() => {
                fetchCrawlStatus(currentSessionId);
            }, 2000);

        } catch (e) {
            console.error(e);
            resultsContainer.innerHTML = `<div class="alert alert-danger">Failed to start filtered crawling: ${e.message}</div>`;
            stopCrawling();
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
        const urlsToExport = isFilterActive ? filteredResults : allResults;
        if (!urlsToExport.length) {
            alert('No URLs to export');
            return;
        }

        let content = '';
        let filename = '';
        const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
        
        switch (format) {
            case 'csv':
                content = 'URL,Text,Type,Depth,Source URL,Domain\n';
                urlsToExport.forEach(item => {
                    const text = (item.text || '').replace(/"/g, '""');
                    const sourceUrl = (item.source_url || '').replace(/"/g, '""');
                    const domain = item.domain || new URL(item.url).hostname;
                    content += `"${item.url}","${text}","${item.is_internal ? 'Internal' : 'External'}","${item.depth || ''}","${sourceUrl}","${domain}"\n`;
                });
                filename = `urls_${timestamp}.csv`;
                break;
                
            case 'json':
                content = JSON.stringify(urlsToExport, null, 2);
                filename = `urls_${timestamp}.json`;
                break;
                
            case 'txt':
                urlsToExport.forEach(item => {
                    content += `URL: ${item.url}\n`;
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
                content = 'URL,Text,Type,Depth,Source URL,Domain\n';
                itemsToExport.forEach(item => {
                    const text = (item.text || '').replace(/"/g, '""');
                    const sourceUrl = (item.source_url || '').replace(/"/g, '""');
                    const domain = item.domain || new URL(item.url).hostname;
                    content += `"${item.url}","${text}","${item.is_internal ? 'Internal' : 'External'}","${item.depth || ''}","${sourceUrl}","${domain}"\n`;
                });
                filename = `selected_urls_${timestamp}.csv`;
                break;
                
            case 'json':
                content = JSON.stringify(itemsToExport, null, 2);
                filename = `selected_urls_${timestamp}.json`;
                break;
                
            case 'txt':
                itemsToExport.forEach(item => {
                    content += `URL: ${item.url}\n`;
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

    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    // Restore background crawl when page loads
    async function restoreBackgroundCrawl(sessionInfo) {
        try {
            const { sessionId, url, depth, filters, stats } = sessionInfo;
            
            // Set current session
            currentSessionId = sessionId;
            isCrawling = true;
            
            // Load existing results from background manager
            if (window.__backgroundManager) {
                const existingResults = window.__backgroundManager.getSessionResults(sessionId);
                allResults = existingResults;
            }
            
            // Update UI
            const searchBtn = document.getElementById("search-url-btn");
            if (searchBtn) {
                searchBtn.disabled = true;
                searchBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Ползание...';
                
                let stopBtn = document.getElementById("stop-crawl-btn");
                if (!stopBtn) {
                    stopBtn = document.createElement('button');
                    stopBtn.id = 'stop-crawl-btn';
                    stopBtn.className = 'btn btn-danger btn-sm ms-2';
                    stopBtn.innerHTML = '<i class="bi bi-stop-fill"></i> Останавливаться';
                    stopBtn.onclick = stopCrawling;
                    searchBtn.parentNode.appendChild(stopBtn);
                }
                stopBtn.style.display = 'inline-block';
            }
            
            // Show control panels
            document.getElementById('control-panel').style.display = 'block';
            document.getElementById('console-stats').style.display = 'block';
            document.getElementById('filter-controls').style.display = 'block';
            
            // Setup UI
            const resultsContainer = document.getElementById('results-container');
            resultsContainer.innerHTML = `
                <div class="mb-3">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0">Прогресс сканирования (Background)</h6>
                        <small class="text-muted">Бег: <span id="running-time">0s</span></small>
                    </div>
                    <div class="progress mb-3">
                        <div id="crawl-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" 
                             role="progressbar" style="width: ${allResults.length}%" aria-valuenow="${allResults.length}" aria-valuemin="0" aria-valuemax="100">
                            Restored from background...
                        </div>
                    </div>
                    <div id="crawl-stats" class="mb-3"></div>
                </div>
                <div id="realtime-status" class="realtime-status mb-3" style="max-height: 300px; overflow-y: auto;"></div>
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0">Найденные ссылки <span class="badge bg-primary" id="total-links-badge">${allResults.length}</span></h6>
                    </div>
                    <div class="card-body">
                        <div id="results-content"></div>
                    </div>
                </div>
            `;
            
            // Show existing results
            currentPage = 1;
            paginatedResults = paginateResults(allResults, currentPage, itemsPerPage);
            document.getElementById('results-content').innerHTML = renderResults(paginatedResults, 0);
            
            const totalPages = Math.ceil(allResults.length / itemsPerPage);
            renderPagination(totalPages, currentPage);
            attachCheckboxHandlers();
            
            // Auto-select all results
            selectedItems.clear();
            allResults.forEach((_, index) => {
                selectedItems.add(index.toString());
            });
            
            const checkboxes = document.querySelectorAll('.result-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = true;
            });
            
            updateMarkAllCheckbox();
            updateProgressBar(allResults.length);
            
            if (stats) {
                updateProgressStats(stats);
            }
            
            // Add status message
            const statusContainer = document.getElementById('realtime-status');
            const restoredDiv = document.createElement('div');
            restoredDiv.className = 'alert alert-info alert-dismissible fade show mb-2';
            restoredDiv.innerHTML = `
                <strong>Background Crawl Restored</strong><br>
                <small>Crawling ${url} (Depth: ${depth}) - ${allResults.length} links found so far.</small>
                <button type="button" class="btn-close btn-close-sm" data-bs-dismiss="alert"></button>
            `;
            statusContainer.appendChild(restoredDiv);
            
            // Start local polling
            resultsInterval = setInterval(() => {
                fetchCrawlResults(currentSessionId);
            }, 1000);
            
            statusInterval = setInterval(() => {
                fetchCrawlStatus(currentSessionId);
            }, 2000);
            
            console.log(`Restored background crawl ${sessionId} with ${allResults.length} results`);
            
        } catch (error) {
            console.error('Error restoring background crawl:', error);
        }
    }

    function init(params = {}) {
        const searchBtn = document.getElementById("search-url-btn");
        const urlInput = document.getElementById("url-input");
        const depthInput = document.getElementById("url-depth-input");
        const resultsContainer = document.getElementById("results-container");
        const actionButtonsContainer = document.getElementById("action-buttons-container");

        if (!searchBtn) {
            console.error('Search button not found');
            return;
        }

        // Check if we need to restore background crawls
        if (params.activeCrawls && params.activeCrawls.length > 0) {
            console.log('Restoring background crawls:', params.activeCrawls);
            
            // Restore the most recent crawl
            const latestCrawl = params.activeCrawls[params.activeCrawls.length - 1];
            restoreBackgroundCrawl(latestCrawl);
        } else {
            // Initialize empty state
            allResults = [];
            selectedItems.clear();
            
            if (resultsContainer && !document.getElementById('results-content')) {
                resultsContainer.innerHTML = `
                    <div class="text-center p-5">
                        <i class="bi bi-link-45deg display-1 text-muted"></i>
                        <h4 class="mt-3">URL Crawler</h4>
                        <p class="text-muted">Enter a URL to start crawling</p>
                    </div>
                `;
            }
        }

        // Initialize save panel
        initSavePanel();

        // Add filter event listeners
        const applyFiltersBtn = document.getElementById('apply-filters-btn');
        const clearFiltersBtn = document.getElementById('clear-filters-btn');
        const showFiltersBtn = document.getElementById('show-filters-btn');
        
        if (applyFiltersBtn) applyFiltersBtn.addEventListener('click', applyDisplayFilters);
        if (clearFiltersBtn) clearFiltersBtn.addEventListener('click', clearFilters);
        if (showFiltersBtn) showFiltersBtn.addEventListener('click', toggleFilterPanel);

        // Real-time filtering
        const filterInputs = [
            'url-contains-filter', 'url-excludes-filter', 'text-contains-filter', 'domain-filter', 'regex-filter'
        ];
        
        filterInputs.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('input', debounce(applyDisplayFilters, 500));
            }
        });

        // Filter on select changes
        const filterSelects = ['link-type-filter', 'depth-filter'];
        filterSelects.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', applyDisplayFilters);
            }
        });

        // Filter on checkbox changes
        const filterCheckboxes = ['case-sensitive', 'invert-filter'];
        filterCheckboxes.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', applyDisplayFilters);
            }
        });

        // Export button
        document.addEventListener('click', function(e) {
            if (e.target.id === 'write-to-file-btn' || e.target.closest('#write-to-file-btn')) {
                const urlsToExport = isFilterActive ? filteredResults : allResults;
                if (urlsToExport.length === 0) {
                    alert('No URLs to export');
                    return;
                }
                exportUrls('txt');
            }
        });

        // Control panel buttons
        const clearQueueBtn = document.getElementById('clear-queue-btn');
        const clearResultsBtn = document.getElementById('clear-results-btn');
        
        if (clearQueueBtn) {
            clearQueueBtn.addEventListener('click', () => {
                if (confirm('Clear all queued URLs?')) {
                    console.log('Clear queue functionality');
                }
            });
        }
        
        if (clearResultsBtn) {
            clearResultsBtn.addEventListener('click', () => {
                if (confirm('Clear all results?')) {
                    allResults = [];
                    filteredResults = [];
                    selectedItems.clear();
                    const resultsContent = document.getElementById('results-content');
                    if (resultsContent) resultsContent.innerHTML = '';
                    document.getElementById('action-buttons-container').style.display = 'none';
                    document.getElementById('filter-controls').style.display = 'none';
                    document.getElementById('control-panel').style.display = 'none';
                    document.getElementById('console-stats').style.display = 'none';
                    updateFilteredCount();
                }
            });
        }

        // Load projects
        fetch(`${API_BASE_URL}/api/project-list/`, {
            headers: { Authorization: `Bearer ${localStorage.getItem("accessToken")}` }
        })
        .then(res => res.json())
        .then(projects => {
            // Project loading
        });

        // Regular crawling (without filters)
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
            isParsingWithFilters = false;

            // Update UI
            searchBtn.disabled = true;
            searchBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Ползание...';
            
            let stopBtn = document.getElementById("stop-crawl-btn");
            if (!stopBtn) {
                stopBtn = document.createElement('button');
                stopBtn.id = 'stop-crawl-btn';
                stopBtn.className = 'btn btn-danger btn-sm ms-2';
                stopBtn.innerHTML = '<i class="bi bi-stop-fill"></i> Останавливаться';
                stopBtn.onclick = stopCrawling;
                searchBtn.parentNode.appendChild(stopBtn);
            }
            stopBtn.style.display = 'inline-block';

            // Show control panels
            document.getElementById('control-panel').style.display = 'block';
            document.getElementById('console-stats').style.display = 'block';
            document.getElementById('filter-controls').style.display = 'block';

            // Setup UI
            resultsContainer.innerHTML = `
                <div class="mb-3">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0">Прогресс сканирования</h6>
                        <small class="text-muted">Бег: <span id="running-time">0s</span></small>
                    </div>
                    <div class="progress mb-3">
                        <div id="crawl-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" 
                             role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                            Начинаем сканирование...
                        </div>
                    </div>
                    <div id="crawl-stats" class="mb-3"></div>
                </div>
                <div id="realtime-status" class="realtime-status mb-3" style="max-height: 300px; overflow-y: auto;"></div>
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0">Найденные ссылки <span class="badge bg-primary" id="total-links-badge">0</span></h6>
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
                        use_selenium: true,
                        max_workers: 5
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to start crawling');
                }

                currentSessionId = data.session_id;

                // Register with background manager
                if (window.__backgroundManager) {
                    window.__backgroundManager.startNewCrawl(currentSessionId, url, depth, {});
                }

                // Add status message
                const statusContainer = document.getElementById('realtime-status');
                const infoDiv = document.createElement('div');
                infoDiv.className = 'alert alert-info alert-dismissible fade show mb-2';
                infoDiv.innerHTML = `
                    <strong>Crawl Started</strong><br>
                    <small>Crawl will continue in background even if you navigate away.</small>
                    <button type="button" class="btn-close btn-close-sm" data-bs-dismiss="alert"></button>
                `;
                statusContainer.appendChild(infoDiv);

                // Start local polling
                resultsInterval = setInterval(() => {
                    fetchCrawlResults(currentSessionId);
                }, 1000);

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
        stopCrawling,
        startFilteredParsing,
        applyDisplayFilters,
        clearFilters,
        restoreBackgroundCrawl
    };
}));