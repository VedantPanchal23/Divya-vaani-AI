"""
Divya Vaani AI - LLM Engine (Production Grade)
Uses Gemini for heavy tasks (summary, explanation) to avoid Groq rate limits.
Uses Groq for fast Q&A responses.
Includes query expansion, relevance verification, and context-grounded prompts.
"""
import logging
import json

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None
    logging.getLogger(__name__).warning("groq package not installed — Q&A disabled")

from config import settings

logger = logging.getLogger(__name__)

_groq_client = None
_gemini_client = None


def get_groq_client() -> AsyncGroq:
    """Get Groq client - used for fast Q&A."""
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY.get_secret_value())
        logger.info("Groq client initialized")
    return _groq_client


def get_gemini_client():
    """Get Gemini client - used for summaries and explanations."""
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())
            logger.info("Gemini client initialized (google-genai, gemini-2.0-flash)")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            return None
    return _gemini_client


# ========== System Prompts ==========

SYSTEM_PROMPT_PRAVACHAN = """You are Divya Vaani AI, a deeply compassionate spiritual assistant that guides people using the actual teachings of Maharaj Ji (Premanand Govind Sharan Maharaj) from his pravachans (discourses).

CRITICAL RULES — THESE ARE NON-NEGOTIABLE:

1. CONTEXT-GROUNDED ANSWERS ONLY: You MUST answer ONLY from the provided discourse context. If the context does not contain relevant information to answer the question, be HONEST and say the specific discourse does not address this topic directly, but share what related wisdom is available.

2. NEVER FABRICATE: Do NOT invent teachings, make up quotes, or attribute things to Maharaj Ji that are not in the provided context. People's spiritual journey and even their lives may depend on the accuracy of your answers.

3. ALWAYS CITE TIMESTAMPS: When referencing specific teachings, include the timestamp in format [MM:SS - MM:SS].

4. RESPOND IN THE REQUESTED LANGUAGE: Hindi (Devanagari) or English as specified.

5. COMPASSION FIRST: If someone is going through pain, suffering, or dark thoughts, respond with genuine warmth and care. Connect them to relevant spiritual wisdom from the context.

ANSWERING APPROACH:
- Start with the most relevant teaching from the context
- Quote or paraphrase Maharaj Ji's actual words with timestamp
- Explain the deeper meaning and how it applies
- If the user is struggling, offer hope through the discourse's wisdom
- Be warm, caring, and authentic — like a trusted spiritual guide

STYLE:
- Start directly with relevant teaching: "Maharaj Ji teaches...", "In this discourse, Maharaj Ji explains..."
- Do NOT start with greetings like "Dear friend" or "Priya bhakt"
- Do NOT use second-person forms like "your problem" 
- Keep answers focused and meaningful — quality over quantity

NON-SPIRITUAL QUESTIONS:
If the question is clearly NOT about spirituality, religion, devotion, dharma, moral values, life philosophy, or personal struggles, respond:
Hindi: "yeh prashna adhyatmik vishay se sambandhit nahi hai. Kripya Maharaj Ji ke pravachanon se juda prashna puchein."
English: "This question is not related to spiritual topics. Please ask questions related to Maharaj Ji's discourses."
Do NOT force-fit spiritual context onto unrelated questions."""

SYSTEM_PROMPT_GITA = """You are Divya Vaani AI, a spiritual guide who shares the eternal wisdom of Bhagavad Gita. You help seekers understand Lord Krishna's teachings and apply them to life challenges.

CRITICAL RULES:
1. Only use the provided Gita verses to answer — never fabricate verses or meanings
2. Reference specific chapter and verse numbers
3. Explain the teaching and its practical application
4. Be compassionate and caring — this person is seeking guidance
5. Make the ancient wisdom relatable to their situation

NOTE: You are sharing Bhagavad Gita wisdom because this question was not found in the available pravachan (discourse) transcripts. Frame your answer as Gita's guidance.

STYLE:
- Start with the relevant teaching directly  
- Reference the verse: "In Chapter X, Verse Y, Lord Krishna teaches..."
- Explain practical application
- Be warm and encouraging"""


