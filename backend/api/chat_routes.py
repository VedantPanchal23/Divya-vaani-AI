"""Chat / Q&A Routes — Production-Grade RAG-Powered Spiritual Q&A.

Decision flow:
1. Greetings → fixed response
2. Summary requests → return pre-generated summary
3. Off-topic / sensitive → appropriate response
4. TRANSCRIPT-FIRST: Search video transcripts using hybrid search
5. Multi-query expansion for better recall
6. LLM relevance verification before answering
7. Gita ONLY as explicit fallback (user asks about Gita, OR zero transcript hits)
"""
import logging
import hashlib
import json as _json
import time as _time
from collections import OrderedDict
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
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


# ========== Answer Cache ==========

class _AnswerCache:
    """Simple LRU cache with TTL for Q&A answers."""
    def __init__(self, maxsize: int = 200, ttl_seconds: int = 3600):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds
    
    def _make_key(self, question: str, content_id: str, language: str) -> str:
        normalized = question.strip().lower()
        raw = f"{normalized}|{content_id or ''}|{language}"
        return hashlib.md5(raw.encode('utf-8')).hexdigest()
    
    def get(self, question: str, content_id: str, language: str) -> Optional[ChatResponse]:
        key = self._make_key(question, content_id, language)
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, response = entry
        if _time.time() - ts > self._ttl:
            del self._cache[key]
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        logger.info(f"[Q&A] ⚡ Cache HIT for: '{question[:40]}...'")
        return response
    
    def put(self, question: str, content_id: str, language: str, response: ChatResponse):
        key = self._make_key(question, content_id, language)
        self._cache[key] = (_time.time(), response)
        self._cache.move_to_end(key)
        # Evict oldest if over capacity
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

_answer_cache = _AnswerCache(maxsize=200, ttl_seconds=3600)


# ========== Helper Functions ==========

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
        "life": "जीवन संसार मनुष्य धर्म",
        "devotion": "भक्ति प्रेम सेवा भगवान",
        "peace": "शांति धैर्य गंभीर मन",
        "meditation": "ध्यान साधना मन एकाग्रता",
        "karma": "कर्म कर्तव्य धर्म सेवा",
        "love": "प्रेम भक्ति स्नेह कृपा",
        "god": "भगवान ईश्वर परमात्मा कृष्ण राधा",
        "mind": "मन चंचल एकाग्रता ध्यान शांति",
        "जीना नहीं": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय",
        "मरना": "जीवन परेशान दुख धैर्य सेवा मृत्यु",
        "परेशान": "परेशान दुख धैर्य गंभीर समाधान",
        "दुखी": "दुख परेशान धैर्य भगवान कृपा",
        "भक्ति": "भक्ति प्रेम सेवा भगवान शरणागति",
        "शांति": "शांति मन धैर्य गंभीर ध्यान",
        "कर्म": "कर्म कर्तव्य धर्म सेवा निष्काम",
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
    q_text = question

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
            "Remind them that every life is sacred (har jeev bhagwan ka ansh hai), that God loves them, "
            "and that Maharaj Ji teaches forgiveness, patience, and inner peace. "
            "If they mention self-harm, strongly encourage them to speak to a trusted person or seek help. "
            "NEVER provide any harmful guidance. Be a caring spiritual counselor. "
            "Show them that violence and revenge only bring more suffering, "
            "while compassion and devotion bring true peace. "
            "Also mention helpline: iCall (9152987821) or Vandrevala Foundation (1860-2662-345)."
        )

    # Off-topic detection (not spiritual at all)
    offtopic_en = [
        # General knowledge / geography
        "weather", "stock market", "bitcoin", "crypto", "programming",
        "code", "recipe", "football", "cricket score", "movie review",
        "national anthem", "capital of", "president of", "prime minister",
        "population", "currency", "gdp", "election", "politics",
        # Career / professional
        "salary", "job", "interview", "resume", "dating",
        "girlfriend", "boyfriend", "tinder", "instagram",
        "youtube", "tiktok", "game", "fortnite", "pubg",
        # Technology
        "iphone", "android", "laptop", "wifi", "password",
        "hacking", "hack", "download", "crack", "pirate",
        "chatgpt", "openai", "claude", "artificial intelligence",
        # Academic
        "homework", "exam", "school", "college", "university",
        "science", "physics", "chemistry", "biology", "math",
        # Medical (non-spiritual)
        "hospital", "doctor", "medicine", "disease",
        # Travel / food
        "train", "flight", "hotel", "restaurant", "pizza",
        # Personal / identity probing
        "favorite food", "favourite food", "favorite colour", "favorite movie",
        "how old are you", "your name", "who are you", "where are you from",
        "how to cook", "how to make", "how to build",
        # NSFW / explicit
        "sex", "porn", "nude", "hot girl", "hot boy", "naked",
        "onlyfans", "xxx", "sexy", "boobs", "dick",
        # Gambling / drugs
        "gambling", "casino", "betting", "lottery", "satta",
        "drugs", "weed", "cocaine", "heroin", "marijuana",
        "alcohol", "whiskey", "beer", "vodka", "daaru",
        # Religious controversy
        "islam vs", "hindu vs", "which religion is best", "false god",
        "convert to", "conversion", "anti-hindu", "anti-muslim",
        # Jailbreak / prompt injection (caught here too as off-topic)
        "jailbreak", "ignore previous", "bypass filter",
        "do anything now", "dan mode", "developer mode",
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
        # Gambling / drugs / alcohol
        "जुआ", "सट्टा", "लॉटरी", "शराब", "दारू", "नशा", "गांजा",
        # NSFW
        "अश्लील", "नंगा", "सेक्स",
    ]
    is_offtopic = (
        any(w in q_lower for w in offtopic_en)
        or any(w in q_text for w in offtopic_hi)
    )

    # Pattern-based detection
    if not is_offtopic:
        import re
        nonspi_patterns_hi = [
            r".*(?:का|की|के)\s+(?:राजधानी|राष्ट्रगान|राष्ट्रपति|प्रधानमंत्री|जनसंख्या|मुद्रा)",
            r".*(?:कौन\s+(?:सा|सी)\s+(?:भोजन|खाना|रंग|फिल्म|गाना|खेल|देश|शहर))",
            r".*(?:पसंदीदा|फेवरिट)\s+(?:भोजन|खाना|रंग|फिल्म|गाना|खेल)",
            r".*(?:कैसे\s+(?:बनाते|पकाते|बनाएं))",
        ]
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


