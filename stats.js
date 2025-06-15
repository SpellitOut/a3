function timeSince(timestamp) {
    /*
    Calculates the difference in time between timestamp and Date.now()
    */
    const now = Date.now();
    const diffMs = now - timestamp * 1000;
    if (diffMs < 0) return "just now";

    const seconds = Math.floor(diffMs / 1000);
    if (seconds < 60) return seconds + "s ago";

    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + "m ago";

    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + "h ago";

    const days = Math.floor(hours / 24);
    return days + "d ago";
}

function formatTimestamp(timestamp) {
    /*
    Formats the timestamp to be YEAR-MONTH-DAY HH:MM:SS and returns it string formatted
    */
    if (timestamp < 1e12) { //convert to milliseconds
        timestamp = timestamp * 1000;
    }
    var date = new Date(timestamp);
    return date.getFullYear() + '-' +
        String(date.getMonth() + 1).padStart(2, '0') + '-' +
        String(date.getDate()).padStart(2, '0') + ' ' +
        String(date.getHours()).padStart(2, '0') + ':' +
        String(date.getMinutes()).padStart(2, '0') + ':' +
        String(date.getSeconds()).padStart(2, '0');
}

function fetchStats() {
    var xhr = new XMLHttpRequest();
    xhr.onreadystatechange = function() {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status === 200) {
                var data = JSON.parse(xhr.responseText);

                // Update peer id
                document.getElementById('peer-id').textContent = data.peerId

                // Update peer stats
                var peersTableBody = document.getElementById('peers');
                peersTableBody.innerHTML = '';
                data.peers.forEach(function(peer) {
                    var lastSeen = peer.last_seen ? timeSince(peer.last_seen) : "Unknown";     
                    var row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${peer.peerId}</td>
                        <td>${peer.host}</td>
                        <td>${peer.port}</td>
                        <td>${lastSeen}</td>
                    `;
                    peersTableBody.appendChild(row);
                });

                // Update file table
                var tableBody = document.getElementById('files');
                tableBody.innerHTML = '';
                data.files.forEach(function(file) {
                    var row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${file.file_id}</td>
                        <td>${file.file_name}</td>
                        <td>${file.file_owner}</td>
                        <td>${file.file_size}</td>
                        <td>${formatTimestamp(file.file_timestamp)}</td>
                        <td>${file.has_copy ? 'Yes' : 'No'}</td>
                        <td>${file.peers_with_file.join(', ')}</td>
                    `;
                    tableBody.appendChild(row);
                });
            }
        }
    };
    xhr.open('GET', '/stats.json', true);
    xhr.send();
}

setInterval(fetchStats, 5000);
window.onload = fetchStats;