def _sanitize_user_input(text: str) -> str:
    """Sanitize user input to prevent prompt injection and jailbreak attacks."""
    import re
    injection_patterns = [
        # Direct instruction override
        r'(?i)ignore\s+(all\s+)?previous\s+instructions',
        r'(?i)forget\s+(all\s+)?previous',
        r'(?i)disregard\s+(all\s+)?above',
        r'(?i)override\s+(system|previous)',
        r'(?i)new\s+instructions?:',
        # Role hijacking
        r'(?i)you\s+are\s+now\s+',
        r'(?i)act\s+as\s+(?!a\s+spiritual)',
        r'(?i)pretend\s+(to\s+be|you\s+are)',
        r'(?i)role\s*play\s+as',
        r'(?i)switch\s+to\s+.{0,20}\s+mode',
        r'(?i)enable\s+.{0,20}\s+mode',
        # Jailbreak attempts (DAN, Developer Mode, etc.)
        r'(?i)do\s+anything\s+now',
        r'(?i)\bDAN\b\s+mode',
        r'(?i)developer\s+mode',
        r'(?i)jailbreak',
        r'(?i)no\s+restrictions',
        r'(?i)bypass\s+(filter|safety|content)',
        r'(?i)without\s+(any\s+)?restrictions',
        r'(?i)uncensored',
        # System prompt extraction
        r'(?i)repeat\s+(your\s+)?(system\s+)?prompt',
        r'(?i)show\s+(me\s+)?(your\s+)?(system|initial)\s+(prompt|instructions)',
        r'(?i)what\s+(are|were)\s+your\s+(instructions|rules)',
        r'(?i)print\s+(your\s+)?prompt',
        # Markdown/HTML injection for system blocks
        r'(?i)system\s*:\s*',
        r'(?i)\[\s*system\s*\]',
        r'(?i)\<\s*system\s*\>',
        r'(?i)```\s*system',
        # Token manipulation
        r'(?i)\[INST\]',
        r'(?i)\<\|im_start\|\>',
        r'(?i)\<\|endoftext\|\>',
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, '[filtered]', text)
    return text.strip()


def _is_prompt_injection(text: str) -> bool:
    """Check if the entire message appears to be a prompt injection attempt."""
    import re
    text_lower = text.lower().strip()
    
    # High-confidence jailbreak signatures
    jailbreak_signatures = [
        r'(?i)from\s+now\s+on.*respond.*without',
        r'(?i)you\s+(?:will|must|should)\s+(?:now\s+)?(?:act|behave|respond)\s+as',
        r'(?i)(?:here|these)\s+are\s+(?:your\s+)?new\s+(?:instructions|rules)',
        r'(?i)(?:for|in)\s+(?:this|the)\s+(?:rest|remainder)\s+of\s+(?:this|our)\s+conversation',
        r'(?i)i\s+want\s+you\s+to\s+(?:act|pretend|behave)\s+(?:as|like)',
        r'(?i)(?:simulate|emulate|imitate)\s+(?:a|an)\s+(?:AI|bot|assistant)\s+(?:without|that)',
    ]
    
    for pattern in jailbreak_signatures:
        if re.search(pattern, text_lower):
            return True
    
    return False


# ========== Core Q&A Functions ==========

async def generate_answer(question: str, context: str, source_type, language: str = "hi", extra_instruction: str = "") -> str:
    """Generate answer from context using Groq (fast model for low latency)."""
    try:
        client = get_groq_client()
        
        safe_question = _sanitize_user_input(question)
        
        lang_instruction = "Respond in Hindi (Devanagari script)." if language == "hi" else "Respond in English."
        extra_block = f"\n\nSPECIAL GUIDANCE:\n{extra_instruction}" if extra_instruction else ""
        
        prompt = f"""SPIRITUAL DISCOURSE CONTEXT (from Maharaj Ji's pravachan):
{context}

USER'S QUESTION/CONCERN: {safe_question}

{lang_instruction}

INSTRUCTIONS:
1. Find the MOST RELEVANT teaching from the above context that addresses the user's question
2. If the context directly addresses their concern, quote/paraphrase with timestamp [MM:SS - MM:SS]
3. Explain how the teaching applies to their situation
4. If the context does NOT contain relevant information for this specific question, honestly say: "Is pravachan mein is vishay par seedhi charcha nahi hai" (Hindi) or "This particular discourse does not directly address this topic" (English) — and share whatever related wisdom IS available
5. Be compassionate — the user may be going through a difficult time
6. NEVER invent quotes or teachings not present in the context
{extra_block}

Provide a helpful, caring, and TRUTHFUL response grounded in the discourse."""

        model = getattr(settings, 'LLM_MODEL_FAST', settings.LLM_MODEL)
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_PRAVACHAN},
                {"role": "user", "content": prompt}
            ],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"generate_answer failed: {e}")
        if language == "hi":
            return "क्षमा करें, उत्तर देने में एक तकनीकी समस्या आई। कृपया पुनः प्रयास करें।"
        return "Sorry, there was a technical issue generating the answer. Please try again."


