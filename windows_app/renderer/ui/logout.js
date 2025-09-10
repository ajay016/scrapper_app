document.addEventListener("DOMContentLoaded", () => {
    const userOptionsBtn = document.getElementById("user-options-btn");
    const userOptionsMenu = document.getElementById("user-options-menu");
    const logoutBtn = document.getElementById("logout-btn");
    const loggedInState = document.getElementById("logged-in-state");
    const loggedOutState = document.getElementById("logged-out-state");

    // Toggle dropdown menu on button click
    if (userOptionsBtn) {
        userOptionsBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            userOptionsMenu.style.display =
                userOptionsMenu.style.display === "block" ? "none" : "block";
        });
    }

    // Close dropdown if clicked outside
    document.addEventListener("click", () => {
        if (userOptionsMenu) {
            userOptionsMenu.style.display = "none";
        }
    });

    // Logout button logic
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            localStorage.removeItem("accessToken");
            localStorage.removeItem("refreshToken");

            loggedInState.style.display = "none";
            loggedOutState.style.display = "flex";

            if (userOptionsMenu) {
                userOptionsMenu.style.display = "none";
            }
        });
    }
});
