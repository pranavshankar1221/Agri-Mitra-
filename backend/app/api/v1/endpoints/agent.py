import logging
import re
import time

from fastapi import APIRouter, HTTPException
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from app.core.config import settings
from app.schemas.agent import AgentQueryRequest, AgentQueryResponse
from app.services.gov_market_data_service import (
    GovernmentMarketDataService,
    MarketDataError,
)

logger = logging.getLogger(__name__)

router = APIRouter()
MARKET_QUERY_PATTERN = re.compile(
    r"\b(?:prices?|mandi|markets?|trends?|compare|highest|selling|sell|rates?)\b",
    re.IGNORECASE,
)
MARKET_TREND_PATTERN = re.compile(
    r"\b(?:trends?|changed|change|last|past|week|month|days?)\b",
    re.IGNORECASE,
)
LOCALIZED_MARKET_TERMS = (
    "कीमत", "कीमतें", "भाव", "मंडी", "बाज़ार", "बाजार", "दाम",
    "দাম", "বাজার", "ధర", "మార్కెట్", "మండి", "విలువ",
    "किंमत", "बाजारभाव", "விலை", "சந்தை", "மண்டி",
    "قیمت", "منڈی", "بازار", "ભાવ", "બજાર", "ಬೆಲೆ", "ಮಾರುಕಟ್ಟೆ",
    "ଦର", "ବଜାର", "വില", "വിപണി", "ਭਾਅ", "ਮੰਡੀ", "দাম", "বজাৰ",
)
LOCALIZED_TREND_TERMS = (
    "रुझान", "बदलाव", "पिछले", "প্রবণতা", "পরিবর্তন",
    "ధోరణి", "మార్పు", "கடந்த", "மாற்றம்", "رجحان", "تبدیلی",
    "વલણ", "ફેરફાર", "ಪ್ರವೃತ್ತಿ", "ಬದಲಾವಣೆ", "ଧାରା", "ପରିବର୍ତ୍ତନ",
    "പ്രവണത", "മാറ്റം", "ਰੁਝਾਨ", "ਤਬਦੀਲੀ", "ধাৰা",
)
MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_MESSAGE_CHARS = 1200
HISTORY_TRUNCATION_MARKER = "[Earlier message truncated]\n"
RESPONSE_LANGUAGES = {
    "en": ("English", "English"),
    "hi": ("Hindi", "हिन्दी"),
    "bn": ("Bengali", "বাংলা"),
    "te": ("Telugu", "తెలుగు"),
    "mr": ("Marathi", "मराठी"),
    "ta": ("Tamil", "தமிழ்"),
    "ur": ("Urdu", "اردو"),
    "gu": ("Gujarati", "ગુજરાતી"),
    "kn": ("Kannada", "ಕನ್ನಡ"),
    "or": ("Odia", "ଓଡ଼ିଆ"),
    "ml": ("Malayalam", "മലയാളം"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ"),
    "as": ("Assamese", "অসমীয়া"),
}


@router.post("/query", response_model=AgentQueryResponse)
def query_agent(request: AgentQueryRequest):
    """Answer using the configured NVIDIA LLM and the supplied conversation only."""
    request_started = time.perf_counter()
    market_evidence = None
    folded_query = request.query.casefold()
    asks_about_markets = (
        MARKET_QUERY_PATTERN.search(request.query) is not None
        or any(term in folded_query for term in LOCALIZED_MARKET_TERMS)
    )
    if not settings.NVIDIA_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="NVIDIA API key is not configured. Set NVIDIA_API_KEY in the environment."
        )

    market_started = time.perf_counter()
    if asks_about_markets:
        try:
            market_evidence = GovernmentMarketDataService.get_market_evidence(request.query)
        except MarketDataError as error:
            logger.warning(
                "AgriMitra request failed stage=market_data category=%s elapsed_ms=%d",
                error.category,
                round((time.perf_counter() - request_started) * 1000),
            )
            raise HTTPException(
                status_code=error.status_code,
                detail=(
                    f"Market data is unavailable: {error}. "
                    "No unverified price or trend was used."
                ),
            ) from error
    market_elapsed = time.perf_counter() - market_started

    system_prompt = (
        "You are AgriMitra, a practical agricultural assistant for Indian farmers. "
        "Answer using your learned knowledge and the conversation only. You have no "
        "live access to market prices, weather, government notices, or the user's farm "
        "data. Never imply that you checked current information and never invent "
        "current prices, forecasts, or statistics. Clearly state when an answer "
        "depends on current or local facts and recommend checking an authoritative "
        "local source. Write a clear, concise user-facing answer in simple language. "
        "Use a short opening, descriptive Markdown headings when useful, and numbered "
        "steps for procedures. Keep paragraphs brief, avoid repetition, and never "
        "include raw data fields, JSON, or private chain-of-thought."
    )
    system_prompt += " Keep standard replies focused and under 100 words unless detail is requested."
    language_name, native_language_name = RESPONSE_LANGUAGES[request.language]
    system_prompt += (
        f" Respond entirely in {language_name} ({native_language_name}), using its "
        "native script. Keep crop names, market names, numbers, units, and official "
        "source names accurate; do not translate proper nouns or change reported values."
    )
    if asks_about_markets:
        if not market_evidence or not market_evidence.records:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No matching mandi records were found. Specify a commodity "
                    "available in the data.gov.in market dataset, then retry."
                ),
            )
        system_prompt = (
            "You are AgriMitra. Answer the user's mandi-price question using only "
            "the supplied government records for factual prices. Do not invent "
            "prices, trends, transport costs, quality adjustments, or forecasts. "
            "Format the answer neatly: start with a short heading and one-sentence "
            "summary, then use a compact Markdown table for reported prices with "
            "market, location, commodity/variety, modal price (INR per quintal), "
            "and report date. List each market only once. State the data.gov.in "
            "source once after the table, not on every row. Use only values in the "
            "provided records. Do not invent totals, ranges, rankings, or trends "
            "unless they are directly computed from all the provided records. "
            "Never print raw JSON, field names, null/None values, or repeated "
            "source labels. If history is missing, say in plain language that there "
            "is not enough stored history to calculate a change. Distinguish reported "
            "facts from any brief practical interpretation."
        )
        system_prompt += (
            "\nThe supplied records are from the newest report date in the "
            "retrieved source page. If they are ordered by modal price, that order "
            "was computed from those records; describe comparisons as being only "
            "among the supplied records."
        )
        if (
            MARKET_TREND_PATTERN.search(request.query)
            or any(term in folded_query for term in LOCALIZED_TREND_TERMS)
        ):
            trend = GovernmentMarketDataService.get_trends(
                market_evidence.records[0].commodity,
                days=31,
            )
            trend_points = "; ".join(
                f"{point['report_date']}: average modal price "
                f"{point['average_modal_price']:.2f} INR per quintal "
                f"({point['observations']} reports)"
                for point in trend["points"]
            ) or "No stored historical observations"
            change_7d = trend["change_7d_pct"]
            change_30d = trend["change_30d_pct"]
            trend_summary = (
                f"7-day change: {change_7d:.2f}%"
                if change_7d is not None
                else "7-day change: unavailable because stored history is insufficient"
            )
            trend_summary += (
                f"; 30-day change: {change_30d:.2f}%"
                if change_30d is not None
                else "; 30-day change: unavailable because stored history is insufficient"
            )
            system_prompt += (
                "\nStored historical trend evidence (daily average modal prices): "
                f"{trend_points}. {trend_summary}."
            )
            system_prompt += (
                " Explain any available trend in plain language. If a 7-day or "
                "30-day change is unavailable, say there is not enough stored "
                "history; never expose internal field names."
            )
        evidence = [
            {
                "state": row.state,
                "district": row.district,
                "market": row.market,
                "commodity": row.commodity,
                "variety": row.variety,
                "report_date": row.report_date,
                "min_price": row.min_price,
                "max_price": row.max_price,
                "modal_price": row.modal_price,
                "unit": row.unit,
                "source": row.source,
            }
            for row in market_evidence.records
        ]
        system_prompt += f"\nVerified market records (JSON): {evidence!r}"
        if market_evidence.total is not None and market_evidence.total > len(evidence):
            system_prompt += (
                f"\nCoverage note: {len(evidence)} selected records from the "
                f"{market_evidence.total} matching source records were supplied. "
                "These are the latest-report-date records; comparisons are only "
                "among the supplied records and must not be presented as a "
                "nationwide or dataset-wide ranking."
            )
    if request.detailed:
        system_prompt += (
            " Give a more thorough user-facing explanation with practical "
            "considerations, without revealing private chain-of-thought."
        )
    system_prompt += (
        f"\nLANGUAGE REQUIREMENT: Write the entire user-facing answer only in "
        f"{language_name} ({native_language_name}). Use the {native_language_name} "
        "script for all explanatory text; translate explanations rather than "
        "leaving them in English. Do not switch to another language, even "
        "if previous conversation messages use one. Keep names, figures, units, "
        "and source labels accurate."
    )

    llm_started = time.perf_counter()
    try:
        llm = ChatOpenAI(
            model=settings.NVIDIA_MODEL,
            api_key=settings.NVIDIA_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            temperature=0.3,
            max_tokens=1024 if request.detailed else 512,
            timeout=settings.NVIDIA_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        messages = [("system", system_prompt)]
        for message in request.history[-MAX_HISTORY_MESSAGES:]:
            content = message.content
            if len(content) > MAX_HISTORY_MESSAGE_CHARS:
                content = (
                    HISTORY_TRUNCATION_MARKER
                    + content[-(MAX_HISTORY_MESSAGE_CHARS - len(HISTORY_TRUNCATION_MARKER)):]
                )
            messages.append((message.role, content))
        messages.append(("human", request.query))

        response = llm.invoke(messages)
        llm_elapsed = time.perf_counter() - llm_started
        content = response.content
        if isinstance(content, list):
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            )
        if not isinstance(content, str) or not content.strip():
            metadata = getattr(response, "response_metadata", {})
            logger.error(
                "NVIDIA LLM returned empty user-facing content "
                "finish_reason=%s token_usage=%s",
                metadata.get("finish_reason") if isinstance(metadata, dict) else None,
                metadata.get("token_usage") if isinstance(metadata, dict) else None,
            )
            raise RuntimeError("The model returned an empty response.")

        logger.info(
            "AgriMitra request complete market_lookup_ms=%d llm_ms=%d total_ms=%d "
            "market_query=%s market_records=%d",
            round(market_elapsed * 1000),
            round(llm_elapsed * 1000),
            round((time.perf_counter() - request_started) * 1000),
            asks_about_markets,
            market_evidence.count if market_evidence else 0,
        )
        return AgentQueryResponse(
            query=request.query,
            response=content.strip(),
        )

    except APITimeoutError as error:
        logger.warning(
            "NVIDIA LLM request timed out llm_ms=%d total_ms=%d",
            round((time.perf_counter() - llm_started) * 1000),
            round((time.perf_counter() - request_started) * 1000),
        )
        raise HTTPException(
            status_code=504,
            detail="AI request timed out. Please retry in a moment.",
        ) from error
    except RateLimitError as error:
        logger.warning("NVIDIA LLM rate limit reached.")
        raise HTTPException(
            status_code=429,
            detail="AI service is rate limited. Please wait before retrying.",
        ) from error
    except APIConnectionError as error:
        logger.warning("NVIDIA LLM connection failed.")
        raise HTTPException(
            status_code=503,
            detail="AI service is temporarily unreachable. Please retry shortly.",
        ) from error
    except APIStatusError as error:
        logger.error("NVIDIA LLM returned HTTP %d.", error.status_code)
        raise HTTPException(
            status_code=503,
            detail="AI service returned an error. Please retry shortly.",
        ) from error
    except Exception as error:
        logger.exception("NVIDIA LLM request failed")
        raise HTTPException(
            status_code=503,
            detail="AI service unavailable. Check the backend logs and try again."
        ) from error
