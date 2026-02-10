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

    if is_explicit_gita_question and gita_results:
        use_gita = True
    elif gita_results and best_gita_score >= GOOD_GITA_THRESHOLD:
        if not transcript_results or best_transcript_score < best_gita_score:
            use_gita = True
        else:
            use_transcript = True
    elif transcript_results and best_transcript_score >= GOOD_TRANSCRIPT_THRESHOLD:
        use_transcript = True
    elif transcript_results:
        use_transcript = True

    if use_transcript and transcript_results:
        chunks = [r["chunk"] for r in transcript_results]
        context_parts = []
        for c in chunks:
            timestamp = f"[{_format_time(c.start_time)} - {_format_time(c.end_time)}]"
            context_parts.append(f"{timestamp}: {c.text}")
        context = "\n\n".join(context_parts)
        answer = await llm_engine.generate_answer(question, context, SourceType.PRAVACHAN, language)
        response = ChatResponse(
            answer=answer,
            source_type=SourceType.PRAVACHAN,
            source_reference=f"Based on {len(chunks)} segments from the discourse (relevance: {best_transcript_score:.0%})",
            audio_url=""
        )
        await _persist_chat(db, user, content_id, question, response)
        return response

    if use_gita and gita_results:
        answer = await llm_engine.generate_gita_answer(question, gita_results, language)
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
