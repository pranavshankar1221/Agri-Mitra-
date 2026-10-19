import hashlib
import json
import logging
import math
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.market_observation import MarketObservation
from app.schemas.market import MarketPriceRecord, MarketPricesResponse

logger = logging.getLogger(__name__)

SOURCE_NAME = "data.gov.in — Current Daily Price of Various Commodities from Various Markets (Mandi)"
DATASET_FIELDS = (
    "state",
    "district",
    "market",
    "commodity",
    "variety",
    "grade",
    "arrival_date",
    "min_price",
    "max_price",
    "modal_price",
)
DATASET_COMMODITIES = (
    "Almond(Badam)", "Amaranthus", "Amla(Nelli Kai)", "Apple",
    "Arecanut(Betelnut/Supari)", "Ashgourd", "Baby Corn",
    "Bajra(Pearl Millet/Cumbu)", "Banana", "Banana - Green", "Basmati Rice",
    "Beans", "Beetroot", "Bengal Gram(Gram)(Whole)", "Betal Leaves",
    "Bhindi(Ladies Finger)", "Bitter gourd", "Black Gram Dal(Urd Dal)",
    "Black Gram(Urd Beans)(Whole)", "Black pepper", "Bottle gourd", "Brinjal",
    "Cabbage", "Capsicum", "Cardamom", "Carrot", "Castor Seed", "Cauliflower",
    "Chikoos(Sapota)", "Chilly Capsicum", "Chow Chow", "Cluster beans",
    "Coconut", "Colacasia", "Copra", "Coriander(Leaves)", "Corriander seed",
    "Cotton", "Cowpea(Lobia/Karamani)", "Cowpea(Veg)", "Cucumbar(Kheera)",
    "Custard Apple(Sharifa)", "Drumstick", "Dry Chillies",
    "Elephant Yam(Suran)/Amorphophallus", "Field Bean(Anumulu)",
    "French Beans(Frasbean)", "Garlic", "Ginger(Green)", "Grapes",
    "Green Avare(W)", "Green Chilli", "Green Gram(Moong)(Whole)", "Green Peas",
    "Ground Nut Seed", "Groundnut", "Guar", "Guar Seed(Cluster Beans Seed)",
    "Guava", "Indian Beans(Seam)", "Jasmine", "Jowar(Sorghum)",
    "Karbuja(Musk Melon)", "Knool Khol", "Kodo Millet(Varagu)",
    "Ladies Finger", "Leafy Vegetable", "Lemon", "Lime", "Little gourd(Kundru)",
    "Maize", "Mango(Raw-Ripe)", "Marigold(Calcutta)", "Methi(Leaves)",
    "Mint(Pudina)", "Mousambi(Sweet Lime)", "Mushroom", "Mustard", "Onion",
    "Onion Green", "Orange", "Paddy(Basmati)", "Paddy(Common)", "Papaya",
    "Peas Wet", "Pineapple", "Pointed gourd(Parval)", "Pomegranate", "Potato",
    "Pumpkin", "Raddish", "Red gram/Arhar/Tur(whole)", "Rice",
    "Ridgeguard(Tori)", "Rose(Local)", "Safflower", "Snakeguard", "Soanf",
    "Soyabean", "Spinach", "Sponge gourd", "Sweet Corn", "Sweet Potato",
    "Tamarind Fruit", "Tapioca", "Tender Coconut", "Thondekai", "Tinda",
    "Tomato", "Turnip", "Water Melon", "Wheat", "Wood", "Yam(Ratalu)",
)
COMMODITY_ALIASES = {
    "tomatoes": "Tomato",
    "tamatar": "Tomato",
    "टमाटर": "Tomato",
    "టమాటా": "Tomato",
    "தக்காளி": "Tomato",
    "টমেটো": "Tomato",
    "onions": "Onion",
    "pyaaz": "Onion",
    "pyaz": "Onion",
    "प्याज": "Onion",
    "ఉల్లిపాయ": "Onion",
    "வெங்காயம்": "Onion",
    "পেঁয়াজ": "Onion",
    "potatoes": "Potato",
    "आलू": "Potato",
    "బంగాళాదుంప": "Potato",
    "உருளைக்கிழங்கு": "Potato",
    "আলু": "Potato",
    "चावल": "Rice",
    "धान": "Paddy(Common)",
    "wheat": "Wheat",
    "गेहूं": "Wheat",
    "గోధుమ": "Wheat",
    "கோதுமை": "Wheat",
    "গম": "Wheat",
    "cotton": "Cotton",
    "કપાસ": "Cotton",
    "పత్తి": "Cotton",
    "பருத்தி": "Cotton",
}
FILTER_FIELDS = {
    "state": "state",
    "district": "district",
    "market": "market",
    "commodity": "commodity",
    "date": "arrival_date",
}

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()
MAX_PROVIDER_ATTEMPTS = 2
MAX_CACHE_ENTRIES = 512
MAX_CHAT_MARKET_EVIDENCE = 5
MAX_CHAT_COMPARISON_EVIDENCE = 5
MARKET_COMPARISON_PATTERN = re.compile(
    r"\b(?:compare|comparison|highest|lowest|cheapest|costliest|"
    r"most expensive|best priced|which market)\b",
    re.IGNORECASE,
)
MARKET_COMPARISON_TERMS = (
    "तुलना", "सबसे महंगा", "सबसे सस्ता", "ഏറ്റവും വില", "తులన",
    "ஒப்பிடு", "மிகவும் விலை", "তুলনা", "তুলনা", "موازنہ",
    "అత్యధిక ధర", "સૌથી વધુ", "அதிக விலை", "સૌથી સસ્તું",
)
MARKET_LOCATION_PATTERN = re.compile(
    r"\b(?:in|near|at|around|within)\s+[\w-]+",
    re.IGNORECASE,
)


