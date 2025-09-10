document.addEventListener('DOMContentLoaded', function () {
    const actionButtons = document.querySelectorAll('.action-bar .btn, .action-buttons .btn');

    function addLoadingState(button, duration = 2000) {
        const originalContent = button.innerHTML;
        button.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Loading...';
        button.disabled = true;
        setTimeout(() => {
            button.innerHTML = originalContent;
            button.disabled = false;
        }, duration);
    }

    actionButtons.forEach(btn => {
        if (btn.textContent.includes('Start') || btn.textContent.includes('Restart')) {
            btn.addEventListener('click', function () {
                addLoadingState(this);
            });
        }
        btn.addEventListener('click', function () {
            this.style.transform = 'scale(0.95)';
            setTimeout(() => this.style.transform = '', 150);
        });
    });
});