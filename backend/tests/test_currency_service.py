"""
Tests for the currency exchange rate service.
"""
import pytest
from unittest.mock import patch, AsyncMock

# Import the service functions and constants
import sys
sys.path.insert(0, '/home/user/HR-bot-/backend')

from api.services.currency import (
    get_exchange_rates,
    convert_currency,
    convert_to_base,
    fetch_rates_from_api,
    clear_cache,
    get_rate_info,
    SUPPORTED_CURRENCIES,
    FALLBACK_RATES_TO_RUB,
    BASE_CURRENCY,
    _convert_rates_to_base,
)


class TestCurrencyConstants:
    """Tests for currency service constants."""

    def test_supported_currencies_include_common_currencies(self):
        """All common currencies should be supported."""
        expected = ["RUB", "USD", "EUR", "KZT", "UAH", "BYN", "GEL", "AED", "TRY", "GBP"]
        for currency in expected:
            assert currency in SUPPORTED_CURRENCIES

    def test_base_currency_is_rub(self):
        """Default base currency should be RUB."""
        assert BASE_CURRENCY == "RUB"

    def test_fallback_rates_have_all_supported_currencies(self):
        """Fallback rates should cover all supported currencies."""
        for currency in SUPPORTED_CURRENCIES:
            assert currency in FALLBACK_RATES_TO_RUB
            assert FALLBACK_RATES_TO_RUB[currency] > 0

    def test_fallback_rate_for_rub_is_one(self):
        """Fallback rate for RUB should be 1.0."""
        assert FALLBACK_RATES_TO_RUB["RUB"] == 1.0


class TestConvertCurrency:
    """Tests for the convert_currency function."""

    @pytest.fixture
    def sample_rates(self):
        """Sample exchange rates for testing."""
        return {
            "RUB": 1.0,
            "USD": 90.0,
            "EUR": 98.0,
            "GBP": 115.0,
        }

    def test_convert_same_currency(self, sample_rates):
        """Converting to same currency should return same amount."""
        result = convert_currency(100, "USD", "USD", sample_rates)
        assert result == 100

    def test_convert_usd_to_rub(self, sample_rates):
        """Converting USD to RUB should multiply by rate."""
        result = convert_currency(100, "USD", "RUB", sample_rates)
        # 100 USD * 90 (USD rate) / 1 (RUB rate) = 9000 RUB
        assert result == 9000.0

    def test_convert_rub_to_usd(self, sample_rates):
        """Converting RUB to USD should divide by rate."""
        result = convert_currency(9000, "RUB", "USD", sample_rates)
        # 9000 RUB * 1 (RUB rate) / 90 (USD rate) = 100 USD
        assert result == 100.0

    def test_convert_eur_to_usd(self, sample_rates):
        """Converting between non-base currencies should work."""
        result = convert_currency(100, "EUR", "USD", sample_rates)
        # 100 EUR * 98 (EUR rate) / 90 (USD rate) = 108.89 USD
        assert result == pytest.approx(108.89, rel=0.01)

    def test_convert_unknown_from_currency(self, sample_rates):
        """Converting from unknown currency should return None."""
        result = convert_currency(100, "XXX", "RUB", sample_rates)
        assert result is None

    def test_convert_unknown_to_currency(self, sample_rates):
        """Converting to unknown currency should return None."""
        result = convert_currency(100, "USD", "XXX", sample_rates)
        assert result is None

    def test_convert_zero_amount(self, sample_rates):
        """Converting zero should return zero."""
        result = convert_currency(0, "USD", "RUB", sample_rates)
        assert result == 0

    def test_convert_negative_amount(self, sample_rates):
        """Converting negative amount should work (for refunds etc)."""
        result = convert_currency(-100, "USD", "RUB", sample_rates)
        assert result == -9000.0

    def test_convert_decimal_amount(self, sample_rates):
        """Converting decimal amounts should work."""
        result = convert_currency(99.99, "USD", "RUB", sample_rates)
        assert result == pytest.approx(8999.10, rel=0.01)


class TestConvertToBase:
    """Tests for convert_to_base function."""

    @pytest.fixture
    def sample_rates(self):
        """Sample exchange rates for testing."""
        return {
            "RUB": 1.0,
            "USD": 90.0,
            "EUR": 98.0,
        }

    def test_convert_usd_to_base(self, sample_rates):
        """Converting USD to base (RUB) should work."""
        result = convert_to_base(100, "USD", sample_rates)
        assert result == 9000.0

    def test_convert_rub_to_base(self, sample_rates):
        """Converting RUB to base should return same amount."""
        result = convert_to_base(100, "RUB", sample_rates)
        assert result == 100.0

    def test_convert_to_custom_base(self, sample_rates):
        """Converting to custom base currency should work."""
        result = convert_to_base(100, "RUB", sample_rates, base_currency="USD")
        # 100 RUB * 1 / 90 = 1.11 USD
        assert result == pytest.approx(1.11, rel=0.01)


