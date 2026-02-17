"""Chat / Q&A routes — RAG-powered spiritual Q&A."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from data.schema import ChatRequest, ChatResponse, SourceType
from core import llm_engine, rag_engine
from db.database import get_db
from db import crud
from db.models import User
from auth.dependencies import get_current_user
from ._helpers import limiter, _format_time

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_QUESTION_LENGTH = 1000


def _expand_question_for_search(question: str) -> str:
    """Expand the user's question with spiritual keywords to improve semantic search."""
    expansion_keywords = {
        "don't want to live": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय कमजोर",
        "want to die": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय मरना",
        "hopeless": "परेशान दुख धैर्य गंभीर विपत्ति समाधान",
        "depressed": "परेशान दुख कमजोर धैर्य गंभीर भगवान कृपा",
        "sad": "परेशान दुख धैर्य गंभीर भगवान कृपा",
        "struggling": "परेशान विपत्ति समस्या धैर्य गंभीर",
        "difficult": "विपत्ति समस्या धैर्य गंभीर समाधान",
        "problem": "समस्या विपत्ति समाधान धैर्य",
        "suffering": "दुख पीड़ा धैर्य भगवदाश्रय",
        "pain": "पीड़ा दुख धैर्य सहन भगवदाश्रय",
        "fear": "भय डर धैर्य भगवदाश्रय",
        "anxiety": "परेशान चिंता धैर्य गंभीर",
        "worried": "परेशान चिंता धैर्य गंभीर",
        "जीना नहीं": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय",
        "मरना": "जीवन परेशान दुख धैर्य सेवा मृत्यु",
        "परेशान": "परेशान दुख धैर्य गंभीर समाधान",
        "दुखी": "दुख परेशान धैर्य भगवान कृपा",
    }
    expanded = question
    question_lower = question.lower()
    for key, expansion in expansion_keywords.items():
        if key in question_lower:
            expanded = f"{question} {expansion}"
            break
    return expanded


