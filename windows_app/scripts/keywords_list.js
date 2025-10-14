// scripts/project_folders.js
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.__pages = root.__pages || {};
        root.__pages['keywords_list'] = factory();
    }
}(this, function () {

    async function keywordList() {
        const container = document.querySelector(".keywords-list-container");
        if (!container) return;

        try {
            container.innerHTML = `
                <div class="proj-loading">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mt-2">Loading folders...</p>
                </div>
            `;

            const res = await fetch(`${API_BASE_URL}/api/keywords-list/`, {
                headers: {
                    Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                }
            });

            if (!res.ok) throw new Error("Failed to fetch folders");
            const folders = await res.json();
            renderFolders(container, folders);
        } catch (err) {
            console.error(err);
            container.innerHTML = `
                <div class="proj-error">
                    <i class="bi bi-exclamation-triangle"></i>
                    <h5>Unable to load folders</h5>
                    <p>Please try again later</p>
                </div>
            `;
        }
    }

    function renderFolders(container, folders) {
        if (!folders || !folders.length) {
            container.innerHTML = `
                <div class="proj-empty-state">
                    <i class="bi bi-folder-x"></i>
                    <h4>No folders found</h4>
                    <p>This project doesn't have any folders yet</p>
                </div>
            `;
            return;
        }

        const html = `
                        <div class="proj-folders">
                            ${folders.map((folder) => `
                                <div class="proj-folder-item" data-folder-id="${folder.id}">
                                    <i class="bi bi-folder proj-folder-icon"></i>
                                    <div class="proj-folder-info">
                                        <h6 class="proj-folder-name">${folder.name}</h6>
                                        <p class="proj-folder-desc">${folder.description || "No description"}</p>
                                    </div>
                                    <div class="proj-actions">
                                        <button class="btn btn-sm btn-outline-secondary">
                                            <i class="bi bi-pencil"></i>
                                        </button>
                                        <!-- Add delete checkbox -->
                                        <input type="checkbox" class="delete-checkbox" 
                                            data-folder-id="${folder.id}">
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    `;

        container.innerHTML = html;

        document.querySelectorAll('.proj-folder-item').forEach(item => {
            item.addEventListener('click', () => {
                const folderId = item.dataset.folderId;
                const pageContent = document.getElementById('page-content-id'); // replace with your container id
                window.__nav.loadPage(pageContent, 'folder_details', { folderId });
            });
        });

        // Add after the folder item click handlers
        container.querySelectorAll(".delete-checkbox").forEach(checkbox => {
            checkbox.addEventListener("click", (e) => {
                e.stopPropagation(); // Prevent triggering folder item click
            });
            
            checkbox.addEventListener("change", () => toggleDeleteButton(container));
        });

        // Add toggle function
        function toggleDeleteButton() {
            const checkedBoxes = container.querySelectorAll(".delete-checkbox:checked");
            const deleteContainer = document.getElementById("delete-selected-container");
            const messageContainer = document.getElementById("delete-message-container");
            
            messageContainer.innerHTML = ''; // Clear messages
            
            if (checkedBoxes.length > 0) {
                deleteContainer.classList.add('show');
            } else {
                deleteContainer.classList.remove('show');
            }
        }
    }

    // Default Success & Error message
    function showAlert(type, message) {
        const messageContainer = document.getElementById("delete-message-container");
        const existingAlert = messageContainer.querySelector('.alert');
        if (existingAlert) existingAlert.remove();

        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        messageContainer.appendChild(alertDiv);
        
        // Add event listener to close button
        const closeBtn = alertDiv.querySelector('.btn-close');
        closeBtn.addEventListener('click', () => {
            alertDiv.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        });
    }

    async function deleteSelectedFolders() {
        const selectedIds = Array.from(document.querySelectorAll(".delete-checkbox:checked"))
            .map(checkbox => checkbox.dataset.folderId);
        const messageContainer = document.getElementById("delete-message-container");

        if (selectedIds.length === 0) {
            showAlert('danger', 'Please select at least one folder to delete.');
            return;
        }

        if (!confirm(`Are you sure you want to delete ${selectedIds.length} folder(s)?`)) {
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/api/delete-folders/`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                },
                body: JSON.stringify({ ids: selectedIds })
            });

            if (response.ok) {
                const data = await response.json();
                document.getElementById("delete-selected-container").classList.remove('show');
                showAlert('success', data.detail || `${selectedIds.length} folder(s) deleted successfully.`);
                setTimeout(() => keywordList(), 1000); // Refresh
            } else {
                const data = await response.json();
                throw new Error(data.detail || "Some deletions failed");
            }
        } catch (err) {
            console.error(err);
            showAlert('danger', err.message || "Failed to delete folders. Please try again.");
        }
    }

    function init() {
        keywordList();
        
        // Add delete button event listener
        document.getElementById("delete-selected-btn")?.addEventListener("click", deleteSelectedFolders);
    }

    return { init };
}));