async def generate_gita_answer(question: str, verses: list, language: str = "hi", extra_instruction: str = "") -> str:
    """Generate answer from Bhagavad Gita verses."""
    try:
        client = get_groq_client()
        
        safe_question = _sanitize_user_input(question)
        
        # Build context from Gita verses
        context_parts = []
        for v in verses:
            verse_text = f"""Chapter {v['verse'].chapter}, Verse {v['verse'].verse}
Sanskrit: {v['verse'].sanskrit}
Hindi meaning: {v['verse'].hindi}
English meaning: {v['verse'].english}"""
            context_parts.append(verse_text)
        
        context = "\n\n---\n\n".join(context_parts)
        
        lang_instruction = "Respond in Hindi (Devanagari script)." if language == "hi" else "Respond in English."
        extra_block = f"\n\nSPECIAL GUIDANCE:\n{extra_instruction}" if extra_instruction else ""
        
        prompt = f"""BHAGAVAD GITA VERSES:
{context}

USER'S QUESTION: {safe_question}

{lang_instruction}

INSTRUCTIONS:
1. This answer is from Bhagavad Gita because no relevant pravachan (discourse) content was found
2. Reference the specific Gita verse (chapter and verse number)
3. Explain how this eternal wisdom from Lord Krishna applies to their situation
4. Keep the tone spiritual, compassionate, and practical
5. Start directly with the teaching — no greetings
{extra_block}

Provide a helpful response using the wisdom from Bhagavad Gita."""

        model = getattr(settings, 'LLM_MODEL_FAST', settings.LLM_MODEL)
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_GITA},
                {"role": "user", "content": prompt}
            ],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"generate_gita_answer failed: {e}")
        if language == "hi":
            return "क्षमा करें, भगवद्गीता से उत्तर देने में एक तकनीकी समस्या आई। कृपया पुनः प्रयास करें।"
        return "Sorry, there was a technical issue generating the answer from Bhagavad Gita. Please try again."


async def generate_not_found(language: str = "hi") -> str:
    """Generate 'not found' response."""
    if language == "hi":
        return "क्षमा करें, इस प्रश्न का उत्तर उपलब्ध प्रवचनों में नहीं मिला। कृपया कोई अन्य आध्यात्मिक प्रश्न पूछें या अपना प्रश्न दूसरे शब्दों में पूछें।"
    return "I'm sorry, I couldn't find an answer to this question in the available discourses. Please try asking another spiritual question or rephrase your question."


# ========== Advanced Q&A Functions ==========

async def generate_search_queries(question: str, language: str = "hi") -> list:
    """
    Generate multiple search query variants for better retrieval.
    Takes the user's question and creates 2-3 semantic variants
    that capture different aspects/phrasings of the same intent.
    """
    try:
        client = get_groq_client()
        
        prompt = f"""Given this spiritual question, generate 2-3 search query variants in Hindi (Devanagari) that capture different aspects of the same question. These will be used to search through Hindi spiritual discourse transcripts.

Original question: {question}

Rules:
- Each variant should use different Hindi words/phrases for the same concept
- Include spiritual/religious vocabulary (भक्ति, धर्म, कर्म, सेवा, etc.) where relevant
- Keep each variant concise (5-15 words)
- At least one variant should be in Hindi even if the original is in English

Return ONLY a JSON array of strings, nothing else. Example: ["query1", "query2", "query3"]"""

        model = getattr(settings, 'LLM_MODEL_FAST', settings.LLM_MODEL)
        
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=300
        )
        
        text = response.choices[0].message.content.strip()
        
        # Clean up JSON response
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        queries = json.loads(text)
        if isinstance(queries, list) and len(queries) > 0:
            logger.info(f"Generated {len(queries)} search queries for: {question[:50]}...")
            return queries[:3]  # Max 3 variants
        
        return []
    except Exception as e:
        logger.warning(f"Query expansion failed (non-critical): {e}")
        return []


