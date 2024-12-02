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
            const frontHTML = marked.parse(card.front);


            // Sanitize back content
            let sanitizedBackHTML = card.back.replace(/\xa0/g, ' ');

            // Ensure each list item starts on a new line
            sanitizedBackHTML = sanitizedBackHTML.replace(/(\d+\.)\s*/g, '\n$1 ');

            // Convert markdown to HTML using the marked function
            const backHTML = marked.parse(sanitizedBackHTML);

            cardElement.innerHTML = `
                <div>
                    <p class="font-semibold">Front:</p>
                    <div class="mt-2">${frontHTML}</div>
                </div>
                <div class="mt-4">
                    <p class="font-semibold">Back:</p>
                    <div class="mt-2">${backHTML}</div>
                </div>
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
        const historyData = await response.json();

        let history = historyData.history ? historyData.history : historyData;

        const historyList = document.getElementById('history-list');
        if (!historyList) {
            console.error('History list element not found');
            return;
        }

        // Clear existing history
        historyList.innerHTML = '';

        // Handle empty history case
        if (!history || !Array.isArray(history) || history.length === 0) {
            historyList.innerHTML = `
                <div class="p-4 rounded-md bg-gray-100 text-gray-600 text-center">
                    <p>No flashcard generation history yet.</p>
                    <p class="text-sm mt-2">Generated flashcards will appear here.</p>
                </div>
            `;
            return;
        }

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
            // Get the filename from the Content-Disposition header
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = `flashcards_${taskId}.csv`; // Default fallback
            
            if (contentDisposition) {
                const matches = /filename=(.+)$/.exec(contentDisposition);
                if (matches && matches[1]) {
                    filename = matches[1];
                }
            }

            // Create a blob from the response
            const blob = await response.blob();
            // Create a temporary link element
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
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

    const formData = {
        notion_page: document.getElementById('notionPage').value,
        export_format: document.getElementById('exportFormat').value,
        summary_length: document.getElementById('summaryLength').value,
        use_chatbot: document.getElementById('useChatbot').checked,
        chatbot_type: document.getElementById('useChatbot').checked ? document.getElementById('chatbotType').value : null,
        include_urls: document.getElementById('includeUrls').checked,
        include_toggles: document.getElementById('includeToggles').checked,
        include_bullets: document.getElementById('includeBullets').checked
    };

    const statusDiv = document.getElementById('status');
    const resultDiv = document.getElementById('result');
    const progressSection = document.getElementById('progress-section');
    const downloadSection = document.getElementById('download-section');

    // Reset UI elements
    progressSection.classList.remove('hidden');
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-status').textContent = 'Starting generation...';
    statusDiv.classList.add('hidden');
    resultDiv.classList.add('hidden');
    downloadSection.classList.add('hidden');

    try {
        const response = await fetch('/generate-flashcards/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData),
        });

        const data = await response.json();
        console.log(data);

        if (response.ok) {
            currentTaskId = data.task_id;
            console.log("Task ID received:", currentTaskId);
            socket = connectWebSocket(currentTaskId);
            statusDiv.classList.remove('hidden');
            resultDiv.classList.add('hidden');
            downloadSection.classList.add('hidden');
        } else {
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


const contentOptions = document.querySelectorAll('.content-option');
const selectionMessage = document.getElementById('selection-message');
const generateButton = document.getElementById('generateButton');

// Function to check if at least one checkbox is checked
function checkContentOptions() {
    let isChecked = false;
    contentOptions.forEach(function(checkbox) {
        if (checkbox.checked) {
            isChecked = true;
        }
    });
    if (!isChecked) {
        selectionMessage.classList.remove('hidden');
        generateButton.disabled = true; // Disable the button
    } else {
        selectionMessage.classList.add('hidden');
        generateButton.disabled = false; // Enable the button
    }
}

// Attach the function to the change event of each checkbox
contentOptions.forEach(function(checkbox) {
    checkbox.addEventListener('change', checkContentOptions);
});

// Initial check to set the correct state on page load
checkContentOptions();