def _is_summary_request(question: str) -> bool:
    """Detect if the user is asking for a summary/explanation of the current video."""
    q_lower = question.lower().strip()
    q_text = question.strip()

    summary_en = [
        "summarize", "summary", "summarise", "explain this", "what is this about",
        "what is this video about", "tell me about this", "overview",
        "what does he say", "what did he say", "what is he saying",
        "brief", "gist", "main points", "key points", "highlights",
        "key takeaways", "key takeaway", "takeaways", "takeaway",
        "key learnings", "key learning", "teachings", "main teachings",
        "important points", "what did maharaj", "what does maharaj",
        "what is the topic", "what is the subject", "what is discussed",
        "what is being taught", "theme of this", "topics covered",
    ]
    summary_hi = [
        "सारांश", "सारांशित", "संक्षेप",
        "इसका सारांश", "इसका सार", "सार बताइए", "सार बताओ",
        "इसमें क्या है", "इसमें क्या बताया", "इसमें क्या कहा",
        "क्या कहा है", "क्या बताया है", "क्या सिखाया",
        "विषय क्या है", "मुख्य बात", "किस बारे में",
        "समझाइए", "समझाओ", "मुख्य शिक्षा", "मुख्य सीख",
        "प्रवचन का सार", "प्रवचन का विषय", "प्रवचन के बारे",
    ]

    return (
        any(w in q_lower for w in summary_en)
        or any(w in q_text for w in summary_hi)
    )


def _rerank_results(question: str, results: list) -> list:
    """
    Re-rank transcript results by scoring keyword overlap between the question
    and each chunk's text. This acts as a lightweight cross-encoder substitute
    and helps push truly relevant chunks to the top.
    
    Scoring: original_score * 0.7 + keyword_overlap_score * 0.3
    """
    import re as re_mod
    
    # Tokenize question (Hindi + English)
    q_lower = question.lower()
    q_tokens = set(re_mod.findall(r'[\u0900-\u097F]+|[a-z]{2,}', q_lower))
    
    if not q_tokens:
        return results
    
    # Spiritual boost terms — if both question & chunk mention these, big relevance signal
    spiritual_boost = {
        "भक्ति", "भगवान", "प्रेम", "सेवा", "कृपा", "धर्म", "कर्म",
        "ज्ञान", "मोक्ष", "ध्यान", "शांति", "माया", "आत्मा", "गुरु",
        "devotion", "god", "love", "karma", "peace", "meditation", "soul",
    }
    
    reranked = []
    for r in results:
        chunk_text = r["chunk"].text.lower()
        chunk_tokens = set(re_mod.findall(r'[\u0900-\u097F]+|[a-z]{2,}', chunk_text))
        
        if not chunk_tokens:
            reranked.append(r)
            continue
        
        # Overlap score
        overlap = q_tokens & chunk_tokens
        overlap_ratio = len(overlap) / max(len(q_tokens), 1)
        
        # Spiritual term co-occurrence boost
        spiritual_overlap = overlap & spiritual_boost
        spiritual_bonus = min(len(spiritual_overlap) * 0.05, 0.15)
        
        # Combine: 70% original score + 30% keyword overlap + spiritual boost
        original_score = r.get("score", 0)
        rerank_score = original_score * 0.7 + overlap_ratio * 0.3 + spiritual_bonus
        
        reranked.append({**r, "score": min(rerank_score, 1.0)})
    
    # Sort by new score
    reranked.sort(key=lambda x: x.get("score", 0), reverse=True)
    return reranked


