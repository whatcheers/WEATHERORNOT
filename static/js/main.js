import { Feed } from './feed.js';

document.addEventListener('DOMContentLoaded', () => {
    const leftchatFeed = new Feed('leftchat');
    const rightchatFeed = new Feed('rightchat');

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
        const testSoundImage = document.getElementById('test-sound-image');
        document.body.classList.toggle('dark-mode', selectedTheme === 'dark');
    if (selectedTheme === 'dark') {
        testSoundImage.src = 'static/images/soundtest_modedark.png'; // Change to dark mode image
    } else {
        testSoundImage.src = 'static/images/soundtest_modelight.png'; // Change to default/light mode image
    }

    // Save the selected theme in a cookie by sending a request to Flask
    fetch(`/set_mode/${selectedTheme}`)
        .then(response => {
        if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.text();
        })
        .then(data => {
            console.log(data);
        })
        .catch(error => {
            console.error('There was a problem with the fetch operation:', error);
        });
    });

    const testMySound = document.getElementById('test-sound-image');
    testMySound.addEventListener('click', () => {
        const sound = document.getElementById('notification-sound');
        sound.play().catch(error => {
            console.error('Error playing notification sound:', error);
        });
    });
});