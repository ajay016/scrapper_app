// Use module.exports instead of export
module.exports.loadPage = async function(pageContentElement, pageName) {
    try {
        const response = await fetch(`pages/${pageName}.html`);
        const html = await response.text();
        pageContentElement.innerHTML = html;

        try {
            const pageModule = require(`./${pageName}.js`);
            if (pageModule.init) pageModule.init();
        } catch (err) {
            console.warn(`No JS module for page ${pageName}`, err);
        }
    } catch (err) {
        console.error('Failed to load page:', err);
    }
};