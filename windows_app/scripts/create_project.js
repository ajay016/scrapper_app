// scripts/project.js
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.__pages = root.__pages || {};
        root.__pages['project'] = factory();
    }
}(this, function () {
    function init() {

        function showToast(message, type = 'success') {
            const toast = document.createElement('div');
            toast.className = `toast-notification toast-${type}`;
            toast.textContent = message;

            document.body.appendChild(toast);

            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }
        const btn = document.getElementById("create-project-btn");
        const nameInput = document.getElementById("project-name");
        const descInput = document.getElementById("project-desc");
        const message = document.getElementById("project-message");

        if (!btn) return;

        btn.addEventListener("click", async () => {
            const accessToken = localStorage.getItem("accessToken");
            const name = (nameInput.value || '').trim();
            const description = descInput.value || '';

            // Clear previous messages
            message.innerHTML = '';

            if (!name) {
                message.innerHTML = `<div class="alert alert-danger alert-dismissible fade show" role="alert">
                                        Project name is required
                                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                                    </div>`;
                return;
            }

            try {
                const res = await fetch(`${API_BASE_URL}/api/projects/`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${accessToken}`
                    },
                    body: JSON.stringify({ name, description })
                });
                const data = await res.json();

                if (!res.ok) {
                    message.innerHTML = `<div class="alert alert-danger alert-dismissible fade show" role="alert">
                                            Error: ${data.error || 'Failed to create project'}
                                            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                                        </div>`;
                    return;
                }

                message.innerHTML = `<div class="alert alert-success alert-dismissible fade show" role="alert">
                                        Project created successfully "Name: "${data.name}"
                                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                                    </div>`;

                // Clear form fields on success
                nameInput.value = '';
                descInput.value = '';

            } catch (e) {
                console.error(e);
                message.innerHTML = `<div class="alert alert-danger alert-dismissible fade show" role="alert">
                                        Server error - please try again
                                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                                    </div>`;
            }
        });
    }

    return { init };
}));