class MarketDataError(Exception):
    def __init__(self, status_code: int, message: str, category: str = "provider_error"):
        super().__init__(message)
        self.status_code = status_code
        self.category = category


def _safe_detail(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    detail = value
    for secret in (settings.DATA_GOV_API_KEY, quote_plus(settings.DATA_GOV_API_KEY)):
        if secret:
            detail = detail.replace(secret, "[redacted]")
    detail = re.sub(
        r"(?i)(api[-_]?key\s*[=:]\s*)[^&\s,}\"']+",
        r"\1[redacted]",
        detail,
    )
    detail = " ".join(detail.split())
    return detail[:240] or None


def _response_diagnostics(response: httpx.Response) -> tuple[str, str, str | None]:
    content_type = response.headers.get("content-type", "missing")
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError:
            structure = "non-json"
            detail = None
        else:
            root_name = root.tag.rsplit("}", 1)[-1]
            records = _xml_record_nodes(root)
            fields = _xml_field_names(records[0]) if records else []
            structure = (
                f"xml root={root_name}; record_nodes={len(records)}; "
                f"first_record_fields={fields}"
            )
            detail = None
    else:
        if isinstance(payload, dict):
            keys = sorted(str(key) for key in payload)
            records = payload.get("records")
            record_fields = (
                sorted(str(key) for key in records[0])
                if isinstance(records, list) and records and isinstance(records[0], dict)
                else []
            )
            structure = (
                f"object keys={keys}; records_count="
                f"{len(records) if isinstance(records, list) else 'missing'}; "
                f"first_record_fields={record_fields}"
            )
            detail = next(
                (
                    _safe_detail(payload.get(key))
                    for key in ("message", "error", "detail", "description")
                    if _safe_detail(payload.get(key))
                ),
                None,
            )
        elif isinstance(payload, list):
            structure = f"array length={len(payload)}"
            detail = None
        else:
            structure = f"scalar type={type(payload).__name__}"
            detail = None
    return content_type, structure, detail


def _xml_record_nodes(root: ElementTree.Element) -> list[ElementTree.Element]:
    records = next(
        (
            element
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].casefold() == "records"
        ),
        None,
    )
    if records is not None:
        return list(records)
    return [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].casefold() in {"record", "row"}
    ]


