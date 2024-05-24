import { Feed } from './feed.js';

document.addEventListener('DOMContentLoaded', () => {
    const dvnchatFeed = new Feed('dvnchat');
    const dmxchatFeed = new Feed('dmxchat');

    const refreshTimeSelect = document.getElementById('refresh-time');
    refreshTimeSelect.addEventListener('change', (event) => {
        const interval = event.target.value;
        const socket = io();
        socket.emit('update_interval', { interval });
        alert(`Refresh interval set to ${interval} seconds.`);
    });

    const themeSelect = document.getElementById('theme');
    themeSelect.addEventListener('change', (event) => {
        const selectedTheme = event.target.value;
        document.body.classList.toggle('dark-mode', selectedTheme === 'dark');
    });
});cown