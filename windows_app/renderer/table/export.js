window.exportData = function(format) {
    const table = document.querySelector('.table');
    const rows = Array.from(table.querySelectorAll('tr'));
    const data = rows.map(row => Array.from(row.querySelectorAll('th, td')).map(cell => cell.textContent.trim()));

    switch (format) {
        case 'csv': exportToCSV(data); break;
        case 'excel': exportToExcel(data); break;
        case 'pdf': exportToPDF(data); break;
    }
};

function exportToCSV(data) {
    const csvContent = data.map(row => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'scraper-data.csv'; a.click();
    window.URL.revokeObjectURL(url);
}

function exportToExcel(data) { console.log('Excel export would be implemented with SheetJS'); }
function exportToPDF(data) { console.log('PDF export would be implemented with jsPDF'); }