async def verify_context_relevance(question: str, context: str, language: str = "hi") -> dict:
    """
    LLM-based verification that retrieved context is actually relevant to the question.
    Returns {"relevant": bool, "confidence": float, "reason": str}
    
    This is a critical guardrail — prevents the system from fabricating answers
    from irrelevant context, which could mislead people seeking spiritual guidance.
    """
    try:
        client = get_groq_client()
        
        prompt = f"""You are a relevance judge. Determine if the following discourse context actually contains information relevant to answering the user's question.

QUESTION: {question}

DISCOURSE CONTEXT:
{context[:3000]}

Evaluate:
1. Does the context contain teachings or information that DIRECTLY address the question?
2. Is there meaningful overlap between what the user is asking and what the discourse discusses?
3. Would using this context lead to an ACCURATE, helpful answer?

Respond with ONLY a JSON object:
{{"relevant": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}

Be STRICT — if the context is only vaguely related or would force a stretched interpretation, mark as NOT relevant. People's spiritual wellbeing depends on honest answers."""

        model = getattr(settings, 'LLM_MODEL_FAST', settings.LLM_MODEL)
        
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )
        
        text = response.choices[0].message.content.strip()
        
        # Clean up JSON
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        result = json.loads(text)
        logger.info(f"Relevance check: relevant={result.get('relevant')}, confidence={result.get('confidence')}, reason={result.get('reason', '')[:80]}")
        return result
    except Exception as e:
        logger.warning(f"Relevance check failed (allowing answer): {e}")
        # On failure, allow the answer through (fail-open)
        return {"relevant": True, "confidence": 0.5, "reason": "Verification failed, allowing answer"}


# ========== Translation & Language ==========

async def translate_to_hindi(english_text: str) -> str:
    """
    Translate English text to Hindi for better semantic search.
    The transcripts are in Hindi, so translating helps cross-lingual matching.
    Enhanced with spiritual vocabulary hints for better translation.
    """
    client = get_groq_client()
    
    prompt = f"""Translate this English spiritual/religious question to Hindi (Devanagari script).
Use appropriate spiritual vocabulary: भक्ति (devotion), धर्म (dharma), कर्म (karma), सेवा (service), 
कृपा (grace), ज्ञान (knowledge), वैराग्य (detachment), मोक्ष (liberation), 
धैर्य (patience), शांति (peace), प्रेम (love), गुरु (guru), महाराज (maharaj).

Only output the Hindi translation, nothing else.

English: {english_text}
Hindi:"""
    
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_FAST,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )
        hindi = response.choices[0].message.content.strip()
        logger.info(f"Translated '{english_text}' -> '{hindi}'")
        return hindi
    except Exception as e:
        logger.warning(f"Translation failed: {e}")
        return english_text


def is_english_text(text: str) -> bool:
    """Check if text is primarily English (ASCII letters)."""
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in text if c.isalpha())
    
    if total_letters == 0:
        return False
    
    return (ascii_letters / total_letters) > 0.7


# ========== Summary & Explanation ==========

async def generate_summary(text: str, language: str = "hi") -> str:
    """Generate summary using Gemini (to avoid Groq rate limits)."""
    lang = "Hindi (Devanagari script)" if language == "hi" else "English"
    
    prompt = f"""Summarize this spiritual discourse in {lang}.

Provide:
1. A short paragraph (2-3 sentences) with the main message
2. 3-5 key teachings as bullet points

TRANSCRIPT:
{text[:15000]}"""

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
            logger.info(f"Summary generated with Gemini ({language})")
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
            logger.info(f"Explanation generated with Gemini ({language})")
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


async def generate_video_themes(transcript: str) -> dict:
    """
    Generate themes, main topic, and key teachings from transcript.
    Used during video upload to auto-generate metadata.
    """
    client = get_groq_client()
    
    max_chars = 8000
    truncated_transcript = transcript[:max_chars] if len(transcript) > max_chars else transcript
    
    prompt = f"""Analyze this Hindi spiritual discourse (pravachan) transcript and extract:

1. **main_topic** (string): The primary topic discussed in 5-10 words (in Hindi)
2. **main_topic_en** (string): Same topic in English
3. **themes** (array): List of 3-6 key themes/topics discussed (in Hindi)
4. **themes_en** (array): Same themes in English
5. **key_teachings** (array): 2-4 practical teachings or takeaways (in Hindi)

IMPORTANT: 
- Focus on the actual spiritual content, not the chanting parts
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
        
        # Clean up response
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        metadata = json.loads(text)
        logger.info(f"Generated themes: {metadata.get('themes', [])}")
        return metadata
        
    except Exception as e:
        logger.error(f"Failed to generate themes: {e}")
        return {
            "main_topic": "",
            "main_topic_en": "",
            "themes": [],
            "themes_en": [],
            "key_teachings": []
        }
