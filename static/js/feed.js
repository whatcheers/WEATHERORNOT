export class Feed {
    constructor(feedName) {
        this.feedName = feedName;
        this.currentPage = 1;
        this.lastUpdateTime = null;
        this.feedElement = document.getElementById(`feed-${feedName}`);
        this.prevPageButton = document.getElementById(`prevPage-${feedName}`);
        this.nextPageButton = document.getElementById(`nextPage-${feedName}`);
        this.lastUpdateTimeElement = document.getElementById(`last-update-time-${feedName}`);
        this.countdownElement = document.getElementById(`countdown-${feedName}`);
        this.notificationSound = document.getElementById('notification-sound');
        this.originalTitle = document.title;
        this.flashingInterval = null;
        this.countdownSinceRefreshElement = document.getElementById('countdown-since-refresh');

        this.prevPageButton.addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.fetchFeed();
            }
        });

        this.nextPageButton.addEventListener('click', () => {
            this.currentPage++;
            this.fetchFeed();
        });

        this.socket = io();
        this.socket.on(`update_feed_${this.feedName}`, (data) => {
            const newItems = data.items.filter(item => !this.isItemExists(item));

            if (newItems.length > 0) {
                this.lastUpdateTime = new Date(data.last_update_time);
                this.lastUpdateTimeElement.textContent = this.formatDateTime(this.lastUpdateTime);
                this.playNotification();
                this.flashTitle(`New items in ${this.feedName}`);
            }

            this.fetchFeed();
        });

        this.fetchFeed();
        this.updateCountdown();
        setInterval(() => this.updateCountdown(), 1000);
        this.updateCountdownSinceRefresh();
        setInterval(() => this.updateCountdownSinceRefresh(), 1000);
    }

    fetchFeed() {
        fetch(`/feed/${this.feedName}?page=${this.currentPage}`)
            .then(response => response.json())
            .then(data => {
                const newItems = data.items.filter(item => !this.isItemExists(item));

                this.feedElement.innerHTML = '';
                data.items.forEach(item => {
                    const itemElement = document.createElement('div');
                    itemElement.className = 'item';

                    const parsedTitle = this.parseTitle(item.title);
                    const summaryTable = this.createSummaryTable(item.description);

                    itemElement.innerHTML = `
                        <h2><a href="${item.link}" target="_blank">${parsedTitle}</a></h2>
                        ${summaryTable}
                        <p><small>${item.pub_date}</small></p>
                    `;
                    this.feedElement.appendChild(itemElement);
                });

                // Update pagination buttons
                this.prevPageButton.classList.toggle('disabled', this.currentPage === 1);
                this.nextPageButton.classList.toggle('disabled', this.currentPage * 10 >= data.total);
            })
            .catch(error => {
                console.error('Error fetching feed:', error);
            });
    }

    isItemExists(item) {
        const existingItems = this.feedElement.getElementsByTagName('a');
        for (let i = 0; i < existingItems.length; i++) {
            if (existingItems[i].href === item.link) {
                return true;
            }
        }
        return false;
    }

    parseTitle(title) {
        // Remove the product code (e.g., WUUS53 KDVN 240911)
        title = title.replace(/^[A-Z]{4}\d{1,2}\s[A-Z]{4}\s\d{6}\s?/, '');

        // Remove the priority level (e.g., Immediate Broadcast Requested)
        title = title.replace(/Immediate Broadcast Requested\s?/, '');

        // Remove the alert type (e.g., Severe Thunderstorm Warning)
        title = title.replace(/Severe Thunderstorm Warning\s?/, '');

        // Capitalize the first letter of the title
        title = title.charAt(0).toUpperCase() + title.slice(1);

        return title;
    }

    createSummaryTable(description) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(description, 'text/html');
        const preElement = doc.querySelector('pre');
        const alertText = preElement ? preElement.textContent : '';

        const summaryData = {
            'Hazard': this.extractValue(alertText, 'HAZARD...'),
            'Source': this.extractValue(alertText, 'SOURCE...'),
            'Impact': this.extractValue(alertText, 'IMPACT...'),
            'Hail Size': this.extractValue(alertText, 'MAX HAIL SIZE...'),
            'Wind Gust': this.extractValue(alertText, 'MAX WIND GUST...'),
        };

        let tableHtml = '<table class="summary-table">';
        for (const [key, value] of Object.entries(summaryData)) {
            if (value) {
                tableHtml += `
                    <tr>
                        <td>${key}</td>
                        <td class="tooltip">${value}
                            <span class="tooltip-text">${value}</span>
                        </td>
                    </tr>
                `;
            }
        }
        tableHtml += '</table>';

        return tableHtml;
    }

    extractValue(text, key) {
        const regex = new RegExp(`${key}(.+)`);
        const match = text.match(regex);
        return match ? match[1].trim() : '';
    }

    updateCountdown() {
        if (this.lastUpdateTime) {
            const now = new Date();
            const diff = now - this.lastUpdateTime;
            const seconds = Math.floor(diff / 1000);
            const minutes = Math.floor(seconds / 60);
            const hours = Math.floor(minutes / 60);
            const days = Math.floor(hours / 24);

            let countdownText = '';
            if (days > 0) {
                countdownText += `${days}d `;
            }
            if (hours % 24 > 0) {
                countdownText += `${hours % 24}h `;
            }
            if (minutes % 60 > 0) {
                countdownText += `${minutes % 60}m `;
            }
            countdownText += `${seconds % 60}s ago`;

            this.countdownElement.textContent = countdownText;
        } else {
            this.countdownElement.textContent = 'No updates yet';
        }
    }

    formatDateTime(dateTime) {
        const options = {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: 'numeric',
            second: 'numeric',
            timeZoneName: 'short'
        };
        return dateTime.toLocaleString(undefined, options);
    }

    playNotification() {
        this.notificationSound.play().catch(error => {
            console.error('Error playing notification sound:', error);
        });
    }

    flashTitle(message) {
        let isOriginalTitle = true;
        if (this.flashingInterval) {
            clearInterval(this.flashingInterval);
        }
        this.flashingInterval = setInterval(() => {
            document.title = isOriginalTitle ? message : this.originalTitle;
            isOriginalTitle = !isOriginalTitle;
        }, 1000);
        setTimeout(() => {
            clearInterval(this.flashingInterval);
            document.title = this.originalTitle;
        }, 10000); // Stop flashing after 10 seconds
    }

    updateCountdownSinceRefresh() {
        if (this.lastUpdateTime) {
            const now = new Date();
            const diff = now - this.lastUpdateTime;
            const seconds = Math.floor(diff / 1000);
            this.countdownSinceRefreshElement.textContent = `(Last refresh: ${seconds}s ago)`;
        } else {
            this.countdownSinceRefreshElement.textContent = '(No refresh yet)';
        }
    }
}