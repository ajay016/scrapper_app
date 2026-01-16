(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.__pages = root.__pages || {};
        root.__pages['projects'] = factory();
    }
}(this, function () {

    async function fetchProjects() {
        const container = document.querySelector(".projects-container");
        if (!container) return;

        try {
            container.innerHTML = `
                <div class="proj-loading">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mt-2">Loading your projects...</p>
                </div>
            `;

            const res = await fetch(`${API_BASE_URL}/api/user-projects/`, {
                headers: {
                    Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                }
            });

            if (!res.ok) throw new Error("Failed to fetch projects");
            const projects = await res.json();
            renderProjects(container, projects);
        } catch (err) {
            console.error(err);
            container.innerHTML = `
                <div class="proj-error">
                    <i class="bi bi-exclamation-triangle"></i>
                    <h5>Unable to load projects</h5>
                    <p>Please try again later</p>
                </div>
            `;
        }
    }

    function renderProjects(container, projects) {
        if (!projects || !projects.length) {
            container.innerHTML = `
                <div class="proj-empty-state">
                    <i class="bi bi-folder-x"></i>
                    <h4>No projects found</h4>
                    <p>Get started by creating your first project</p>
                </div>
            `;
            return;
        }

        const html = `
                        <div class="proj-folders">
                            ${projects.map((project) => `
                                <div class="proj-folder-item" data-project-id="${project.id}">
                                    <i class="bi bi-kanban proj-folder-icon"></i>
                                    <div class="proj-folder-info">
                                        <h6 class="proj-folder-name">${project.name}</h6>
                                        <p class="proj-folder-desc">${project.folders.length} folders</p>
                                    </div>
                                    <div class="proj-actions">
                                        <button class="btn btn-sm btn-outline-secondary">
                                            <i class="bi bi-pencil"></i>
                                        </button>
                                        <!-- Delete icon that acts as checkbox -->
                                        <input type="checkbox" class="delete-checkbox" 
                                            data-project-id="${project.id}">
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    `;

        container.innerHTML = html;

        // Project item click handlers
        container.querySelectorAll(".proj-folder-item").forEach(el => {
            el.addEventListener("click", (e) => {
                // Don't navigate if clicking on checkbox or edit button
                if (e.target.closest('.delete-checkbox') || e.target.closest('.btn')) {
                    return;
                }
                const projectId = el.dataset.projectId;
                if (window.__nav && projectId) {
                    window.__nav.loadPage(
                        document.getElementById('page-content-id'),
                        "project_folders",
                        { projectId }
                    );
                }
            });
        });

        // Checkbox event handlers
        container.querySelectorAll(".delete-checkbox").forEach(checkbox => {
            checkbox.addEventListener("click", (e) => {
                e.stopPropagation(); // Prevent triggering project item click
            });
            
            checkbox.addEventListener("change", () => toggleDeleteButton(container));
        });

        function toggleDeleteButton() {
            const checkedBoxes = container.querySelectorAll(".delete-checkbox:checked");
            const deleteContainer = document.getElementById("delete-selected-container");
            const messageContainer = document.getElementById("delete-message-container");
            
            // Clear any existing messages when selection changes
            messageContainer.innerHTML = '';
            
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

    // function to handle single/bulk deletion
    async function deleteSelectedProjects() {
        const selectedIds = Array.from(document.querySelectorAll(".delete-checkbox:checked"))
            .map(checkbox => checkbox.dataset.projectId);
        const messageContainer = document.getElementById("delete-message-container");

        if (selectedIds.length === 0) {
            showAlert('danger', 'Please select at least one project to delete.');
            return;
        }

        // if (!confirm(`All the keywords/folders inside the projects will be deleted. Are you sure you want to delete ${selectedIds.length} project(s)?`)) {
        //     return;
        // }

        if (!confirm(`Все ключевые слова и папки внутри проектов будут удалены. Вы уверены, что хотите удалить ${selectedIds.length} проект(а/ов)?`)) {
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/api/delete-projects/`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${localStorage.getItem("accessToken")}`
                },
                body: JSON.stringify({ ids: selectedIds })
            });

            if (response.ok) {
                const data = await response.json();
                
                // Hide delete button
                document.getElementById("delete-selected-container").classList.remove('show');
                
                // Show success message
                showAlert('success', data.detail || `${selectedIds.length} project(s) deleted successfully.`);
                
                // Refresh projects after a short delay
                setTimeout(() => {
                    fetchProjects();
                    // Clear message after refresh
                    setTimeout(() => {
                        messageContainer.innerHTML = '';
                    }, 3000);
                }, 1000);
                
            } else {
                const data = await response.json();
                throw new Error(data.detail || "Some deletions failed");
            }
        } catch (err) {
            console.error(err);
            showAlert('danger', err.message || "Failed to delete projects. Please try again.");
            
            // Auto-hide error message after 5 seconds
            setTimeout(() => {
                messageContainer.innerHTML = '';
            }, 5000);
        }
    }

    function init() {
        fetchProjects();
        
        // Add this line to set up the delete button click handler
        document.getElementById("delete-selected-btn")?.addEventListener("click", deleteSelectedProjects);
    }

    return { init };
}));