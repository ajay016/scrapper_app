document.addEventListener('DOMContentLoaded', function () {
    const selectAllCheckbox = document.getElementById('selectAll');
    const rowCheckboxes = document.querySelectorAll('tbody input[type="checkbox"]');
    if (!selectAllCheckbox) return;

    selectAllCheckbox.addEventListener('change', function () {
        rowCheckboxes.forEach(cb => cb.checked = this.checked);
    });

    rowCheckboxes.forEach(cb => cb.addEventListener('change', function () {
        const checkedBoxes = document.querySelectorAll('tbody input[type="checkbox"]:checked');
        selectAllCheckbox.checked = checkedBoxes.length === rowCheckboxes.length;
        selectAllCheckbox.indeterminate = checkedBoxes.length > 0 && checkedBoxes.length < rowCheckboxes.length;
    }));
});
