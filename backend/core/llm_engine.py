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
_gemini_client = None


def get_groq_client() -> AsyncGroq:
    """Get Groq client - used for fast Q&A."""
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        logger.info("✅ Groq client initialized")
    return _groq_client


def get_gemini_client():
    """Get Gemini client - used for summaries and explanations."""
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("✅ Gemini client initialized (google-genai, gemini-2.0-flash)")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Gemini: {e}")
            return None
    return _gemini_client


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

DO NOT:
- Start with "प्रिय भाई/बहन", "Dear friend", or any personal greeting
- Use second person address like "तुम्हारी समस्या", "आपकी परेशानी"
- Start by addressing the person directly

DO:
- Start directly with the relevant teaching or "महाराज जी ने कहा है..."
- Present the wisdom and then explain its meaning
- Be warm and compassionate in explanation
"""


async def generate_answer(question: str, context: str, source_type, language: str = "hi") -> str:
    """Generate answer from context using Groq (fast model for low latency)."""
    try:
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
    except Exception as e:
        logger.error(f"❌ generate_answer failed: {e}")
        if language == "hi":
            return "क्षमा करें, उत्तर देने में एक तकनीकी समस्या आई। कृपया पुनः प्रयास करें।"
        return "Sorry, there was a technical issue generating the answer. Please try again."


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
    gemini = get_gemini_client()
    if gemini:
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: gemini.models.generate_content(
                    model='gemini-2.0-flash', contents=prompt
                )
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
    gemini = get_gemini_client()
    if gemini:
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: gemini.models.generate_content(
                    model='gemini-2.0-flash', contents=prompt
                )
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


async def generate_gita_answer(question: str, verses: list, language: str = "hi") -> str:
    """Generate answer from Bhagavad Gita verses."""
    try:
        client = get_groq_client()
        
        # Build context from Gita verses
        context_parts = []
        for v in verses:
            verse_text = f"""📖 अध्याय {v['verse'].chapter}, श्लोक {v['verse'].verse}
संस्कृत: {v['verse'].sanskrit}
अर्थ (हिंदी): {v['verse'].hindi}
Meaning (English): {v['verse'].english}"""
            context_parts.append(verse_text)
        
        context = "\n\n---\n\n".join(context_parts)
        
        lang_instruction = "Respond in Hindi (Devanagari script)." if language == "hi" else "Respond in English."
        
        prompt = f"""BHAGAVAD GITA VERSES:
{context}

USER'S QUESTION: {question}

{lang_instruction}

INSTRUCTIONS:
1. This question was not found in Maharaj Ji's discourses, so we are using Bhagavad Gita wisdom
2. Reference the relevant Gita verse (chapter and verse number) 
3. Explain how this eternal wisdom from Lord Krishna applies to their situation
4. Keep the tone spiritual, compassionate and practical
5. Don't start with greetings - directly address their question with the Gita's wisdom

Provide a helpful response using the wisdom from Bhagavad Gita."""

        model = getattr(settings, 'LLM_MODEL_FAST', settings.LLM_MODEL)
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a spiritual guide who explains Bhagavad Gita's eternal wisdom. You help seekers understand Lord Krishna's teachings and apply them to modern life challenges."},
                {"role": "user", "content": prompt}
            ],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ generate_gita_answer failed: {e}")
        if language == "hi":
            return "क्षमा करें, भगवद्गीता से उत्तर देने में एक तकनीकी समस्या आई। कृपया पुनः प्रयास करें।"
        return "Sorry, there was a technical issue generating the answer from Bhagavad Gita. Please try again."


async def generate_not_found(language: str = "hi") -> str:
    """Generate 'not found' response."""
    if language == "hi":
        return "मुझे खेद है, इस प्रश्न का उत्तर उपलब्ध स्रोतों में नहीं मिला। कृपया कोई अन्य प्रश्न पूछें।"
    return "I'm sorry, I couldn't find an answer to this question in the available sources. Please ask another question."


async def translate_to_hindi(english_text: str) -> str:
    """
    Translate English text to Hindi for better semantic search.
    The transcripts are in Hindi, so translating helps cross-lingual matching.
    """
    client = get_groq_client()
    
    prompt = f"""Translate this English spiritual/religious question to Hindi (Devanagari script).
Only output the Hindi translation, nothing else.

English: {english_text}
Hindi:"""
    
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_FAST,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=200
        )
        hindi = response.choices[0].message.content.strip()
        logger.info(f"🔄 Translated '{english_text}' → '{hindi}'")
        return hindi
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
        return english_text  # Return original if translation fails


def is_english_text(text: str) -> bool:
    """Check if text is primarily English (ASCII letters)."""
    # Count ASCII letters vs non-ASCII characters
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in text if c.isalpha())
    
    if total_letters == 0:
        return False
    
    # If more than 70% of letters are ASCII, it's English
    return (ascii_letters / total_letters) > 0.7


async def generate_video_themes(transcript: str) -> dict:
    """
    Generate themes, main topic, and key teachings from transcript.
    Used during video upload to auto-generate metadata.
    """
    client = get_groq_client()
    
    # Truncate transcript if too long (Groq has token limits)
    max_chars = 8000
    truncated_transcript = transcript[:max_chars] if len(transcript) > max_chars else transcript
    
    prompt = f"""Analyze this Hindi spiritual discourse (pravachan) transcript and extract:

1. **main_topic** (string): The primary topic discussed in 5-10 words (in Hindi)
2. **main_topic_en** (string): Same topic in English
3. **themes** (array): List of 3-6 key themes/topics discussed (in Hindi)
4. **themes_en** (array): Same themes in English
5. **key_teachings** (array): 2-4 practical teachings or takeaways (in Hindi)

IMPORTANT: 
- Focus on the actual spiritual content, not the chanting parts (राधा राधा etc.)
- Identify the core teachings of Maharaj Ji
- Be concise and specific

Return ONLY valid JSON in this exact format:
{{
    "main_topic": "...",
    "main_topic_en": "...",
    "themes": ["theme1", "theme2", ...],
    "themes_en": ["theme1", "theme2", ...],
    "key_teachings": ["teaching1", "teaching2", ...]
}}

TRANSCRIPT:
{truncated_transcript}
"""
    
    try:
        model = getattr(settings, 'LLM_MODEL_FAST', settings.LLM_MODEL)
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes Hindi spiritual discourses and returns JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        text = response.choices[0].message.content.strip()
        
        # Clean up response - remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # Parse JSON
        import json
        metadata = json.loads(text)
        logger.info(f"✅ Generated themes: {metadata.get('themes', [])}")
        return metadata
        
    except Exception as e:
        logger.error(f"❌ Failed to generate themes: {e}")
        return {
            "main_topic": "",
            "main_topic_en": "",
            "themes": [],
            "themes_en": [],
            "key_teachings": []
        }
