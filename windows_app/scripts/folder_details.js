// scripts/folder_details.js
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.__pages = root.__pages || {};
        root.__pages['folder_details'] = factory();
    }
}(this, function () {

    async function loadFolderDetails(folderId) {
        const container = document.querySelector(".url-links-container");
        if (!container) return;

        container.innerHTML = `
            <div class="text-center my-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p>Loading folder details...</p>
            </div>
        `;

        try {
            const res = await fetch(`${API_BASE_URL}/api/folder/${folderId}/keyword-results/`, {
                headers: { Authorization: `Bearer ${localStorage.getItem("accessToken")}` }
            });
            const data = await res.json();
            console.log('folder details data: ', data);

            if (!res.ok) throw new Error(data.error || "Failed to fetch folder details");

            renderFolderResults(container, data.results || [], data.keyword || null);
        } catch (err) {
            console.error(err);
            container.innerHTML = `
                <div class="proj-error text-center">
                    <i class="bi bi-exclamation-triangle"></i>
                    <h5>Unable to load folder details</h5>
                    <p>${err.message}</p>
                </div>
            `;
        }
    }

    function renderFolderResults(container, results, keyword) {
        if (!results.length) {
            container.innerHTML = `
                <div class="proj-empty-state text-center">
                    <i class="bi bi-folder-x"></i>
                    <h4>No results found for keyword "${keyword?.word || ''}"</h4>
                </div>
            `;
            return;
        }

        const itemsHtml = renderResults(results);

        container.innerHTML = `
            <h5>Results for "${keyword.word}"</h5>
            <div class="d-flex align-items-center mt-5 mb-3 ms-2" id="action-buttons-container">
                <div class="form-check me-5">
                    <input class="form-check-input" type="checkbox" id="mark-all-checkbox">
                    <label class="form-check-label" for="mark-all-checkbox">Mark All</label>
                </div>
                <button id="delete-selected-btn" class="btn btn-danger">Delete Selected</button>
            </div>
            <div id="save-message-container" class="mt-2"></div>
            ${itemsHtml}
        `;

        setupCheckboxes();

        // delete button logic starts
        const deleteBtn = document.getElementById("delete-selected-btn");
        deleteBtn.addEventListener("click", async () => {
            const checked = Array.from(document.querySelectorAll(".result-checkbox:checked"));
            const message = document.getElementById("save-message-container");

            if (!checked.length) {
                message.innerHTML = `
                    <div class="alert alert-danger alert-dismissible fade show" role="alert">
                        Please select at least one item to delete.
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>`;
                return;
            }

            if (!confirm("Are you sure you want to delete the selected items?")) return;

            const ids = checked.map(cb => parseInt(cb.dataset.dbId, 10)).filter(Boolean);

            try {
                const res = await fetch(`${API_BASE_URL}/api/folder/${window.currentFolderId}/delete-folder-results/`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                    },
                    body: JSON.stringify({ ids })
                });

                const data = await res.json();
                if (!res.ok) {
                    message.innerHTML = `
                        <div class="alert alert-danger alert-dismissible fade show" role="alert">
                            ${data.error || "Failed to delete items"}
                            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                        </div>`;
                    return;
                }

                // ✅ Show success message
                message.innerHTML = `
                    <div class="alert alert-success alert-dismissible fade show" role="alert">
                        Successfully deleted ${data.deleted.length} item(s).
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>`;

                // Refresh folder details after short delay so user sees success
                setTimeout(() => {
                    loadFolderDetails(window.currentFolderId);
                }, 1000);

            } catch (err) {
                message.innerHTML = `
                    <div class="alert alert-danger alert-dismissible fade show" role="alert">
                        Error deleting items: ${err.message}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>`;
            }
        });
        // Delete button logic ends
    }

    function renderResults(results, level = 0, parentIndex = null) {
        if (!results || !results.length) return '';

        return results.map((r, index) => {
            const uniqueId = parentIndex !== null ? `${parentIndex}-${index}` : `${index}`;
            const childrenHtml = renderResults(r.children, level + 1, uniqueId);

            return `
                <div class="card my-2 p-2" style="margin-left:${level * 20}px;">
                    <div class="form-check">
                        <input class="form-check-input result-checkbox" type="checkbox" 
                            data-id="${uniqueId}" data-db-id="${r.id}"
                            data-has-children="${r.children && r.children.length > 0}">
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

    function setupCheckboxes() {
        const markAllCheckbox = document.getElementById('mark-all-checkbox');
        const resultCheckboxes = document.querySelectorAll('.result-checkbox');

        markAllCheckbox.checked = false;
        markAllCheckbox.indeterminate = false;

        // Mark All
        markAllCheckbox.onchange = (e) => {
            resultCheckboxes.forEach(cb => {
                cb.checked = e.target.checked;
                cb.indeterminate = false;
            });
        };

        // Individual checkbox behavior
        resultCheckboxes.forEach(cb => {
            cb.onchange = () => {
                if (cb.dataset.hasChildren === "true") {
                    const childCheckboxes = getChildCheckboxes(cb.dataset.id);
                    childCheckboxes.forEach(child => child.checked = cb.checked);
                } else if (cb.checked) {
                    updateParentState(cb);
                }

                // Update mark all state
                const allChecked = Array.from(resultCheckboxes).every(cb => cb.checked);
                const someChecked = Array.from(resultCheckboxes).some(cb => cb.checked);
                markAllCheckbox.checked = allChecked;
                markAllCheckbox.indeterminate = someChecked && !allChecked;
            };
        });
    }

    function getChildCheckboxes(parentId) {
        return Array.from(document.querySelectorAll(`.result-checkbox[data-id^="${parentId}-"]`));
    }

    function updateParentState(checkbox) {
        const idParts = checkbox.dataset.id.split('-');
        while (idParts.length > 1) {
            idParts.pop();
            const parentId = idParts.join('-');
            const parentCheckbox = document.querySelector(`.result-checkbox[data-id="${parentId}"]`);
            if (parentCheckbox) parentCheckbox.checked = true;
        }
    }

    function init(params = {}) {
        if (!params.folderId) {
            console.error("folderId is required to load folder details");
            return;
        }

        // 🔥 Store globally for later (delete, refresh, etc.)
        window.currentFolderId = params.folderId;

        loadFolderDetails(params.folderId);
    }

    return { init };
}));
