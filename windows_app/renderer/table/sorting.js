document.addEventListener('DOMContentLoaded', function () {
    const sortHeaders = document.querySelectorAll('th .sort-icon');
    sortHeaders.forEach(icon => {
        icon.parentElement.style.cursor = 'pointer';
        icon.parentElement.addEventListener('click', function () {
            const isAscending = icon.classList.contains('bi-arrow-down-up');
            sortHeaders.forEach(otherIcon => otherIcon.className = 'bi bi-arrow-down-up sort-icon');
            icon.className = isAscending ? 'bi bi-arrow-down sort-icon' : 'bi bi-arrow-up sort-icon';
            console.log('Sorting by:', this.textContent.trim(), isAscending ? 'desc' : 'asc');
        });
    });
});