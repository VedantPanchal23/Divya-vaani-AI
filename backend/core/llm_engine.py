"""
Divya Vaani AI - LLM Engine
Uses Groq for ALL LLM tasks (fast + reliable).
"""
import logging
from groq import AsyncGroq

from config import settings

logger = logging.getLogger(__name__)

_groq_client = None


def get_groq_client() -> AsyncGroq:
    """Get Groq client - used for all LLM tasks."""
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        logger.info("✅ Groq client initialized")
    return _groq_client


# System prompts
SYSTEM_PROMPT = """You are Divya Vaani AI, a spiritual assistant that provides guidance ONLY from the given context.

CRITICAL RULES:
1. ONLY use information from the provided context
2. NEVER use your own knowledge or make up information
3. ALWAYS cite your source (timestamp for Pravachan, chapter:verse for Gita)
4. If context is insufficient, say honestly that you don't have the answer
5. Respond in the same language as the question (Hindi or English)

STYLE:
- Calm, respectful, spiritual tone
- Simple language, not academic
- Like a wise guide explaining to a seeker
"""


async def generate_answer(question: str, context: str, source_type, language: str = "hi") -> str:
    """Generate answer from context using Groq."""
    client = get_groq_client()
    
    lang_instruction = "Respond in Hindi (Devanagari script)." if language == "hi" else "Respond in English."
    
    prompt = f"""CONTEXT ({source_type.value}):
{context}

QUESTION: {question}

{lang_instruction}
Answer based ONLY on the above context. Cite the source."""

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS
    )
    
    return response.choices[0].message.content


async def generate_summary(text: str, language: str = "hi") -> str:
    """Generate summary using Groq."""
    lang = "Hindi (Devanagari script)" if language == "hi" else "English"
    
    prompt = f"""Summarize this spiritual discourse in {lang}.

Provide:
1. A short paragraph (2-3 sentences) with the main message
2. 3-5 key teachings as bullet points

TRANSCRIPT:
{text[:12000]}"""

    client = get_groq_client()
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": "You are a spiritual discourse summarizer."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1000
    )
    
    return response.choices[0].message.content


async def generate_explanation(text: str, language: str = "hi") -> str:
    """Generate detailed explanation using Groq."""
    lang = "Hindi (Devanagari script)" if language == "hi" else "English"
    
    prompt = f"""Analyze this spiritual discourse and explain its deeper purpose in {lang}.

Cover:
1. Main spiritual topic
2. Deeper purpose of this teaching  
3. How should the listener transform?
4. Practical wisdom to take away

Keep the tone spiritual and respectful.

TRANSCRIPT:
{text[:12000]}"""

    client = get_groq_client()
    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": "You are a spiritual discourse analyst."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1500
    )
    
    return response.choices[0].message.content


async def generate_not_found(language: str = "hi") -> str:
    """Generate 'not found' response."""
    if language == "hi":
        return "मुझे खेद है, इस प्रश्न का उत्तर उपलब्ध स्रोतों में नहीं मिला। कृपया कोई अन्य प्रश्न पूछें।"
    return "I'm sorry, I couldn't find an answer to this question in the available sources. Please ask another question."