def _detect_sensitive_topic(question: str) -> str | None:
    """Detect if user is in distress or asking off-topic questions.
    Returns:
        - Compassion instruction string if distress detected
        - "OFF_TOPIC" if clearly unrelated to spirituality
        - None if normal question
    """
    q_lower = question.lower()
    q_text = question  # Hindi doesn't need lowering

    # Distress / harm keywords — user needs compassionate spiritual guidance
    distress_en = [
        "kill", "murder", "suicide", "want to die", "hurt myself",
        "end my life", "harm", "attack", "destroy", "revenge",
        "hate someone", "beat", "abuse",
    ]
    distress_hi = [
        "मारना", "हत्या", "आत्महत्या", "मरना चाहता", "मर जाना",
        "नुकसान", "बदला", "मार डालना", "मारूंगा", "पीटना",
    ]

    is_distress = (
        any(w in q_lower for w in distress_en)
        or any(w in q_text for w in distress_hi)
    )

    if is_distress:
        return (
            "CRITICAL: The user seems to be in emotional distress or discussing harmful thoughts. "
            "You MUST respond with deep compassion and spiritual wisdom. Guide them AWAY from harm. "
            "Remind them that every life is sacred (हर जीव भगवान का अंश है), that God loves them, "
            "and that Maharaj Ji teaches forgiveness, patience, and inner peace. "
            "If they mention self-harm, strongly encourage them to speak to a trusted person or seek help. "
            "NEVER provide any harmful guidance. Be a caring spiritual counselor. "
            "Show them that violence and revenge only bring more suffering, "
            "while compassion and devotion bring true peace."
        )

    # ── Off-topic detection (not spiritual at all) ──
    offtopic_en = [
        "weather", "stock market", "bitcoin", "crypto", "programming",
        "code", "recipe", "football", "cricket score", "movie review",
        "national anthem", "capital of", "president of", "prime minister",
        "population", "currency", "gdp", "election", "politics",
        "salary", "job", "interview", "resume", "dating",
        "girlfriend", "boyfriend", "tinder", "instagram",
        "youtube", "tiktok", "game", "fortnite", "pubg",
        "iphone", "android", "laptop", "wifi", "password",
        "homework", "exam", "school", "college", "university",
        "science", "physics", "chemistry", "biology", "math",
        "hospital", "doctor", "medicine", "disease",
        "train", "flight", "hotel", "restaurant", "pizza",
        "favorite food", "favourite food", "favorite colour", "favorite movie",
        "how old are you", "your name", "who are you", "where are you from",
        "how to cook", "how to make", "how to build",
        "sex", "porn", "nude", "hot girl", "hot boy",
    ]
    offtopic_hi = [
        "मौसम", "शेयर बाजार", "बिटकॉइन", "प्रोग्रामिंग", "क्रिकेट स्कोर",
        "राष्ट्रगान", "राष्ट्रगीत", "राजधानी", "राष्ट्रपति", "प्रधानमंत्री",
        "जनसंख्या", "मुद्रा", "चुनाव", "राजनीति", "नौकरी",
        "तनख्वाह", "इंटरव्यू", "परीक्षा", "स्कूल", "कॉलेज",
        "विज्ञान", "भौतिकी", "रसायन", "गणित", "अस्पताल",
        "डॉक्टर", "दवाई", "ट्रेन", "होटल", "रेस्टोरेंट",
        "फिल्म", "गाना", "अभिनेता", "मूवी",
        "भोजन", "खाना", "पसंदीदा", "रंग", "फेवरिट",
        "आपका नाम", "तुम कौन हो", "तुम्हारा नाम", "कहाँ से हो",
        "बनाना सिखाओ", "पकाना", "रेसिपी",
        "क्रिकेट", "फुटबॉल", "मैच", "स्कोर",
    ]
    is_offtopic = (
        any(w in q_lower for w in offtopic_en)
        or any(w in q_text for w in offtopic_hi)
    )

    # Pattern-based detection for common non-spiritual question formats
    if not is_offtopic:
        import re
        # Non-spiritual "what is X" patterns (Hindi)
        nonspi_patterns_hi = [
            r".*(?:का|की|के)\s+(?:राजधानी|राष्ट्रगान|राष्ट्रपति|प्रधानमंत्री|जनसंख्या|मुद्रा)",
            r".*(?:कौन\s+(?:सा|सी)\s+(?:भोजन|खाना|रंग|फिल्म|गाना|खेल|देश|शहर))",
            r".*(?:पसंदीदा|फेवरिट)\s+(?:भोजन|खाना|रंग|फिल्म|गाना|खेल)",
            r".*(?:कैसे\s+(?:बनाते|पकाते|बनाएं))",
        ]
        # Non-spiritual "what is X" patterns (English)
        nonspi_patterns_en = [
            r"(?:what|who)\s+(?:is|are|was|were)\s+(?:the\s+)?(?:capital|anthem|president|flag|population)",
            r"(?:your|my)\s+(?:favorite|favourite|fav)",
            r"how\s+(?:to|do\s+(?:i|you|we))\s+(?:cook|make|build|fix|install|download)",
            r"(?:tell|say)\s+(?:me\s+)?(?:a\s+)?(?:joke|story|poem|riddle)",
        ]
        for p in nonspi_patterns_hi:
            if re.search(p, q_text):
                is_offtopic = True
                break
        if not is_offtopic:
            for p in nonspi_patterns_en:
                if re.search(p, q_lower):
                    is_offtopic = True
                    break

    if is_offtopic:
        return "OFF_TOPIC"

    return None


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask a question — answers from pre-loaded spiritual discourses."""
    question = chat_request.question.strip()
    language = chat_request.language if chat_request.language in ["hi", "en"] else "hi"

    if not question:
        raise HTTPException(400, "Question cannot be empty")
    if len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(400, f"Question too long. Max {MAX_QUESTION_LENGTH} characters.")

    content_id = chat_request.transcript_id

    # Greetings
    greetings_en = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "namaste"]
    greetings_hi = ["नमस्ते", "नमस्कार", "हेलो", "हाय", "राधे राधे", "जय श्री कृष्ण", "हरि ॐ"]
    question_lower = question.lower().strip()
    is_greeting = question_lower in greetings_en or question in greetings_hi

    if is_greeting:
        if language == "hi":
            greeting_response = "🙏 राधे राधे! मैं दिव्य वाणी AI हूं। आप महाराज जी के प्रवचनों से संबंधित कोई भी प्रश्न पूछ सकते हैं। जैसे - 'भक्ति क्या है?', 'मन को शांत कैसे करें?', 'जीवन में धैर्य कैसे रखें?'"
        else:
            greeting_response = "🙏 Radhe Radhe! I am Divya Vaani AI. You can ask any question related to Maharaj Ji's discourses. For example - 'What is devotion?', 'How to find peace of mind?', 'How to have patience in life?'"

        response = ChatResponse(
            answer=greeting_response,
            source_type=SourceType.NOT_FOUND,
            source_reference="",
            audio_url=""
        )
        await _persist_chat(db, user, content_id, question, response)
        return response

    # ── Sensitive topic detection ──
    sensitivity = _detect_sensitive_topic(question)

    if sensitivity == "OFF_TOPIC":
        off_topic_msg = (
            "🙏 यह प्रश्न मेरे विषय से बाहर है। मैं महाराज जी के प्रवचनों और भगवद्गीता से आध्यात्मिक मार्गदर्शन में सहायता कर सकता हूं। कृपया आध्यात्मिक विषय पर प्रश्न पूछें।"
            if language == "hi" else
            "🙏 This question is outside my area of expertise. I can help with spiritual guidance from Maharaj Ji's discourses and the Bhagavad Gita. Please ask a spirituality-related question."
        )
        response = ChatResponse(
            answer=off_topic_msg,
            source_type=SourceType.NOT_FOUND,
            source_reference="",
            audio_url=""
        )
        await _persist_chat(db, user, content_id, question, response)
        return response

    # Compassion instruction for distressed users (passed to LLM later)
    extra_instruction = sensitivity if sensitivity and sensitivity != "OFF_TOPIC" else ""

    is_english = llm_engine.is_english_text(question)
    search_query = question

    if is_english:
        hindi_question = await llm_engine.translate_to_hindi(question)
        search_query = f"{question} {hindi_question}"

    transcript_results = []
    gita_results = []
    best_transcript_score = 0.0
    best_gita_score = 0.0

    transcript_threshold = 0.45 if is_english else 0.60
    gita_threshold = 0.55 if is_english else 0.75

    if content_id or rag_engine.has_transcripts():
        expanded_query = _expand_question_for_search(search_query)
        transcript_results = rag_engine.search_transcripts_with_scores(
            expanded_query, transcript_id=content_id, top_k=5
        )
        if not transcript_results:
            transcript_results = rag_engine.search_transcripts_with_scores(
                search_query, transcript_id=content_id, top_k=5
            )
        if transcript_results:
            best_transcript_score = transcript_results[0]["score"]

    gita_results = rag_engine.search_gita(search_query, top_k=3)
    if gita_results:
        best_gita_score = gita_results[0]["score"]

    GOOD_TRANSCRIPT_THRESHOLD = transcript_threshold
    GOOD_GITA_THRESHOLD = gita_threshold

    question_lower = question.lower()
    gita_keywords_en = ["gita", "geeta", "arjun", "bhagavad", "bhagwat", "chapter", "verse"]
    gita_keywords_hi = ["गीता", "अर्जुन", "भगवद", "श्लोक", "अध्याय", "कृष्ण ने अर्जुन"]
    is_explicit_gita_question = (
        any(kw in question_lower for kw in gita_keywords_en)
        or any(kw in question for kw in gita_keywords_hi)
    )

    use_transcript = False
    use_gita = False

    # ── Decision Logic: TRANSCRIPTS FIRST, Gita as last resort ──
    # PRIORITY 1: If user is on a specific video, strongly prefer its transcript
    if content_id and transcript_results and best_transcript_score >= 0.35:
        use_transcript = True
    # PRIORITY 2: Transcripts with good score — always use
    elif transcript_results and best_transcript_score >= GOOD_TRANSCRIPT_THRESHOLD:
        use_transcript = True
    # PRIORITY 3: Transcripts with reasonable score — still prefer over Gita
    elif transcript_results and best_transcript_score >= 0.35:
        use_transcript = True
    # PRIORITY 4: Explicit Gita question AND no transcript found
    elif is_explicit_gita_question and gita_results:
        use_gita = True
    # PRIORITY 5: Last resort — Gita only when NO transcript matches at all
    elif gita_results and best_gita_score >= GOOD_GITA_THRESHOLD:
        use_gita = True

    if use_transcript and transcript_results:
        chunks = [r["chunk"] for r in transcript_results]
        context_parts = []
        for c in chunks:
            timestamp = f"[{_format_time(c.start_time)} - {_format_time(c.end_time)}]"
            context_parts.append(f"{timestamp}: {c.text}")
        context = "\n\n".join(context_parts)
        answer = await llm_engine.generate_answer(
            question, context, SourceType.PRAVACHAN, language,
            extra_instruction=extra_instruction
        )
        response = ChatResponse(
            answer=answer,
            source_type=SourceType.PRAVACHAN,
            source_reference=f"Based on {len(chunks)} segments from the discourse (relevance: {best_transcript_score:.0%})",
            audio_url=""
        )
        await _persist_chat(db, user, content_id, question, response)
        return response

    if use_gita and gita_results:
        answer = await llm_engine.generate_gita_answer(
            question, gita_results, language,
            extra_instruction=extra_instruction
        )
        verse_refs = [f"Chapter {v['verse'].chapter}, Verse {v['verse'].verse}" for v in gita_results]
        response = ChatResponse(
            answer=answer,
            source_type=SourceType.GITA,
            source_reference=f"📖 Bhagavad Gita - {', '.join(verse_refs)}",
            audio_url=""
        )
        await _persist_chat(db, user, content_id, question, response)
        return response

    not_found = await llm_engine.generate_not_found(language)
    response = ChatResponse(
        answer=not_found,
        source_type=SourceType.NOT_FOUND,
        source_reference="",
        audio_url=""
    )
    await _persist_chat(db, user, content_id, question, response)
    return response


async def _persist_chat(
    db: AsyncSession,
    user: Optional[User],
    video_id: Optional[str],
    question: str,
    response: ChatResponse,
):
    """Save user question + assistant answer to DB for authenticated users."""
    if user is None or not video_id:
        return
    try:
        # Save user message
        await crud.save_chat_message(
            db, user.id, video_id, "user", question
        )
        # Save assistant message
        await crud.save_chat_message(
            db, user.id, video_id, "assistant", response.answer,
            source_type=response.source_type.value if response.source_type else None,
            source_reference=response.source_reference,
            audio_url=response.audio_url,
        )
    except Exception as e:
        logger.warning(f"Failed to persist chat: {e}")
