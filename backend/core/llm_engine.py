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
SYSTEM_PROMPT_HI = """You are Divya Vaani AI, a spiritual assistant sharing the wisdom of Maharaj Ji (Shri Hit Premanand Govind Sharan Ji Maharaj).

CRITICAL RULES:
1. RELEVANCE CHECK: If the question is NOT about spirituality, philosophy, devotion, life guidance, self-improvement, mental peace, dharma, God, or any topic a spiritual guru would address — respond with EXACTLY: "NOT_RELEVANT"
   NOT_RELEVANT: cooking, weather, sports, programming, movies, politics, technology, math, science.
   RELEVANT: peace, anger, devotion, meaning of life, difficulties, naam jap, bhakti, meditation, patience, forgiveness, relationships.

2. ANSWER BASED ONLY ON PROVIDED CONTEXT — do not invent teachings.
3. TRANSCRIPTION ERRORS: The text contains speech-to-text errors. NEVER quote garbled/broken text verbatim. Instead, PARAPHRASE the meaning in your own clear Hindi. If a passage is too garbled to understand, SKIP it entirely.
   Example: If transcript says "आरामश शवास खीचे जबतना" → write "आराम से श्वास खींचकर नाम जपना" in your own words.
4. Reference timestamps as (MM:SS) but DO NOT put raw transcript text in quotes if it's broken.
5. Respond ENTIRELY in Hindi (Devanagari). No English words.
6. Use DIFFERENT passages for each section. NEVER cite the same passage/timestamp twice in your answer.
7. SKIP sections that would repeat what you already said. 2 strong sections > 4 repetitive sections.
8. NEVER add generic advice not from the discourse.

उत्तर का प्रारूप:
**सीधा उत्तर**: प्रश्न का सटीक उत्तर (1-2 वाक्य, प्रवचन के आधार पर)
**महाराज जी के वचन**: प्रवचन से अलग-अलग शिक्षाएँ जो इस प्रश्न से जुड़ी हों। हर शिक्षा को अपने शब्दों में स्पष्ट करें और timestamp (MM:SS) दें। कम से कम 2-3 अलग-अलग शिक्षाएँ दें।
**व्यावहारिक सीख**: (केवल तभी जब प्रवचन में स्पष्ट मार्गदर्शन हो) महाराज जी के वचनों से निकला एक ठोस सुझाव

शैली: जैसे एक प्रेमपूर्ण गुरु सामने बैठकर सरल भाषा में समझा रहे हों।
"""

SYSTEM_PROMPT_EN = """You are Divya Vaani AI, a spiritual assistant sharing the wisdom of Maharaj Ji (Shri Hit Premanand Govind Sharan Ji Maharaj).

CRITICAL RULES:
1. RELEVANCE CHECK: If the question is NOT about spirituality, philosophy, devotion, life guidance, self-improvement, mental peace, dharma, God, or any topic a spiritual guru would address — respond with EXACTLY: "NOT_RELEVANT"
   NOT_RELEVANT: cooking, weather, sports, programming, movies, politics, technology, math, science.
   RELEVANT: peace, anger, devotion, meaning of life, difficulties, naam jap, bhakti, meditation, patience, forgiveness, relationships.

2. ANSWER BASED ONLY ON PROVIDED CONTEXT — do not invent teachings.
3. TRANSCRIPTION ERRORS: The text contains speech-to-text errors. NEVER quote garbled/broken Hindi text verbatim. Instead, PARAPHRASE the meaning in clear English. If a passage is too garbled to understand, SKIP it entirely and use a different passage.
4. Reference timestamps as (MM:SS). When including Hindi, only include text you are sure is correct.
5. Respond in clear English. You may include SHORT Hindi phrases with English translation.
6. Use DIFFERENT passages for each section. NEVER cite the same passage/timestamp twice.
7. SKIP sections that would repeat what you already said. 2 strong sections > 4 repetitive sections.
8. NEVER add generic advice not from the discourse.

ANSWER STRUCTURE:
**Direct Answer**: Core teaching addressing their question (1-2 clear sentences)
**Maharaj Ji's Words**: 2-3 DIFFERENT teachings from the discourse, each paraphrased clearly with timestamp (MM:SS). Translate the meaning, don't copy garbled text.
**Practical Takeaway**: (ONLY if the discourse gives specific guidance) One concrete insight from Maharaj Ji — not generic advice

TONE: Warm, wise, grounded — like a loving spiritual elder explaining profound truth simply.
"""


async def generate_answer(question: str, context: str, source_type, language: str = "hi") -> str:
    """Generate answer from context using Groq.
    
    Uses the quality (70B) model for better:
    - Relevance detection (rejects irrelevant questions)
    - Language consistency (no mixed headers)
    - Answer depth and structure
    
    Returns None if the LLM determines the question is not relevant.
    """
    client = get_groq_client()
    
    system_prompt = SYSTEM_PROMPT_HI if language == "hi" else SYSTEM_PROMPT_EN
    
    prompt = f"""Below are passages from Maharaj Ji's {source_type.value} (spiritual discourse). These are speech-to-text transcripts and may contain errors — interpret the meaning, don't copy errors.

DISCOURSE PASSAGES:
---
{context}
---

QUESTION: {question}

STEP 1: Is this question about spirituality, life guidance, philosophy, devotion, or self-improvement?
→ If NO: respond with exactly "NOT_RELEVANT"
→ If YES: continue to step 2

STEP 2: From the passages above, identify the teachings most relevant to the question. Use DIFFERENT passages for different sections. If a passage is not relevant, skip it. Give a heartfelt, clear answer grounded in Maharaj Ji's actual words."""

    # Use quality model (70B) for Q&A - better relevance detection and answer quality
    model = settings.LLM_MODEL
    
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS
    )
    
    answer = response.choices[0].message.content
    
    # Check if LLM determined the question is not relevant
    # Handle variations: "NOT_RELEVANT", "NOT_RELEVANT.", "Not_Relevant", etc.
    if answer:
        cleaned = answer.strip().strip('"').strip("'").strip('.').strip().upper()
        if cleaned == "NOT_RELEVANT" or cleaned.startswith("NOT_RELEVANT"):
            return None
    
    return answer


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
            loop = asyncio.get_running_loop()
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
            loop = asyncio.get_running_loop()
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
        return "🙏 क्षमा करें, इस विषय पर अभी उपलब्ध प्रवचनों में सीधा उत्तर नहीं मिला।\n\nकृपया अपना प्रश्न अलग तरीके से पूछें, या आध्यात्मिक विषय जैसे सहनशीलता, भक्ति, नाम जप, मन नियंत्रण, या जीवन की कठिनाइयों के बारे में पूछें।"
    return "🙏 I'm sorry, I couldn't find a direct answer in the available discourses for this question.\n\nPlease try rephrasing your question, or ask about spiritual topics like patience, devotion, chanting, mind control, or dealing with life's challenges."