def _is_explicit_gita_question(question: str) -> bool:
    """Check if the user is explicitly asking about Bhagavad Gita."""
    q_lower = question.lower()
    gita_keywords_en = ["gita", "geeta", "bhagavad", "bhagwat gita", "bhagavadgita"]
    gita_keywords_hi = ["गीता", "भगवद्गीता", "भगवत गीता", "श्रीमद्भगवद्गीता"]
    
    # Must be an explicit mention of Gita as a source
    is_gita = (
        any(kw in q_lower for kw in gita_keywords_en)
        or any(kw in question for kw in gita_keywords_hi)
    )
    
    # Additional check: "arjun" alone isn't enough — it could be about the discourse
    # Only count arjun/krishna as Gita when combined with Gita keywords
    if not is_gita:
        arjun_keywords = ["arjun", "अर्जुन", "कृष्ण ने अर्जुन"]
        verse_keywords = ["verse", "chapter", "shlok", "श्लोक", "अध्याय"]
        has_arjun = any(kw in q_lower or kw in question for kw in arjun_keywords)
        has_verse = any(kw in q_lower or kw in question for kw in verse_keywords)
        is_gita = has_arjun and has_verse
    
    return is_gita


def _should_use_gita_fallback(
    is_gita_question: bool,
    transcript_results: list,
    content_id: Optional[str],
) -> bool:
    """
    Decide if Bhagavad Gita fallback should be used.
    When user is scoped to a specific discourse, stay transcript-first and
    don't auto-switch to Gita unless the user explicitly asks for it.
    """
    if is_gita_question:
        return True
    if content_id:
        return False
    return not transcript_results


# ========== Main Chat Endpoint ==========

