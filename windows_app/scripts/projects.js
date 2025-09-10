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
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        container.innerHTML = html;

        // 🔥 Add click handlers here
        container.querySelectorAll(".proj-folder-item").forEach(el => {
            el.addEventListener("click", () => {
                const projectId = el.dataset.projectId;
                if (window.__nav && projectId) {
                    window.__nav.loadPage(
                        document.getElementById('page-content-id'), // 1️⃣ container element
                        "project_folders",                          // 2️⃣ page name
                        { projectId }                               // 3️⃣ params
                    );
                } else {
                    console.error("No projectId or window.__nav not defined");
                }
            });
        });
    }

    function init() {
        fetchProjects();
    }

    return { init };
}));