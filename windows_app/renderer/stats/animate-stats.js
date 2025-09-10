document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.stat-value').forEach(stat => {
        const finalValue = stat.textContent;
        const numericValue = parseInt(finalValue.replace(/[^\d]/g, ''));
        if (isNaN(numericValue)) return;
        let currentValue = 0;
        const increment = numericValue / 50;
        const timer = setInterval(() => {
            currentValue += increment;
            if (currentValue >= numericValue) {
                stat.textContent = finalValue;
                clearInterval(timer);
            } else {
                stat.textContent = Math.floor(currentValue).toLocaleString();
            }
        }, 30);
    });
});