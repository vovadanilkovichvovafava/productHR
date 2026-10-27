"""
Tests for the currency exchange rate API routes.
"""
import pytest
from unittest.mock import patch, AsyncMock

# Ensure testing mode is set
import os
os.environ["TESTING"] = "1"

import sys
sys.path.insert(0, '/home/user/HR-bot-/backend')

from api.services.currency import clear_cache, SUPPORTED_CURRENCIES


class TestCurrencyRatesEndpoint:
    """Tests for GET /api/currency/rates endpoint."""

    @pytest.fixture(autouse=True)
    def clear_cache_fixture(self):
        """Clear cache before each test."""
        clear_cache()
        yield
        clear_cache()

    @pytest.mark.asyncio
    async def test_get_rates_default_base(self, client):
        """Should return rates with default base currency (RUB)."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None  # Use fallback rates

            response = await client.get("/api/currency/rates")

            assert response.status_code == 200
            data = response.json()
            assert "rates" in data
            assert "base_currency" in data
            assert "is_fallback" in data
            assert "supported_currencies" in data
            assert data["base_currency"] == "RUB"
            assert data["rates"]["RUB"] == 1.0
            assert "USD" in data["rates"]
            assert "EUR" in data["rates"]

    @pytest.mark.asyncio
    async def test_get_rates_custom_base(self, client):
        """Should return rates with custom base currency."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            response = await client.get("/api/currency/rates?base=USD")

            assert response.status_code == 200
            data = response.json()
            assert data["base_currency"] == "USD"

    @pytest.mark.asyncio
    async def test_get_rates_invalid_base(self, client):
        """Should return error for unsupported base currency."""
        response = await client.get("/api/currency/rates?base=XXX")

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported currency" in data["detail"]

    @pytest.mark.asyncio
    async def test_get_rates_force_refresh(self, client):
        """Should allow force refresh parameter."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            response = await client.get("/api/currency/rates?refresh=true")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_rates_include_all_supported_currencies(self, client):
        """Rates should include all supported currencies."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            response = await client.get("/api/currency/rates")

            assert response.status_code == 200
            data = response.json()

            for currency in SUPPORTED_CURRENCIES:
                assert currency in data["rates"], f"Missing currency: {currency}"
                assert data["rates"][currency] > 0


class TestCurrencyConvertEndpoint:
    """Tests for POST /api/currency/convert endpoint."""

    @pytest.fixture(autouse=True)
    def clear_cache_fixture(self):
        """Clear cache before each test."""
        clear_cache()
        yield
        clear_cache()

    @pytest.mark.asyncio
    async def test_convert_usd_to_rub(self, client):
        """Should convert USD to RUB."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            response = await client.post(
                "/api/currency/convert",
                json={
                    "amount": 100,
                    "from_currency": "USD",
                    "to_currency": "RUB"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["original_amount"] == 100
            assert data["from_currency"] == "USD"
            assert data["to_currency"] == "RUB"
            assert data["converted_amount"] > 0
            assert data["rate"] > 0

    @pytest.mark.asyncio
    async def test_convert_same_currency(self, client):
        """Converting to same currency should return same amount."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            response = await client.post(
                "/api/currency/convert",
                json={
                    "amount": 100,
                    "from_currency": "USD",
                    "to_currency": "USD"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["converted_amount"] == 100

    @pytest.mark.asyncio
    async def test_convert_invalid_from_currency(self, client):
        """Should return error for invalid source currency."""
        response = await client.post(
            "/api/currency/convert",
            json={
                "amount": 100,
                "from_currency": "XXX",
                "to_currency": "RUB"
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported source currency" in data["detail"]

    @pytest.mark.asyncio
    async def test_convert_invalid_to_currency(self, client):
        """Should return error for invalid target currency."""
        response = await client.post(
            "/api/currency/convert",
            json={
                "amount": 100,
                "from_currency": "USD",
                "to_currency": "XXX"
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported target currency" in data["detail"]

    @pytest.mark.asyncio
    async def test_convert_zero_amount(self, client):
        """Should handle zero amount."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            response = await client.post(
                "/api/currency/convert",
                json={
                    "amount": 0,
                    "from_currency": "USD",
                    "to_currency": "RUB"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["converted_amount"] == 0


class TestSupportedCurrenciesEndpoint:
    """Tests for GET /api/currency/supported endpoint."""

    @pytest.mark.asyncio
    async def test_get_supported_currencies(self, client):
        """Should return list of supported currencies."""
        response = await client.get("/api/currency/supported")

        assert response.status_code == 200
        data = response.json()
        assert "currencies" in data
        assert "default_base" in data
        assert len(data["currencies"]) == len(SUPPORTED_CURRENCIES)

        # Check that each currency has required fields
        for currency in data["currencies"]:
            assert "code" in currency
            assert "name" in currency
            assert "symbol" in currency

    @pytest.mark.asyncio
    async def test_supported_currencies_include_common(self, client):
        """Should include common currencies."""
        response = await client.get("/api/currency/supported")

        data = response.json()
        codes = [c["code"] for c in data["currencies"]]

        assert "RUB" in codes
        assert "USD" in codes
        assert "EUR" in codes
        assert "GBP" in codes

    @pytest.mark.asyncio
    async def test_default_base_is_rub(self, client):
        """Default base should be RUB."""
        response = await client.get("/api/currency/supported")

        data = response.json()
        assert data["default_base"] == "RUB"
