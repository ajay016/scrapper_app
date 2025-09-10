document.addEventListener('DOMContentLoaded', function () {
    let menuTimeout;
    const menuDelay = 200;

    function setupHoverDelay(parentSelector) {
        const menuItems = document.querySelectorAll(parentSelector);
        const openSubmenus = [];

        menuItems.forEach(item => {
            const submenu = item.querySelector('.submenu');
            if (!submenu) return;

            let menuTimeout;

            item.addEventListener('mouseenter', () => {
                openSubmenus.forEach(s => { if (s !== submenu) s.style.display = 'none'; });
                clearTimeout(menuTimeout);
                submenu.style.display = 'block';
                if (!openSubmenus.includes(submenu)) openSubmenus.push(submenu);
            });

            item.addEventListener('mouseleave', () => {
                menuTimeout = setTimeout(() => {
                    submenu.style.display = 'none';
                    const index = openSubmenus.indexOf(submenu);
                    if (index > -1) openSubmenus.splice(index, 1);
                }, menuDelay);
            });

            submenu.addEventListener('mouseenter', () => clearTimeout(menuTimeout));
            submenu.addEventListener('mouseleave', () => {
                menuTimeout = setTimeout(() => {
                    submenu.style.display = 'none';
                    const index = openSubmenus.indexOf(submenu);
                    if (index > -1) openSubmenus.splice(index, 1);
                }, menuDelay);
            });
        });
    }

    setupHoverDelay('.menu-bar > .menu-item');
});