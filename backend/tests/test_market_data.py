import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import agent, market
from app.core.config import settings
from app.main import app
from app.models.market_observation import MarketObservation
from app.schemas.market import MarketPriceRecord, MarketPricesResponse
from app.services import gov_market_data_service as service


SOURCE_RECORD = {
    "state": "Maharashtra",
    "district": "Nashik",
    "market": "Nashik",
    "commodity": "Tomato",
    "variety": "Local",
    "grade": "A",
    "arrival_date": "01/10/2026",
    "min_price": "1000",
    "max_price": "2000",
    "modal_price": "1500",
}


class GovernmentMarketDataTests(unittest.TestCase):
    def setUp(self):
        service.clear_cache()
        self.api_key_patch = patch.object(settings, "DATA_GOV_API_KEY", "test-api-key")
        self.resource_patch = patch.object(
            settings,
            "DATA_GOV_RESOURCE_ID",
            "resource-id",
        )
        self.api_key_patch.start()
        self.resource_patch.start()
        self.addCleanup(self.api_key_patch.stop)
        self.addCleanup(self.resource_patch.stop)

    def tearDown(self):
        service.clear_cache()

    @staticmethod
    def response(status_code, payload=None):
        class Response:
            def __init__(self):
                self.status_code = status_code
                self.headers = {"content-type": "application/json"}

            def json(self):
                return payload

        return Response()

    def test_successful_response_normalizes_values_and_sends_official_filters(self):
        fake_response = self.response(
            200,
            {"records": [SOURCE_RECORD], "total": "1"},
        )
        with (
            patch.object(service.httpx, "get", return_value=fake_response) as get,
            patch.object(service.GovernmentMarketDataService, "_store_observations"),
        ):
            result = service.GovernmentMarketDataService.fetch_prices(
                commodity="Tomato",
                state="Maharashtra",
                report_date="01/10/2026",
                limit=20,
                offset=40,
            )

        self.assertEqual(result.count, 1)
        self.assertEqual(result.total, 1)
        record = result.records[0]
        self.assertEqual(record.modal_price, 1500.0)
        self.assertEqual(record.unit, "INR per quintal")
        self.assertEqual(record.report_date, "01/10/2026")
        self.assertEqual(record.grade, "A")
        self.assertEqual(record.source_values["modal_price"], "1500")
        self.assertNotIn("test-api-key", result.model_dump_json())
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["filters[commodity]"], "Tomato")
        self.assertEqual(params["filters[state]"], "Maharashtra")
        self.assertEqual(params["filters[arrival_date]"], "01/10/2026")
        self.assertEqual(params["limit"], 20)
        self.assertEqual(params["offset"], 40)
        self.assertNotIn("sort[arrival_date]", params)
        timeout = get.call_args.kwargs["timeout"]
        self.assertEqual(timeout.connect, settings.DATA_GOV_CONNECT_TIMEOUT_SECONDS)
        self.assertEqual(timeout.read, settings.DATA_GOV_READ_TIMEOUT_SECONDS)
        self.assertEqual(timeout.write, 5.0)
        headers = get.call_args.kwargs["headers"]
        self.assertEqual(headers["User-Agent"], "AgriMitra/0.1")
        self.assertEqual(headers["Accept"], "application/json")

    def test_unfiltered_default_request_is_small_and_uses_resource_records_path(self):
        fake_response = self.response(200, {"records": [], "total": 0})
        with (
            patch.object(service.httpx, "get", return_value=fake_response) as get,
            patch.object(service.GovernmentMarketDataService, "_store_observations"),
        ):
            result = service.GovernmentMarketDataService.fetch_prices(refresh=True)

        self.assertEqual(result.records, [])
        self.assertEqual(
            get.call_args.args[0],
            "https://api.data.gov.in/resource/resource-id",
        )
        params = get.call_args.kwargs["params"]
        self.assertEqual(
            params,
            {
                "api-key": "test-api-key",
                "format": "json",
                "limit": 10,
                "offset": 0,
            },
        )
        self.assertEqual(get.call_args.kwargs["headers"]["User-Agent"], "AgriMitra/0.1")

    def test_xml_price_records_are_parsed_using_their_content_type(self):
        xml = b"""<?xml version="1.0"?>
        <response><total>1</total><records><item>
          <state>Maharashtra</state><district>Nashik</district>
          <market>Nashik</market><commodity>Tomato</commodity>
          <variety>Local</variety><arrival_date>01/10/2026</arrival_date>
          <min_price>1000</min_price><max_price>2000</max_price>
          <modal_price>1500</modal_price>
        </item></records></response>"""
        response = httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            content=xml,
        )
        with (
            patch.object(service.httpx, "get", return_value=response),
            patch.object(service.GovernmentMarketDataService, "_store_observations"),
        ):
            result = service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(result.count, 1)
        self.assertEqual(result.records[0].commodity, "Tomato")
        self.assertEqual(result.records[0].modal_price, 1500)

    def test_xml_metadata_is_not_mistaken_for_price_records(self):
        metadata = b"""<?xml version="1.0"?>
        <response><index_name>9ef84268-d588-465a-a308-a864a43d0070</index_name>
        <title>Current Daily Price of Various Commodities</title>
        <field><item><name>State</name><id>state</id></item></field>
        </response>"""
        response = httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            content=metadata,
        )
        with patch.object(service.httpx, "get", return_value=response):
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.category, "metadata_response")
        self.assertIn("not market price records", str(raised.exception))

    def test_empty_and_incomplete_source_records_are_safe(self):
        with (
            patch.object(
                service.httpx,
                "get",
                return_value=self.response(
                    200,
                    {
                        "records": [
                            {"commodity": "Tomato", "market": "Nashik"},
                            {
                                **SOURCE_RECORD,
                                "min_price": "NA",
                                "max_price": None,
                                "modal_price": "unknown",
                            },
                        ],
                        "total": 0,
                    },
                ),
            ),
            patch.object(service.GovernmentMarketDataService, "_store_observations"),
        ):
            result = service.GovernmentMarketDataService.fetch_prices()
        self.assertEqual(result.count, 1)
        self.assertIsNone(result.records[0].min_price)
        self.assertIsNone(result.records[0].max_price)
        self.assertIsNone(result.records[0].modal_price)

        service.clear_cache()
        with (
            patch.object(
                service.httpx,
                "get",
                return_value=self.response(200, {"records": [], "total": 0}),
            ),
            patch.object(service.GovernmentMarketDataService, "_store_observations"),
        ):
            empty = service.GovernmentMarketDataService.fetch_prices()
        self.assertEqual(empty.records, [])
        self.assertEqual(empty.total, 0)

    def test_storage_failure_does_not_hide_verified_source_records(self):
        with (
            patch.object(
                service.httpx,
                "get",
                return_value=self.response(200, {"records": [SOURCE_RECORD], "total": 1}),
            ),
            patch.object(
                service.GovernmentMarketDataService,
                "_store_observations",
                side_effect=SQLAlchemyError("database unavailable"),
            ),
            self.assertLogs(service.logger, level="WARNING"),
        ):
            result = service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(result.count, 1)
        self.assertEqual(result.records[0].commodity, "Tomato")
        self.assertFalse(result.history_saved)
        self.assertIn("historical storage failed", result.history_warning)

    def test_missing_api_configuration_is_reported(self):
        with patch.object(settings, "DATA_GOV_API_KEY", ""):
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices()
        self.assertEqual(raised.exception.status_code, 503)
        with patch.object(settings, "DATA_GOV_RESOURCE_ID", ""):
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices()
        self.assertEqual(raised.exception.status_code, 503)

    def test_rate_limit_is_not_retried_or_hidden(self):
        with patch.object(
            service.httpx,
            "get",
            return_value=self.response(429),
        ) as get:
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(get.call_count, 1)

    def test_server_errors_are_retried_once_then_reported_as_unavailable(self):
        with patch.object(
            service.httpx,
            "get",
            side_effect=[self.response(503), self.response(503)],
        ) as get:
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(get.call_count, 2)

    def test_read_timeout_is_not_retried_then_reported(self):
        with patch.object(
            service.httpx,
            "get",
            side_effect=httpx.TimeoutException("timeout"),
        ) as get:
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(get.call_count, 1)
        self.assertIn("after 1 attempt", str(raised.exception))
        self.assertIn("15-second timeout", str(raised.exception))

    def test_network_failure_is_retried_once_then_reported(self):
        with patch.object(
            service.httpx,
            "get",
            side_effect=httpx.ConnectError("offline"),
        ) as get:
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(get.call_count, 2)

    def test_http_error_and_invalid_schema_do_not_return_fake_prices(self):
        with patch.object(
            service.httpx,
            "get",
            return_value=self.response(403, {"error": "Forbidden"}),
        ):
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.category, "authentication_error")
        self.assertIn("HTTP 403", str(raised.exception))

        service.clear_cache()
        with patch.object(
            service.httpx,
            "get",
            return_value=self.response(200, {"data": []}),
        ):
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.category, "invalid_response")

    def test_authentication_and_invalid_request_errors_are_distinguished(self):
        for status_code, category, phrase in (
            (401, "authentication_error", "API key"),
            (403, "authentication_error", "denied access"),
            (400, "invalid_request", "HTTP 400"),
            (404, "invalid_request", "resource was not found"),
        ):
            service.clear_cache()
            with patch.object(
                service.httpx,
                "get",
                return_value=self.response(status_code, {"message": "upstream detail"}),
            ):
                with self.assertRaises(service.MarketDataError) as raised:
                    service.GovernmentMarketDataService.fetch_prices(refresh=True)
            self.assertEqual(raised.exception.category, category)
            self.assertIn(phrase, str(raised.exception))

    def test_authorization_missing_provider_error_is_not_misreported_as_bad_resource(self):
        with patch.object(
            service.httpx,
            "get",
            return_value=self.response(400, {"error": "Authorization field missing"}),
        ):
            with self.assertRaises(service.MarketDataError) as raised:
                service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.category, "authentication_error")
        self.assertIn("authorization error", str(raised.exception))

    def test_provider_logs_response_shape_and_redacts_api_key(self):
        key = settings.DATA_GOV_API_KEY
        fake_response = self.response(
            403,
            {
                "error": f"API key {key} rejected",
                "records": [{"state": "Maharashtra", "api-key": key}],
            },
        )
        with self.assertLogs(service.logger, level="INFO") as captured:
            with patch.object(service.httpx, "get", return_value=fake_response):
                with self.assertRaises(service.MarketDataError):
                    service.GovernmentMarketDataService.fetch_prices(refresh=True)
        combined = "\n".join(captured.output)
        self.assertIn("status=403", combined)
        self.assertIn("content_type=application/json", combined)
        self.assertIn("first_record_fields", combined)
        self.assertNotIn(key, combined)

    def test_timeout_logs_status_content_type_and_response_as_unavailable(self):
        with self.assertLogs(service.logger, level="WARNING") as captured:
            with patch.object(
                service.httpx,
                "get",
                side_effect=httpx.ReadTimeout("read timed out"),
            ):
                with self.assertRaises(service.MarketDataError) as raised:
                    service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(raised.exception.category, "read_timeout")
        self.assertIn("status=unavailable", "\n".join(captured.output))
        self.assertIn("content_type=unavailable", "\n".join(captured.output))
        self.assertIn("response_structure=unavailable", "\n".join(captured.output))

    def test_cache_reuses_response_until_explicit_refresh(self):
        with (
            patch.object(
                service.httpx,
                "get",
                return_value=self.response(200, {"records": [SOURCE_RECORD]}),
            ) as get,
            patch.object(service.GovernmentMarketDataService, "_store_observations"),
        ):
            service.GovernmentMarketDataService.fetch_prices()
            service.GovernmentMarketDataService.fetch_prices()
            service.GovernmentMarketDataService.fetch_prices(refresh=True)
        self.assertEqual(get.call_count, 2)

    def test_price_parser_rejects_invalid_and_nonfinite_values(self):
        self.assertEqual(service._number("1,250.5"), 1250.5)
        self.assertIsNone(service._number("NaN"))
        self.assertIsNone(service._number("-2"))
        self.assertIsNone(service._number("NA"))

    def test_trend_changes_use_stored_report_dates_only(self):
        test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        MarketObservation.__table__.create(bind=test_engine)
        TestSession = sessionmaker(bind=test_engine)
        session = TestSession()
        for day, price in (("01/01/2026", 100), ("08/01/2026", 120), ("01/02/2026", 150)):
            session.add(
                MarketObservation(
                    id=day,
                    record_key=day,
                    commodity="Tomato",
                    market="Nashik",
                    report_date=day,
                    modal_price=price,
                    source="data.gov.in",
                    source_payload="{}",
                    retrieved_at=datetime.now(timezone.utc),
                    unit="INR per quintal",
                )
            )
        session.commit()
        session.close()
        with (
            patch.object(service, "engine", test_engine),
            patch.object(service, "SessionLocal", TestSession),
        ):
            trend = service.GovernmentMarketDataService.get_trends("Tomato", days=31)
        self.assertEqual(len(trend["points"]), 3)
        self.assertAlmostEqual(trend["change_7d_pct"], 25.0)
        self.assertAlmostEqual(trend["change_30d_pct"], 50.0)
        test_engine.dispose()

    def test_observations_are_upserted_by_market_and_source_report_date(self):
        test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestSession = sessionmaker(bind=test_engine)
        first = service.GovernmentMarketDataService._normalize_record(
            SOURCE_RECORD,
            datetime.now(timezone.utc).isoformat(),
        )
        revised = service.GovernmentMarketDataService._normalize_record(
            {**SOURCE_RECORD, "modal_price": "1750"},
            datetime.now(timezone.utc).isoformat(),
        )
        with (
            patch.object(service, "engine", test_engine),
            patch.object(service, "SessionLocal", TestSession),
        ):
            service.GovernmentMarketDataService._store_observations([first])
            service.GovernmentMarketDataService._store_observations([revised])
            session = TestSession()
            observations = session.execute(select(MarketObservation)).scalars().all()
            session.close()
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].modal_price, 1750.0)
        self.assertIn('"modal_price": "1750"', observations[0].source_payload)
        test_engine.dispose()

    def test_endpoint_validation_and_unconfigured_key(self):
        client = TestClient(app)
        invalid_date = client.get("/api/v1/markets/prices?date=not-a-date")
        invalid_limit = client.get("/api/v1/markets/prices?limit=0")
        invalid_trend = client.get("/api/v1/markets/trends?commodity=&days=0")
        with patch.object(settings, "DATA_GOV_API_KEY", ""):
            missing_key = client.get("/api/v1/markets/prices")
        self.assertEqual(invalid_date.status_code, 422)
        self.assertEqual(invalid_limit.status_code, 422)
        self.assertEqual(invalid_trend.status_code, 422)
        self.assertEqual(missing_key.status_code, 503)

    def test_iso_date_filter_is_normalized_to_source_report_format(self):
        self.assertEqual(
            market._validate_date("2026-10-01"),
            "01/10/2026",
        )

    def test_market_questions_never_get_guessed_when_source_is_unavailable(self):
        with (
            patch.object(settings, "DATA_GOV_API_KEY", ""),
            patch.object(agent, "ChatOpenAI") as llm,
        ):
            response = TestClient(app).post(
                "/api/v1/agent/query",
                json={"query": "What is the latest tomato mandi price?"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn("No unverified price or trend", response.json()["detail"])
        self.assertIn("DATA_GOV_API_KEY", response.json()["detail"])
        llm.assert_not_called()

    def test_latest_market_evidence_uses_one_small_source_request(self):
        result = MarketPricesResponse(
            records=[],
            count=0,
            total=0,
            limit=1000,
            offset=0,
            source="data.gov.in",
            retrieved_at="2026-10-19T00:00:00+00:00",
        )
        with patch.object(
            service.GovernmentMarketDataService,
            "fetch_prices",
            return_value=result,
        ) as fetch:
            service.GovernmentMarketDataService.get_market_evidence(
                "What is the tomato mandi price?"
            )
        fetch.assert_called_once_with(
            commodity="Tomato",
            limit=service.MAX_CHAT_MARKET_EVIDENCE,
        )

    def test_location_specific_chat_requests_use_broad_source_page(self):
        result = MarketPricesResponse(
            records=[],
            count=0,
            total=0,
            limit=1000,
            offset=0,
            source="data.gov.in",
            retrieved_at="2026-10-19T00:00:00+00:00",
        )
        with patch.object(
            service.GovernmentMarketDataService,
            "fetch_prices",
            return_value=result,
        ) as fetch:
            service.GovernmentMarketDataService.get_market_evidence(
                "What is the tomato price near Nashik?"
            )
        fetch.assert_called_once_with(commodity="Tomato", limit=1000)

    def test_latest_evidence_selects_only_the_newest_report_date(self):
        retrieved_at = "2026-10-19T00:00:00+00:00"
        records = [
            service.GovernmentMarketDataService._normalize_record(
                {**SOURCE_RECORD, "market": "Old Market", "arrival_date": "18/10/2026"},
                retrieved_at,
            ),
            service.GovernmentMarketDataService._normalize_record(
                {**SOURCE_RECORD, "market": "New Market A", "arrival_date": "19/10/2026"},
                retrieved_at,
            ),
            service.GovernmentMarketDataService._normalize_record(
                {**SOURCE_RECORD, "market": "New Market B", "arrival_date": "19/10/2026"},
                retrieved_at,
            ),
        ]
        result = MarketPricesResponse(
            records=records,
            count=3,
            total=100,
            limit=20,
            offset=0,
            source="data.gov.in",
            retrieved_at=retrieved_at,
        )
        with patch.object(
            service.GovernmentMarketDataService,
            "fetch_prices",
            return_value=result,
        ):
            evidence = service.GovernmentMarketDataService.get_market_evidence(
                "What is the tomato mandi price?"
            )
        self.assertEqual(
            [record.market for record in evidence.records],
            ["New Market A", "New Market B"],
        )

    def test_market_comparison_uses_full_page_but_only_top_five_latest_records(self):
        retrieved_at = "2026-10-19T00:00:00+00:00"
        records = [
            service.GovernmentMarketDataService._normalize_record(
                {
                    **SOURCE_RECORD,
                    "market": f"Market {index}",
                    "arrival_date": "19/10/2026",
                    "modal_price": str(index * 100),
                },
                retrieved_at,
            )
            for index in range(1, 9)
        ]
        result = MarketPricesResponse(
            records=records,
            count=len(records),
            total=100,
            limit=1000,
            offset=0,
            source="data.gov.in",
            retrieved_at=retrieved_at,
        )
        with patch.object(
            service.GovernmentMarketDataService,
            "fetch_prices",
            return_value=result,
        ) as fetch:
            evidence = service.GovernmentMarketDataService.get_market_evidence(
                "Which market has the highest tomato price?"
            )
        fetch.assert_called_once_with(commodity="Tomato", limit=1000)
        self.assertEqual(evidence.count, 5)
        self.assertEqual(
            [record.modal_price for record in evidence.records],
            [800, 700, 600, 500, 400],
        )

    def test_market_commodity_matching_avoids_rice_match_inside_price(self):
        with patch.object(
            service.GovernmentMarketDataService,
            "fetch_prices",
        ) as fetch:
            result = service.GovernmentMarketDataService.get_market_evidence(
                "What is the latest market price?"
            )
        self.assertIsNone(result)
        fetch.assert_not_called()

    def test_market_evidence_resolves_a_supported_regional_crop_name(self):
        result = MarketPricesResponse(
            records=[],
            count=0,
            total=0,
            limit=1000,
            offset=0,
            source="data.gov.in",
            retrieved_at="2026-10-19T00:00:00+00:00",
        )
        with patch.object(
            service.GovernmentMarketDataService,
            "fetch_prices",
            return_value=result,
        ) as fetch:
            service.GovernmentMarketDataService.get_market_evidence(
                "टमाटर का मंडी भाव क्या है?"
            )
        fetch.assert_called_once_with(
            commodity="Tomato",
            limit=service.MAX_CHAT_MARKET_EVIDENCE,
        )

    def test_assistant_receives_retrieved_prices_as_market_evidence(self):
        record = MarketPriceRecord(
            state="Maharashtra",
            district="Nashik",
            market="Nashik",
            commodity="Tomato",
            variety="Local",
            report_date="01/10/2026",
            min_price=1000,
            max_price=2000,
            modal_price=1500,
            unit="INR per quintal",
            source="data.gov.in",
            retrieved_at="2026-10-19T00:00:00+00:00",
            source_values=SOURCE_RECORD,
        )
        evidence = MarketPricesResponse(
            records=[record],
            count=1,
            total=1,
            limit=1000,
            offset=0,
            source="data.gov.in",
            retrieved_at="2026-10-19T00:00:00+00:00",
        )
        captured = {}

        class FakeChatModel:
            def __init__(self, **kwargs):
                pass

            def invoke(self, messages):
                captured["messages"] = messages
                return SimpleNamespace(content="Nashik's reported modal price is ₹1,500.")

        with (
            patch.object(settings, "NVIDIA_API_KEY", "test-nvidia-key"),
            patch.object(agent, "ChatOpenAI", FakeChatModel),
            patch.object(
                agent.GovernmentMarketDataService,
                "get_market_evidence",
                return_value=evidence,
            ),
            patch.object(
                agent.GovernmentMarketDataService,
                "get_trends",
                return_value={
                    "points": [],
                    "change_7d_pct": None,
                    "change_30d_pct": None,
                },
            ),
        ):
            response = TestClient(app).post(
                "/api/v1/agent/query",
                json={"query": "What is the tomato price trend in Nashik?"},
            )

        self.assertEqual(response.status_code, 200)
        prompt = captured["messages"][0][1]
        self.assertIn("1500.0", prompt)
        self.assertIn("01/10/2026", prompt)
        self.assertIn("data.gov.in", prompt)
        self.assertIn("compact Markdown table", prompt)
        self.assertIn("Never print raw JSON", prompt)
        self.assertIn("7-day change: unavailable", prompt)
        self.assertNotIn("change_7d_pct", prompt)
        self.assertNotIn("7-day change: None", prompt)
        self.assertNotIn("30-day change: None", prompt)


if __name__ == "__main__":
    unittest.main()
