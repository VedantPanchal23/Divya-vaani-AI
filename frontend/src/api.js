/**
 * Divya Vaani AI - API Service
 * Frontend API calls to backend
 */

const API_BASE = '/api';

// ========== Video Content APIs ==========

/**
 * Get all pre-loaded videos for the home page
 */
export async function getVideos() {
    const response = await fetch(`${API_BASE}/videos`);
    if (!response.ok) throw new Error('Failed to get videos');
    return response.json();
}

/**
 * Get full video content (transcript, summary, explanation)
 * Returns both Hindi and English variants in a single call.
 * @param {string} videoId - The video ID
 * @param {string} language - Primary language ("hi" or "en")
 */
export async function getVideo(videoId, language = 'hi') {
    const response = await fetch(`${API_BASE}/videos/${videoId}?language=${language}`);
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

// ========== Chat / Q&A ==========

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

// ========== Admin APIs ==========

/**
 * Submit a YouTube URL for processing
 * @param {string} url - YouTube URL
 * @param {string} speaker - Speaker name
 * @param {string} category - Video category
 */
export async function addYouTubeVideo(url, speaker = 'Maharaj Ji', category = 'pravachan') {
    const response = await fetch(`${API_BASE}/admin/youtube`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, speaker, category }),
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to add video');
    }
    return response.json();
}

/**
 * Get YouTube processing job status
 * @param {string} jobId - The job ID
 */
export async function getYouTubeJobStatus(jobId) {
    const response = await fetch(`${API_BASE}/admin/youtube/${jobId}`);
    if (!response.ok) throw new Error('Failed to get job status');
    return response.json();
}

/**
 * List all YouTube processing jobs
 */
export async function listYouTubeJobs() {
    const response = await fetch(`${API_BASE}/admin/youtube`);
    if (!response.ok) throw new Error('Failed to list jobs');
    return response.json();
}

/**
 * Delete a video
 * @param {string} videoId - Video ID to delete
 */
export async function deleteVideo(videoId) {
    const response = await fetch(`${API_BASE}/admin/videos/${videoId}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to delete video');
    }
    return response.json();
}

/**
 * Regenerate summary & explanation for a video
 * @param {string} videoId - Video ID
 */
export async function regenerateVideoContent(videoId) {
    const response = await fetch(`${API_BASE}/admin/videos/${videoId}/regenerate`, {
        method: 'POST',
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to regenerate');
    }
    return response.json();
}
