let currentTaskId = null;
let socket = null;

function connectWebSocket(taskId) {
    if (socket) {
        socket.close();
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${taskId}`;
    console.log("Connecting to WebSocket:", wsUrl);
    
    socket = new WebSocket(wsUrl);
    
    socket.onopen = function() {
        console.log("WebSocket connection established");
    };
    
    socket.onmessage = function(event) {
        console.log("WebSocket message received:", event.data);
        const data = JSON.parse(event.data);
        updateProgress(data);
    };
    
    socket.onerror = function(error) {
        console.error("WebSocket error:", error);
    };
    
    socket.onclose = function(event) {
        console.log("WebSocket connection closed:", event);
    };
    
    return socket;
}

// Function to update progress
function updateProgress(data) {
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const statusDiv = document.getElementById('status');
    const resultDiv = document.getElementById('result');

    // Hide the status spinner once we start getting progress
    statusDiv.classList.add('hidden');

    progressBar.style.width = `${data.progress}%`;
    progressStatus.textContent = data.message;

    if (data.status === 'completed' || data.status === 'completed_with_errors' || data.status === 'failed') {
        showDownloadButton();
        loadPreview();
        loadHistory();
        socket.close();

        // Clear progress status message
        progressStatus.textContent = '';

        // Show result message
        resultDiv.querySelector('p').textContent = data.message;
        if (data.status === 'completed') {
            resultDiv.querySelector('div').className = 'p-4 rounded-md bg-green-100 text-green-700';
        } else if (data.status === 'completed_with_errors') {
            resultDiv.querySelector('div').className = 'p-4 rounded-md bg-yellow-100 text-yellow-700';
        } else if (data.status === 'failed') {
            resultDiv.querySelector('div').className = 'p-4 rounded-md bg-red-100 text-red-700';
        }
        resultDiv.classList.remove('hidden');
    }
}

// Function to show download button
function showDownloadButton() {
    const downloadSection = document.getElementById('download-section');
    downloadSection.classList.remove('hidden');
}

// Function to load preview
async function loadPreview() {
    if (!currentTaskId) return;

    try {
        const response = await fetch(`/preview-flashcards/${currentTaskId}`);
        const cards = await response.json();

        const previewSection = document.getElementById('preview-section');
        const previewCards = document.getElementById('preview-cards');
        previewCards.innerHTML = '';

        cards.forEach(card => {
            const cardElement = document.createElement('div');
            cardElement.className = 'border rounded-md p-4';
            cardElement.innerHTML = `
                <p class="font-semibold">Front: ${card.front}</p>
                <p class="mt-2">Back: ${card.back}</p>
            `;
            previewCards.appendChild(cardElement);
        });

        previewSection.classList.remove('hidden');
    } catch (error) {
        console.error('Error loading preview:', error);
    }
}

// Function to load history
async function loadHistory() {
    try {
        const response = await fetch('/generation-history');
        const history = await response.json();

        const historyList = document.getElementById('history-list');
        if (!historyList) {
            console.error('History list element not found');
            return;
        }

        // Clear existing history
        historyList.innerHTML = '';

        // Sort history by timestamp in descending order
        const sortedHistory = history.sort((a, b) => 
            new Date(b.timestamp) - new Date(a.timestamp)
        );

        sortedHistory.forEach(item => {
            const historyItem = document.createElement('div');
            historyItem.className = 'border rounded-md p-4 hover:shadow-md transition-shadow duration-200';
            
            // Format the timestamp to be more readable
            const formattedDate = new Date(item.timestamp).toLocaleString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });

            historyItem.innerHTML = `
                <div class="flex justify-between items-start">
                    <div>
                        <p class="font-semibold break-all">
                            <a href="${item.notion_page}" target="_blank" rel="noopener noreferrer">
                                ${item.notion_page}
                            </a>
                        </p>
                        <p class="text-sm text-gray-600 mt-1">${formattedDate}</p>
                        <p class="text-sm mt-1">
                            <span class="px-2 py-1 rounded ${
                                item.status === 'completed' ? 'bg-green-100 text-green-800' :
                                item.status === 'completed_with_errors' ? 'bg-yellow-100 text-yellow-800' :
                                'bg-red-100 text-red-800'
                            }">
                                ${item.status.charAt(0).toUpperCase() + item.status.slice(1)}
                            </span>
                        </p>
                    </div>
                    ${item.status !== 'failed' ? `
                        <button 
                            onclick="downloadFlashcards('${item.task_id}')"
                            class="ml-4 py-1 px-3 text-sm text-white bg-indigo-600 hover:bg-indigo-700 rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2">
                            Download
                        </button>
                    ` : ''}
                </div>
            `;
            historyList.appendChild(historyItem);
        });
    } catch (error) {
        console.error('Error loading history:', error);
        // Show error message to user
        const historyList = document.getElementById('history-list');
        if (historyList) {
            historyList.innerHTML = `
                <div class="p-4 rounded-md bg-red-100 text-red-700">
                    Failed to load history. Please try refreshing the page.
                </div>
            `;
        }
    }
}

// Function to download flashcards
async function downloadFlashcards(taskId) {
    try {
        const response = await fetch(`/download/${taskId}`);
        if (response.ok) {
            // Create a blob from the response
            const blob = await response.blob();
            // Create a temporary link element
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `flashcards_${taskId}.csv`;
            document.body.appendChild(a);
            a.click();
            // Cleanup
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } else {
            console.error('Download failed:', await response.text());
        }

    } catch (error) {
        console.error('Error downloading flashcards:', error);
    }
}

// Main form submission handler
document.getElementById('flashcardForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const notionPage = document.getElementById('notionPage').value;
    const useChatbot = document.getElementById('useChatbot').checked;
    const chatbotType = useChatbot ? document.getElementById('chatbotType').value : null;
    const statusDiv = document.getElementById('status');
    const resultDiv = document.getElementById('result');
    const progressSection = document.getElementById('progress-section');
    const downloadSection = document.getElementById('download-section');

    // Reset UI elements
    progressSection.classList.remove('hidden');
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-status').textContent = 'Starting generation...';
    // Show loading status
    statusDiv.classList.add('hidden');
    resultDiv.classList.add('hidden');
    downloadSection.classList.add('hidden'); // Hide download button when starting new generation

    try {
        const response = await fetch('/generate-flashcards/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                notion_page: notionPage,
                use_chatbot: useChatbot,
                chatbot_type: chatbotType
            }),
        });

        const data = await response.json();

        if (response.ok) {
            currentTaskId = data.task_id;
            console.log("Task ID received:", currentTaskId);

            // Connect to WebSocket for real-time updates
            socket = connectWebSocket(currentTaskId);

            // Show loading status
            statusDiv.classList.remove('hidden');
            resultDiv.classList.add('hidden');
            downloadSection.classList.add('hidden');
        } else {
            // Handle error responses from the server
            statusDiv.classList.add('hidden');
            resultDiv.classList.remove('hidden');
            if (response.status === 429) {
                resultDiv.querySelector('p').textContent = data.error;
            } else {
                resultDiv.querySelector('p').textContent = `Error: ${data.detail}`;
            }
            resultDiv.querySelector('div').className = 'p-4 rounded-md bg-red-100 text-red-700';
        }
    } catch (error) {
        statusDiv.classList.add('hidden');
        resultDiv.classList.remove('hidden');
        resultDiv.querySelector('p').textContent = `Error: ${error.message}`;
        resultDiv.querySelector('div').className = 'p-4 rounded-md bg-red-100 text-red-700';
    }
});

document.getElementById('useChatbot').addEventListener('change', function(e) {
    const chatbotTypeContainer = document.getElementById('chatbotTypeContainer');
    const chatbotTypeSelect = document.getElementById('chatbotType');
    
    if (e.target.checked) {
        chatbotTypeContainer.classList.remove('hidden');
        chatbotTypeSelect.disabled = false;
        chatbotTypeSelect.required = true;
    } else {
        chatbotTypeContainer.classList.add('hidden');
        chatbotTypeSelect.disabled = true;
        chatbotTypeSelect.required = false;
    }
});

// Load history on page load
document.addEventListener('DOMContentLoaded', () => {
    loadHistory();
});

// Download button click handler
document.getElementById('download-btn').addEventListener('click', () => {
    if (currentTaskId) {
        downloadFlashcards(currentTaskId);
    }
});