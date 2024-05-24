export function parseTitle(title) {
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

export function createSummaryTable(description) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(description, 'text/html');
    const preElement = doc.querySelector('pre');
    const alertText = preElement ? preElement.textContent : '';

    const summaryData = {
        'Hazard': extractValue(alertText, 'HAZARD...'),
        'Source': extractValue(alertText, 'SOURCE...'),
        'Impact': extractValue(alertText, 'IMPACT...'),
        'Hail Size': extractValue(alertText, 'MAX HAIL SIZE...'),
        'Wind Gust': extractValue(alertText, 'MAX WIND GUST...'),
        'Locations': extractLocations(alertText),
        'Time': extractTime(alertText),
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

function extractValue(text, key) {
    const regex = new RegExp(`${key}(.+)`);
    const match = text.match(regex);
    return match ? match[1].trim() : '';
}

function extractLocations(text) {
    const regex = /\*\sLocations impacted include\.\.\.(.+)/s;
    const match = text.match(regex);
    return match ? match[1].trim() : '';
}

function extractTime(text) {
    const regex = /till (.+)$/;
    const match = text.match(regex);
    return match ? match[1].trim() : '';
}