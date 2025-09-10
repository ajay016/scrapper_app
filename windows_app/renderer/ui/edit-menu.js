document.addEventListener('DOMContentLoaded', function () {
    const editActions = [
        { id: 'undo-btn', command: 'undo' },
        { id: 'redo-btn', command: 'redo' },
        { id: 'cut-btn', command: 'cut' },
        { id: 'copy-btn', command: 'copy' },
        { id: 'paste-btn', command: 'paste' },
        { id: 'delete-btn', command: 'delete' },
        { id: 'selectall-btn', command: 'selectAll' }
    ];

    editActions.forEach(action => {
        const el = document.getElementById(action.id);
        if (el) {
            el.addEventListener('click', () => document.execCommand(action.command));
        }
    });
});