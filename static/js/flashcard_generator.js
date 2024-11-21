let currentTaskId = null;
let socket = null;

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

    if (data.status === 'completed') {
        showDownloadButton();
        loadPreview();
        loadHistory();
        socket.close();

        // Show completion message
        resultDiv.querySelector('p').textContent = "Flashcard generation completed successfully!";
        resultDiv.querySelector('div').className = 'p-4 rounded-md bg-green-100 text-green-700';
        resultDiv.classList.remove('hidden');
    } else if (data.status === 'failed') {
        progressStatus.textContent = `Error: ${data.message}`;

        // Show error message
        resultDiv.querySelector('p').textContent = `Error: ${data.message}`;
        resultDiv.querySelector('div').className = 'p-4 rounded-md bg-red-100 text-red-700';
        resultDiv.classList.remove('hidden');

        socket.close();
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
        historyList.innerHTML = '';

        history.forEach(item => {
            const historyItem = document.createElement('div');
            historyItem.className = 'border rounded-md p-4';
            historyItem.innerHTML = `
                <p class="font-semibold">Page ID: ${item.notion_page_id}</p>
                <p class="text-sm text-gray-600">Generated: ${new Date(item.timestamp).toLocaleString()}</p>
                <p class="text-sm">Status: ${item.status}</p>
                <button onclick="downloadFlashcards('${item.task_id}')" 
                        class="mt-2 py-1 px-3 text-sm text-white bg-indigo-600 hover:bg-indigo-700 rounded">
                    Download
                </button>
            `;
            historyList.appendChild(historyItem);
        });
    } catch (error) {
        console.error('Error loading history:', error);
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

    const notionPageId = document.getElementById('notionPageId').value;
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
                notion_page_id: notionPageId,
                use_chatbot: useChatbot,
                chatbot_type: chatbotType
            }),
        });

        const data = await response.json();

        if (response.ok) {
            currentTaskId = data.task_id;
            console.log("Task ID received:", currentTaskId);

            // Connect to WebSocket for real-time updates
            socket = new WebSocket(`ws://${window.location.host}/ws/${currentTaskId}`);
            socket.onmessage = function(event) {
                const data = JSON.parse(event.data);
                updateProgress(data);
            };

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