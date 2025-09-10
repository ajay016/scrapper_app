(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.__pages = root.__pages || {};
        root.__pages['keywords'] = factory();
    }
}(this, function () {

    function renderResults(results, level = 0, parentIndex = null) {
        if (!results || !results.length) return '';

        return results.map((r, index) => {
            const uniqueId = parentIndex !== null ? `${parentIndex}-${index}` : `${index}`;
            const childrenHtml = renderResults(r.children, level + 1, uniqueId);
            return `
                <div class="card my-2 p-2" style="margin-left:${level * 20}px;">
                    <div class="form-check">
                        <input class="form-check-input result-checkbox" type="checkbox" 
                            data-url="${r.url}" data-title="${r.title || r.url}" 
                            data-id="${uniqueId}" data-has-children="${r.children && r.children.length > 0}">
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

    function init() {
        const searchBtn = document.getElementById("search-keyword-btn");
        const keywordInput = document.getElementById("keyword-input");
        const depthInput = document.getElementById("depth-input");
        const resultsContainer = document.getElementById("results-container");

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

                // Validate project selected
                if (!projectSelect || !projectSelect.value) {
                    showAlert('danger', 'Please select a project first');
                    return;
                }

                // Make sure we have results
                if (!window.lastResults || window.lastResults.length === 0) {
                    showAlert('danger', 'No search results found. Please run a search first.');
                    return;
                }
                if (!window.currentKeywordId) {
                    showAlert('danger', 'Missing keyword context. Please run a new search.');
                    return;
                }

                // Collect checked boxes
                const resultCheckboxes = document.querySelectorAll('.result-checkbox');
                const checkedBoxes = Array.from(resultCheckboxes).filter(cb => cb.checked);
                if (checkedBoxes.length === 0) {
                    showAlert('danger', 'Please select at least one item to save');
                    return;
                }

                // Helper: find node in lastResults by path
                function findNodeByPath(nodes, path) {
                    let current = nodes;
                    let node = null;
                    for (let i = 0; i < path.length; i++) {
                        node = current[path[i]];
                        if (!node) return null;
                        current = node.children || [];
                    }
                    return node;
                }

                // Helper: build minimal nested tree for saving
                function addSelectedNode(path, origNode, mergedTree, checkedIds) {
                    let current = mergedTree;

                    for (let i = 0; i < path.length; i++) {
                        const index = path[i];

                        // Check if node already exists at this level
                        let found = current.find(n => n.url === origNode.url);
                        if (!found) {
                            found = {
                                url: origNode.url,
                                title: origNode.title || '',
                                children: []
                            };
                            current.push(found);
                        }

                        // Only at the last node in the path, add selected children recursively
                        if (i === path.length - 1) {
                            if (origNode.children && origNode.children.length > 0) {
                                origNode.children.forEach((child, idx) => {
                                    const childId = path.concat(idx).join('-');
                                    if (checkedIds.has(childId)) {
                                        addSelectedNode(path.concat(idx), child, found.children, checkedIds);
                                    }
                                });
                            }
                        }

                        // Move down one level
                        current = found.children;
                    }
                }

                // Build merged tree
                const merged = [];
                const checkedIds = new Set(checkedBoxes.map(cb => cb.dataset.id));

                checkedBoxes.forEach(cb => {
                    const path = cb.dataset.id.split('-').map(n => parseInt(n));
                    const origNode = findNodeByPath(window.lastResults, path);
                    if (origNode) {
                        addSelectedNode(path, origNode, merged, checkedIds);
                    }
                });

                if (merged.length === 0) {
                    showAlert('danger', 'No valid items to save.');
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
                        project_id: projectSelect?.value || null   // <-- send project here
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

        // When project changes → load folders
        // projectSelect.addEventListener("change", () => {
        //     const projectId = projectSelect.value;
        //     folderSelect.innerHTML = `<option value="">Select Folder</option>`;

        //     if (!projectId) {
        //         folderSelect.disabled = true;
        //         return;
        //     }

        //     fetch(`${API_BASE_URL}/api/projects/${projectId}/folders/`, {
        //         headers: {
        //             Authorization: `Bearer ${localStorage.getItem("accessToken")}`
        //         }
        //     })
        //         .then(res => res.json())
        //         .then(folders => {
        //             folderSelect.innerHTML = `<option value="">Select Folder</option>`;
        //             folders.forEach(f => {
        //                 folderSelect.innerHTML += `<option value="${f.id}">${f.name}</option>`;
        //             });
        //             folderSelect.disabled = false;
        //         })
        //         .catch(err => console.error("Failed to load folders", err));
        // });
        // When project changes → load folders ends

        searchBtn.addEventListener("click", async () => {
            const keyword = (keywordInput.value || '').trim();
            const depth = depthInput.value || 0;

            if (!keyword) {
                resultsContainer.innerHTML = `<p class="text-danger">Please enter a keyword</p>`;
                return;
            }

            try {
                // ADD: Disable search button and add spinner
                searchBtn.disabled = true;
                searchBtn.innerHTML = `
                    <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                    Searching...
                `;

                // ADD: Modern loading animation
                resultsContainer.innerHTML = `
                    <div class="text-center">
                        <div class="spinner-border text-primary mb-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="searching-pulse">Searching for "${keyword}"...</p>
                    </div>
                `;
                const response = await fetch(`${API_BASE_URL}/api/search-keywords/?q=${encodeURIComponent(keyword)}&depth=${depth}`);
                const data = await response.json();
                window.lastResults = data.results || [];
                window.currentKeywordId = data.keyword?.id || null;

                // Store keyword_id globally for later use in Save
                window.currentKeywordId = data.keyword.id;

                console.log("Search results:", data);

                if (!response.ok) {
                    resultsContainer.innerHTML = `<p class="text-danger">Error: ${data.error || 'Unknown error'}</p>`;
                    return;
                }

                const itemsHtml = renderResults(data.results || []);

                resultsContainer.innerHTML = `
                    <h5>Results for "${data.keyword.word}"</h5>
                    <div class="d-flex align-items-center mt-5 mb-3 ms-2" id="action-buttons-container" style="display: ${data.results && data.results.length > 0 ? 'flex' : 'none'};">
                        <div class="form-check me-5">
                            <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
                            <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
                        </div>
                        <button id="save-selected-btn" class="btn btn-primary btn-sm">Save Selected</button>
                    </div>
                    <div id="save-message-container" class="mt-2"></div>
                    ${itemsHtml || '<p>No results.</p>'}
                `;

                // Checkboxes functionality starts:
                const actionButtonsContainer = document.getElementById('action-buttons-container');
                const markAllCheckbox = document.getElementById('mark-all-checkbox');
                const saveSelectedBtn = document.getElementById('save-selected-btn');

                // Checkbox functionality starts
                const resultCheckboxes = document.querySelectorAll('.result-checkbox');

                // Show mark all container if there are results
                if (data.results && data.results.length > 0) {
                    actionButtonsContainer.style.display = 'flex';
                } else {
                    actionButtonsContainer.style.display = 'none';
                }

                // Reset mark all checkbox state
                markAllCheckbox.checked = false;
                markAllCheckbox.indeterminate = false;

                // ADD Mark All functionality:
                // ADD Mark All functionality:
                markAllCheckbox.onchange = (e) => {
                    resultCheckboxes.forEach(checkbox => {
                        checkbox.checked = e.target.checked;
                        // Clear indeterminate state when using Mark All
                        checkbox.indeterminate = false;
                    });
                };

                // Individual checkbox functionality
                resultCheckboxes.forEach(checkbox => {
                    checkbox.onchange = () => {
                        // If this is a parent checkbox, check/uncheck all children
                        if (checkbox.dataset.hasChildren === "true") {
                            const childCheckboxes = getChildCheckboxes(checkbox.dataset.id);
                            childCheckboxes.forEach(child => {
                                child.checked = checkbox.checked;
                            });
                        } else {
                            // If this is a child checkbox, update parent state
                            // But DON'T auto-uncheck the parent - parents only get checked, never auto-unchecked
                            if (checkbox.checked) {
                                updateParentState(checkbox);
                            }
                        }
                        
                        // Update Mark All checkbox state
                        const allChecked = Array.from(resultCheckboxes).every(cb => cb.checked);
                        const someChecked = Array.from(resultCheckboxes).some(cb => cb.checked);
                        
                        markAllCheckbox.checked = allChecked;
                        markAllCheckbox.indeterminate = someChecked && !allChecked;
                    };
                });
                // Checkbox functionality ends
            }
            catch (e) {
                console.error(e);
                resultsContainer.innerHTML = `<p class="text-danger">Failed to fetch results</p>`;
            }
            finally {
                // ADD: Re-enable search button and restore original text
                searchBtn.disabled = false;
                searchBtn.innerHTML = 'Search';
            }
        });
    }

    return { init };
}));
