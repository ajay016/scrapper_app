(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.__pages = root.__pages || {};
        root.__pages['keywords'] = factory();
    }
}(this, function () {

    function renderResults(results, level = 0, parentIndex = null, baseIndex = 0) { // CHANGED: added baseIndex
        if (!results || !results.length) return '';

        return results.map((r, index) => {
            const absoluteIndex = baseIndex + index; // ADDED: absolute index
            const uniqueId = parentIndex !== null ? `${parentIndex}-${absoluteIndex}` : `${absoluteIndex}`; // CHANGED
            const childrenHtml = renderResults(r.children, level + 1, uniqueId, 0); // CHANGED: pass 0 for children baseIndex

            const isChecked = selectedItems.has(uniqueId);

            return `
                <div class="card my-2 p-2" style="margin-left:${level * 20}px;">
                    <div class="form-check">
                        <input class="form-check-input result-checkbox" type="checkbox" 
                            data-url="${r.url}" data-title="${r.title || r.url}" 
                            data-id="${uniqueId}" data-has-children="${r.children && r.children.length > 0}"
                            ${isChecked ? 'checked' : ''}>
                        <label class="form-check-label">
                            <a href="${r.url}" target="_blank" rel="noreferrer noopener">
                                ${r.title || r.url}
                            </a>
                        </label>
                    </div>
                    ${childrenHtml || ''}
                </div>
            `;
        }).join('');
    }

    // Helper function to get all child checkboxes of a parent
    function getChildCheckboxes(parentId) {
        return document.querySelectorAll(`.result-checkbox[data-id^="${parentId}-"]`);
    }

    // Helper function to get parent checkbox
    function getParentCheckbox(childId) {
        const parts = childId.split('-');
        if (parts.length > 1) {
            parts.pop(); // Remove the last part to get parent ID
            const parentId = parts.join('-');
            return document.querySelector(`.result-checkbox[data-id="${parentId}"]`);
        }
        return null;
    }
    

    function updateParentState(checkbox) {
        const parentCheckbox = getParentCheckbox(checkbox.dataset.id);
        if (parentCheckbox) {
            // Parent should ALWAYS stay checked, never be auto-unchecked by children
            parentCheckbox.checked = true;
            parentCheckbox.indeterminate = false;
            
            // Recursively update grandparents (they should also always stay checked)
            updateParentState(parentCheckbox);
        }
    }


    const selectedItems = new Set();

    function init() {

        // Add these pagination variables
        let currentPage = 1;
        let itemsPerPage = 10;
        let paginatedResults = [];


        // file upload variables
        const fileInput = document.getElementById('keywords-file');
        const startButton = document.getElementById('start-parsing-btn');
        const filenameDisplay = document.querySelector('#filename-display .filename-text');
        const filenameText = filenameDisplay.querySelector('.filename-text');
        const removeFileBtn = document.querySelector('#filename-display .btn-remove-file');
        const errorMessage = document.getElementById('file-error-message');
        const resultsContainer = document.getElementById('results-container');

        // Show selected filename
        fileInput.addEventListener('change', () => {
            const file = fileInput.files[0];
            if (file) {
                filenameDisplay.textContent = file.name;
                removeFileBtn.style.display = 'inline-block';
            } else {
                filenameDisplay.textContent = 'No file selected';
                removeFileBtn.style.display = 'none';
            }
        });

        // Remove file button functionality
        removeFileBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            fileInput.value = '';
            resetFilenameDisplay();
        });

        // Clear filename when form is submitted successfully
        function resetFilenameDisplay() {
            filenameText.textContent = 'No file selected';
            filenameDisplay.classList.remove('has-file');
            removeFileBtn.style.display = 'none';
        }

        // Start button
        startButton.addEventListener('click', async (e) => {
            e.preventDefault();
            const file = fileInput.files[0];
            if (!file) {
                showFileError('Please select a file before starting.');
                return;
            }
            await uploadFileToBackend(file);
        });

        function showFileError(message) {
            const errorMessage = document.getElementById('file-error-message');
            const errorText = errorMessage.querySelector('.error-text');
            
            errorText.textContent = message;
            errorMessage.style.display = 'block';
            
            // Auto-hide after 5 seconds
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 5000);
        }

        // ckeckbox for bulk keywords starts
        function initializeBulkSearchCheckboxes() {
            const markAllCheckbox = document.getElementById('mark-all-checkbox');
            const keywordCheckboxes = document.querySelectorAll('.keyword-checkbox');
            const resultCheckboxes = document.querySelectorAll('.result-checkbox');
            
            // Mark All functionality - mark ALL results across ALL pages
            if (markAllCheckbox) {
                markAllCheckbox.onchange = (e) => {
                    const isChecked = e.target.checked;
                    window.markAllActive = isChecked;
                    
                    // Clear or fill selectedItems based on markAllActive
                    if (isChecked) {
                        // Add ALL results from ALL keywords to selectedItems
                        Object.entries(window.bulkResults).forEach(([keyword, results]) => {
                            results.forEach((result, index) => {
                                const uniqueId = `${keyword}-${index}`;
                                window.selectedItems.add(uniqueId);
                            });
                        });
                    } else {
                        // Clear all selections
                        window.selectedItems.clear();
                    }
                    
                    // Update all visible checkboxes on current page
                    keywordCheckboxes.forEach(checkbox => {
                        checkbox.checked = isChecked;
                    });
                    
                    resultCheckboxes.forEach(checkbox => {
                        checkbox.checked = isChecked;
                    });
                };
            }
            
            // Keyword checkbox functionality - mark ALL results for this keyword across ALL pages
            keywordCheckboxes.forEach(keywordCheckbox => {
                keywordCheckbox.onchange = (e) => {
                    const isChecked = e.target.checked;
                    const keyword = keywordCheckbox.dataset.keyword;
                    
                    // Update all results for this keyword in selectedItems
                    if (window.bulkResults[keyword]) {
                        window.bulkResults[keyword].forEach((result, index) => {
                            const uniqueId = `${keyword}-${index}`;
                            if (isChecked) {
                                window.selectedItems.add(uniqueId);
                            } else {
                                window.selectedItems.delete(uniqueId);
                            }
                        });
                    }
                    
                    // Update visible checkboxes for this keyword on current page
                    const keywordSection = keywordCheckbox.closest('.keyword-results-section');
                    const keywordResultCheckboxes = keywordSection.querySelectorAll('.result-checkbox');
                    
                    keywordResultCheckboxes.forEach(checkbox => {
                        checkbox.checked = isChecked;
                    });
                    
                    // Update Mark All checkbox state
                    updateMarkAllState();
                };
            });
            
            // Individual result checkbox functionality
            resultCheckboxes.forEach(checkbox => {
                checkbox.onchange = () => {
                    const itemId = checkbox.dataset.id;
                    
                    if (checkbox.checked) {
                        window.selectedItems.add(itemId);
                    } else {
                        window.selectedItems.delete(itemId);
                        // If unchecking any item, markAllActive should be false
                        window.markAllActive = false;
                        const markAllCheckbox = document.getElementById('mark-all-checkbox');
                        if (markAllCheckbox) {
                            markAllCheckbox.checked = false;
                            markAllCheckbox.indeterminate = false;
                        }
                    }
                    
                    // Update keyword checkbox state
                    updateKeywordCheckboxState(checkbox);
                    
                    // Update Mark All checkbox state
                    updateMarkAllState();
                };
                
                // Set initial state based on selectedItems
                checkbox.checked = window.selectedItems.has(checkbox.dataset.id);
            });
            
            // Set initial state for keyword checkboxes
            keywordCheckboxes.forEach(keywordCheckbox => {
                updateKeywordCheckboxState(keywordCheckbox);
            });
            
            // Set initial state for mark all checkbox
            updateMarkAllState();
        }

        function updateKeywordCheckboxState(keywordCheckbox) {
            const keyword = keywordCheckbox.dataset.keyword;
            if (!window.bulkResults[keyword]) return;
            
            const totalResultsForKeyword = window.bulkResults[keyword].length;
            let selectedCountForKeyword = 0;
            
            // Count how many results for this keyword are selected
            window.bulkResults[keyword].forEach((result, index) => {
                const uniqueId = `${keyword}-${index}`;
                if (window.selectedItems.has(uniqueId)) {
                    selectedCountForKeyword++;
                }
            });
            
            const allSelected = selectedCountForKeyword === totalResultsForKeyword;
            const someSelected = selectedCountForKeyword > 0 && selectedCountForKeyword < totalResultsForKeyword;
            
            keywordCheckbox.checked = allSelected;
            keywordCheckbox.indeterminate = someSelected;
        }

        function updateMarkAllState() {
            const markAllCheckbox = document.getElementById('mark-all-checkbox');
            if (!markAllCheckbox) return;
            
            // Calculate total results and selected results across ALL keywords
            let totalResults = 0;
            let selectedResults = 0;
            
            Object.entries(window.bulkResults).forEach(([keyword, results]) => {
                totalResults += results.length;
                results.forEach((result, index) => {
                    const uniqueId = `${keyword}-${index}`;
                    if (window.selectedItems.has(uniqueId)) {
                        selectedResults++;
                    }
                });
            });
            
            const allSelected = totalResults > 0 && selectedResults === totalResults;
            const someSelected = selectedResults > 0 && selectedResults < totalResults;
            
            markAllCheckbox.checked = allSelected;
            markAllCheckbox.indeterminate = someSelected;
            window.markAllActive = allSelected;
        }
        // checkbox for bulk keywords ends

        function renderBulkResults(results, startIndex = 0) {
            if (!results || results.length === 0) {
                return '<p>No results.</p>';
            }

            let html = '';
            results.forEach((result, index) => {
                const uniqueId = result.uniqueId || `${result.keyword}-${result.originalIndex || index}`;
                const isChecked = window.selectedItems.has(uniqueId) || window.markAllActive;
                
                html += `
                    <div class="card card-stream my-2 p-2">
                        <div class="form-check">
                            <input class="form-check-input result-checkbox" type="checkbox" 
                                data-url="${result.url}" data-title="${result.title || result.url}"
                                data-id="${uniqueId}" data-has-children="${result.children && result.children.length > 0}"
                                data-keyword="${result.keyword}"
                                ${isChecked ? 'checked' : ''}>
                            <label class="form-check-label">
                                <a href="${result.url}" target="_blank" rel="noreferrer noopener">
                                    ${result.title || result.url}
                                </a>
                            </label>
                        </div>
                    </div>
                `;
                
                // Recursively render children if they exist
                if (result.children && result.children.length > 0) {
                    result.children.forEach((child, childIndex) => {
                        const childUniqueId = `${uniqueId}-${childIndex}`;
                        const childChecked = window.selectedItems.has(childUniqueId) || window.markAllActive;
                        
                        html += `
                            <div class="card card-stream my-2 p-2" style="margin-left: 20px">
                                <div class="form-check">
                                    <input class="form-check-input result-checkbox" type="checkbox" 
                                        data-url="${child.url}" data-title="${child.title || child.url}"
                                        data-id="${childUniqueId}" data-has-children="false"
                                        data-keyword="${result.keyword}"
                                        ${childChecked ? 'checked' : ''}>
                                    <label class="form-check-label">
                                        <a href="${child.url}" target="_blank" rel="noreferrer noopener">
                                            ${child.title || child.url}
                                        </a>
                                    </label>
                                </div>
                            </div>
                        `;
                    });
                }
            });
            
            return html;
        }

        function renderBulkPagination(totalPages, currentPage) {
            // Remove existing pagination if any
            const existingPagination = document.getElementById('keyword-pagination');
            if (existingPagination) {
                existingPagination.remove();
            }

            // Create pagination container with your existing structure
            const paginationContainer = document.createElement('div');
            paginationContainer.id = 'keyword-pagination';
            paginationContainer.className = 'pagination-container mt-3';
            paginationContainer.innerHTML = `
                <nav aria-label="Keyword results pagination">
                    <ul class="pagination keyword-pagination-list justify-content-center"></ul>
                </nav>
            `;
            
            resultsContainer.appendChild(paginationContainer);

            // Use your existing renderPagination function
            renderPagination(totalPages, currentPage);

            // Add event listeners to pagination buttons
            const prevBtn = document.querySelector('.keyword-pagination-prev');
            const nextBtn = document.querySelector('.keyword-pagination-next');
            const pageBtns = document.querySelectorAll('.keyword-pagination-number');

            if (prevBtn) {
                prevBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = parseInt(e.target.dataset.page);
                    if (page && page !== currentPage) {
                        renderBulkPaginatedResults(page);
                    }
                });
            }

            if (nextBtn) {
                nextBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = parseInt(e.target.dataset.page);
                    if (page && page !== currentPage) {
                        renderBulkPaginatedResults(page);
                    }
                });
            }

            pageBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = parseInt(e.target.dataset.page);
                    if (page && page !== currentPage) {
                        renderBulkPaginatedResults(page);
                    }
                });
            });
        }

        // Render paginated results for bulk search
        function renderBulkPaginatedResults(page = 1) {
            const startIndex = (page - 1) * window.bulkItemsPerPage;
            let allResults = [];
            
            // Flatten all results for pagination
            Object.entries(window.bulkResults).forEach(([keyword, results]) => {
                results.forEach((result, index) => {
                    allResults.push({
                        ...result,
                        keyword: keyword,
                        globalIndex: allResults.length,
                        uniqueId: `${keyword}-${index}` // Add consistent unique ID
                    });
                });
            });

            const paginated = allResults.slice(startIndex, startIndex + window.bulkItemsPerPage);

            // Build results HTML grouped by keyword
            let resultsHtml = '<h5>Bulk Search Results</h5>';
            const keywordGroups = {};
            
            paginated.forEach(result => {
                if (!keywordGroups[result.keyword]) {
                    keywordGroups[result.keyword] = [];
                }
                keywordGroups[result.keyword].push(result);
            });

            Object.entries(keywordGroups).forEach(([keyword, results]) => {
                resultsHtml += `
                    <div class="keyword-results-section mb-4">
                        <div class="form-check mt-4">
                            <input class="form-check-input keyword-checkbox" type="checkbox" 
                                data-keyword="${keyword}">
                            <label class="form-check-label h5 mb-0">
                                Results for "${keyword}"
                            </label>
                            <span class="badge bg-secondary ms-2">${results.length} links</span>
                        </div>
                        <div class="keyword-results-content mt-2">
                            ${renderBulkResults(results, startIndex)}
                        </div>
                    </div>
                `;
            });

            resultsContainer.innerHTML = `
                <div id="action-buttons-container" class="d-flex align-items-center mt-5 mb-3 ms-2" style="display: flex;">
                    <div class="form-check me-5">
                        <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
                        <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
                    </div>
                    <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
                    <div class="dropdown ms-2">
                        <button class="btn btn-outline-success btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            <i class="bi bi-download"></i>
                            Export
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item export-btn" href="#" data-format="csv"><i class="bi bi-filetype-csv"></i> Export as CSV</a></li>
                            <li><a class="dropdown-item export-btn" href="#" data-format="excel"><i class="bi bi-file-earmark-excel"></i> Export as Excel</a></li>
                            <li><a class="dropdown-item export-btn" href="#" data-format="pdf"><i class="bi bi-filetype-pdf"></i> Export as PDF</a></li>
                        </ul>
                    </div>
                    <div id="links-counter" class="ms-3 px-2 py-1 border rounded small fw-bold">Links: ${allResults.length}</div>
                </div>
                <div id="save-message-container" class="mt-2"></div>
                <div id="results-content">${resultsHtml || '<p>No results.</p>'}</div>
            `;

            // Add export button event listeners for bulk paginated view
            setTimeout(() => {
                const exportBtns = document.querySelectorAll('.export-btn');
                exportBtns.forEach(btn => {
                    btn.addEventListener('click', function(e) {
                        e.preventDefault();
                        const format = this.getAttribute('data-format');
                        console.log('Export button clicked in bulk paginated view:', format);
                        exportResults(format);
                    });
                });
            }, 100);

            // Initialize bulk search checkboxes
            initializeBulkSearchCheckboxes();

            // Pagination UI
            if (allResults.length > window.bulkItemsPerPage) {
                const totalPages = Math.ceil(allResults.length / window.bulkItemsPerPage);
                window.currentBulkPage = page;
                renderBulkPagination(totalPages, page);
            }
        }

        // Also update the handleFileUpload function to reset on success
        async function uploadFileToBackend(file) {
            // Remove existing pagination before starting new search
            const existingPagination = document.getElementById('keyword-pagination');
            if (existingPagination) {
                existingPagination.remove();
            }
            
            // Also clear any existing results container content
            resultsContainer.innerHTML = '';

            const startButton = document.getElementById('start-parsing-btn');
            const originalText = startButton.innerHTML;
            
            try {
                // Show loading state
                startButton.disabled = true;
                startButton.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> Processing...';

                // Clear previous results
                resultsContainer.innerHTML = `
                    <div class="text-center">
                        <div class="spinner-border text-primary mb-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="searching-pulse">Starting bulk search for all keywords...</p>
                    </div>
                    <div id="progress-container" class="mt-2">
                        <div class="progress">
                            <div id="progress-bar" class="progress-bar" role="progressbar" style="width: 0%">0%</div>
                        </div>
                    </div>
                    <div id="results-tree-container" class="mt-3">
                        <div id="results-tree"></div>
                    </div>
                `;

                const treeContainerWrapper = document.getElementById('results-tree-container');
                const treeContainer = document.getElementById('results-tree');
                const progressBar = document.getElementById('progress-bar');

                // Set up container for scrolling
                treeContainerWrapper.style.maxHeight = '500px';
                treeContainerWrapper.style.overflowY = 'auto';

                // Global state for bulk search
                window.bulkResults = {}; // { keyword1: [results], keyword2: [results] }
                window.selectedItems = new Set();
                window.markAllActive = true;
                window.currentBulkPage = 1;
                window.bulkItemsPerPage = 10;

                // Create action buttons
                const actionButtonsContainer = document.createElement("div");
                actionButtonsContainer.id = 'action-buttons-container';
                actionButtonsContainer.className = 'd-flex align-items-center mt-5 mb-3 ms-2';
                actionButtonsContainer.style.display = 'none';
                actionButtonsContainer.innerHTML = `
                    <div class="form-check me-5">
                        <input class="form-check-input" type="checkbox" id="mark-all-checkbox" checked>
                        <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
                    </div>
                    <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
                    <div class="dropdown ms-2">
                        <button class="btn btn-outline-success btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            <i class="bi bi-download"></i>
                            Export
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item export-btn" href="#" data-format="csv"><i class="bi bi-filetype-csv"></i> Export as CSV</a></li>
                            <li><a class="dropdown-item export-btn" href="#" data-format="excel"><i class="bi bi-file-earmark-excel"></i> Export as Excel</a></li>
                            <li><a class="dropdown-item export-btn" href="#" data-format="pdf"><i class="bi bi-filetype-pdf"></i> Export as PDF</a></li>
                        </ul>
                    </div>
                    <div id="links-counter" class="ms-3 px-2 py-1 bg-light border rounded small fw-bold">Links: 0</div>
                `;

                // Add export button event listeners for bulk search
                setTimeout(() => {
                    const exportBtns = actionButtonsContainer.querySelectorAll('.export-btn');
                    exportBtns.forEach(btn => {
                        btn.addEventListener('click', function(e) {
                            e.preventDefault();
                            const format = this.getAttribute('data-format');
                            console.log('Export button clicked in bulk search:', format);
                            exportResults(format);
                        });
                    });
                }, 100);

                treeContainerWrapper.parentNode.insertBefore(actionButtonsContainer, treeContainerWrapper);

                // Create Stop button
                let stopBtn = document.getElementById('stop-search-btn');
                if (!stopBtn) {
                    stopBtn = document.createElement('button');
                    stopBtn.id = 'stop-search-btn';
                    stopBtn.className = 'btn btn-danger btn-sm ms-2';
                    stopBtn.textContent = 'Stop';
                }
                stopBtn.style.display = 'none';

                const formData = new FormData();
                formData.append('keywords_file', file);

                const urlInclude = document.getElementById('url-include-filter').value;
                const urlExclude = document.getElementById('url-exclude-filter').value;
                const domainFilter = document.getElementById('domain-filter').value;
                const fileTypeFilter = document.getElementById('filetype-filter').value;


                // Append filters to FormData if they have values
                if (urlInclude) formData.append('url_include', urlInclude);
                if (urlExclude) formData.append('url_exclude', urlExclude);
                if (domainFilter) formData.append('domain_filter', domainFilter);
                if (fileTypeFilter) formData.append('file_type_filter', fileTypeFilter);

                

                // Auto-scroll setup
                let autoScroll = true;
                treeContainerWrapper.addEventListener('scroll', () => {
                    const threshold = 50;
                    const isAtBottom = treeContainerWrapper.scrollTop + treeContainerWrapper.clientHeight >= treeContainerWrapper.scrollHeight - threshold;
                    autoScroll = isAtBottom;
                });

                // Update links counter
                function updateLinksCounter() {
                    const totalLinks = Object.values(window.bulkResults).reduce((sum, results) => sum + results.length, 0);
                    const linksCounter = document.getElementById('links-counter');
                    if (linksCounter) {
                        linksCounter.textContent = `Links: ${totalLinks}`;
                    }
                }

                // Render node for bulk search (similar to single search)
                function renderBulkNode(n, parentContainer, level = 0, parentIndex = null, baseIndex = 0, keyword) {
                    // ensure container exists
                    if (!window.bulkResults) window.bulkResults = {};
                    if (!window.bulkResults[keyword]) window.bulkResults[keyword] = [];

                    // Prefer existing uniqueId if provided by processStreamData; otherwise assign one now
                    let renderUniqueId;
                    if (n && n.uniqueId) {
                        renderUniqueId = n.uniqueId;
                        // ensure it's present in bulkResults (avoid duplicates)
                        const exists = window.bulkResults[keyword].some(r => r.uniqueId === renderUniqueId);
                        if (!exists) {
                            const resultIndex = window.bulkResults[keyword].length;
                            const resultWithId = { ...n, keyword: keyword, originalIndex: resultIndex, uniqueId: renderUniqueId };
                            window.bulkResults[keyword].push(resultWithId);
                        }
                    } else {
                        const resultIndex = window.bulkResults[keyword].length;
                        renderUniqueId = `${keyword}-${resultIndex}`;
                        const resultWithId = { ...n, keyword: keyword, originalIndex: resultIndex, uniqueId: renderUniqueId };
                        window.bulkResults[keyword].push(resultWithId);

                        // If mark-all is active, mark this id as selected
                        if (window.markAllActive) window.selectedItems.add(renderUniqueId);

                        // Update keyword counter if visible
                        try {
                            const keywordSection = parentContainer ? parentContainer.parentNode : null;
                            const keywordCounter = keywordSection ? keywordSection.querySelector('.keyword-counter') : null;
                            if (keywordCounter) keywordCounter.textContent = `${window.bulkResults[keyword].length} links`;
                            updateLinksCounter();
                        } catch (e) { /* ignore UI update errors */ }
                    }

                    const cardDiv = document.createElement("div");
                    cardDiv.className = "card card-stream my-2 p-2";
                    cardDiv.style.marginLeft = `${level * 20}px`;

                    const isChecked = window.selectedItems.has(renderUniqueId) || !!window.markAllActive;

                    cardDiv.innerHTML = `
                        <div class="form-check">
                            <input class="form-check-input result-checkbox" type="checkbox" 
                                data-url="${n.url || ''}" data-title="${(n.title || n.url) || ''}"
                                data-id="${renderUniqueId}" data-has-children="${n.children && n.children.length > 0}"
                                data-keyword="${keyword}"
                                ${isChecked ? 'checked' : ''}>
                            <label class="form-check-label">
                                <a href="${n.url || '#'}" target="_blank" rel="noreferrer noopener">
                                    ${n.title || n.url || 'no title'}
                                </a>
                            </label>
                        </div>
                    `;

                    parentContainer.appendChild(cardDiv);

                    const checkbox = cardDiv.querySelector(".result-checkbox");
                    const id = checkbox.dataset.id;

                    if (isChecked) window.selectedItems.add(id);

                    checkbox.onchange = () => {
                        // re-read id in case dataset changed
                        const checkedId = checkbox.dataset.id;
                        if (checkbox.checked) window.selectedItems.add(checkedId);
                        else window.selectedItems.delete(checkedId);

                        if (checkbox.dataset.hasChildren === "true") {
                            const childCheckboxes = cardDiv.querySelectorAll('.result-checkbox');
                            childCheckboxes.forEach(child => {
                                child.checked = checkbox.checked;
                                const childId = child.dataset.id;
                                if (checkbox.checked) window.selectedItems.add(childId);
                                else window.selectedItems.delete(childId);
                            });
                        }

                        if (window.markAllActive && !checkbox.checked) {
                            window.markAllActive = false;
                            const markEl = document.getElementById('mark-all-checkbox');
                            if (markEl) { markEl.checked = false; markEl.indeterminate = false; }
                        }

                        updateMarkAllCheckbox();
                    };

                    // Render children recursively; pass renderUniqueId as parentIndex to keep hierarchical context
                    if (n.children && n.children.length > 0) {
                        n.children.forEach(child => renderBulkNode(child, parentContainer, level + 1, renderUniqueId, 0, keyword));
                    }

                    // Auto-scroll
                    if (autoScroll) {
                        setTimeout(() => {
                            treeContainerWrapper.scrollTop = treeContainerWrapper.scrollHeight;
                        }, 10);
                    }
                }

                function updateMarkAllCheckbox() {
                    const allCheckboxes = treeContainer.querySelectorAll('.result-checkbox');
                    const allChecked = allCheckboxes.length > 0 && Array.from(allCheckboxes).every(cb => cb.checked);
                    const someChecked = Array.from(allCheckboxes).some(cb => cb.checked);
                    const markAllCheckbox = document.getElementById('mark-all-checkbox');
                    if (markAllCheckbox) {
                        markAllCheckbox.checked = allChecked;
                        markAllCheckbox.indeterminate = someChecked && !allChecked;
                    }
                }

                window.bulkSearchController = null;

                window.bulkSearchController = new AbortController();

                stopBtn.onclick = () => {
                    if (!window.bulkSearchController) return;

                    console.warn('⛔ Stopping bulk search...');
                    stopBtn.disabled = true;
                    stopBtn.textContent = 'Stopping...';

                    // Abort frontend fetch
                    window.bulkSearchController.abort();

                    // 🔹 Send stop request to backend
                    fetch(`${API_BASE_URL}/api/stop-bulk-search/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                    })
                    .then(res => res.json())
                    .then(data => console.log('🛑 Bulk stop response:', data))
                    .catch(err => console.error('⚠️ Bulk stop request failed:', err))
                    .finally(() => {
                        setTimeout(() => {
                            stopBtn.textContent = 'Stopped';
                            stopBtn.disabled = false;
                            stopBtn.style.display = 'none';

                            // Clean up UI
                            startButton.disabled = false;
                            startButton.innerHTML = originalText;

                            // Remove loading elements
                            const loadingBlock = document.querySelector('.text-center');
                            if (loadingBlock) loadingBlock.remove();
                            const progressContainer = document.getElementById('progress-container');
                            if (progressContainer) progressContainer.remove();

                            // ✅ Render paginated results with collected data
                            if (window.bulkResults && Object.keys(window.bulkResults).length > 0) {
                                renderBulkPaginatedResults(1);

                                // Re-initialize checkboxes after a short delay
                                setTimeout(() => {
                                    if (typeof initializeBulkSearchCheckboxes === 'function') {
                                        initializeBulkSearchCheckboxes();
                                    }
                                }, 100);
                            } else {
                                resultsContainer.innerHTML = `
                                    <div class="alert alert-info mt-3">
                                        Search was stopped. No results were collected.
                                    </div>
                                `;
                            }

                            // Clean up abort controller
                            window.bulkSearchController = null;
                        }, 600);
                    });
                };

                try {
                    // Get the bulk limit from the input field
                    const bulkLimitInput = document.getElementById('bulk-limit-input');
                    const bulkLimit = bulkLimitInput.value ? parseInt(bulkLimitInput.value) : 0; // Default to 20 if empty
                    const response = await fetch(`${API_BASE_URL}/api/bulk-keywords-search/?bulk_limit=${bulkLimit}`, {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${localStorage.getItem("accessToken")}`
                        },
                        body: formData,
                        signal: window.bulkSearchController.signal  // Add abort signal
                    });

                    if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.detail || 'Failed to start bulk search');
                    }

                    if (!response.body) {
                        throw new Error('ReadableStream not supported in this browser');
                    }

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';

                    // Process the stream
                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        
                        // Check if aborted
                        if (window.bulkSearchController.signal.aborted) {
                            break;
                        }
                        
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        
                        // Keep the last incomplete line in buffer
                        buffer = lines.pop() || '';
                        
                        for (const line of lines) {
                            if (line.trim() === '') continue;
                            
                            if (line.startsWith('event: ')) {
                                const eventType = line.slice(7).trim();
                                console.log('Event:', eventType);
                            } else if (line.startsWith('data: ')) {
                                try {
                                    const data = JSON.parse(line.slice(6));
                                    processStreamData(data);
                                } catch (e) {
                                    console.error('Parse error:', e, 'Line:', line);
                                }
                            }
                        }
                    }

                    // Stream completed
                    console.log('Bulk search completed');
                    
                } catch (error) {
                    if (error.name === 'AbortError') {
                        console.log('Bulk search was cancelled by user');
                        showFileError('Bulk search was cancelled');
                    } else {
                        console.error('Stream processing error:', error);
                        showFileError(error.message || 'Error processing bulk search');
                    }
                } finally {
                    // Clean up the controller
                    window.bulkSearchController = null;
                }

                // Function to process stream data
                function processStreamData(data) {
                    // Handle meta event
                    if (data.total_keywords !== undefined) {
                        console.log(`Total keywords to process: ${data.total_keywords}`);
                        return;
                    }

                    // Handle keyword_start event
                    if (data.keyword && data.index) {
                        const keyword = data.keyword.word;
                        const keywordId = data.keyword.id;

                        console.log(`Starting keyword ${data.index}: ${keyword}`);
                        console.log(`Starting keyword ID ${data.index}: ${keywordId}`);
                        
                        if (!window.bulkResults[keyword]) {
                            window.bulkResults[keyword] = [];

                            // Store keyword ID mapping
                            if (!window.bulkKeywordIds) {
                                window.bulkKeywordIds = {};
                            }
                            window.bulkKeywordIds[keyword] = keywordId;
                            
                            // Create keyword section
                            const keywordSection = document.createElement('div');
                            keywordSection.className = 'keyword-results-section mb-4';
                            keywordSection.id = `keyword-${keyword.replace(/\s+/g, '-')}`;
                            keywordSection.innerHTML = `
                                <div class="form-check mt-4">
                                    <input class="form-check-input keyword-checkbox" type="checkbox" 
                                        data-keyword="${keyword}" checked>
                                    <label class="form-check-label h5 mb-0">
                                        Results for "${keyword}"
                                    </label>
                                    <span class="badge bg-secondary ms-2 keyword-counter">0 links</span>
                                </div>
                                <div class="keyword-results-content mt-2" id="results-${keyword.replace(/\s+/g, '-')}"></div>
                            `;
                            
                            treeContainer.appendChild(keywordSection);

                            // Show action buttons when first keyword starts
                            if (actionButtonsContainer.style.display === 'none') {
                                actionButtonsContainer.style.display = 'flex';
                                
                                // Add Stop button to action container
                                const stopBtnWrapper = document.createElement('div');
                                stopBtnWrapper.className = 'ms-2';
                                stopBtnWrapper.appendChild(stopBtn);
                                actionButtonsContainer.appendChild(stopBtnWrapper);
                                stopBtn.style.display = 'inline-block';
                            }
                        }
                        return;
                    }

                    // Handle regular data with node
                    if (data.keyword && data.node) {
                        const keyword = data.keyword.word;
                        const node = data.node;
                        const progress = data.progress;

                        if (!window.bulkResults[keyword]) {
                            window.bulkResults[keyword] = [];
                        }

                        // Create unique ID for tracking
                        const resultIndex = window.bulkResults[keyword].length;
                        const resultWithId = {
                            ...node,
                            keyword: keyword,
                            originalIndex: resultIndex,
                            uniqueId: `${keyword}-${resultIndex}`
                        };

                        // Add to selectedItems if markAllActive
                        if (window.markAllActive) {
                            window.selectedItems.add(resultWithId.uniqueId);
                        }

                        // Render the node — this function will handle internal storage
                        const keywordResultsContainer = document.getElementById(`results-${keyword.replace(/\s+/g, '-')}`);
                        if (keywordResultsContainer) {
                            renderBulkNode(resultWithId, keywordResultsContainer, 0, null, 0, keyword);

                            // Update keyword counter
                            const keywordCounter = keywordResultsContainer.parentNode.querySelector('.keyword-counter');
                            if (keywordCounter) {
                                keywordCounter.textContent = `${window.bulkResults[keyword].length} links`;
                            }
                        }

                        // Update overall progress bar
                        if (progress && progressBar) {
                            const percent = progress.total ? Math.round((progress.current / progress.total) * 100) : 0;
                            progressBar.style.width = percent + "%";
                            progressBar.innerText = percent + "%";
                        }

                        updateLinksCounter();
                        console.log("✅ bulkResults updated for", keyword, window.bulkResults[keyword].length, "items total");
                        return;
                    }

                    // Handle keyword_done event
                    if (data.keyword && data.total_results !== undefined) {
                        console.log(`Completed keyword: ${data.keyword.word}, Results: ${data.total_results}, Engine: ${data.engine_used}`);
                        return;
                    }

                    // Handle done event
                    if (data.message) {
                        console.log('Bulk search complete:', data.message);
                        
                        // Clean up
                        if (stopBtn) {
                            stopBtn.style.display = 'none';
                        }
                        
                        startButton.disabled = false;
                        startButton.innerHTML = originalText;

                        // Remove loading elements
                        const loadingBlock = document.querySelector('.text-center');
                        if (loadingBlock) loadingBlock.remove();
                        const progressContainer = document.getElementById('progress-container');
                        if (progressContainer) progressContainer.remove();

                        // Clean up abort controller
                        window.bulkSearchController = null;

                        // Render paginated results for bulk search
                        renderBulkPaginatedResults(1);
                        return;
                    }
                }

            } catch (error) {
                console.error('Upload error:', error);
                showFileError(error.message || 'Failed to upload file. Please try again.');
                startButton.disabled = false;
                startButton.innerHTML = originalText;
            }
        }


        // Make uploadFileToBackend available globally if needed
        window.uploadFileToBackend = uploadFileToBackend;
        
        // ADD: Global selected items tracker
        // Reset selected items when initializing
        selectedItems.clear(); // Store item IDs that are selected across all pages


        const searchBtn = document.getElementById("search-keyword-btn");
        const keywordInput = document.getElementById("keyword-input");
        const depthInput = document.getElementById("depth-input");

        const projectSelect = document.getElementById("project-select");
        const folderSelect = document.getElementById("folder-select");

        // Save selected button functionality starts
        document.addEventListener('click', function(e) {
            if (e.target && e.target.id === 'save-selected-btn') {
                const messageContainer = document.getElementById('save-message-container');
                if (!messageContainer) return;

                function showAlert(type, message) {
                    const existingAlert = messageContainer.querySelector('.alert');
                    if (existingAlert) existingAlert.remove();

                    const alertDiv = document.createElement('div');
                    alertDiv.className = `alert alert-${type} alert-dismissible fade`;
                    alertDiv.role = 'alert';
                    alertDiv.innerHTML = `
                        ${message}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    `;
                    messageContainer.appendChild(alertDiv);
                    void alertDiv.offsetWidth; // force reflow
                    alertDiv.classList.add('show');
                }

                if (!projectSelect || !projectSelect.value) {
                    showAlert('danger', 'Please select a project first');
                    return;
                }

                // Check if it's a bulk search or single search
                const isBulkSearch = window.bulkResults && Object.keys(window.bulkResults).length > 0;
                const isSingleSearch = window.lastResults && Array.isArray(window.lastResults) && window.lastResults.length > 0;

                if (!isBulkSearch && !isSingleSearch) {
                    console.log('No search results found. Please run a search first.')
                    showAlert('danger', 'No search results found. Please run a search first.');
                    return;
                }

                // Use selectedItems for all pages
                const checkedIds = new Set(window.selectedItems || []);

                if (checkedIds.size === 0) {
                    showAlert('danger', 'Please select at least one item to save');
                    return;
                }

                console.debug('SAVE CLICKED -> window.selectedItems:', Array.from(window.selectedItems || []));
                
                let merged = [];
                let notFound = [];

                if (isBulkSearch) {
                    // Build keyword_results from window.bulkResults (your code stores an ARRAY per keyword)
                    const keywordResults = [];
                    const selectedSet = new Set(Array.from(window.selectedItems || []));

                    Object.keys(window.bulkResults || {}).forEach(keyword => {
                        const allResults = window.bulkResults[keyword] || []; // plain array in your app
                        const selectedForThisKeyword = allResults.filter(r => {
                            // r.uniqueId is created as `${keyword}-${resultIndex}` in processStreamData
                            if (!r) return false;
                            if (selectedSet.has(r.uniqueId)) return true;
                            // fallback checks (some older ids in your selectedSet may be numeric strings or just indexes)
                            if (selectedSet.has(String(r.originalIndex))) return true;
                            if (selectedSet.has(`${keyword}-${r.originalIndex}`)) return true;
                            // final fallback: selected entries that end with `-<index>` (covers some path-like ids)
                            return Array.from(selectedSet).some(s => typeof s === 'string' && s.endsWith(`-${r.originalIndex}`));
                        });

                        if (selectedForThisKeyword.length > 0) {
                            keywordResults.push({
                                keyword_id: (window.bulkKeywordIds && window.bulkKeywordIds[keyword]) || null,
                                keyword: keyword,
                                items: selectedForThisKeyword
                            });
                        }
                    });

                    if (keywordResults.length === 0) {
                        showAlert('danger', 'No selected results found in bulk search.');
                        return;
                    }

                    // Send to bulk endpoint expected by your backend
                    fetch(`${API_BASE_URL}/api/save-bulk-keyword-results/`, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                        },
                        body: JSON.stringify({
                            bulk_data: window.bulkResults,
                            keyword_results: keywordResults,
                            folder_id: folderSelect?.value || null,
                            project_id: projectSelect?.value || null
                        })
                    })
                    .then(async res => {
                        const payload = await res.json().catch(() => null);
                        if (!res.ok) {
                            const errMsg = (payload && payload.error) || (payload && payload.message) || 'Bulk save failed';
                            showAlert('danger', errMsg);
                            return;
                        }
                        showAlert('success', (payload && payload.message) || `Saved ${payload?.total_saved || 0} items across keywords`);
                    })
                    .catch(err => {
                        console.error("Bulk save failed", err);
                        showAlert('danger', 'Bulk save failed (network or server error)');
                    });
                } else {
                    // SINGLE SEARCH SAVE LOGIC
                    console.debug('Single search - lastResults length:', window.lastResults.length);
                    
                    // Check for single search keyword context
                    if (!window.currentKeywordId) {
                        showAlert('danger', 'Missing keyword context. Please run a new search.');
                        return;
                    }
                    
                    // normalize helper
                    function normalizeUrlForMatch(u) {
                        if (!u) return u;
                        try {
                            let s = u + '';
                            try { s = decodeURIComponent(s); } catch (e) { /* ignore decode errors */ }
                            s = s.replace(/^https?:\/\//i, '').replace(/^\/\/+/,'').replace(/\/+$/,'');
                            s = s.replace(/^www\./i, '');
                            return s;
                        } catch (e) {
                            return u;
                        }
                    }

                    // find by path
                    function findNodeByPath(nodes, pathArr) {
                        let current = nodes;
                        let node = null;
                        for (let i = 0; i < pathArr.length; i++) {
                            const idx = pathArr[i];
                            if (!Array.isArray(current) || typeof current[idx] === 'undefined') return null;
                            node = current[idx];
                            current = node.children || [];
                        }
                        return node;
                    }

                    // flexible recursive search by URL
                    function findNodeByUrlFlexible(nodes, id) {
                        if (!nodes || !nodes.length) return null;
                        const normId = normalizeUrlForMatch(id);

                        for (let i = 0; i < nodes.length; i++) {
                            const node = nodes[i];
                            if (!node) continue;

                            if (node.url === id) return node;
                            if (normalizeUrlForMatch(node.url) === normId) return node;

                            try {
                                if (decodeURIComponent(node.url) === id || decodeURIComponent(id) === node.url) return node;
                            } catch (e) { }

                            try {
                                const nnode = normalizeUrlForMatch(node.url);
                                if (nnode && normId && (nnode === normId || nnode.indexOf(normId) !== -1 || normId.indexOf(nnode) !== -1)) {
                                    return node;
                                }
                            } catch (e) {}

                            if (node.children && node.children.length) {
                                const found = findNodeByUrlFlexible(node.children, id);
                                if (found) return found;
                            }
                        }
                        return null;
                    }

                    const seenUrls = new Set();
                    (Array.from(window.selectedItems || [])).forEach(idStr => {
                        if (!idStr) return;

                        const pathLike = /^(\d+(-\d+)*)$/.test(idStr);
                        let origNode = null;
                        
                        if (pathLike) {
                            const pathArr = idStr.split('-').map(x => parseInt(x, 10));
                            origNode = findNodeByPath(window.lastResults, pathArr);
                        }

                        if (!origNode) {
                            origNode = findNodeByUrlFlexible(window.lastResults, idStr);
                        }

                        if (!origNode) {
                            notFound.push(idStr);
                        } else {
                            const urlKey = origNode.url || JSON.stringify(origNode).slice(0,50);
                            if (seenUrls.has(urlKey)) return;
                            merged.push(JSON.parse(JSON.stringify(origNode)));
                            seenUrls.add(urlKey);
                        }
                    });
                }

                // Common save logic for both bulk and single search
                if (!isBulkSearch && merged.length === 0) {
                    showAlert('danger', 'No valid items to save — selections did not match results. Check console logs for details.');
                    console.error('Save aborted: no matched nodes. selectedIds:', Array.from(window.selectedItems || []), 'notFound:', notFound);
                    return;
                }

                // POST to backend - handle bulk vs single search differently
                if (isBulkSearch) {
                    // For bulk search, we don't use keyword_id since we have multiple keywords
                    fetch(`${API_BASE_URL}/api/save-keyword-results/`, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                        },
                        body: JSON.stringify({
                            items: merged,
                            // No keyword_id for bulk search - backend should handle multiple keywords
                            folder_id: folderSelect?.value || null,
                            project_id: projectSelect?.value || null
                        })
                    })
                    .then(async res => {
                        const payload = await res.json().catch(() => null);
                        if (!res.ok) {
                            const errMsg = (payload && payload.error) || (payload && payload.message) || 'Save failed';
                            showAlert('danger', errMsg);
                            return;
                        }
                        showAlert('success', (payload && payload.message) || `Saved ${payload?.ids?.length || 0} items from bulk search`);
                    })
                    .catch(err => {
                        console.error("Bulk save failed", err);
                        showAlert('danger', 'Bulk save failed (network or server error)');
                    });
                } else {
                    // For single search, use the original logic with keyword_id
                    fetch(`${API_BASE_URL}/api/save-keyword-results/`, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                        },
                        body: JSON.stringify({
                            items: merged,
                            keyword_id: window.currentKeywordId,
                            folder_id: folderSelect?.value || null,
                            project_id: projectSelect?.value || null
                        })
                    })
                    .then(async res => {
                        const payload = await res.json().catch(() => null);
                        if (!res.ok) {
                            const errMsg = (payload && payload.error) || (payload && payload.message) || 'Save failed';
                            showAlert('danger', errMsg);
                            return;
                        }
                        showAlert('success', (payload && payload.message) || `Saved ${payload?.ids?.length || 0} items`);
                    })
                    .catch(err => {
                        console.error("Save failed", err);
                        showAlert('danger', 'Save failed (network or server error)');
                    });
                }
            }
        });
        // Save selected button functionality ends

        if (!searchBtn) return;

        console.log("Keywords page script loaded");

        // Load projects on page load
        fetch(`${API_BASE_URL}/api/project-list/`, {
            headers: {
                Authorization: `Bearer ${localStorage.getItem("accessToken")}`
            }
        })
            .then(res => res.json())
            .then(projects => {
                projectSelect.innerHTML = `<option value="">Выберите проект</option>`;
                projects.forEach(p => {
                    projectSelect.innerHTML += `<option value="${p.id}">${p.name}</option>`;
                });
            })
            .catch(err => console.error("Failed to load projects", err));


        // Pagination helper functions
        function paginateResults(results, page, itemsPerPage) {
            const startIndex = (page - 1) * itemsPerPage;
            const endIndex = startIndex + itemsPerPage;
            return results.slice(startIndex, endIndex);
        }

        function renderPagination(totalPages, currentPage) {
            const paginationContainer = document.getElementById('keyword-pagination');
            const paginationList = document.querySelector('.keyword-pagination-list');
            
            paginationContainer.classList.remove('d-none');
            paginationList.innerHTML = '';
            
            // Previous button
            const prevLi = document.createElement('li');
            prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
            prevLi.innerHTML = `
                <a class="page-link keyword-pagination-prev" href="#" data-page="${currentPage - 1}">
                    &laquo; Previous
                </a>
            `;
            paginationList.appendChild(prevLi);
            
            // Always show first 3 pages
            for (let i = 1; i <= Math.min(3, totalPages); i++) {
                if (i > totalPages) break;
                const pageLi = document.createElement('li');
                pageLi.className = `page-item ${i === currentPage ? 'active' : ''}`;
                pageLi.innerHTML = `
                    <a class="page-link keyword-pagination-number" href="#" data-page="${i}">
                        ${i}
                    </a>
                `;
                paginationList.appendChild(pageLi);
            }
            
            // Add ellipsis if needed (when there are pages between first 3 and current page - 2)
            if (currentPage > 5) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = `<span class="page-link">...</span>`;
                paginationList.appendChild(ellipsisLi);
            }
            
            // Show pages around current page (current - 2 to current + 2)
            const startPage = Math.max(4, currentPage - 2);
            const endPage = Math.min(totalPages - 3, currentPage + 2);
            
            for (let i = startPage; i <= endPage; i++) {
                // Skip if we already showed this page in first 3 or it's beyond total pages
                if (i <= 3 || i > totalPages) continue;
                
                const pageLi = document.createElement('li');
                pageLi.className = `page-item ${i === currentPage ? 'active' : ''}`;
                pageLi.innerHTML = `
                    <a class="page-link keyword-pagination-number" href="#" data-page="${i}">
                        ${i}
                    </a>
                `;
                paginationList.appendChild(pageLi);
            }
            
            // Add ellipsis if needed (when there are pages between current page + 2 and last 3)
            if (currentPage < totalPages - 4) {
                const ellipsisLi = document.createElement('li');
                ellipsisLi.className = 'page-item disabled';
                ellipsisLi.innerHTML = `<span class="page-link">...</span>`;
                paginationList.appendChild(ellipsisLi);
            }
            
            // Always show last 3 pages
            const lastStartPage = Math.max(totalPages - 2, 4); // Don't overlap with first 3
            for (let i = Math.max(lastStartPage, endPage + 1); i <= totalPages; i++) {
                // Skip if we already showed this page in the middle section
                if (i <= endPage) continue;
                
                const pageLi = document.createElement('li');
                pageLi.className = `page-item ${i === currentPage ? 'active' : ''}`;
                pageLi.innerHTML = `
                    <a class="page-link keyword-pagination-number" href="#" data-page="${i}">
                        ${i}
                    </a>
                `;
                paginationList.appendChild(pageLi);
            }
            
            // Next button
            const nextLi = document.createElement('li');
            nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
            nextLi.innerHTML = `
                <a class="page-link keyword-pagination-next" href="#" data-page="${currentPage + 1}">
                    Next &raquo;
                </a>
            `;
            paginationList.appendChild(nextLi);
        }

        // Helper function to get all result IDs recursively
        function getAllResultIds(results, parentIndex = null) {
            const ids = [];
            
            results.forEach((result, index) => {
                const uniqueId = parentIndex !== null ? `${parentIndex}-${index}` : `${index}`;
                ids.push(uniqueId);
                
                if (result.children && result.children.length > 0) {
                    ids.push(...getAllResultIds(result.children, uniqueId));
                }
            });
            
            return ids;
        }


        // const resultsContainer = document.getElementById("results-content");
        // const progressBar = document.getElementById("progress-bar");



        // Delegated handler for Mark All checkbox — always uses the live element
        document.addEventListener('change', function (e) {
            if (!e.target) return;
            if (e.target.id !== 'mark-all-checkbox') return;

            const markAllChecked = !!e.target.checked;
            // toggle global behavior so future nodes respect this state
            window.markAllActive = markAllChecked;

            // collect all known URLs from the full results tree
            function collectAllUrls(nodes, out = []) {
                for (let i = 0; i < (nodes || []).length; i++) {
                    const n = nodes[i];
                    if (!n) continue;
                    if (n.url) out.push(n.url);
                    if (n.children && n.children.length) collectAllUrls(n.children, out);
                }
                return out;
            }

            const allUrls = collectAllUrls(window.lastResults || []);

            if (markAllChecked) {
                allUrls.forEach(url => window.selectedItems.add(url));
            } else {
                allUrls.forEach(url => window.selectedItems.delete(url));
            }

            // update any checkboxes currently rendered in the DOM
            const visibleCheckboxes = document.querySelectorAll('.result-checkbox');
            visibleCheckboxes.forEach(cb => {
                cb.checked = markAllChecked;
                cb.indeterminate = false;
                const id = cb.dataset.id;
                if (markAllChecked) window.selectedItems.add(id);
                else window.selectedItems.delete(id);
            });

            // if you have a function to update the mark-all UI state, call it.
            // e.g. updateMarkAllCheckboxForCheckboxList(document.getElementById('mark-all-checkbox'), visibleCheckboxes);
        });

        // Update links counter
        function updateLinksCounter() {
            const linksCounter = document.getElementById('links-counter');
            if (linksCounter) {
                linksCounter.textContent = `Links: ${window.lastResults.length}`;
            }
        }

        searchBtn.addEventListener("click", async () => {
            const keyword = (keywordInput.value || '').trim();
            const depth = depthInput.value || 0;

            if (!keyword) {
                resultsContainer.innerHTML = `<p class="text-danger">Please enter a keyword</p>`;
                return;
            }

            // CLEAR EXISTING PAGINATION - ADD THIS
            const existingPagination = document.getElementById('keyword-pagination');
            if (existingPagination) {
                existingPagination.remove();
            }

            // Clear any bulk search specific elements if they exist
            const bulkPagination = document.querySelector('.pagination-container');
            if (bulkPagination) {
                bulkPagination.remove();
            }

            // Reset any conflicting global states
            window.bulkResults = null;
            window.currentBulkPage = 1;

            try {
                searchBtn.disabled = true;
                searchBtn.innerHTML = `
                    <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                   Идет поиск...
                `;
                

                console.log('Searching single search results')

                // Auto-scroll to results container when search starts
                setTimeout(() => {
                    resultsContainer.scrollIntoView({ 
                        behavior: 'smooth', 
                        block: 'start' 
                    });
                }, 100);

                // Initial loading + progress
                resultsContainer.innerHTML = `
                    <div id="loading-container" class="text-center mb-3">
                        <div class="spinner-border text-primary mb-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="searching-pulse">Поиск "${keyword}"...</p>
                    </div>
                    <div id="progress-container" class="mt-2">
                        <div class="progress">
                            <div id="progress-bar" class="progress-bar" role="progressbar" style="width: 0%">0%</div>
                        </div>
                    </div>
                    <div id="results-tree-container" class="mt-3">
                        <ul id="results-tree" class="list-group list-group-flush"></ul>
                    </div>
                `;

                const treeContainerWrapper = document.getElementById('results-tree-container');
                const treeContainer = document.getElementById('results-tree');
                const progressBar = document.getElementById('progress-bar');

                // Set fixed height and scrolling for results container
                treeContainerWrapper.style.maxHeight = '500px';
                treeContainerWrapper.style.overflowY = 'auto';
                treeContainerWrapper.style.border = '1px solid #ddd';

                // Auto-scroll setup
                let autoScroll = true;
                let scrollTimeout;

                treeContainerWrapper.addEventListener('scroll', () => {
                    const threshold = 50;
                    const isAtBottom = treeContainerWrapper.scrollTop + treeContainerWrapper.clientHeight >= treeContainerWrapper.scrollHeight - threshold;
                    autoScroll = isAtBottom;
                });

                // Use MutationObserver to detect when new content is added and scroll to it
                const scrollObserver = new MutationObserver((mutations) => {
                    if (autoScroll) {
                        // Cancel any pending scroll
                        if (scrollTimeout) clearTimeout(scrollTimeout);
                        
                        // Schedule scroll after DOM update
                        scrollTimeout = setTimeout(() => {
                            treeContainerWrapper.scrollTo({
                                top: treeContainerWrapper.scrollHeight,
                                behavior: 'smooth'
                            });
                        }, 100);
                    }
                });

                // Single source of truth
                window.lastResults = [];
                window.selectedItems = new Set();
                
                // Since markAllActive is true, we'll add items to selectedItems as they come in
                // The renderNode function will handle checking them based on markAllActive

                window.markAllActive = true;
                updateLinksCounter();

                // Create action buttons (Mark All + Save)
                const actionButtonsContainer = document.createElement("div");
                actionButtonsContainer.id = 'action-buttons-container';
                actionButtonsContainer.className = 'd-flex align-items-center mt-5 mb-3 ms-2';
                actionButtonsContainer.style.display = 'none';

                actionButtonsContainer.innerHTML = `
                    <div class="form-check me-5">
                        <input class="form-check-input" type="checkbox" id="mark-all-checkbox" checked>
                        <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
                    </div>
                    <button id="save-selected-btn" class="btn btn-primary btn-sm">Сохранить выбранное</button>
                    <div class="dropdown ms-2">
                        <button class="btn btn-outline-success btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            <i class="bi bi-download"></i>
                          Экспорт
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item export-btn" href="#" data-format="csv"><i class="bi bi-filetype-csv"></i> Экспорт as CSV</a></li>
                            <li><a class="dropdown-item export-btn" href="#" data-format="excel"><i class="bi bi-file-earmark-excel"></i> Экспорт as Excel</a></li>
                            <li><a class="dropdown-item export-btn" href="#" data-format="pdf"><i class="bi bi-filetype-pdf"></i> Экспорт as PDF</a></li>
                        </ul>
                    </div>
                    <div id="links-counter" class="links-counter ms-3 text-muted small">Ссылки: 0</div>
                `;

                // Add export button event listeners
                setTimeout(() => {
                    const exportBtns = document.querySelectorAll('.export-btn');
                    exportBtns.forEach(btn => {
                        btn.addEventListener('click', function(e) {
                            e.preventDefault();
                            const format = this.getAttribute('data-format');
                            console.log('Export button clicked:', format);
                            exportResults(format);
                        });
                    });
                }, 100);

                treeContainerWrapper.parentNode.insertBefore(actionButtonsContainer, treeContainerWrapper);

                const markAllCheckbox = document.getElementById('mark-all-checkbox');
                const saveSelectedBtn = document.getElementById('save-selected-btn');

                // Create Stop button to stop the Crawking starts
                let stopBtn = document.getElementById('stop-search-btn');
                if (!stopBtn) {
                    stopBtn = document.createElement('button');
                    stopBtn.id = 'stop-search-btn';
                    stopBtn.className = 'btn btn-danger btn-sm ms-2';
                    stopBtn.textContent = 'Stop';
                }
                stopBtn.style.display = 'none'; // Hide initially
                stopBtn.disabled = false;
                // Create Stop button to stop the Crawking ends

                // SSE node rendering
                function renderNode(n, parentContainer, level = 0, parentIndex = null, baseIndex = 0) {
                    const absoluteIndex = baseIndex + (window.lastResults.length || 0);
                    const uniqueId = parentIndex !== null ? `${parentIndex}-${absoluteIndex}` : `${absoluteIndex}`;

                    // ✅ Create the same card structure used in renderResults()
                    const cardDiv = document.createElement("div");
                    cardDiv.className = "card card-stream my-2 p-2";
                    cardDiv.style.marginLeft = `${level * 20}px`;

                    const isChecked = window.selectedItems.has(uniqueId) || !!window.markAllActive;

                    cardDiv.innerHTML = `
                        <div class="form-check">
                            <input class="form-check-input result-checkbox" type="checkbox" 
                                data-url="${n.url}" data-title="${n.title || n.url}"
                                data-id="${uniqueId}" data-has-children="${n.children && n.children.length > 0}"
                                ${isChecked ? 'checked' : ''}>
                            <label class="form-check-label">
                                <a href="${n.url}" target="_blank" rel="noreferrer noopener">
                                    ${n.title || n.url}
                                </a>
                            </label>
                        </div>
                    `;

                    parentContainer.appendChild(cardDiv);

                    const checkbox = cardDiv.querySelector(".result-checkbox");
                    const id = checkbox.dataset.id;

                    // Maintain selected items + Mark All sync
                    if (isChecked) window.selectedItems.add(id);

                    checkbox.onchange = () => {
                        if (checkbox.checked) window.selectedItems.add(id);
                        else window.selectedItems.delete(id);

                        if (checkbox.dataset.hasChildren === "true") {
                            const childCheckboxes = cardDiv.querySelectorAll('.result-checkbox');
                            childCheckboxes.forEach(child => {
                                child.checked = checkbox.checked;
                                const childId = child.dataset.id;
                                if (checkbox.checked) window.selectedItems.add(childId);
                                else window.selectedItems.delete(childId);
                            });
                        }

                        if (window.markAllActive && !checkbox.checked) {
                            window.markAllActive = false;
                            const markEl = document.getElementById('mark-all-checkbox');
                            if (markEl) { markEl.checked = false; markEl.indeterminate = false; }
                        }

                        updateMarkAllCheckbox();
                    };

                    // ✅ Recursive children rendering, keeping card layout indentation
                    if (n.children && n.children.length > 0) {
                        n.children.forEach(child => renderNode(child, parentContainer, level + 1, uniqueId, 0));
                    }
                }

                // Update mark all checkbox state
                function updateMarkAllCheckbox() {
                    const allCheckboxes = treeContainer.querySelectorAll('.result-checkbox');
                    const allChecked = allCheckboxes.length > 0 && Array.from(allCheckboxes).every(cb => cb.checked);
                    const someChecked = Array.from(allCheckboxes).some(cb => cb.checked);
                    markAllCheckbox.checked = allChecked;
                    markAllCheckbox.indeterminate = someChecked && !allChecked;
                }

                window.currentKeywordId = null;
                console.log('limit given: ', depth)

                // SSE connection
                // const evtSource = new EventSource(`${API_BASE_URL}/api/search-keywords/?q=${encodeURIComponent(keyword)}&limit=${depth}`);

                // Create abort controller for the search
                window.searchController = new AbortController();

                stopBtn.onclick = () => {
                    if (window.searchController) {
                        console.warn('⛔ Stopping search...');
                        stopBtn.disabled = true;
                        stopBtn.textContent = 'Stopping...';
                        
                        // Abort the fetch request
                        window.searchController.abort();
                        
                        // Optional: Send stop request to backend
                        fetch(`${API_BASE_URL}/api/stop_search/`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                keyword: keyword,
                                filters: {
                                    url_include: urlInclude,
                                    url_exclude: urlExclude,
                                    domain_filter: domainFilter,
                                    file_type_filter: fileTypeFilter
                                }
                            })
                        })
                        .then(res => res.json())
                        .then(data => console.log('🛑 Stop response:', data))
                        .catch(err => console.error('⚠️ Stop request failed:', err))
                        .finally(() => {
                            // Reset UI
                            setTimeout(() => {
                                stopBtn.textContent = 'Stopped';
                                stopBtn.disabled = false;
                                stopBtn.style.display = 'none';
                                
                                searchBtn.disabled = false;
                                searchBtn.innerHTML = 'Search';

                                // Remove loading elements
                                const loadingBlock = document.getElementById('loading-container');
                                if (loadingBlock) loadingBlock.remove();
                                const progressContainer = document.getElementById('progress-container');
                                if (progressContainer) progressContainer.remove();
                                
                                // Render collected results if any
                                if (window.lastResults && window.lastResults.length > 0) {
                                    renderPaginatedResults(1);
                                } else {
                                    resultsContainer.innerHTML = `
                                        <div class="alert alert-info mt-3">
                                            Search was stopped. No results were collected.
                                        </div>
                                    `;
                                }
                            }, 600);
                        });
                    }
                };

                const requestBody = {
                    q: keyword,
                    limit: depth
                };

                const urlInclude = document.getElementById('url-include-filter').value;
                const urlExclude = document.getElementById('url-exclude-filter').value;
                const domainFilter = document.getElementById('domain-filter').value;
                const fileTypeFilter = document.getElementById('filetype-filter').value;

                // Add filters to request body if they have values
                if (urlInclude) requestBody.url_include = urlInclude;
                if (urlExclude) requestBody.url_exclude = urlExclude;
                if (domainFilter) requestBody.domain_filter = domainFilter;
                if (fileTypeFilter) requestBody.file_type_filter = fileTypeFilter;

                console.log('Search request body:', requestBody);

                if (actionButtonsContainer.style.display === 'none') {
                    actionButtonsContainer.style.display = 'flex';
                    
                    // Add Stop button to action buttons container
                    if (!document.getElementById('stop-search-btn')) {
                        const stopBtnWrapper = document.createElement('div');
                        stopBtnWrapper.className = 'ms-2';
                        stopBtnWrapper.appendChild(stopBtn);
                        actionButtonsContainer.appendChild(stopBtnWrapper);
                    }
                    stopBtn.style.display = 'inline-block';
                }

                try {
                    const response = await fetch(`${API_BASE_URL}/api/search-keywords/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${localStorage.getItem("accessToken")}`
                        },
                        body: JSON.stringify(requestBody),
                        signal: window.searchController.signal
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    if (!response.body) {
                        throw new Error('ReadableStream not supported in this browser');
                    }

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';

                    // Process the stream
                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) {
                            console.log('Stream finished by backend (EOF)');
                            // mark EOF — actual cleanup will be handled by the done flag logic in processStreamData or after loop
                            window.backendSignalledDone = true;
                            break;
                        }
                        
                        // Check if aborted
                        // if (window.searchController.signal.aborted) {
                        //     break;
                        // }

                        if (window.searchController && window.searchController.signal.aborted) {
                            break;
                        }
                        
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        
                        // Keep the last incomplete line in buffer
                        buffer = lines.pop() || '';
                        
                        for (const line of lines) {
                            if (line.trim() === '') continue;
                            
                            if (line.startsWith('event: ')) {
                                const eventType = line.slice(7).trim();
                                console.log('Event:', eventType);
                                
                                // Handle done event from server-sent events
                                if (eventType === 'done') {
                                    // mark that backend signalled completion; let processStreamData handle cleanup
                                    console.log('Received done event from server');
                                    // set a flag we can check later if needed
                                    window.backendSignalledDone = true;
                                    // Do not reset UI here — cleanup will happen inside processStreamData or after stream EOF
                                }
                            } else if (line.startsWith('data: ')) {
                                try {
                                    const data = JSON.parse(line.slice(6));
                                    processStreamData(data);
                                } catch (e) {
                                    console.error('Parse error:', e, 'Line:', line);
                                }
                            }
                        }
                    }

                    // Stream completed - additional cleanup
                    console.log('Search completed');
                    searchBtn.disabled = false;
                    searchBtn.innerHTML = 'Search';

                    // Final fallback - if we have results but pagination didn't show, render them
                    setTimeout(() => {
                        if (window.lastResults && window.lastResults.length > 0 && 
                            !document.getElementById('results-content')) {
                            console.log('Fallback: rendering paginated results');
                            renderPaginatedResults(1);
                        }
                    }, 1000);
                    
                } catch (error) {
                    if (error.name === 'AbortError') {
                        console.log('Search was cancelled by user');
                    } else {
                        console.error('Stream processing error:', error);
                        resultsContainer.innerHTML = `<p class="text-danger">Error: ${error.message}</p>`;
                    }
                } finally {
                    // Clean up
                    window.searchController = null;
                }

                // Function to process stream data (replaces your SSE event handlers)
                function processStreamData(data) {
                    // Handle meta event
                    if (data.keyword && data.keyword.id) {
                        window.currentKeywordId = data.keyword.id;
                        window.currentKeyword = data.keyword;
                        console.debug('client: got keyword from meta ->', window.currentKeywordId);
                        return;
                    }

                    // Handle progress and node data
                    const node = data.node;
                    const progress = data.progress;

                    if (progress && progressBar && typeof progress.current === 'number' && typeof progress.total === 'number' && progress.total > 0) {
                        const percent = Math.round((progress.current / progress.total) * 100);
                        progressBar.style.width = percent + "%";
                        progressBar.innerText = percent + "%";
                    } else if (progressBar && (typeof progress === 'undefined' || progress.total === 0)) {
                        // If total is unknown (0) we can show an indeterminate state — keep the bar at 0% or a pulsing class
                        progressBar.style.width = "0%";
                        progressBar.innerText = "…";
                    }

                    if (node) {
                        window.lastResults.push(node);
                        renderNode(node, treeContainer);
                        updateLinksCounter();

                        // Start observing for DOM changes if not already observing
                        if (!window.scrollObserverActive) {
                            scrollObserver.observe(treeContainer, {
                                childList: true,
                                subtree: true,
                                characterData: true
                            });
                            window.scrollObserverActive = true;
                        }

                        // Auto-scroll
                        if (autoScroll) {
                            setTimeout(() => {
                                treeContainerWrapper.scrollTo({
                                    top: treeContainerWrapper.scrollHeight,
                                    behavior: 'instant'
                                });
                                treeContainerWrapper.scrollTop = treeContainerWrapper.scrollHeight;
                            }, 10);
                        }
                    }

                    // Handle done event - FIXED: Check for the actual done signal from backend
                    // Consider "done" only if explicitly signalled or if progress has a meaningful total (> 0)
                    const explicitDone = (data.message === 'done' || data.event === 'done' || window.backendSignalledDone);

                    const progressComplete = (() => {
                        if (!progress) return false;
                        // Only treat as complete if total is a positive number
                        if (typeof progress.total === 'number' && progress.total > 0 &&
                            typeof progress.current === 'number' && progress.current >= progress.total) {
                            return true;
                        }
                        return false;
                    })();

                    if (explicitDone || progressComplete) {
                        console.log('Search completed, cleaning up UI...');
                        
                        // Hide stop button when done
                        if (stopBtn) {
                            stopBtn.style.display = 'none';
                        }

                        searchBtn.disabled = false;
                        searchBtn.innerHTML = 'Search';

                        // Remove live tree + loader
                        const loadingBlock = document.getElementById('loading-container');
                        if (loadingBlock) loadingBlock.remove();
                        const progressContainer = document.getElementById('progress-container');
                        if (progressContainer) progressContainer.remove();
                        
                        // Only remove treeContainerWrapper if it exists
                        if (treeContainerWrapper && treeContainerWrapper.parentNode) {
                            treeContainerWrapper.remove();
                        }

                        // Render paginated results
                        renderPaginatedResults(1);
                        
                        // Clean up controller
                        window.searchController = null;
                    }
                }

                // Update a given mark-all checkbox state based on currently visible page checkboxes
                function updateMarkAllCheckboxForCheckboxList(markAllCheckboxEl, visibleCheckboxes) {
                    const allChecked = visibleCheckboxes.length > 0 && Array.from(visibleCheckboxes).every(cb => cb.checked);
                    const someChecked = Array.from(visibleCheckboxes).some(cb => cb.checked);
                    if (markAllCheckboxEl) {
                        markAllCheckboxEl.checked = allChecked;
                        markAllCheckboxEl.indeterminate = someChecked && !allChecked;
                    }
                }


                // Render paginated results
                function renderPaginatedResults(page = 1) {
                    // CLEAR ANY EXISTING PAGINATION
                    const existingPagination = document.getElementById('keyword-pagination');
                    if (existingPagination) {
                        existingPagination.remove();
                    }


                    const startIndex = (page - 1) * itemsPerPage;
                    const paginated = window.lastResults.slice(startIndex, startIndex + itemsPerPage);

                    // CREATE PAGINATION CONTAINER IF IT DOESN'T EXIST
                    let paginationContainer = document.getElementById('keyword-pagination');
                    if (!paginationContainer) {
                        paginationContainer = document.createElement('div');
                        paginationContainer.id = 'keyword-pagination';
                        paginationContainer.className = 'pagination-container mt-3';
                        paginationContainer.innerHTML = `
                            <nav aria-label="Keyword results pagination">
                                <ul class="pagination keyword-pagination-list justify-content-center"></ul>
                            </nav>
                        `;
                    }

                    // Use your existing renderResults to produce the HTML for the current page
                    const itemsHtml = renderResults(paginated, 0, null, startIndex);

                    // Build the main results HTML but DO NOT include the action-buttons block here
                    resultsContainer.innerHTML = `
                        <h5>Results for "${keyword}"</h5>
                        <div id="save-message-container" class="mt-2"></div>
                        <div id="results-content">${itemsHtml || '<p>No results.</p>'}</div>
                    `;

                    // Ensure there is exactly one action-buttons container and insert it above the save-message-container
                    let actionButtons = document.getElementById('action-buttons-container');
                    if (!actionButtons) {
                        // create it only once
                        actionButtons = document.createElement('div');
                        actionButtons.id = 'action-buttons-container';
                        actionButtons.className = 'd-flex align-items-center mt-5 mb-3 ms-2';

                        actionButtons.innerHTML = `
                            <div class="form-check me-5">
                                <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
                                <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
                            </div>
                            <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
                            <div class="dropdown ms-2">
                                <button class="btn btn-outline-success btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
                                    <i class="bi bi-download"></i>
                                    Export
                                </button>
                                <ul class="dropdown-menu">
                                    <li><a class="dropdown-item export-btn" href="#" data-format="csv"><i class="bi bi-filetype-csv"></i> Export as CSV</a></li>
                                    <li><a class="dropdown-item export-btn" href="#" data-format="excel"><i class="bi bi-file-earmark-excel"></i> Export as Excel</a></li>
                                    <li><a class="dropdown-item export-btn" href="#" data-format="pdf"><i class="bi bi-filetype-pdf"></i> Export as PDF</a></li>
                                </ul>
                            </div>
                            <div id="links-counter" class="ms-3 text-muted small">Links: ${window.lastResults.length}</div>
                        `;

                        // Add export button event listeners for paginated view
                        setTimeout(() => {
                            const exportBtns = actionButtons.querySelectorAll('.export-btn');
                            exportBtns.forEach(btn => {
                                btn.addEventListener('click', function(e) {
                                    e.preventDefault();
                                    const format = this.getAttribute('data-format');
                                    console.log('Export button clicked in paginated view:', format);
                                    exportResults(format);
                                });
                            });
                        }, 100);
                    }

                    const saveMessageContainer = resultsContainer.querySelector('#save-message-container');
                    resultsContainer.insertBefore(actionButtons, saveMessageContainer);

                    // Live references
                    const markAllCheckboxFinal = document.getElementById('mark-all-checkbox');

                    // Query checkboxes in the newly rendered page
                    const resultCheckboxesFinal = resultsContainer.querySelectorAll('.result-checkbox');

                    // Restore checkbox states and wire onchange to update window.selectedItems
                    resultCheckboxesFinal.forEach(cb => {
                        // Check if markAllActive is true OR if item is already selected
                        cb.checked = window.markAllActive || window.selectedItems.has(cb.dataset.id);
                        
                        // If markAllActive is true, ensure this item is in selectedItems
                        if (window.markAllActive) {
                            window.selectedItems.add(cb.dataset.id);
                        }

                        cb.onchange = () => {
                            if (cb.checked) window.selectedItems.add(cb.dataset.id);
                            else window.selectedItems.delete(cb.dataset.id);

                            // If any checkbox is unchecked, turn off markAllActive
                            if (!cb.checked && window.markAllActive) {
                                window.markAllActive = false;
                                markAllCheckboxFinal.checked = false;
                                markAllCheckboxFinal.indeterminate = false;
                            }

                            // Keep mark all in sync for visible page
                            updateMarkAllCheckboxForCheckboxList(markAllCheckboxFinal, resultCheckboxesFinal);
                        };
                    });

                    // Ensure mark all checkbox reflects the current state
                    if (markAllCheckboxFinal) {
                        markAllCheckboxFinal.checked = window.markAllActive;
                        updateMarkAllCheckboxForCheckboxList(markAllCheckboxFinal, resultCheckboxesFinal);
                    }

                    // Initialize mark-all state for the current page
                    updateMarkAllCheckboxForCheckboxList(markAllCheckboxFinal, resultCheckboxesFinal);

                    

                    // If you want to programmatically show the user how many items are selected (optional)
                    // saveSelectedBtnFinal.onclick = () => {
                    //     console.log("Selected items:", Array.from(window.selectedItems));
                    // };

                    // Pagination UI
                    if (window.lastResults.length > itemsPerPage) {
                        const totalPages = Math.ceil(window.lastResults.length / itemsPerPage);
                        currentPage = page;
                        
                        // Make sure pagination container is added to DOM
                        if (!paginationContainer.parentNode) {
                            resultsContainer.appendChild(paginationContainer);
                        }
                        
                        renderPagination(totalPages, page);
                    }
                    updateLinksCounter();
                }

            } catch (e) {
                console.error(e);
                resultsContainer.innerHTML = `<p class="text-danger">Failed to fetch results</p>`;
                searchBtn.disabled = false;
                searchBtn.innerHTML = 'Search';
            }
        });



        document.addEventListener('click', function(e) {
            if (e.target && e.target.classList.contains('page-link')) {
                e.preventDefault();
                const targetPage = parseInt(e.target.dataset.page);
                
                if (!isNaN(targetPage) && targetPage !== currentPage) {
                    currentPage = targetPage;
                    
                    // For bulk search, use the existing renderBulkPaginatedResults function
                    if (window.bulkResults && Object.keys(window.bulkResults).length > 0) {
                        // This is a bulk search - use the bulk pagination function
                        renderBulkPaginatedResults(currentPage);
                        return;
                    }
                    
                    // For single search, use the original approach
                    if (!window.lastResults || !Array.isArray(window.lastResults)) {
                        console.warn('No search results available for pagination');
                        document.getElementById('results-content').innerHTML = '<p class="text-warning">No search results available. Please run a search first.</p>';
                        return;
                    }
                    
                    // Original single search pagination code
                    const startIndex = (currentPage - 1) * itemsPerPage;
                    const endIndex = startIndex + itemsPerPage;
                    const paginatedResults = window.lastResults.slice(startIndex, endIndex);
                    
                    const itemsHtml = renderResults(paginatedResults, 0, null, startIndex);
                    document.getElementById('results-content').innerHTML = itemsHtml || '<p>No results.</p>';

                    // Reinitialize checkbox functionality for single search
                    const resultCheckboxes = document.querySelectorAll('.result-checkbox');
                    resultCheckboxes.forEach(checkbox => {
                        checkbox.checked = selectedItems.has(checkbox.dataset.id);
                        
                        checkbox.onchange = () => {
                            const itemId = checkbox.dataset.id;
                            
                            if (checkbox.checked) {
                                selectedItems.add(itemId);
                            } else {
                                selectedItems.delete(itemId);
                            }
                            
                            if (checkbox.dataset.hasChildren === "true") {
                                const childCheckboxes = getChildCheckboxes(checkbox.dataset.id);
                                childCheckboxes.forEach(child => {
                                    child.checked = checkbox.checked;
                                    if (checkbox.checked) {
                                        selectedItems.add(child.dataset.id);
                                    } else {
                                        selectedItems.delete(child.dataset.id);
                                    }
                                });
                            } else {
                                if (checkbox.checked) {
                                    updateParentState(checkbox);
                                }
                            }
                            
                            const markAllCheckbox = document.getElementById('mark-all-checkbox');
                            const allChecked = Array.from(resultCheckboxes).every(cb => cb.checked);
                            const someChecked = Array.from(resultCheckboxes).some(cb => cb.checked);
                            
                            if (markAllCheckbox) {
                                markAllCheckbox.checked = allChecked;
                                markAllCheckbox.indeterminate = someChecked && !allChecked;
                            }
                        };
                    });
                    
                    // Re-add Mark All functionality for single search
                    const markAllCheckbox = document.getElementById('mark-all-checkbox');
                    if (markAllCheckbox) {
                        const allResultIds = getAllResultIds(window.lastResults);
                        const allSelected = allResultIds.every(id => selectedItems.has(id));
                        const someSelected = allResultIds.some(id => selectedItems.has(id));
                        
                        markAllCheckbox.checked = allSelected;
                        markAllCheckbox.indeterminate = someSelected && !allSelected;
                        
                        markAllCheckbox.onchange = (e) => {
                            const isChecked = e.target.checked;
                            const allResultIds = getAllResultIds(window.lastResults);
                            
                            if (isChecked) {
                                allResultIds.forEach(id => selectedItems.add(id));
                            } else {
                                allResultIds.forEach(id => selectedItems.delete(id));
                            }
                            
                            resultCheckboxes.forEach(checkbox => {
                                checkbox.checked = isChecked;
                                checkbox.indeterminate = false;
                            });
                        };
                    }
                    
                    // Update pagination controls
                    const totalPages = Math.ceil(window.lastResults.length / itemsPerPage);
                    renderPagination(totalPages, currentPage);
                    
                    // Scroll to top of results
                    resultsContainer.scrollIntoView({ behavior: 'smooth' });
                }
            }
        });


        // Export functionality starts
        function exportResults(format) {
            // Get the current results based on whether it's single or bulk search
            let results = [];
            let filename = '';

            if (window.bulkResults && Object.keys(window.bulkResults).length > 0) {
                // Bulk search results
                filename = 'bulk_search_results';
                Object.entries(window.bulkResults).forEach(([keyword, keywordResults]) => {
                    keywordResults.forEach(result => {
                        results.push({
                            keyword: keyword,
                            title: result.title || '',
                            url: result.url || '',
                            depth: getResultDepth(result)
                        });
                    });
                });
            } else if (window.lastResults && window.lastResults.length > 0) {
                // Single search results
                let keywordText = '';
                
                // Handle different cases for keyword
                if (typeof window.currentKeyword === 'string') {
                    keywordText = window.currentKeyword;
                } else if (window.currentKeyword && window.currentKeyword.word) {
                    keywordText = window.currentKeyword.word;
                } else if (keywordInput && keywordInput.value) {
                    keywordText = keywordInput.value;
                } else {
                    keywordText = 'search';
                }
                
                filename = `search_results_${keywordText.replace(/\s+/g, '_')}`;
                results = flattenResults(window.lastResults, keywordText);
            } else {
                alert('No results to export');
                return;
            }

            if (results.length === 0) {
                alert('No results to export');
                return;
            }

            switch (format) {
                case 'csv':
                    exportToCsv(results, filename);
                    break;
                case 'excel':
                    exportToExcel(results, filename);
                    break;
                case 'pdf':
                    exportToPdf(results, filename);
                    break;
            }
        }

        // Helper function to flatten nested results
        function flattenResults(results, parentKeyword = '') {
            const flattened = [];
            
            results.forEach((result) => {
                flattened.push({
                    keyword: parentKeyword,
                    title: result.title || '',
                    url: result.url || '',
                    depth: getResultDepth(result)
                });

                if (result.children && result.children.length > 0) {
                    flattened.push(...flattenResults(result.children, parentKeyword));
                }
            });
            
            return flattened;
        }

        // Helper function to calculate result depth
        function getResultDepth(result) {
            if (!result.children || result.children.length === 0) return 1;
            return 1 + Math.max(...result.children.map(child => getResultDepth(child)));
        }

        // CSV Export
        function exportToCsv(data, filename) {
            const headers = ['Keyword', 'Title', 'URL', 'Depth'];
            const csvContent = [
                headers.join(','),
                ...data.map(row => [
                    `"${(row.keyword || '').replace(/"/g, '""')}"`,
                    `"${(row.title || '').replace(/"/g, '""')}"`,
                    `"${(row.url || '').replace(/"/g, '""')}"`,
                    row.depth || 1
                ].join(','))
            ].join('\n');

            downloadFile(csvContent, `${filename}.csv`, 'text/csv');
        }

        // Excel Export (using CSV with .xlsx extension for simplicity)
        function exportToExcel(data, filename) {
            // For a proper Excel export, you might want to use a library like SheetJS
            // This is a simplified version using CSV
            exportToCsv(data, `${filename}.xlsx`);
        }

        // PDF Export
        function exportToPdf(data, filename) {
            // For PDF export, you can use jsPDF library
            if (typeof jspdf === 'undefined') {
                // Load jsPDF dynamically
                const script = document.createElement('script');
                script.src = 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js';
                script.onload = () => generatePdf(data, filename);
                document.head.appendChild(script);
            } else {
                generatePdf(data, filename);
            }
        }

        function generatePdf(data, filename) {
            const { jsPDF } = window.jspdf;
            const doc = new jsPDF();
            
            let yPosition = 20;
            const pageHeight = doc.internal.pageSize.height;
            const lineHeight = 10;
            
            // Title
            doc.setFontSize(16);
            doc.text('Search Results Export', 20, yPosition);
            yPosition += 20;
            
            // Table headers
            doc.setFontSize(10);
            doc.setFont(undefined, 'bold');
            doc.text('Keyword', 20, yPosition);
            doc.text('Title', 60, yPosition);
            doc.text('URL', 120, yPosition);
            doc.text('Depth', 180, yPosition);
            yPosition += lineHeight;
            
            // Table content
            doc.setFont(undefined, 'normal');
            data.forEach((row) => {
                // Check if we need a new page
                if (yPosition > pageHeight - 20) {
                    doc.addPage();
                    yPosition = 20;
                }
                
                // Truncate long text
                const keyword = (row.keyword || '').substring(0, 30);
                const title = (row.title || '').substring(0, 40);
                const url = (row.url || '').substring(0, 50);
                
                doc.text(keyword, 20, yPosition);
                doc.text(title, 60, yPosition);
                doc.text(url, 120, yPosition);
                doc.text(String(row.depth || 1), 180, yPosition);
                
                yPosition += lineHeight;
            });
            
            doc.save(`${filename}.pdf`);
        }

        // Generic download function
        function downloadFile(content, filename, mimeType) {
            const blob = new Blob([content], { type: mimeType });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }
        // Export fucnctionality ends
    }

    return { init };
}));
