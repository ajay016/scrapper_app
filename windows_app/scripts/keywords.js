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
            
            // Mark All functionality
            if (markAllCheckbox) {
                markAllCheckbox.onchange = (e) => {
                    const isChecked = e.target.checked;
                    
                    // Check/uncheck all keyword checkboxes and their results
                    keywordCheckboxes.forEach(checkbox => {
                        checkbox.checked = isChecked;
                    });
                    
                    resultCheckboxes.forEach(checkbox => {
                        checkbox.checked = isChecked;
                        // Update global selection
                        if (isChecked) {
                            selectedItems.add(checkbox.dataset.id);
                        } else {
                            selectedItems.delete(checkbox.dataset.id);
                        }
                    });
                };
            }
            
            // Keyword checkbox functionality (check all results for this keyword)
            keywordCheckboxes.forEach(keywordCheckbox => {
                keywordCheckbox.onchange = (e) => {
                    const isChecked = e.target.checked;
                    const keywordSection = keywordCheckbox.closest('.keyword-results-section');
                    const keywordResultCheckboxes = keywordSection.querySelectorAll('.result-checkbox');
                    
                    // Check/uncheck all results for this keyword
                    keywordResultCheckboxes.forEach(checkbox => {
                        checkbox.checked = isChecked;
                        // Update global selection
                        if (isChecked) {
                            selectedItems.add(checkbox.dataset.id);
                        } else {
                            selectedItems.delete(checkbox.dataset.id);
                        }
                    });
                    
                    // Update Mark All checkbox state
                    updateMarkAllState();
                };
            });
            
            // Individual result checkbox functionality
            resultCheckboxes.forEach(checkbox => {
                checkbox.onchange = () => {
                    const itemId = checkbox.dataset.id;
                    
                    // Update global selection
                    if (checkbox.checked) {
                        selectedItems.add(itemId);
                    } else {
                        selectedItems.delete(itemId);
                    }
                    
                    // Update keyword checkbox state
                    updateKeywordCheckboxState(checkbox);
                    
                    // Update Mark All checkbox state
                    updateMarkAllState();
                };
            });
        }

        function updateKeywordCheckboxState(resultCheckbox) {
            const keywordSection = resultCheckbox.closest('.keyword-results-section');
            const keywordCheckbox = keywordSection.querySelector('.keyword-checkbox');
            const keywordResultCheckboxes = keywordSection.querySelectorAll('.result-checkbox');
            
            const allChecked = Array.from(keywordResultCheckboxes).every(cb => cb.checked);
            const someChecked = Array.from(keywordResultCheckboxes).some(cb => cb.checked);
            
            keywordCheckbox.checked = allChecked;
            keywordCheckbox.indeterminate = someChecked && !allChecked;
        }

        function updateMarkAllState() {
            const markAllCheckbox = document.getElementById('mark-all-checkbox');
            const resultCheckboxes = document.querySelectorAll('.result-checkbox');
            
            const allChecked = Array.from(resultCheckboxes).every(cb => cb.checked);
            const someChecked = Array.from(resultCheckboxes).some(cb => cb.checked);
            
            if (markAllCheckbox) {
                markAllCheckbox.checked = allChecked;
                markAllCheckbox.indeterminate = someChecked && !allChecked;
            }
        }
        // checkbox for bulk keywords ends

        // Also update the handleFileUpload function to reset on success
        async function uploadFileToBackend(file) {
            const startButton = document.getElementById('start-parsing-btn');
            const originalText = startButton.innerHTML;
            
            try {
                // Show loading state
                startButton.disabled = true;
                startButton.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> Processing...';

                // ADD: Modern loading animation
                resultsContainer.innerHTML = `
                    <div class="text-center">
                        <div class="spinner-border text-primary mb-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="searching-pulse">Searching for All the keywords...</p>
                    </div>
                `;

                const formData = new FormData();
                formData.append('keywords_file', file);

                const response = await fetch(`${API_BASE_URL}/api/bulk-keywords-search/`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem("accessToken")}`
                    },
                    body: formData
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Failed to upload file');
                }

                const result = await response.json();
                
                // Show success message
                // Instead of alert, render results
                resultsContainer.innerHTML = '';

                if (result.keywords && result.keywords.length > 0) {
                    // Create a single action buttons container at the top
                    resultsContainer.innerHTML = `
                        <div class="d-flex align-items-center mt-5 mb-3 ms-2" id="action-buttons-container" style="display: flex;">
                            <div class="form-check me-5">
                                <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
                                <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
                            </div>
                            <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
                        </div>
                        <div id="save-message-container" class="mt-2"></div>
                    `;
                    
                    // Add each keyword's results
                    result.keywords.forEach(keywordData => {
                        const keywordDiv = document.createElement('div');
                        keywordDiv.className = 'keyword-results-section';
                        
                        keywordDiv.innerHTML = `
                                                    <div class="form-check mt-4">
                                                        <input class="form-check-input keyword-checkbox" type="checkbox" 
                                                            data-keyword="${keywordData.keyword.word}" data-keyword-id="${keywordData.keyword.id}">
                                                        <label class="form-check-label h5 mb-0">
                                                            Results for "${keywordData.keyword.word}"
                                                        </label>
                                                    </div>
                                                    <div class="keyword-results-content">
                                                        ${renderResults(keywordData.results || [], 0, null, 0) || '<p>No results.</p>'}
                                                    </div>
                                                `;

                        resultsContainer.appendChild(keywordDiv);
                    });
                    
                    // Initialize checkbox functionality for bulk search
                    initializeBulkSearchCheckboxes();
                } else {
                    resultsContainer.innerHTML = `<p class="text-warning">No results found for uploaded keywords.</p>`;
                }
                
                // Reset the file input and display
                fileInput.value = '';
                resetFilenameDisplay();
                
                // Optional: Refresh the keywords list
                // loadKeywords();

            } catch (error) {
                console.error('Upload error:', error);
                showFileError(error.message || 'Failed to upload file. Please try again.');
            } finally {
                // Reset button state
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
                if (!window.lastResults || window.lastResults.length === 0) {
                    showAlert('danger', 'No search results found. Please run a search first.');
                    return;
                }
                if (!window.currentKeywordId) {
                    showAlert('danger', 'Missing keyword context. Please run a new search.');
                    return;
                }

                // ✅ CHANGED: Use selectedItems for all pages instead of querying DOM
                const checkedIds = new Set(window.selectedItems || []);

                if (checkedIds.size === 0) { // CHANGED
                    showAlert('danger', 'Please select at least one item to save');
                    return;
                }

                console.debug('SAVE CLICKED -> window.selectedItems:', Array.from(window.selectedItems || []));
                console.debug('window.lastResults length:', window.lastResults ? window.lastResults.length : 0);
                console.debug('window.lastResults sample (first 3):', (window.lastResults || []).slice(0,3));

                // normalize helper (strip trailing slashes and protocol for best-effort matching)
                function normalizeUrlForMatch(u) {
                    if (!u) return u;
                    try {
                        // return host+path without trailing slash and protocol
                        // leave query/hash intact to be conservative
                        let s = u + '';
                        // decode percent-encoding where possible
                        try { s = decodeURIComponent(s); } catch (e) { /* ignore decode errors */ }
                        s = s.replace(/^https?:\/\//i, '').replace(/^\/\/+/,'').replace(/\/+$/,'');
                        // optional: remove leading www. for looser match
                        s = s.replace(/^www\./i, '');
                        return s;
                    } catch (e) {
                        return u;
                    }
                }

                // find by path (e.g. "0-2-1"), returns node or null
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

                // flexible recursive search by URL with several fallbacks
                function findNodeByUrlFlexible(nodes, id) {
                    if (!nodes || !nodes.length) return null;
                    const normId = normalizeUrlForMatch(id);

                    // depth-first
                    for (let i = 0; i < nodes.length; i++) {
                        const node = nodes[i];
                        if (!node) continue;

                        // direct match
                        if (node.url === id) return node;

                        // normalized match
                        if (normalizeUrlForMatch(node.url) === normId) return node;

                        // decoded match (in case one is encoded)
                        try {
                            if (decodeURIComponent(node.url) === id || decodeURIComponent(id) === node.url) return node;
                        } catch (e) { /* ignore decode errors */ }

                        // try partial match (host+path)
                        try {
                            const nnode = normalizeUrlForMatch(node.url);
                            if (nnode && normId && (nnode === normId || nnode.indexOf(normId) !== -1 || normId.indexOf(nnode) !== -1)) {
                                return node;
                            }
                        } catch (e) {}

                        // search children
                        if (node.children && node.children.length) {
                            const found = findNodeByUrlFlexible(node.children, id);
                            if (found) return found;
                        }
                    }
                    return null;
                }

                // Build merged result list using flexible matching and path fallback.
                // We'll report which selected IDs couldn't be found.
                const merged = [];
                const seenUrls = new Set();
                const notFound = [];

                (Array.from(window.selectedItems || [])).forEach(idStr => {
                    if (!idStr) return;

                    // if idStr looks like a path "0-2-1" (only digits and dashes), try path lookup first
                    const pathLike = /^(\d+(-\d+)*)$/.test(idStr);

                    let origNode = null;
                    if (pathLike) {
                        // try path lookup
                        const pathArr = idStr.split('-').map(x => parseInt(x, 10));
                        origNode = findNodeByPath(window.lastResults, pathArr);
                    }

                    // if not found by path (or not path-like), try URL-flexible search
                    if (!origNode) {
                        origNode = findNodeByUrlFlexible(window.lastResults, idStr);
                    }

                    if (!origNode) {
                        notFound.push(idStr);
                    } else {
                        const urlKey = origNode.url || JSON.stringify(origNode).slice(0,50);
                        if (seenUrls.has(urlKey)) return;
                        // deep clone to decouple from in-memory objects
                        merged.push(JSON.parse(JSON.stringify(origNode)));
                        seenUrls.add(urlKey);
                    }
                });

                // debug results
                console.debug('Merged items count:', merged.length, 'notFound count:', notFound.length, 'notFound sample:', notFound.slice(0,10));

                if (merged.length === 0) {
                    // show a clearer message to user while also printing debug to console
                    showAlert('danger', 'No valid items to save — selections did not match results. Check console logs for details.');
                    console.error('Save aborted: no matched nodes. selectedIds:', Array.from(window.selectedItems || []), 'notFound:', notFound, 'lastResults sample:', (window.lastResults||[]).slice(0,5));
                    return;
                }


                // POST to backend
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
                projectSelect.innerHTML = `<option value="">Select Project</option>`;
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
        const progressBar = document.getElementById("progress-bar");

        // searchBtn.addEventListener("click", async () => {
        //     const keyword = (keywordInput.value || '').trim();
        //     const depth = depthInput.value || 0;

        //     if (!keyword) {
        //         resultsContainer.innerHTML = `<p class="text-danger">Please enter a keyword</p>`;
        //         return;
        //     }

        //     try {
        //         // Disable search button and show spinner
        //         searchBtn.disabled = true;
        //         searchBtn.innerHTML = `
        //             <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
        //             Searching...
        //         `;

        //         // Render initial loading + progress + results container (keeps original look)
        //         resultsContainer.innerHTML = `
        //             <div id="loading-container" class="text-center mb-3">
        //                 <div class="spinner-border text-primary mb-2" role="status">
        //                     <span class="visually-hidden">Loading...</span>
        //                 </div>
        //                 <p class="searching-pulse">Searching for "${keyword}"...</p>
        //             </div>
        //             <div id="progress-container" class="mt-2">
        //                 <div class="progress">
        //                     <div id="progress-bar" class="progress-bar" role="progressbar" style="width: 0%">0%</div>
        //                 </div>
        //             </div>
        //             <div id="results-tree-container" class="mt-3">
        //                 <ul id="results-tree" class="list-group list-group-flush"></ul>
        //             </div>
        //         `;

        //         // Initialize
        //         window.lastResults = [];
        //         const selectedItems = new Set();
        //         const treeContainer = document.getElementById("results-tree");
        //         const progressBar = document.getElementById("progress-bar");

        //         // Insert action buttons same as original style location
        //         // We put them above the results-tree-container to match existing layout
        //         const actionButtonsContainer = document.createElement("div");
        //         actionButtonsContainer.id = 'action-buttons-container';
        //         actionButtonsContainer.className = 'd-flex align-items-center mt-3 mb-3 ms-2';
        //         actionButtonsContainer.style.display = 'none';
        //         actionButtonsContainer.innerHTML = `
        //             <div class="form-check me-5">
        //                 <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
        //                 <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
        //             </div>
        //             <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
        //         `;
        //         // place action buttons just before results tree container
        //         const treeContainerWrapper = document.getElementById('results-tree-container');
        //         treeContainerWrapper.parentNode.insertBefore(actionButtonsContainer, treeContainerWrapper);

        //         const markAllCheckbox = document.getElementById('mark-all-checkbox');
        //         const saveSelectedBtn = document.getElementById('save-selected-btn');

        //         // Render a single node (styled similarly to original)
        //         function renderNode(n, parentUl) {
        //             const li = document.createElement("li");
        //             li.className = "list-group-item py-1"; // good Bootstrap default
        //             // Keep link clickable and same minimal markup as original aesthetics
        //             li.innerHTML = `
        //                 <input type="checkbox" class="result-checkbox me-2" data-id="${n.url}" data-has-children="${n.children && n.children.length > 0}">
        //                 <a href="${n.url}" target="_blank" rel="noopener noreferrer"><strong>${n.title || n.url}</strong></a>
        //                 <div><small class="text-muted">${n.url}</small></div>
        //             `;
        //             parentUl.appendChild(li);

        //             const checkbox = li.querySelector(".result-checkbox");

        //             // checkbox behavior — keeps parent-child semantics
        //             checkbox.onchange = () => {
        //                 if (checkbox.checked) {
        //                     selectedItems.add(checkbox.dataset.id);
        //                 } else {
        //                     selectedItems.delete(checkbox.dataset.id);
        //                 }

        //                 if (checkbox.dataset.hasChildren === "true") {
        //                     // check/uncheck all children in this subtree
        //                     const childCheckboxes = li.querySelectorAll('.result-checkbox');
        //                     childCheckboxes.forEach(child => {
        //                         child.checked = checkbox.checked;
        //                         if (checkbox.checked) {
        //                             selectedItems.add(child.dataset.id);
        //                         } else {
        //                             selectedItems.delete(child.dataset.id);
        //                         }
        //                     });
        //                 }

        //                 // update mark-all state
        //                 const allCheckboxes = treeContainer.querySelectorAll('.result-checkbox');
        //                 const allChecked = allCheckboxes.length > 0 && Array.from(allCheckboxes).every(cb => cb.checked);
        //                 const someChecked = Array.from(allCheckboxes).some(cb => cb.checked);
        //                 markAllCheckbox.checked = allChecked;
        //                 markAllCheckbox.indeterminate = someChecked && !allChecked;
        //             };

        //             // children
        //             if (n.children && n.children.length > 0) {
        //                 const ul = document.createElement("ul");
        //                 ul.className = "list-group list-group-flush ms-4";
        //                 li.appendChild(ul);
        //                 n.children.forEach(child => renderNode(child, ul));
        //             }
        //         }

        //         // Open SSE connection
        //         const evtSource = new EventSource(`${API_BASE_URL}/api/search-keywords/?q=${encodeURIComponent(keyword)}&limit=${depth}`);

        //         evtSource.onmessage = function(event) {
        //             // incoming data is a node + progress
        //             try {
        //                 const data = JSON.parse(event.data);
        //                 const node = data.node;
        //                 const progress = data.progress;

        //                 // show action buttons when first item arrives
        //                 if (actionButtonsContainer.style.display === 'none') {
        //                     actionButtonsContainer.style.display = 'flex';
        //                 }

        //                 // update progress bar (progress.total may be 'limit' expected)
        //                 if (progress && typeof progress.current !== 'undefined') {
        //                     const total = progress.total || 0; // may be expected limit
        //                     const percent = total ? Math.round((progress.current / total) * 100) : 0;
        //                     progressBar.style.width = (percent ? percent : 0) + "%";
        //                     progressBar.innerText = (percent ? percent : 0) + "%";
        //                 }

        //                 // append immediately
        //                 window.lastResults.push(node);
        //                 renderNode(node, treeContainer);
        //             } catch (parseErr) {
        //                 console.error("Failed to parse SSE message", parseErr);
        //             }
        //         };

        //         evtSource.addEventListener("done", function(event) {
        //             // stream finished
        //             try {
        //                 const payload = event.data ? JSON.parse(event.data) : null;
        //                 const total_received = payload?.total_received ?? null;
        //             } catch (e) {
        //                 // ignore parse errors here
        //             }

        //             evtSource.close();
        //             // Re-enable UI
        //             searchBtn.disabled = false;
        //             searchBtn.innerHTML = 'Search';

        //             // Remove the initial loader block
        //             const loadingBlock = document.getElementById('loading-container');
        //             if (loadingBlock) loadingBlock.remove();

        //             // Hide progress bar container entirely (user requested it be hidden after completion)
        //             const progressContainer = document.getElementById('progress-container');
        //             if (progressContainer) progressContainer.remove();

        //             // Optional success message (brief)
        //             const doneMsg = document.createElement("div");
        //             doneMsg.className = "alert alert-success py-1 mt-2";
        //             doneMsg.innerText = "Search complete.";
        //             // place it above results
        //             treeContainerWrapper.parentNode.insertBefore(doneMsg, treeContainerWrapper);

        //             // Remove the message after 3 seconds so UI is not cluttered
        //             setTimeout(() => {
        //                 try { doneMsg.remove(); } catch (e) {}
        //             }, 3000);
        //         });

        //         evtSource.onerror = function(err) {
        //             console.error("SSE error:", err);
        //             evtSource.close();
        //             searchBtn.disabled = false;
        //             searchBtn.innerHTML = 'Search';
        //             const errMsg = document.createElement("p");
        //             errMsg.className = "text-danger mt-2";
        //             errMsg.innerText = "Error streaming results.";
        //             resultsContainer.appendChild(errMsg);
        //         };

        //         // mark all checkbox
        //         markAllCheckbox.onchange = (e) => {
        //             const isChecked = e.target.checked;
        //             const allCheckboxes = treeContainer.querySelectorAll('.result-checkbox');
        //             allCheckboxes.forEach(cb => {
        //                 cb.checked = isChecked;
        //                 if (isChecked) selectedItems.add(cb.dataset.id);
        //                 else selectedItems.delete(cb.dataset.id);
        //             });
        //         };

        //         // save selected
        //         saveSelectedBtn.onclick = () => {
        //             console.log("Selected items:", Array.from(selectedItems));
        //             alert(`Selected ${selectedItems.size} items saved!`);
        //         };

        //     } catch (e) {
        //         console.error(e);
        //         resultsContainer.innerHTML = `<p class="text-danger">Failed to fetch results</p>`;
        //         searchBtn.disabled = false;
        //         searchBtn.innerHTML = 'Search';
        //     }
        // });


        // searchBtn.addEventListener("click", async () => {
        //     const keyword = (keywordInput.value || '').trim();
        //     const depth = depthInput.value || 0;

        //     if (!keyword) {
        //         resultsContainer.innerHTML = `<p class="text-danger">Please enter a keyword</p>`;
        //         return;
        //     }

        //     try {
        //         searchBtn.disabled = true;
        //         searchBtn.innerHTML = `
        //             <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
        //             Searching...
        //         `;

        //         // Initial loading + progress
        //         resultsContainer.innerHTML = `
        //             <div id="loading-container" class="text-center mb-3">
        //                 <div class="spinner-border text-primary mb-2" role="status">
        //                     <span class="visually-hidden">Loading...</span>
        //                 </div>
        //                 <p class="searching-pulse">Searching for "${keyword}"...</p>
        //             </div>
        //             <div id="progress-container" class="mt-2">
        //                 <div class="progress">
        //                     <div id="progress-bar" class="progress-bar" role="progressbar" style="width: 0%">0%</div>
        //                 </div>
        //             </div>
        //             <div id="results-tree-container" class="mt-3">
        //                 <ul id="results-tree" class="list-group list-group-flush"></ul>
        //             </div>
        //         `;

        //         const treeContainerWrapper = document.getElementById('results-tree-container');
        //         const treeContainer = document.getElementById('results-tree');
        //         const progressBar = document.getElementById('progress-bar');

        //         // Single source of truth
        //         window.lastResults = [];
        //         window.selectedItems = new Set();

        //         // Create action buttons (Mark All + Save)
        //         const actionButtonsContainer = document.createElement("div");
        //         actionButtonsContainer.id = 'action-buttons-container';
        //         actionButtonsContainer.className = 'd-flex align-items-center mt-5 mb-3 ms-2';
        //         actionButtonsContainer.style.display = 'none';
        //         actionButtonsContainer.innerHTML = `
        //             <div class="form-check me-5">
        //                 <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
        //                 <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
        //             </div>
        //             <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
        //         `;
        //         treeContainerWrapper.parentNode.insertBefore(actionButtonsContainer, treeContainerWrapper);

        //         const markAllCheckbox = document.getElementById('mark-all-checkbox');
        //         const saveSelectedBtn = document.getElementById('save-selected-btn');

        //         // SSE node rendering
        //         function renderNode(n, parentUl) {
        //             const li = document.createElement("li");
        //             li.className = "list-group-item py-1";
        //             li.innerHTML = `
        //                 <input type="checkbox" class="result-checkbox me-2" data-id="${n.url}" data-has-children="${n.children && n.children.length > 0}">
        //                 <a href="${n.url}" target="_blank" rel="noopener noreferrer"><strong>${n.title || n.url}</strong></a>
        //                 <div><small class="text-muted">${n.url}</small></div>
        //             `;
        //             parentUl.appendChild(li);

        //             const checkbox = li.querySelector(".result-checkbox");
        //             // Restore state if previously selected
        //             checkbox.checked = window.selectedItems.has(n.url);

        //             checkbox.onchange = () => {
        //                 if (checkbox.checked) window.selectedItems.add(checkbox.dataset.id);
        //                 else window.selectedItems.delete(checkbox.dataset.id);

        //                 if (checkbox.dataset.hasChildren === "true") {
        //                     const childCheckboxes = li.querySelectorAll('.result-checkbox');
        //                     childCheckboxes.forEach(child => {
        //                         child.checked = checkbox.checked;
        //                         if (checkbox.checked) window.selectedItems.add(child.dataset.id);
        //                         else window.selectedItems.delete(child.dataset.id);
        //                     });
        //                 }

        //                 updateMarkAllCheckbox();
        //             };

        //             if (n.children && n.children.length > 0) {
        //                 const ul = document.createElement("ul");
        //                 ul.className = "list-group list-group-flush ms-4";
        //                 li.appendChild(ul);
        //                 n.children.forEach(child => renderNode(child, ul));
        //             }
        //         }

        //         // Update mark all checkbox state
        //         function updateMarkAllCheckbox() {
        //             const allCheckboxes = treeContainer.querySelectorAll('.result-checkbox');
        //             const allChecked = allCheckboxes.length > 0 && Array.from(allCheckboxes).every(cb => cb.checked);
        //             const someChecked = Array.from(allCheckboxes).some(cb => cb.checked);
        //             markAllCheckbox.checked = allChecked;
        //             markAllCheckbox.indeterminate = someChecked && !allChecked;
        //         }

        //         // SSE connection
        //         const evtSource = new EventSource(`${API_BASE_URL}/api/search-keywords/?q=${encodeURIComponent(keyword)}&limit=${depth}`);

        //         evtSource.onmessage = function(event) {
        //             try {
        //                 const data = JSON.parse(event.data);
        //                 const node = data.node;
        //                 const progress = data.progress;

        //                 if (actionButtonsContainer.style.display === 'none') actionButtonsContainer.style.display = 'flex';

        //                 if (progress && typeof progress.current !== 'undefined') {
        //                     const percent = progress.total ? Math.round((progress.current / progress.total) * 100) : 0;
        //                     progressBar.style.width = percent + "%";
        //                     progressBar.innerText = percent + "%";
        //                 }

        //                 window.lastResults.push(node);
        //                 renderNode(node, treeContainer);
        //             } catch (err) {
        //                 console.error("SSE parse error:", err);
        //             }
        //         };

        //         evtSource.addEventListener("done", function() {
        //             evtSource.close();
        //             searchBtn.disabled = false;
        //             searchBtn.innerHTML = 'Search';

        //             // Remove live tree + loader
        //             const loadingBlock = document.getElementById('loading-container');
        //             if (loadingBlock) loadingBlock.remove();
        //             const progressContainer = document.getElementById('progress-container');
        //             if (progressContainer) progressContainer.remove();
        //             treeContainerWrapper.remove();

        //             // Render paginated results
        //             renderPaginatedResults(1);
        //         });

        //         evtSource.onerror = function(err) {
        //             console.error("SSE error:", err);
        //             evtSource.close();
        //             searchBtn.disabled = false;
        //             searchBtn.innerHTML = 'Search';
        //             const errMsg = document.createElement("p");
        //             errMsg.className = "text-danger mt-2";
        //             errMsg.innerText = "Error streaming results.";
        //             resultsContainer.appendChild(errMsg);
        //         };

        //         // Render paginated results
        //         function renderPaginatedResults(page = 1) {
        //             const startIndex = (page - 1) * itemsPerPage;
        //             const paginated = window.lastResults.slice(startIndex, startIndex + itemsPerPage);
        //             const itemsHtml = renderResults(paginated, 0, null, startIndex);

        //             resultsContainer.innerHTML = `
        //                 <h5>Results for "${keyword}"</h5>
        //                 <div class="d-flex align-items-center mt-5 mb-3 ms-2" id="action-buttons-container">
        //                     <div class="form-check me-5">
        //                         <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
        //                         <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
        //                     </div>
        //                     <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
        //                 </div>
        //                 <div id="save-message-container" class="mt-2"></div>
        //                 <div id="results-content">${itemsHtml || '<p>No results.</p>'}</div>
        //             `;

        //             // Restore references
        //             const markAllCheckboxFinal = document.getElementById('mark-all-checkbox');
        //             const saveSelectedBtnFinal = document.getElementById('save-selected-btn');
        //             const resultCheckboxesFinal = document.querySelectorAll('.result-checkbox');

        //             // Restore checkbox states
        //             resultCheckboxesFinal.forEach(cb => {
        //                 cb.checked = window.selectedItems.has(cb.dataset.id);
        //                 cb.onchange = () => {
        //                     if (cb.checked) window.selectedItems.add(cb.dataset.id);
        //                     else window.selectedItems.delete(cb.dataset.id);
        //                     updateMarkAllCheckboxFinal();
        //                 };
        //             });

        //             function updateMarkAllCheckboxFinal() {
        //                 const allChecked = Array.from(resultCheckboxesFinal).every(cb => cb.checked);
        //                 const someChecked = Array.from(resultCheckboxesFinal).some(cb => cb.checked);
        //                 markAllCheckboxFinal.checked = allChecked;
        //                 markAllCheckboxFinal.indeterminate = someChecked && !allChecked;
        //             }

        //             markAllCheckboxFinal.onchange = () => {
        //                 const allResultIds = window.lastResults.map(r => r.url);
        //                 if (markAllCheckboxFinal.checked) allResultIds.forEach(id => window.selectedItems.add(id));
        //                 else allResultIds.forEach(id => window.selectedItems.delete(id));
        //                 resultCheckboxesFinal.forEach(cb => {
        //                     cb.checked = markAllCheckboxFinal.checked;
        //                     cb.indeterminate = false;
        //                 });
        //             };

        //             saveSelectedBtnFinal.onclick = () => {
        //                 console.log("Selected items:", Array.from(window.selectedItems));
        //                 alert(`Selected ${window.selectedItems.size} items saved!`);
        //             };

        //             // Pagination
        //             if (window.lastResults.length > itemsPerPage) {
        //                 const totalPages = Math.ceil(window.lastResults.length / itemsPerPage);
        //                 currentPage = page;
        //                 renderPagination(totalPages, page);
        //             }
        //         }

        //     } catch (e) {
        //         console.error(e);
        //         resultsContainer.innerHTML = `<p class="text-danger">Failed to fetch results</p>`;
        //         searchBtn.disabled = false;
        //         searchBtn.innerHTML = 'Search';
        //     }
        // });



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

        searchBtn.addEventListener("click", async () => {
            const keyword = (keywordInput.value || '').trim();
            const depth = depthInput.value || 0;

            if (!keyword) {
                resultsContainer.innerHTML = `<p class="text-danger">Please enter a keyword</p>`;
                return;
            }

            try {
                searchBtn.disabled = true;
                searchBtn.innerHTML = `
                    <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                    Searching...
                `;

                // Initial loading + progress
                resultsContainer.innerHTML = `
                    <div id="loading-container" class="text-center mb-3">
                        <div class="spinner-border text-primary mb-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="searching-pulse">Searching for "${keyword}"...</p>
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

                // Single source of truth
                window.lastResults = [];
                window.selectedItems = new Set();
                window.markAllActive = false;

                // Create action buttons (Mark All + Save)
                const actionButtonsContainer = document.createElement("div");
                actionButtonsContainer.id = 'action-buttons-container';
                actionButtonsContainer.className = 'd-flex align-items-center mt-5 mb-3 ms-2';
                actionButtonsContainer.style.display = 'none';
                actionButtonsContainer.innerHTML = `
                    <div class="form-check me-5">
                        <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
                        <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
                    </div>
                    <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
                `;
                treeContainerWrapper.parentNode.insertBefore(actionButtonsContainer, treeContainerWrapper);

                const markAllCheckbox = document.getElementById('mark-all-checkbox');
                const saveSelectedBtn = document.getElementById('save-selected-btn');

                // SSE node rendering
                function renderNode(n, parentUl) {
                    const li = document.createElement("li");
                    li.className = "list-group-item py-1";
                    li.innerHTML = `
                        <input type="checkbox" class="result-checkbox me-2" data-id="${n.url}" data-has-children="${n.children && n.children.length > 0}">
                        <a href="${n.url}" target="_blank" rel="noopener noreferrer"><strong>${n.title || n.url}</strong></a>
                        <div><small class="text-muted">${n.url}</small></div>
                    `;
                    parentUl.appendChild(li);

                    const checkbox = li.querySelector(".result-checkbox");
                    // Restore state if previously selected
                    const id = checkbox.dataset.id;
                    checkbox.checked = window.selectedItems.has(id) || !!window.markAllActive;

                    // If global mark-all is active, ensure we record this id (and children) immediately
                    if (window.markAllActive && checkbox.checked) {
                        window.selectedItems.add(id);
                        if (checkbox.dataset.hasChildren === "true") {
                            // add all child IDs that are currently in DOM (future children rendered will also pick up markAllActive)
                            const childCheckboxes = li.querySelectorAll('.result-checkbox');
                            childCheckboxes.forEach(child => {
                                window.selectedItems.add(child.dataset.id);
                                child.checked = true;
                            });
                        }
                    }

                    checkbox.onchange = () => {
                        if (checkbox.checked) {
                            window.selectedItems.add(id);
                        } else {
                            window.selectedItems.delete(id);
                        }

                        if (checkbox.dataset.hasChildren === "true") {
                            const childCheckboxes = li.querySelectorAll('.result-checkbox');
                            childCheckboxes.forEach(child => {
                                child.checked = checkbox.checked;
                                const childId = child.dataset.id;
                                if (checkbox.checked) window.selectedItems.add(childId);
                                else window.selectedItems.delete(childId);
                            });
                        }

                        // If user manually unchecks one checkbox while markAllActive was true,
                        // consider marking markAllActive as false so future nodes are not auto-selected.
                        // (Optional decision: below line disables global auto-select if user unchecks any checkbox)
                        if (window.markAllActive && !checkbox.checked) {
                            window.markAllActive = false;
                            // update the Mark All checkbox UI if it exists
                            const markEl = document.getElementById('mark-all-checkbox');
                            if (markEl) { markEl.checked = false; markEl.indeterminate = false; }
                        }

                        updateMarkAllCheckbox();
                    };

                    if (n.children && n.children.length > 0) {
                        const ul = document.createElement("ul");
                        ul.className = "list-group list-group-flush ms-4";
                        li.appendChild(ul);
                        n.children.forEach(child => renderNode(child, ul));
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

                // SSE connection
                const evtSource = new EventSource(`${API_BASE_URL}/api/search-keywords/?q=${encodeURIComponent(keyword)}&limit=${depth}`);

                evtSource.addEventListener('meta', (e) => {
                    console.debug('SSE meta event raw data:', e.data);
                    try {
                        const d = JSON.parse(e.data);
                        if (d.keyword && d.keyword.id) {
                            window.currentKeywordId = d.keyword.id;
                            window.currentKeyword = d.keyword;
                            console.debug('client: got keyword from meta ->', window.currentKeywordId);
                        }
                    } catch (err) {
                        console.error('Failed to parse meta event', err, e.data);
                    }
                });


                evtSource.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);

                        // -------------- NEW: capture keyword context if server sends it --------------
                        // Try several common property names the server might use
                        if (data.keyword && data.keyword.id) {
                            window.currentKeywordId = data.keyword.id;
                            window.currentKeyword = data.keyword; // optional, store whole object
                        } else if (data.keyword_id) {
                            window.currentKeywordId = data.keyword_id;
                        } else if (data.meta && data.meta.keyword_id) {
                            window.currentKeywordId = data.meta.keyword_id;
                        }
                        // debugging: show when we get the id
                        if (window.currentKeywordId) {
                            console.debug('SSE: got keyword id ->', window.currentKeywordId);
                        }
                        // ---------------------------------------------------------------------------

                        const node = data.node;
                        const progress = data.progress;

                        if (actionButtonsContainer.style.display === 'none') actionButtonsContainer.style.display = 'flex';

                        if (progress && typeof progress.current !== 'undefined') {
                            const percent = progress.total ? Math.round((progress.current / progress.total) * 100) : 0;
                            progressBar.style.width = percent + "%";
                            progressBar.innerText = percent + "%";
                        }

                        window.lastResults.push(node);
                        renderNode(node, treeContainer);
                    } catch (err) {
                        console.error("SSE parse error:", err, event.data);
                    }
                };

                evtSource.addEventListener("done", function(event) {
                    try {
                        // sometimes servers put summary/meta into the done event
                        if (event.data) {
                            try {
                                const doneData = JSON.parse(event.data);
                                if (doneData.keyword && doneData.keyword.id) window.currentKeywordId = doneData.keyword.id;
                                else if (doneData.keyword_id) window.currentKeywordId = doneData.keyword_id;
                            } catch (e) {
                                // not JSON — ignore
                            }
                        }
                    } catch (e) {
                        console.error('Error handling done event', e);
                    }

                    // final debug log
                    console.debug('SSE done. final keyword id =', window.currentKeywordId);

                    evtSource.close();
                    searchBtn.disabled = false;
                    searchBtn.innerHTML = 'Search';

                    // Remove live tree + loader
                    const loadingBlock = document.getElementById('loading-container');
                    if (loadingBlock) loadingBlock.remove();
                    const progressContainer = document.getElementById('progress-container');
                    if (progressContainer) progressContainer.remove();
                    treeContainerWrapper.remove();

                    // Render paginated results
                    renderPaginatedResults(1);
                });

                evtSource.onerror = function(err) {
                    console.error("SSE error:", err);
                    evtSource.close();
                    searchBtn.disabled = false;
                    searchBtn.innerHTML = 'Search';
                    const errMsg = document.createElement("p");
                    errMsg.className = "text-danger mt-2";
                    errMsg.innerText = "Error streaming results.";
                    resultsContainer.appendChild(errMsg);
                };

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
                    const startIndex = (page - 1) * itemsPerPage;
                    const paginated = window.lastResults.slice(startIndex, startIndex + itemsPerPage);

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
                        `;
                    }

                    const saveMessageContainer = resultsContainer.querySelector('#save-message-container');
                    resultsContainer.insertBefore(actionButtons, saveMessageContainer);

                    // Live references
                    const markAllCheckboxFinal = document.getElementById('mark-all-checkbox');

                    // Query checkboxes in the newly rendered page
                    const resultCheckboxesFinal = resultsContainer.querySelectorAll('.result-checkbox');

                    // Restore checkbox states and wire onchange to update window.selectedItems
                    resultCheckboxesFinal.forEach(cb => {
                        // If your checkboxes already have dataset.id as "path" (e.g. "0-2-1"), this will work.
                        // If not, ensure renderResults uses path-based IDs or set them here appropriately.
                        cb.checked = window.selectedItems.has(cb.dataset.id);

                        cb.onchange = () => {
                            if (cb.checked) window.selectedItems.add(cb.dataset.id);
                            else window.selectedItems.delete(cb.dataset.id);

                            // Keep mark all in sync for visible page
                            updateMarkAllCheckboxForCheckboxList(markAllCheckboxFinal, resultCheckboxesFinal);
                        };
                    });

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
                        renderPagination(totalPages, page);
                    }
                }

            } catch (e) {
                console.error(e);
                resultsContainer.innerHTML = `<p class="text-danger">Failed to fetch results</p>`;
                searchBtn.disabled = false;
                searchBtn.innerHTML = 'Search';
            }
        });

        


        // Pagination click event handler
        document.addEventListener('click', function(e) {
            if (e.target && e.target.classList.contains('page-link')) {
                e.preventDefault();
                const targetPage = parseInt(e.target.dataset.page);
                
                if (!isNaN(targetPage) && targetPage !== currentPage) {
                    currentPage = targetPage;
                    paginatedResults = paginateResults(window.lastResults, currentPage, itemsPerPage);
                    
                    // Re-render results (replace content, not append)
                    // const itemsHtml = renderResults(paginatedResults);
                    const startIndex = (currentPage - 1) * itemsPerPage; // ADDED
                    const itemsHtml = renderResults(paginatedResults, 0, null, startIndex); // CHANGED

                    document.getElementById('results-content').innerHTML = itemsHtml || '<p>No results.</p>';

                    // Reinitialize checkbox functionality
                    // Reinitialize checkbox functionality
                    const resultCheckboxes = document.querySelectorAll('.result-checkbox');
                    resultCheckboxes.forEach(checkbox => {
                        // ADD: Set checked state from global tracker
                        checkbox.checked = selectedItems.has(checkbox.dataset.id);
                        
                        checkbox.onchange = () => {
                            const itemId = checkbox.dataset.id;
                            
                            // ADD: Update global selection tracker
                            if (checkbox.checked) {
                                selectedItems.add(itemId);
                            } else {
                                selectedItems.delete(itemId);
                            }
                            
                            if (checkbox.dataset.hasChildren === "true") {
                                const childCheckboxes = getChildCheckboxes(checkbox.dataset.id);
                                childCheckboxes.forEach(child => {
                                    child.checked = checkbox.checked;
                                    // ADD: Update global selection for children too
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
                            
                            // Update Mark All checkbox state
                            const markAllCheckbox = document.getElementById('mark-all-checkbox');
                            const allChecked = Array.from(resultCheckboxes).every(cb => cb.checked);
                            const someChecked = Array.from(resultCheckboxes).some(cb => cb.checked);
                            
                            if (markAllCheckbox) {
                                markAllCheckbox.checked = allChecked;
                                markAllCheckbox.indeterminate = someChecked && !allChecked;
                            }
                        };
                    });
                    
                    // Re-add Mark All functionality
                    const markAllCheckbox = document.getElementById('mark-all-checkbox');
                    if (markAllCheckbox) {
                        // Check if ALL items across ALL pages are selected
                        const allResultIds = getAllResultIds(window.lastResults);
                        const allSelected = allResultIds.every(id => selectedItems.has(id));
                        const someSelected = allResultIds.some(id => selectedItems.has(id));
                        
                        markAllCheckbox.checked = allSelected;
                        markAllCheckbox.indeterminate = someSelected && !allSelected;
                        
                        markAllCheckbox.onchange = (e) => {
                            const isChecked = e.target.checked;
                            
                            // Get ALL results (not just current page)
                            const allResultIds = getAllResultIds(window.lastResults);
                            
                            if (isChecked) {
                                // Add all IDs to selected items
                                allResultIds.forEach(id => selectedItems.add(id));
                            } else {
                                // Remove all IDs from selected items
                                allResultIds.forEach(id => selectedItems.delete(id));
                            }
                            
                            // Update checkboxes on current page
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
    }

    return { init };
}));
