/**
 * Divya Vaani AI - API Service
 * Frontend API calls to backend
 */

const API_BASE = '/api';

/**
 * Upload audio/video file for transcription
 */
export async function uploadFile(file, onProgress) {
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
        headers: {
            'Content-Type': 'application/json',
        },
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
        body: JSON.stringify({ text, language }),
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
    const response = await fetch(`${API_BASE}/health`);
    if (!response.ok) throw new Error('Health check failed');
    return response.json();
}

// Legacy API compatibility - map old names to new ones
export const getSessions = getTranscripts;
export const getSession = getTranscript;
export const getUploadStatus = getTranscript;
