const { ipcRenderer, webFrame, shell } = require("electron");




// Import modules
require('./renderer/ui/menu');
require('./renderer/ui/tooltips');
require('./renderer/ui/theme');
require('./renderer/ui/notifications');
require('./renderer/ui/buttons');
require('./renderer/ui/search');
require('./renderer/ui/edit-menu');

require('./renderer/table/sorting');
require('./renderer/table/select-all');
require('./renderer/table/export');

require('./renderer/stats/animate-stats');
require('./renderer/window-controls');

require('./renderer/ui/logout');


// ADD THIS FUNCTION near the top of your file (after imports):
function setActiveNavItem(clickedItem) {
    // Remove active class from all nav items
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    
    // Add active class to the clicked item
    clickedItem.classList.add('active');
}

// MODIFY your existing event listeners to include the active state:
document.querySelector('.projects-nav-item')
    ?.addEventListener('click', function() {
        loadPage(pageContent, 'projects');
        setActiveNavItem(this.querySelector('.nav-link')); // ADD THIS LINE
    });

document.querySelector('.keywords-list-nav-item')
    ?.addEventListener('click', function() {
        loadPage(pageContent, 'keywords_list');
        setActiveNavItem(this.querySelector('.nav-link')); // ADD THIS LINE
    });

// ADD similar event listeners for the other nav items:
document.querySelectorAll('.nav-item:not(.projects-nav-item):not(.keywords-list-nav-item)').forEach(item => {
    item.addEventListener('click', function() {
        // You'll need to determine the page name based on the item
        const pageName = determinePageName(this); // You need to implement this
        loadPage(pageContent, pageName);
        setActiveNavItem(this.querySelector('.nav-link'));
    });
});

// ADD this helper function (implement your own logic for page names):
function determinePageName(navItem) {
    // Example implementation - adjust based on your structure
    const text = navItem.querySelector('span').textContent.toLowerCase();
    if (text === 'dashboard') return 'dashboard';
    if (text === 'urls') return 'urls';
    if (text === 'settings') return 'settings';
    return text;
}


window.__pages = window.__pages || {}; // global registry for page modules

async function loadPage(pageContent, pageName, params = {}) {
    try {
        // 1) Load HTML
        const res = await fetch(`pages/${pageName}.html`);
        const html = await res.text();
        pageContent.innerHTML = html;

        // 2) Load script if not already loaded
        if (!window.__pages[pageName]) {
            await new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = `scripts/${pageName}.js`;
                script.async = true;

                script.onload = () => {
                    // Support Node-style exports too
                    if (typeof module !== "undefined" && module.exports && !window.__pages[pageName]) {
                        window.__pages[pageName] = module.exports;
                    }
                    resolve();
                };

                script.onerror = reject;
                document.head.appendChild(script);
            });
        }

        console.log('hit in load page 3')

        // 3) Call init if available
        if (window.__pages[pageName]?.init) {
            window.__pages[pageName].init(params);
        } else {
            console.warn(`No init() found for page: ${pageName}`);
        }
    } catch (err) {
        console.error("Failed to load page:", err);
    }
}

window.__nav = window.__nav || {};
window.__nav.loadPage = loadPage;


const pageContent = document.getElementById('page-content-id');

// Load default page
// loadPage(pageContent, 'dashboard');
// Page loader function. Dynamically loads HTML and JS for different pages. Ends



// Button click
document.querySelector('.action-bar .btn-outline-secondary i.bi-tag')?.parentElement
    ?.addEventListener('click', () => loadPage(pageContent, 'keywords'));

// New Project
document.querySelector('.new-project-btn')?.parentElement
    ?.addEventListener('click', () => loadPage(pageContent, 'create_project'));

// New Project button → load new project page
document.querySelector('.action-bar .btn-primary i.bi-plus-circle')?.parentElement
    ?.addEventListener('click', () => loadPage(pageContent, 'create_project'));

document.querySelector('.projects-nav-item')
    ?.addEventListener('click', () => loadPage(pageContent, 'projects'));

