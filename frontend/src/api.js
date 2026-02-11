/**
 * Divya Vaani AI - API Service
 * Frontend API calls to backend
 */

const API_BASE = '/api';

// ========== Auth Header Helper ==========

function authHeaders(extraHeaders = {}) {
    const headers = { ...extraHeaders };
    const token = localStorage.getItem('dv_access_token');
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

// ========== Video Content APIs ==========

/**
 * Get all pre-loaded videos for the home page
 */
export async function getVideos() {
    const response = await fetch(`${API_BASE}/videos`, { headers: authHeaders() });
    if (!response.ok) throw new Error('Failed to get videos');
    return response.json();
}

/**
 * Get full video content (transcript, summary, explanation)
 * @param {string} videoId - The video ID
 * @param {string} language - Language for content ("hi" or "en")
 */
export async function getVideo(videoId, language = 'hi') {
    const response = await fetch(`${API_BASE}/videos/${videoId}?language=${language}`, {
        headers: authHeaders(),
    });
    if (!response.ok) {
        if (response.status === 404) throw new Error('Video not found');
        throw new Error('Failed to get video');
    }
    return response.json();
}

/**
 * Get video thumbnail URL
 */
export function getThumbnailUrl(videoId) {
    return `${API_BASE}/thumbnail/${videoId}`;
}

/**
 * Request summary generation for a video
 * @param {string} videoId - The video ID
 */
export async function generateVideoSummary(videoId) {
    const response = await fetch(`${API_BASE}/videos/${videoId}/generate-summary`, {
        method: 'POST',
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to generate summary');
    }
    return response.json();
}

// ========== Legacy Upload APIs (kept for admin use) ==========

/**
 * Upload audio/video file for transcription
 */
export async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
    }

    return response.json();
}

/**
 * Get transcript status and content
 * @param {string} transcriptId - The transcript/file ID
 * @param {string} language - Language for summary/explanation ("hi" or "en")
 */
export async function getTranscript(transcriptId, language = 'hi') {
    const response = await fetch(`${API_BASE}/transcript/${transcriptId}?language=${language}`);
    if (!response.ok) {
        if (response.status === 404) throw new Error('Transcript not found');
        throw new Error('Failed to get transcript');
    }
    return response.json();
}

/**
 * List all transcripts
 */
export async function getTranscripts() {
    const response = await fetch(`${API_BASE}/transcripts`);
    if (!response.ok) throw new Error('Failed to get transcripts');
    return response.json();
}

/**
 * Send a chat message / ask a question
 * @param {string} question - The question to ask
 * @param {string} transcriptId - Optional transcript ID to search within
 * @param {string} language - Response language ("hi" or "en")
 */
export async function sendMessage(question, transcriptId = null, language = 'hi') {
    const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            question,
            transcript_id: transcriptId,
            language
        }),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to get answer');
    }

    return response.json();
}

/**
 * Transcribe voice input
 * @param {Blob} audioBlob - Audio blob from recording
 */
export async function transcribeVoice(audioBlob) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'voice.webm');

    const response = await fetch(`${API_BASE}/transcribe-voice`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Voice transcription failed');
    }

    return response.json();
}

/**
 * Generate text-to-speech audio
 * @param {string} text - Text to convert to speech
 * @param {string} language - Language ("hi" or "en")
 */
export async function textToSpeech(text, language = 'hi') {
    const response = await fetch(`${API_BASE}/tts`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text, language, gender: 'male' }),
    });

    if (!response.ok) {
        throw new Error('TTS generation failed');
    }

    return response.json();
}

/**
 * Get audio file URL
 */
export function getAudioUrl(filename) {
    return `${API_BASE}/audio/${filename}`;
}

/**
 * Health check
 */
export async function healthCheck() {
    const response = await fetch('/health');
    if (!response.ok) throw new Error('Health check failed');
    return response.json();
}

// ========== Favorites APIs ==========

/**
 * Get user's favorite video IDs
 */
export async function getFavorites() {
    const response = await fetch(`${API_BASE}/user/favorites`, {
        headers: authHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get favorites');
    return response.json();
}

/**
 * Add a video to favorites
 */
export async function addFavorite(videoId) {
    const response = await fetch(`${API_BASE}/user/favorites/${videoId}`, {
        method: 'POST',
        headers: authHeaders(),
    });
    if (!response.ok) throw new Error('Failed to add favorite');
    return response.json();
}

/**
 * Remove a video from favorites
 */
export async function removeFavorite(videoId) {
    const response = await fetch(`${API_BASE}/user/favorites/${videoId}`, {
        method: 'DELETE',
        headers: authHeaders(),
    });
    if (!response.ok) throw new Error('Failed to remove favorite');
    return response.json();
}

// ========== Chat History APIs ==========

/**
 * Get list of videos user has chatted with
 */
export async function getChatHistoryVideos() {
    const response = await fetch(`${API_BASE}/user/chat-history`, {
        headers: authHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get chat history');
    return response.json();
}

/**
 * Get chat messages for a specific video
 */
export async function getChatHistory(videoId) {
    const response = await fetch(`${API_BASE}/user/chat-history/${videoId}`, {
        headers: authHeaders(),
    });
    if (!response.ok) throw new Error('Failed to get chat history');
    return response.json();
}

/**
 * Clear chat history for a video
 */
export async function clearChatHistoryApi(videoId) {
    const response = await fetch(`${API_BASE}/user/chat-history/${videoId}`, {
        method: 'DELETE',
        headers: authHeaders(),
    });
    if (!response.ok) throw new Error('Failed to clear chat history');
    return response.json();
}