class TestConvertRatesToBase:
    """Tests for _convert_rates_to_base helper function."""

    def test_convert_to_same_base(self):
        """Converting to same base should return same rates."""
        rates = {"USD": 1.0, "RUB": 90.0}
        result = _convert_rates_to_base(rates, "USD", "USD")
        assert result == rates

    def test_convert_usd_base_to_rub_base(self):
        """Converting from USD base to RUB base.

        API format: 1 USD = X currency
        - USD = 1 (1 USD = 1 USD)
        - RUB = 90 (1 USD = 90 RUB)
        - EUR = 0.95 (1 USD = 0.95 EUR, so 1 EUR = 1/0.95 USD)

        Target format: 1 currency = X RUB
        - RUB = 1 (1 RUB = 1 RUB)
        - USD = 90 (1 USD = 90 RUB)
        - EUR = 90/0.95 = 94.7 (1 EUR = 94.7 RUB)
        """
        rates = {"USD": 1.0, "RUB": 90.0, "EUR": 0.95}
        result = _convert_rates_to_base(rates, "USD", "RUB")

        # In RUB base format (1 currency = X RUB):
        assert result["RUB"] == pytest.approx(1.0, rel=0.01)
        assert result["USD"] == pytest.approx(90.0, rel=0.01)
        assert result["EUR"] == pytest.approx(94.74, rel=0.01)  # 90 / 0.95


class TestGetExchangeRates:
    """Tests for get_exchange_rates function with mocking."""

    @pytest.fixture(autouse=True)
    def clear_cache_before_each(self):
        """Clear cache before each test."""
        clear_cache()
        yield
        clear_cache()

    @pytest.mark.asyncio
    async def test_returns_fallback_when_api_fails(self):
        """Should return fallback rates when API fails."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            rates = await get_exchange_rates()

            assert "USD" in rates
            assert "EUR" in rates
            assert "RUB" in rates
            assert rates["RUB"] == 1.0

    @pytest.mark.asyncio
    async def test_returns_api_rates_when_available(self):
        """Should return API rates when available."""
        api_rates = {
            "RUB": 90.0,
            "USD": 1.0,
            "EUR": 1.1,
        }

        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = api_rates

            rates = await get_exchange_rates(base_currency="USD")

            # Should have been called
            mock_fetch.assert_called_once()
            # Rates should be based on USD
            assert rates is not None

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self):
        """Should use cached rates on second call."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            # First call
            await get_exchange_rates()
            # Second call
            await get_exchange_rates()

            # Should only fetch once due to caching
            assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self):
        """Force refresh should bypass cache."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            # First call
            await get_exchange_rates()
            # Second call with force refresh
            await get_exchange_rates(force_refresh=True)

            # Should fetch twice
            assert mock_fetch.call_count == 2


class TestGetRateInfo:
    """Tests for get_rate_info function."""

    @pytest.fixture(autouse=True)
    def clear_cache_before_each(self):
        """Clear cache before each test."""
        clear_cache()
        yield
        clear_cache()

    @pytest.mark.asyncio
    async def test_rate_info_after_fetch(self):
        """Rate info should reflect cache state."""
        with patch('api.services.currency.fetch_rates_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            await get_exchange_rates()

            info = get_rate_info()

            assert "base_currency" in info
            assert "last_updated" in info
            assert "is_fallback" in info
            assert "supported_currencies" in info
            assert info["is_fallback"] is True


class TestFetchRatesFromApi:
    """Tests for fetch_rates_from_api with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        """Should return None on timeout."""
        import httpx

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.TimeoutException("Timeout")
            mock_client.return_value = mock_instance

            result = await fetch_rates_from_api()
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        """Should return None on HTTP error."""
        import httpx

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance

            response = AsyncMock()
            response.status_code = 500
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server Error",
                request=AsyncMock(),
                response=response
            )
            mock_instance.get.return_value = response
            mock_client.return_value = mock_instance

            result = await fetch_rates_from_api()
            assert result is None


class TestEdgeCases:
    """Edge case tests for currency conversion."""

    def test_very_small_amounts(self):
        """Should handle very small amounts."""
        rates = {"RUB": 1.0, "USD": 90.0}
        result = convert_currency(0.01, "USD", "RUB", rates)
        assert result == pytest.approx(0.90, rel=0.01)

    def test_very_large_amounts(self):
        """Should handle very large amounts."""
        rates = {"RUB": 1.0, "USD": 90.0}
        result = convert_currency(1_000_000_000, "USD", "RUB", rates)
        assert result == 90_000_000_000

    def test_floating_point_precision(self):
        """Should maintain reasonable precision."""
        rates = {"RUB": 1.0, "EUR": 98.123456}
        result = convert_currency(100, "EUR", "RUB", rates)
        # Should be rounded to 2 decimal places
        assert isinstance(result, float)
        # Check that it's rounded properly (result should be 9812.35)
        assert abs(result - 9812.35) < 0.01