def _xml_field_names(record: ElementTree.Element) -> list[str]:
    return sorted(child.tag.rsplit("}", 1)[-1].casefold() for child in record)


def _response_payload(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "").casefold()
    if "xml" in content_type:
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as error:
            raise MarketDataError(
                502,
                "data.gov.in returned malformed XML instead of market records.",
                "invalid_response",
            ) from error
        nodes = _xml_record_nodes(root)
        records: list[dict[str, str | None]] = []
        for node in nodes:
            record = {
                child.tag.rsplit("}", 1)[-1].casefold():
                    child.text.strip() if child.text else None
                for child in node
            }
            if record:
                records.append(record)
        if not records:
            root_name = root.tag.rsplit("}", 1)[-1]
            raise MarketDataError(
                502,
                f"data.gov.in returned XML metadata (root '{root_name}'), not market price records.",
                "metadata_response",
            )
        total = next(
            (
                element.text.strip()
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1].casefold() == "total"
                and element.text
            ),
            str(len(records)),
        )
        return {"records": records, "total": total}

    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as error:
        if response.content.lstrip().startswith(b"<"):
            raise MarketDataError(
                502,
                "data.gov.in returned XML without a records content type.",
                "unexpected_xml",
            ) from error
        raise MarketDataError(
            502,
            f"data.gov.in returned an invalid response "
            f"(content type: {response.headers.get('content-type', 'missing')}).",
            "invalid_response",
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise MarketDataError(
            502,
            "data.gov.in response schema is missing the expected records list.",
            "invalid_response",
        )
    return payload


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() in ("", "NA", "N/A", "-", "null"):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _record_key(record: MarketPriceRecord) -> str:
    fields = {
        "state": record.state,
        "district": record.district,
        "market": record.market,
        "commodity": record.commodity,
        "variety": record.variety,
        "grade": record.grade,
        "report_date": record.report_date,
    }
    raw = json.dumps(fields, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class GovernmentMarketDataService:
    @staticmethod
    def _validate_config() -> None:
        if not settings.DATA_GOV_API_KEY:
            raise MarketDataError(503, "DATA_GOV_API_KEY is not configured.")
        if not settings.DATA_GOV_RESOURCE_ID:
            raise MarketDataError(503, "DATA_GOV_RESOURCE_ID is not configured.")

    @staticmethod
    def _normalize_record(
        source_record: dict[str, Any],
        retrieved_at: str,
    ) -> MarketPriceRecord | None:
        commodity = str(source_record.get("commodity") or "").strip()
        market = str(source_record.get("market") or "").strip()
        report_date = str(source_record.get("arrival_date") or "").strip()
        if not commodity or not market or not report_date:
            return None
        return MarketPriceRecord(
            state=_optional_text(source_record.get("state")),
            district=_optional_text(source_record.get("district")),
            market=market,
            commodity=commodity,
            variety=_optional_text(source_record.get("variety")),
            grade=_optional_text(source_record.get("grade")),
            report_date=report_date,
            min_price=_number(source_record.get("min_price")),
            max_price=_number(source_record.get("max_price")),
            modal_price=_number(source_record.get("modal_price")),
            unit="INR per quintal",
            source=SOURCE_NAME,
            retrieved_at=retrieved_at,
            source_values={
                field: source_record.get(field)
                for field in DATASET_FIELDS
                if field in source_record
            },
        )

    @staticmethod
    def fetch_prices(
        *,
        state: str | None = None,
        district: str | None = None,
        market: str | None = None,
        commodity: str | None = None,
        report_date: str | None = None,
        limit: int = 10,
        offset: int = 0,
        refresh: bool = False,
    ) -> MarketPricesResponse:
        GovernmentMarketDataService._validate_config()
        filters = {
            "state": state,
            "district": district,
            "market": market,
            "commodity": commodity,
            "date": report_date,
        }
        cache_key = json.dumps(
            {"filters": filters, "limit": limit, "offset": offset},
            sort_keys=True,
        )
        request_started = time.perf_counter()
        now = time.monotonic()
        with _cache_lock:
            cached = _cache.get(cache_key)
            if not refresh and cached and cached[0] > now:
                logger.info(
                    "data.gov.in cache hit elapsed_ms=%d limit=%d offset=%d",
                    round((time.perf_counter() - request_started) * 1000),
                    limit,
                    offset,
                )
                return MarketPricesResponse.model_validate(cached[1])

        params: dict[str, str | int] = {
            "api-key": settings.DATA_GOV_API_KEY,
            "format": "json",
            "limit": limit,
            "offset": offset,
        }
        for name, value in filters.items():
            if value:
                params[f"filters[{FILTER_FIELDS[name]}]"] = value

        url = f"{settings.DATA_GOV_API_BASE.rstrip('/')}/{settings.DATA_GOV_RESOURCE_ID}"
        logger.info(
            "data.gov.in request started method=GET endpoint=%s resource_id=%s "
            "filter_fields=%s limit=%d offset=%d",
            url,
            settings.DATA_GOV_RESOURCE_ID,
            sorted(key for key, value in filters.items() if value),
            limit,
            offset,
        )
        response = None
        for attempt in range(MAX_PROVIDER_ATTEMPTS):
            try:
                response = httpx.get(
                    url,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "AgriMitra/0.1",
                    },
                    timeout=httpx.Timeout(
                        connect=settings.DATA_GOV_CONNECT_TIMEOUT_SECONDS,
                        read=settings.DATA_GOV_READ_TIMEOUT_SECONDS,
                        write=5.0,
                        pool=5.0,
                    ),
                )
            except httpx.TimeoutException as error:
                logger.warning(
                    "data.gov.in request timed out attempt=%d/%d exception_type=%s "
                    "status=unavailable content_type=unavailable response_structure=unavailable",
                    attempt + 1,
                    MAX_PROVIDER_ATTEMPTS,
                    type(error).__name__,
                )
                is_connect_timeout = isinstance(error, httpx.ConnectTimeout)
                if is_connect_timeout and attempt + 1 < MAX_PROVIDER_ATTEMPTS:
                    continue
                category = "connect_timeout" if is_connect_timeout else "read_timeout"
                timeout_seconds = (
                    settings.DATA_GOV_CONNECT_TIMEOUT_SECONDS
                    if is_connect_timeout
                    else settings.DATA_GOV_READ_TIMEOUT_SECONDS
                )
                raise MarketDataError(
                    504,
                    f"data.gov.in {category.replace('_', ' ')} after "
                    f"{attempt + 1} attempt(s) ({timeout_seconds:g}-second timeout).",
                    category,
                ) from error
            except httpx.RequestError as error:
                logger.warning(
                    "data.gov.in request failed attempt=%d/%d exception_type=%s "
                    "status=unavailable content_type=unavailable response_structure=unavailable",
                    attempt + 1,
                    MAX_PROVIDER_ATTEMPTS,
                    type(error).__name__,
                )
                if attempt + 1 < MAX_PROVIDER_ATTEMPTS:
                    continue
                raise MarketDataError(
                    503,
                    f"data.gov.in network request failed ({type(error).__name__}).",
                    "network_error",
                ) from error

            content_type, structure, upstream_detail = _response_diagnostics(response)
            logger.info(
                "data.gov.in response status=%d content_type=%s structure=%s",
                response.status_code,
                content_type,
                structure,
            )

            if response.status_code == 429:
                logger.warning("data.gov.in rate limited request status=429")
                raise MarketDataError(
                    429,
                    "data.gov.in rate limit reached (HTTP 429). Retry after a delay.",
                    "rate_limited",
                )
            if response.status_code in (401, 403):
                logger.error(
                    "data.gov.in authorization rejected status=%d content_type=%s detail=%s",
                    response.status_code,
                    content_type,
                    upstream_detail or "not provided",
                )
                message = (
                    "data.gov.in rejected the API key (HTTP 401). Verify that "
                    "DATA_GOV_API_KEY is valid and active."
                    if response.status_code == 401
                    else "data.gov.in denied access (HTTP 403). Verify the API key permissions "
                    "and access to this resource."
                )
                raise MarketDataError(502, message, "authentication_error")
            if response.status_code == 400 and upstream_detail and any(
                marker in upstream_detail.casefold()
                for marker in ("authorization", "authentication", "api key", "api-key")
            ):
                logger.error(
                    "data.gov.in authentication parameter missing/rejected status=400 "
                    "content_type=%s detail=%s",
                    content_type,
                    upstream_detail,
                )
                raise MarketDataError(
                    502,
                    "data.gov.in reported an authorization error (HTTP 400). Verify "
                    "the API key is supplied as the api-key query parameter.",
                    "authentication_error",
                )
            if response.status_code in (400, 404):
                logger.error(
                    "data.gov.in rejected resource request status=%d content_type=%s detail=%s",
                    response.status_code,
                    content_type,
                    upstream_detail or "not provided",
                )
                message = (
                    "data.gov.in rejected the request (HTTP 400). Verify the resource ID "
                    "and supported query parameters."
                    if response.status_code == 400
                    else "data.gov.in resource was not found (HTTP 404). Verify DATA_GOV_RESOURCE_ID."
                )
                raise MarketDataError(502, message, "invalid_request")
            if response.status_code >= 500:
                if attempt + 1 < MAX_PROVIDER_ATTEMPTS:
                    continue
                logger.error(
                    "data.gov.in provider failure status=%d content_type=%s detail=%s",
                    response.status_code,
                    content_type,
                    upstream_detail or "not provided",
                )
                raise MarketDataError(
                    503,
                    f"data.gov.in provider unavailable (HTTP {response.status_code}).",
                    "provider_unavailable",
                )
            if response.status_code >= 400:
                logger.error(
                    "data.gov.in unexpected client error status=%d content_type=%s detail=%s",
                    response.status_code,
                    content_type,
                    upstream_detail or "not provided",
                )
                raise MarketDataError(
                    502,
                    f"data.gov.in returned HTTP {response.status_code}.",
                    "provider_error",
                )
            break

        if response is None:
            raise MarketDataError(
                503,
                "data.gov.in returned no response.",
                "provider_unavailable",
            )
        try:
            payload = _response_payload(response)
        except MarketDataError as error:
            content_type, structure, upstream_detail = _response_diagnostics(response)
            logger.error(
                "data.gov.in response parsing failed category=%s status=%d "
                "content_type=%s structure=%s detail=%s",
                error.category,
                response.status_code,
                content_type,
                structure,
                upstream_detail or "not provided",
            )
            raise

        retrieved_at = datetime.now(timezone.utc).isoformat()
        records = [
            normalized
            for item in payload["records"]
            if isinstance(item, dict)
            and (normalized := GovernmentMarketDataService._normalize_record(item, retrieved_at))
            is not None
        ]
        if not payload["records"]:
            logger.info("data.gov.in returned an empty result set.")
        if payload["records"] and not records:
            source_fields = sorted(
                {
                    str(key)
                    for item in payload["records"]
                    if isinstance(item, dict)
                    for key in item
                }
            )
            logger.error(
                "data.gov.in records contain no parseable observations; "
                "observed_fields=%s expected_fields=%s",
                source_fields,
                list(DATASET_FIELDS),
            )
            raise MarketDataError(
                502,
                "data.gov.in records did not contain expected mandi fields "
                "(commodity, market, and arrival_date).",
                "invalid_response",
            )
        total = payload.get("total")
        try:
            total = int(total) if total is not None else None
        except (TypeError, ValueError):
            total = None

        result = MarketPricesResponse(
            records=records,
            count=len(records),
            total=total,
            limit=limit,
            offset=offset,
            source=SOURCE_NAME,
            retrieved_at=retrieved_at,
        )
        logger.info(
            "data.gov.in request complete elapsed_ms=%d records=%d limit=%d offset=%d",
            round((time.perf_counter() - request_started) * 1000),
            result.count,
            limit,
            offset,
        )
        try:
            GovernmentMarketDataService._store_observations(records)
        except SQLAlchemyError:
            result.history_saved = False
            result.history_warning = (
                "Current source records were retrieved, but historical storage failed."
            )
            logger.warning(
                "Returning verified market records despite an observation-storage failure."
            )
        with _cache_lock:
            expired = [
                key for key, (expires_at, _) in _cache.items()
                if expires_at <= time.monotonic()
            ]
            for key in expired:
                _cache.pop(key, None)
            if cache_key not in _cache and len(_cache) >= MAX_CACHE_ENTRIES:
                oldest_key = min(_cache, key=lambda key: _cache[key][0])
                _cache.pop(oldest_key)
            _cache[cache_key] = (
                time.monotonic() + max(0, settings.DATA_GOV_CACHE_TTL_SECONDS),
                result.model_dump(mode="json"),
            )
        return result

    @staticmethod
    def _store_observations(records: list[MarketPriceRecord]) -> None:
        if not records:
            return
        MarketObservation.__table__.create(bind=engine, checkfirst=True)
        session = SessionLocal()
        try:
            for record in records:
                record_key = _record_key(record)
                source_payload = json.dumps(record.source_values, sort_keys=True)
                values = {
                    "id": record_key,
                    "record_key": record_key,
                    "state": record.state,
                    "district": record.district,
                    "market": record.market,
                    "commodity": record.commodity,
                    "variety": record.variety,
                    "report_date": record.report_date,
                    "min_price": record.min_price,
                    "max_price": record.max_price,
                    "modal_price": record.modal_price,
                    "unit": record.unit,
                    "source": record.source,
                    "source_payload": source_payload,
                    "retrieved_at": datetime.fromisoformat(record.retrieved_at),
                }
                statement = (
                    sqlite_insert(MarketObservation)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=["record_key"],
                        set_={
                            "min_price": values["min_price"],
                            "max_price": values["max_price"],
                            "modal_price": values["modal_price"],
                            "source_payload": values["source_payload"],
                            "retrieved_at": values["retrieved_at"],
                        },
                    )
                )
                session.execute(statement)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Unable to persist government market observations.")
            raise
        finally:
            session.close()

    @staticmethod
    def get_trends(
        commodity: str,
        *,
        state: str | None = None,
        district: str | None = None,
        market: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        MarketObservation.__table__.create(bind=engine, checkfirst=True)
        session = SessionLocal()
        try:
            statement = select(MarketObservation).where(
                MarketObservation.commodity.ilike(commodity),
                MarketObservation.modal_price.is_not(None),
            )
            if state:
                statement = statement.where(MarketObservation.state.ilike(state))
            if district:
                statement = statement.where(MarketObservation.district.ilike(district))
            if market:
                statement = statement.where(MarketObservation.market.ilike(market))
            observations = session.execute(statement).scalars().all()
        finally:
            session.close()

        by_date: dict[str, list[float]] = {}
        for observation in observations:
            try:
                report_day = datetime.strptime(observation.report_date, "%d/%m/%Y").date()
            except ValueError:
                try:
                    report_day = datetime.strptime(observation.report_date, "%Y-%m-%d").date()
                except ValueError:
                    continue
            by_date.setdefault(report_day.isoformat(), []).append(observation.modal_price)

        points = [
            {
                "report_date": day,
                "average_modal_price": sum(prices) / len(prices),
                "observations": len(prices),
            }
            for day, prices in sorted(by_date.items())
        ][-days:]
        latest_day = datetime.strptime(points[-1]["report_date"], "%Y-%m-%d").date() if points else None

        def change_at(period: int) -> float | None:
            if latest_day is None or not points:
                return None
            target = latest_day.fromordinal(latest_day.toordinal() - period)
            baseline = next(
                (
                    point["average_modal_price"]
                    for point in reversed(points)
                    if datetime.strptime(point["report_date"], "%Y-%m-%d").date() <= target
                ),
                None,
            )
            current = points[-1]["average_modal_price"]
            if baseline is None or baseline == 0:
                return None
            return (current - baseline) / baseline * 100

        return {
            "commodity": commodity,
            "market": market,
            "unit": "INR per quintal",
            "points": points,
            "change_7d_pct": change_at(7),
            "change_30d_pct": change_at(30),
            "source": SOURCE_NAME,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def get_market_evidence(query: str) -> MarketPricesResponse | None:
        query_folded = query.casefold()
        matches: list[tuple[int, str]] = []
        for commodity in _known_commodities():
            if re.search(
                rf"(?<!\w){re.escape(commodity.casefold())}(?!\w)",
                query_folded,
            ):
                matches.append((len(commodity), commodity))
        for alias, commodity in COMMODITY_ALIASES.items():
            if re.search(
                rf"(?<!\w){re.escape(alias.casefold())}(?!\w)",
                query_folded,
            ):
                matches.append((len(alias), commodity))
        if not matches:
            return None
        commodity = max(matches, key=lambda match: match[0])[1]
        needs_comparison = (
            MARKET_COMPARISON_PATTERN.search(query) is not None
            or any(term in query_folded for term in MARKET_COMPARISON_TERMS)
        )
        needs_location_search = MARKET_LOCATION_PATTERN.search(query) is not None
        records = GovernmentMarketDataService.fetch_prices(
            commodity=commodity,
            limit=(
                1000
                if needs_comparison or needs_location_search
                else MAX_CHAT_MARKET_EVIDENCE
            ),
        )
        comparable_locations = {
            value
            for record in records.records
            for value in (record.market, record.district, record.state)
            if value and len(value) > 3 and value.casefold() not in {
                "market", "markets", "mandi", "price", "prices",
            }
        }
        mentioned_locations = {
            location
            for location in comparable_locations
            if re.search(
                rf"(?<!\w){re.escape(location.casefold())}(?!\w)",
                query_folded,
            )
        }
        localized = [
            record
            for record in records.records
            if any(
                location.casefold() in {
                    value.casefold()
                    for value in (record.market, record.district, record.state)
                    if value
                }
                for location in mentioned_locations
            )
        ]
        candidates = localized or records.records
        dated_candidates = [
            (record, _report_date_sort_key(record.report_date))
            for record in candidates
        ]
        latest_date = max(
            (date_key for _, date_key in dated_candidates if date_key is not None),
            default=None,
        )
        latest_records = [
            record
            for record, date_key in dated_candidates
            if date_key == latest_date
        ] if latest_date is not None else candidates
        if needs_comparison:
            ranked_records = sorted(
                latest_records,
                key=lambda record: (
                    record.modal_price is not None,
                    record.modal_price if record.modal_price is not None else float("-inf"),
                ),
                reverse=True,
            )
            selected_records = [
                record for record in ranked_records if record.modal_price is not None
            ][:MAX_CHAT_COMPARISON_EVIDENCE]
        else:
            selected_records = latest_records[:MAX_CHAT_MARKET_EVIDENCE]
        return MarketPricesResponse(
            records=selected_records,
            count=len(selected_records),
            total=records.total,
            limit=records.limit,
            offset=records.offset,
            source=records.source,
            retrieved_at=records.retrieved_at,
            history_saved=records.history_saved,
            history_warning=records.history_warning,
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _report_date_sort_key(value: str) -> datetime | None:
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    return None


def _known_commodities() -> set[str]:
    commodities = set(DATASET_COMMODITIES)
    try:
        MarketObservation.__table__.create(bind=engine, checkfirst=True)
        with SessionLocal() as session:
            commodities.update(
                commodity
                for commodity in session.execute(
                    select(MarketObservation.commodity).distinct()
                ).scalars()
                if commodity
            )
    except SQLAlchemyError:
        logger.exception(
            "Unable to load previously observed mandi commodity names; "
            "using the verified built-in dataset list."
        )
    return commodities


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
