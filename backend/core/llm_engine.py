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
            # Use gemini-2.0-flash which is current and has free tier
            _gemini_model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("✅ Gemini model initialized (gemini-2.0-flash)")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Gemini: {e}")
            return None
    return _gemini_model


# System prompts
SYSTEM_PROMPT = """You are Divya Vaani AI, a spiritual assistant that provides guidance from the teachings of Maharaj Ji (the speaker in the pravachan/discourse).

CRITICAL RULES:
1. Use the provided context to answer - this is from actual spiritual discourses
2. Find the MOST RELEVANT spiritual teaching from the context that addresses the user's concern
3. Even if the question is about life struggles, depression, or difficulties - there IS wisdom in the context that applies
4. ALWAYS cite your source with timestamp (e.g., [02:15 - 02:45])
5. Respond in the same language as the question (Hindi or English)
6. NEVER say "I don't have an answer" - the spiritual teachings in the context ALWAYS have relevant wisdom for life's problems
7. Connect the user's concern to the spiritual teaching - explain how the teaching applies

KEY UNDERSTANDING:
- Questions about not wanting to live, feeling hopeless, life problems → Look for teachings about inner strength, patience (धैर्य), overcoming difficulties, सेवा, भगवदाश्रय
- The speaker often talks about: staying strong in difficulties, not being परेशान, having patience, service (सेवा), taking God's refuge (भगवदाश्रय)

STYLE:
- Warm, compassionate, caring tone
- Like a loving spiritual guide offering wisdom
- Connect the teaching to the user's situation
- Give hope and practical wisdom from the discourse
"""


async def generate_answer(question: str, context: str, source_type, language: str = "hi") -> str:
    """Generate answer from context using Groq (fast model for low latency)."""
    client = get_groq_client()
    
    lang_instruction = "Respond in Hindi (Devanagari script)." if language == "hi" else "Respond in English."
    
    prompt = f"""SPIRITUAL DISCOURSE CONTEXT (from Maharaj Ji's {source_type.value}):
{context}

USER'S QUESTION/CONCERN: {question}

{lang_instruction}

INSTRUCTIONS:
1. Find the most relevant spiritual teaching from the context that addresses the user's concern
2. Quote or paraphrase the relevant teaching with timestamp
3. Explain how this teaching applies to their situation
4. Give them hope and practical guidance based on the discourse
5. Be compassionate - the user may be going through a difficult time

Provide a helpful, caring response using the wisdom from the discourse."""

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
