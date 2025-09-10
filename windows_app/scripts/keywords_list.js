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
    }

    function init() {
        keywordList();
    }

    return { init };
}));