"""
Divya Vaani AI - LLM Engine
Uses Gemini for heavy tasks (summary, explanation) to avoid Groq rate limits.
Uses Groq for fast Q&A responses.
"""
import logging
from groq import AsyncGroq

from config import settings

logger = logging.getLogger(__name__)

_groq_client = None
_gemini_model = None


def get_groq_client() -> AsyncGroq:
    """Get Groq client - used for fast Q&A."""
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        logger.info("✅ Groq client initialized")
    return _groq_client


def get_gemini_model():
    """Get Gemini model - used for summaries and explanations."""
    global _gemini_model
    if _gemini_model is None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            # Use gemini-1.5-flash-latest which has free tier
            _gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
            logger.info("✅ Gemini model initialized (gemini-1.5-flash-latest)")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Gemini: {e}")
            return None
    return _gemini_model


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
    """Generate answer from context using Groq (fast model for low latency)."""
    client = get_groq_client()
    
    lang_instruction = "Respond in Hindi (Devanagari script)." if language == "hi" else "Respond in English."
    
    prompt = f"""CONTEXT ({source_type.value}):
{context}

QUESTION: {question}

{lang_instruction}
Answer based ONLY on the above context. Cite the source."""

    # Use fast model for Q&A (lower latency)
    model = getattr(settings, 'LLM_MODEL_FAST', settings.LLM_MODEL)
    
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS
    )
    
    return response.choices[0].message.content


async def generate_summary(text: str, language: str = "hi") -> str:
    """Generate summary using Gemini (to avoid Groq rate limits)."""
    lang = "Hindi (Devanagari script)" if language == "hi" else "English"
    
    prompt = f"""Summarize this spiritual discourse in {lang}.

Provide:
1. A short paragraph (2-3 sentences) with the main message
2. 3-5 key teachings as bullet points

TRANSCRIPT:
{text[:15000]}"""

    # Try Gemini first (no rate limits like Groq)
    gemini = get_gemini_model()
    if gemini:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: gemini.generate_content(prompt)
            )
            logger.info(f"✅ Summary generated with Gemini ({language})")
            return response.text
        except Exception as e:
            logger.warning(f"Gemini failed, falling back to Groq: {e}")
    
    # Fallback to Groq
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
    """Generate detailed explanation using Gemini (to avoid Groq rate limits)."""
    lang = "Hindi (Devanagari script)" if language == "hi" else "English"
    
    prompt = f"""Analyze this spiritual discourse and explain its deeper purpose in {lang}.

Cover:
1. Main spiritual topic
2. Deeper purpose of this teaching  
3. How should the listener transform?
4. Practical wisdom to take away

Keep the tone spiritual and respectful.

TRANSCRIPT:
{text[:15000]}"""

    # Try Gemini first (no rate limits like Groq)
    gemini = get_gemini_model()
    if gemini:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: gemini.generate_content(prompt)
            )
            logger.info(f"✅ Explanation generated with Gemini ({language})")
            return response.text
        except Exception as e:
            logger.warning(f"Gemini failed, falling back to Groq: {e}")
    
    # Fallback to Groq
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