document.querySelector('.keywords-list-nav-item')
    ?.addEventListener('click', () => loadPage(pageContent, 'keywords_list'));


// Login and logout starts
document.getElementById("login-btn")?.addEventListener("click", () => {
    const redirectUri = "scraper://auth";  // deep link
    // Open login page in default browser with redirect_uri
    require('electron').shell.openExternal(
        `${API_BASE_URL}/login-user/?redirect_uri=${redirectUri}`
    );
});

// Logout button
document.getElementById("logout-btn")?.addEventListener("click", () => {
    localStorage.removeItem("accessToken");
    localStorage.removeItem("refreshToken");
    document.getElementById("logged-in-state").style.display = "none";
    document.getElementById("logged-out-state").style.display = "flex";
});

// Receive token from deep link
ipcRenderer.on("auth-token-received", (event, url) => {
    try {
        const params = new URL(url).searchParams;
        const accessToken = params.get("token");
        const refreshToken = params.get("refresh");
        // const accessToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzU3MzYwMDQ5LCJpYXQiOjE3NTczNTY0NDksImp0aSI6IjNjZjJkMTE4OTk1ZjRkNmZiNzIyODA0MzdkZDRjMDY5IiwidXNlcl9pZCI6IjEifQ.aMs2xFKkaF1CbRxI5fNVIltp2z_jlk6l1WuN0qWqbMA";
        // const refreshToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc1NzQ0Mjg0OSwiaWF0IjoxNzU3MzU2NDQ5LCJqdGkiOiJiZjM1ZTgwMmQxZDM0NWE2OTFlMmFkYzM0NjEyZmM4OCIsInVzZXJfaWQiOiIxIn0.l1hu3TsyYYBoKewvJKDMKx7WSi6ShCygNbw0BGDi4DY";

        if (accessToken) {
            localStorage.setItem("accessToken", accessToken);
            localStorage.setItem("refreshToken", refreshToken);

            // Optional: fetch user info from API
            fetch(`${API_BASE_URL}/api/user/`, {
                headers: { Authorization: `Bearer ${accessToken}` }
            })
            .then(res => res.json())
            .then(user => {
                let displayName = user.first_name || user.last_name || user.email || "User";
                console.log("User info:", displayName);
                document.querySelector(".user-name").innerText = displayName;
                document.querySelector(".user-role").innerText = user.role || "";
            })
            .catch(() => {
                document.querySelector(".user-name").innerText = "Logged In User";
            });


            document.getElementById("logged-out-state").style.display = "none";
            document.getElementById("logged-in-state").style.display = "flex";
            document.querySelector(".user-name").innerText = "Logged In User";
        } else {
            alert("Login failed. No token received.");
        }
    } catch (err) {
        console.error("Error parsing deep link URL:", err);
    }
});

// On app load, check for existing token
function checkSession() {
    const token = localStorage.getItem("accessToken");
    if (token) {
        document.getElementById("logged-out-state").style.display = "none";
        document.getElementById("logged-in-state").style.display = "flex";
        document.querySelector(".user-name").innerText = "Logged In User";
        // Optionally call refreshToken() to validate
    } else {
        document.getElementById("logged-out-state").style.display = "flex";
        document.getElementById("logged-in-state").style.display = "none";
    }
}

checkSession();

// Optional: Token refresh function
async function refreshToken() {
    const refresh = localStorage.getItem("refreshToken");
    if (!refresh) return;
    try {
        const res = await fetch(`${API_BASE_URL}/api/token/refresh/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh })
        });
        const data = await res.json();
        if (data.access) localStorage.setItem("accessToken", data.access);
    } catch (err) {
        console.error("Failed to refresh token:", err);
    }
}
// Login ends



// Remove this in production starts
// Forward renderer errors to main process
window.addEventListener('error', (event) => {
    ipcRenderer.send('renderer-error', `${event.message} at ${event.filename}:${event.lineno}`);
});

window.addEventListener('unhandledrejection', (event) => {
    ipcRenderer.send('renderer-error', `Unhandled Promise Rejection: ${event.reason}`);
});
// Forward renderer errors to main process ends
// Remove this in production ends