@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask a question — answers come from pre-loaded spiritual discourses (transcript-first)."""
    question = chat_request.question.strip()
    language = chat_request.language if chat_request.language in ["hi", "en"] else "hi"

    if not question:
        raise HTTPException(400, "Question cannot be empty")
    if len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(400, f"Question too long. Max {MAX_QUESTION_LENGTH} characters.")

    content_id = chat_request.transcript_id

    # ── Step 0: Prompt injection / jailbreak detection ──
    if llm_engine._is_prompt_injection(question):
        logger.warning(f"[Q&A] Prompt injection attempt detected: '{question[:80]}...'")
        injection_msg = (
            "यह प्रश्न मान्य नहीं है। मैं केवल आध्यात्मिक मार्गदर्शन में सहायता कर सकता हूं। कृपया महाराज जी के प्रवचनों से संबंधित प्रश्न पूछें।"
            if language == "hi" else
            "This is not a valid question. I can only help with spiritual guidance. Please ask questions related to Maharaj Ji's discourses."
        )
        response = ChatResponse(
            answer=injection_msg,
            source_type=SourceType.NOT_FOUND,
            source_reference="",
            audio_url=""
        )
        await _persist_chat(db, user, content_id, question, response)
        return response

    # ── Step 1: Greetings ──
    greetings_en = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "namaste"]
    greetings_hi = ["नमस्ते", "नमस्कार", "हेलो", "हाय", "राधे राधे", "जय श्री कृष्ण", "हरि ॐ"]
    question_lower = question.lower().strip()
    is_greeting = question_lower in greetings_en or question in greetings_hi

    if is_greeting:
        if language == "hi":
            greeting_response = "राधे राधे! मैं दिव्य वाणी AI हूं। आप महाराज जी के प्रवचनों से संबंधित कोई भी प्रश्न पूछ सकते हैं। जैसे - 'भक्ति क्या है?', 'मन को शांत कैसे करें?', 'जीवन में धैर्य कैसे रखें?'"
        else:
            greeting_response = "Radhe Radhe! I am Divya Vaani AI. You can ask any question related to Maharaj Ji's discourses. For example - 'What is devotion?', 'How to find peace of mind?', 'How to have patience in life?'"

        response = ChatResponse(
            answer=greeting_response,
            source_type=SourceType.NOT_FOUND,
            source_reference="",
            audio_url=""
        )
        await _persist_chat(db, user, content_id, question, response)
        return response

    # ── Step 2: Summary / meta-question handling ──
    if _is_summary_request(question) and content_id:
        try:
            video = await crud.get_video_by_id(db, content_id)
            if video:
                summary_text = (
                    video.summary_hi if language == "hi" else video.summary_en
                ) or video.summary_hi or video.summary_en
                if summary_text:
                    response = ChatResponse(
                        answer=summary_text,
                        source_type=SourceType.PRAVACHAN,
                        source_reference=f"Summary of: {video.title_hi or video.title or 'this discourse'}",
                        audio_url=""
                    )
                    await _persist_chat(db, user, content_id, question, response)
                    return response
                else:
                    no_summary_msg = (
                        "इस प्रवचन का सारांश अभी उपलब्ध नहीं है। कृपया वीडियो पेज पर 'Generate' बटन दबाकर सारांश बनवाएं, या कोई विशिष्ट प्रश्न पूछें।"
                        if language == "hi" else
                        "The summary for this discourse is not available yet. Please click the 'Generate' button on the video page to create a summary, or ask a specific question."
                    )
                    response = ChatResponse(
                        answer=no_summary_msg,
                        source_type=SourceType.NOT_FOUND,
                        source_reference="",
                        audio_url=""
                    )
                    await _persist_chat(db, user, content_id, question, response)
                    return response
        except Exception as e:
            logger.warning(f"Summary lookup failed for {content_id}: {e}")

    # ── Step 3: Sensitive topic detection ──
    sensitivity = _detect_sensitive_topic(question)

    if sensitivity == "OFF_TOPIC":
        off_topic_msg = (
            "यह प्रश्न मेरे विषय से बाहर है। मैं महाराज जी के प्रवचनों और भगवद्गीता से आध्यात्मिक मार्गदर्शन में सहायता कर सकता हूं। कृपया आध्यात्मिक विषय पर प्रश्न पूछें।"
            if language == "hi" else
            "This question is outside my area of expertise. I can help with spiritual guidance from Maharaj Ji's discourses and the Bhagavad Gita. Please ask a spirituality-related question."
        )
        response = ChatResponse(
            answer=off_topic_msg,
            source_type=SourceType.NOT_FOUND,
            source_reference="",
            audio_url=""
        )
        await _persist_chat(db, user, content_id, question, response)
        return response

    # Compassion instruction for distressed users
    extra_instruction = sensitivity if sensitivity and sensitivity != "OFF_TOPIC" else ""

    # ── Step 3b: Check answer cache BEFORE any expensive operations ──
    cached_response = _answer_cache.get(question, content_id, language)
    if cached_response is not None:
        await _persist_chat(db, user, content_id, question, cached_response)
        return cached_response

    # ── Step 4: Prepare search queries ──
    is_english = llm_engine.is_english_text(question)
    search_query = question

    # Translate English to Hindi for better search
    if is_english:
        hindi_question = await llm_engine.translate_to_hindi(question)
        search_query = f"{question} {hindi_question}"

    # Expand query with spiritual keywords
    expanded_query = _expand_question_for_search(search_query)

    # ── Step 5: Multi-query expansion (generate search variants) ──
    search_queries = [expanded_query]
    
    try:
        extra_queries = await llm_engine.generate_search_queries(question, language)
        if extra_queries:
            search_queries.extend(extra_queries)
    except Exception as e:
        logger.warning(f"Multi-query expansion failed (non-critical): {e}")

    # ── Step 6: TRANSCRIPT-FIRST SEARCH ──
    is_gita_question = _is_explicit_gita_question(question)
    transcript_results = []
    best_transcript_score = 0.0

    if not is_gita_question and (content_id or rag_engine.has_transcripts()):
        # Search with primary query using hybrid search
        if settings.HYBRID_SEARCH_ENABLED:
            transcript_results = rag_engine.search_transcripts_hybrid(
                expanded_query, transcript_id=content_id, top_k=8
            )
        else:
            transcript_results = rag_engine.search_transcripts_with_scores(
                expanded_query, transcript_id=content_id, top_k=8
            )

        # If strict content filtering returned nothing, retry with a slightly lower threshold.
        # This helps recover valid matches from noisy ASR transcripts.
        if content_id and not transcript_results:
            relaxed_threshold = max(settings.SIMILARITY_THRESHOLD - 0.12, 0.25)
            logger.info(
                f"[Q&A] No strict hits for content_id={content_id}; retrying with relaxed threshold={relaxed_threshold:.2f}"
            )
            if settings.HYBRID_SEARCH_ENABLED:
                transcript_results = rag_engine.search_transcripts_hybrid(
                    expanded_query,
                    transcript_id=content_id,
                    top_k=8,
                    semantic_min_score=relaxed_threshold,
                )
            else:
                transcript_results = rag_engine.search_transcripts_with_scores(
                    expanded_query,
                    transcript_id=content_id,
                    top_k=8,
                    min_score=relaxed_threshold,
                )

        # Get current best score
        initial_best = transcript_results[0].get("score", 0) if transcript_results else 0.0

        # Only do expensive multi-query expansion if initial search found SOME results
        # If best_score is near 0, the topic simply isn't in our transcripts — expansion won't help
        # and wastes 75+ seconds of CPU embedding time
        if initial_best >= 0.30 and (len(transcript_results) < 3 or initial_best < 0.55):
            for extra_q in search_queries[1:]:  # Skip first (already searched)
                try:
                    if settings.HYBRID_SEARCH_ENABLED:
                        extra_results = rag_engine.search_transcripts_hybrid(
                            extra_q, transcript_id=content_id, top_k=5
                        )
                    else:
                        extra_results = rag_engine.search_transcripts_with_scores(
                            extra_q, transcript_id=content_id, top_k=5
                        )
                    
                    # Merge: add new chunks not already in results
                    existing_ids = {r["chunk"].id for r in transcript_results}
                    for r in extra_results:
                        if r["chunk"].id not in existing_ids:
                            transcript_results.append(r)
                            existing_ids.add(r["chunk"].id)
                except Exception as e:
                    logger.warning(f"Extra query search failed: {e}")
        elif initial_best < 0.30:
            logger.info(f"[Q&A] Skipping multi-query expansion (best_score={initial_best:.3f} too low, not in transcripts)")

        # Sort by score and take top results
        transcript_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        transcript_results = transcript_results[:12]  # Keep more for re-ranking

        # ── Step 6b: Re-ranking — score context relevance to question ──
        if len(transcript_results) > 3:
            transcript_results = _rerank_results(question, transcript_results)

        # Final top 6 after re-ranking
        transcript_results = transcript_results[:6]

        if transcript_results:
            best_transcript_score = transcript_results[0].get("score", 0)

    # ── Step 6d: Fetch conversation history for follow-up context ──
    chat_history = ""
    try:
        if user and content_id:
            recent_messages = await crud.get_chat_history(db, user.id, content_id, limit=4)
            if recent_messages:
                history_parts = []
                for msg in recent_messages[-4:]:
                    role_label = "Seeker" if msg.role == "user" else "Divya Vaani AI"
                    history_parts.append(f"{role_label}: {msg.content[:300]}")
                chat_history = "\n".join(history_parts)
                logger.info(f"[Q&A] Including {len(recent_messages[-4:])} messages of conversation context")
    except Exception as e:
        logger.warning(f"Failed to fetch chat history: {e}")

    # ── Step 7: Determine source and generate answer ──
    
    # Log decision info
    logger.info(
        f"[Q&A] question='{question[:60]}...', content_id={content_id}, "
        f"is_gita_q={is_gita_question}, transcript_results={len(transcript_results)}, "
        f"best_score={best_transcript_score:.3f}"
    )

    # DECISION: Use transcripts if we have results
    if transcript_results and not is_gita_question:
        # Build context from transcript chunks
        chunks = [r["chunk"] for r in transcript_results]
        context_parts = []
        for c in chunks:
            timestamp = f"[{_format_time(c.start_time)} - {_format_time(c.end_time)}]"
            context_parts.append(f"{timestamp}: {c.text}")
        context = "\n\n".join(context_parts)

        # ── Step 7a: LLM Relevance Verification (guardrail, but NOT trigger-happy) ──
        #
        # Philosophy: It's BETTER to answer from the transcript (even if imperfect)
        # than to silently switch to Gita. The LLM prompt already handles "not directly
        # relevant" context gracefully. Only reject when we're VERY sure it's garbage.
        #
        context_is_relevant = True
        
        if settings.RELEVANCE_CHECK_ENABLED and best_transcript_score < 0.55:
            try:
                relevance = await llm_engine.verify_context_relevance(question, context, language)
                context_is_relevant = relevance.get("relevant", True)
                relevance_confidence = relevance.get("confidence", 0.5)
                
                logger.info(
                    f"[Q&A] Relevance check: relevant={context_is_relevant}, "
                    f"confidence={relevance_confidence:.2f}, reason={relevance.get('reason', '')[:60]}"
                )
                
                # Only reject when ALL of these are true:
                # 1. LLM says it's NOT relevant
                # 2. LLM is VERY confident about that (>= 0.85)
                # 3. Semantic score is genuinely low (< 0.40)
                # 4. User is NOT on a specific video page (if they are, let the answer prompt handle it)
                should_reject = (
                    not context_is_relevant
                    and relevance_confidence >= 0.85
                    and best_transcript_score < 0.40
                    and not content_id  # When user is on a video, ALWAYS try transcript answer
                )
                
                if should_reject:
                    logger.info("[Q&A] Context rejected — high confidence irrelevant + low score + no content_id")
                    transcript_results = []
                elif not context_is_relevant:
                    logger.info(
                        f"[Q&A] Context marked irrelevant but KEEPING it: "
                        f"confidence={relevance_confidence:.2f}, score={best_transcript_score:.3f}, "
                        f"content_id={'yes' if content_id else 'no'} — letting answer prompt handle it"
                    )
                    
            except Exception as e:
                logger.warning(f"Relevance check failed (allowing): {e}")

    # Generate answer from transcripts
    if transcript_results and not is_gita_question:
        chunks = [r["chunk"] for r in transcript_results]
        context_parts = []
        for c in chunks:
            timestamp = f"[{_format_time(c.start_time)} - {_format_time(c.end_time)}]"
            context_parts.append(f"{timestamp}: {c.text}")
        context = "\n\n".join(context_parts)
        
        logger.info(f"[Q&A] ✅ Answering from TRANSCRIPT ({len(chunks)} segments, best_score={best_transcript_score:.3f})")
        
        answer = await llm_engine.generate_answer(
            question, context, SourceType.PRAVACHAN, language,
            extra_instruction=extra_instruction,
            chat_history=chat_history
        )
        
        source_ref = f"Based on {len(chunks)} segments from the discourse (relevance: {best_transcript_score:.0%})"
        
        response = ChatResponse(
            answer=answer,
            source_type=SourceType.PRAVACHAN,
            source_reference=source_ref,
            audio_url=""
        )
        _answer_cache.put(question, content_id, language, response)
        await _persist_chat(db, user, content_id, question, response)
        return response

    # ── Step 8: GITA FALLBACK — but ONLY when appropriate ──
    #
    # Key principle: If the user is on a specific video page (content_id is set),
    # they expect answers FROM THAT VIDEO. Don't confuse them with Gita.
    # Instead, give an honest "not found in this discourse" response.
    #
    gita_results = []
    
    use_gita_fallback = _should_use_gita_fallback(
        is_gita_question=is_gita_question,
        transcript_results=transcript_results,
        content_id=content_id,
    )
    if use_gita_fallback:
        logger.info(f"[Q&A] Using Gita fallback (is_gita_q={is_gita_question}, content_id={content_id})")
        gita_threshold = settings.GITA_EXPLICIT_THRESHOLD if is_gita_question else settings.GITA_FALLBACK_THRESHOLD
        gita_results = rag_engine.search_gita(search_query, top_k=3, threshold=gita_threshold)
        
        if gita_results:
            best_gita_score = gita_results[0]["score"]
            logger.info(f"[Q&A] Gita search: {len(gita_results)} results, best_score={best_gita_score:.3f}")
            
            answer = await llm_engine.generate_gita_answer(
                question, gita_results, language,
                extra_instruction=extra_instruction
            )
            verse_refs = [f"Chapter {v['verse'].chapter}, Verse {v['verse'].verse}" for v in gita_results]
            
            source_ref = f"Bhagavad Gita - {', '.join(verse_refs)}"
            
            response = ChatResponse(
                answer=answer,
                source_type=SourceType.GITA,
                source_reference=source_ref,
                audio_url=""
            )
            _answer_cache.put(question, content_id, language, response)
            await _persist_chat(db, user, content_id, question, response)
            return response

    # ── Step 9: Nothing found ──
    # If user is on a specific video, give a video-specific "not found" message
    if content_id:
        logger.info(f"[Q&A] No relevant content for video {content_id}: '{question[:60]}...'")
        if language == "hi":
            not_found = (
                "इस प्रवचन में इस विषय पर सीधे चर्चा नहीं मिली। "
                "कृपया इस प्रवचन से संबंधित कोई अन्य प्रश्न पूछें, या अपना प्रश्न दूसरे शब्दों में पूछकर देखें।"
            )
        else:
            not_found = (
                "I couldn't find information about this topic in the current discourse. "
                "Please try asking another question about this discourse, or rephrase your question."
            )
    else:
        logger.info(f"[Q&A] No relevant content found for: '{question[:60]}...'")
        not_found = await llm_engine.generate_not_found(language)
    
    response = ChatResponse(
        answer=not_found,
        source_type=SourceType.NOT_FOUND,
        source_reference="",
        audio_url=""
    )
    await _persist_chat(db, user, content_id, question, response)
    return response


# ========== Persistence ==========

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
        await crud.save_chat_message(
            db, user.id, video_id, "user", question
        )
        await crud.save_chat_message(
            db, user.id, video_id, "assistant", response.answer,
            source_type=response.source_type.value if response.source_type else None,
            source_reference=response.source_reference,
            audio_url=response.audio_url,
        )
    except Exception as e:
        logger.warning(f"Failed to persist chat: {e}")


# ========== SSE Streaming Chat Endpoint ==========

def _sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
@limiter.limit("15/minute")
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE streaming version of /chat — streams LLM answer tokens in real time."""
    question = (chat_request.question or "").strip()
    language = chat_request.language or "hi"
    content_id = chat_request.transcript_id

    # ── Validation (same as /chat) ──
    if not question:
        raise HTTPException(400, "Question is required.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(400, f"Question too long (max {MAX_QUESTION_LENGTH} chars).")

    # ── Determine answer path FIRST, then stream ──
    # We run the full pipeline synchronously to figure out WHAT to answer,
    # then stream just the LLM generation part.

    # Prompt injection check
    if llm_engine._is_prompt_injection(question):
        async def _stream_blocked():
            msg = ("यह प्रश्न मेरे विषय से बाहर है। मैं महाराज जी के प्रवचनों और भगवद्गीता से आध्यात्मिक मार्गदर्शन में सहायता कर सकता हूं।"
                   if language == "hi" else
                   "This question is outside my area of expertise. I can help with spiritual guidance from Maharaj Ji's discourses and the Bhagavad Gita.")
            yield _sse_event({"type": "meta", "source_type": "not_found", "source_reference": ""})
            yield _sse_event({"type": "chunk", "text": msg})
            yield _sse_event({"type": "done"})
        return StreamingResponse(_stream_blocked(), media_type="text/event-stream")

    # Greeting check
    q_lower = question.lower().strip()
    greetings = ["radhe radhe", "radhey radhey", "ram ram", "jai shree krishna",
                 "jai gurudev", "pranam", "namaste", "hello", "hi", "hare krishna"]
    if any(q_lower.startswith(g) for g in greetings) and len(q_lower.split()) <= 5:
        # Greetings go through LLM — stream them
        pass  # Fall through to the pipeline below

    # Off-topic check
    sensitivity = _detect_sensitive_topic(question)
    if sensitivity == "OFF_TOPIC":
        async def _stream_offtopic():
            msg = ("यह प्रश्न मेरे विषय से बाहर है। मैं महाराज जी के प्रवचनों और भगवद्गीता से आध्यात्मिक मार्गदर्शन में सहायता कर सकता हूं। कृपया आध्यात्मिक विषय पर प्रश्न पूछें।"
                   if language == "hi" else
                   "This question is outside my area of expertise. I can help with spiritual guidance from Maharaj Ji's discourses and the Bhagavad Gita. Please ask a spirituality-related question.")
            yield _sse_event({"type": "meta", "source_type": "not_found", "source_reference": ""})
            yield _sse_event({"type": "chunk", "text": msg})
            yield _sse_event({"type": "done"})
        return StreamingResponse(_stream_offtopic(), media_type="text/event-stream")

    extra_instruction = sensitivity if sensitivity and sensitivity != "OFF_TOPIC" else ""

    # Cache check
    cached = _answer_cache.get(question, content_id, language)
    if cached is not None:
        async def _stream_cached():
            yield _sse_event({"type": "meta", "source_type": cached.source_type.value if cached.source_type else "not_found", "source_reference": cached.source_reference or ""})
            yield _sse_event({"type": "chunk", "text": cached.answer})
            yield _sse_event({"type": "done"})
        return StreamingResponse(_stream_cached(), media_type="text/event-stream")

    # ── Search pipeline (same as /chat) ──
    is_english = llm_engine.is_english_text(question)
    search_query = question
    if is_english:
        hindi_question = await llm_engine.translate_to_hindi(question)
        search_query = f"{question} {hindi_question}"

    expanded_query = _expand_question_for_search(search_query)
    is_gita_question = _is_explicit_gita_question(question)
    transcript_results = []
    best_transcript_score = 0.0

    if not is_gita_question and (content_id or rag_engine.has_transcripts()):
        if settings.HYBRID_SEARCH_ENABLED:
            transcript_results = rag_engine.search_transcripts_hybrid(
                expanded_query, transcript_id=content_id, top_k=8
            )
        else:
            transcript_results = rag_engine.search_transcripts(
                expanded_query, transcript_id=content_id, top_k=8
            )
        transcript_results = _rerank_results(question, transcript_results)
        if transcript_results:
            best_transcript_score = transcript_results[0].get("score", 0)

    # Conversation history
    chat_history = ""
    try:
        if user and content_id:
            recent = await crud.get_chat_history(db, user.id, content_id, limit=4)
            if recent:
                chat_history = "\n".join(
                    f"{m.role}: {m.content[:200]}" for m in recent[-4:]
                )
    except Exception:
        pass

    # ── Relevance check (same as /chat) ──
    if transcript_results and not is_gita_question:
        if settings.RELEVANCE_CHECK_ENABLED and best_transcript_score < 0.55:
            try:
                chunks = [r["chunk"] for r in transcript_results]
                context_parts = [f"[{_format_time(c.start_time)} - {_format_time(c.end_time)}]: {c.text}" for c in chunks]
                context = "\n\n".join(context_parts)
                relevance = await llm_engine.verify_context_relevance(question, context, language)
                context_is_relevant = relevance.get("relevant", True)
                confidence = relevance.get("confidence", 0.5)
                should_reject = (
                    not context_is_relevant
                    and confidence > 0.8
                    and best_transcript_score < 0.40
                    and not content_id
                )
                if should_reject:
                    transcript_results = []
            except Exception:
                pass

    # ── DECISION: Stream from transcript, Gita, or not-found ──

    if transcript_results and not is_gita_question:
        chunks = [r["chunk"] for r in transcript_results]
        context_parts = [f"[{_format_time(c.start_time)} - {_format_time(c.end_time)}]: {c.text}" for c in chunks]
        context = "\n\n".join(context_parts)
        source_ref = f"Based on {len(chunks)} segments from the discourse (relevance: {best_transcript_score:.0%})"

        async def _stream_transcript():
            yield _sse_event({"type": "meta", "source_type": "pravachan", "source_reference": source_ref})
            full_answer = []
            async for token in llm_engine.generate_answer_stream(
                question, context, SourceType.PRAVACHAN, language,
                extra_instruction=extra_instruction, chat_history=chat_history
            ):
                full_answer.append(token)
                yield _sse_event({"type": "chunk", "text": token})
            yield _sse_event({"type": "done"})
            # Cache + persist after streaming completes
            answer = "".join(full_answer)
            resp = ChatResponse(answer=answer, source_type=SourceType.PRAVACHAN, source_reference=source_ref, audio_url="")
            _answer_cache.put(question, content_id, language, resp)
            await _persist_chat(db, user, content_id, question, resp)

        return StreamingResponse(_stream_transcript(), media_type="text/event-stream")

    # Gita fallback
    use_gita = _should_use_gita_fallback(is_gita_question, transcript_results, content_id)
    if use_gita:
        gita_threshold = settings.GITA_EXPLICIT_THRESHOLD if is_gita_question else settings.GITA_FALLBACK_THRESHOLD
        gita_results = rag_engine.search_gita(search_query, top_k=3, threshold=gita_threshold)
        if gita_results:
            verse_refs = [f"Chapter {v['verse'].chapter}, Verse {v['verse'].verse}" for v in gita_results]
            source_ref = f"Bhagavad Gita - {', '.join(verse_refs)}"

            async def _stream_gita():
                yield _sse_event({"type": "meta", "source_type": "bhagavad_gita", "source_reference": source_ref})
                full_answer = []
                async for token in llm_engine.generate_gita_answer_stream(
                    question, gita_results, language, extra_instruction=extra_instruction
                ):
                    full_answer.append(token)
                    yield _sse_event({"type": "chunk", "text": token})
                yield _sse_event({"type": "done"})
                answer = "".join(full_answer)
                resp = ChatResponse(answer=answer, source_type=SourceType.GITA, source_reference=source_ref, audio_url="")
                _answer_cache.put(question, content_id, language, resp)
                await _persist_chat(db, user, content_id, question, resp)

            return StreamingResponse(_stream_gita(), media_type="text/event-stream")

    # Not found
    if content_id:
        not_found = ("इस प्रवचन में इस विषय पर सीधे चर्चा नहीं मिली। कृपया इस प्रवचन से संबंधित कोई अन्य प्रश्न पूछें, या अपना प्रश्न दूसरे शब्दों में पूछकर देखें।"
                     if language == "hi" else
                     "I couldn't find information about this topic in the current discourse. Please try asking another question about this discourse, or rephrase your question.")
    else:
        not_found = await llm_engine.generate_not_found(language)

    async def _stream_notfound():
        yield _sse_event({"type": "meta", "source_type": "not_found", "source_reference": ""})
        yield _sse_event({"type": "chunk", "text": not_found})
        yield _sse_event({"type": "done"})
    return StreamingResponse(_stream_notfound(), media_type="text/event-stream")
