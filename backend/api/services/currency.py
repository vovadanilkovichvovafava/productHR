"""
Currency Exchange Rate Service.

Provides:
- Cached exchange rates from external API (updated once per day)
- Currency conversion between supported currencies
- Fallback rates when API is unavailable
"""

import httpx
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from decimal import Decimal, ROUND_HALF_UP

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..utils.http_client import get_http_client

logger = logging.getLogger("hr-analyzer.currency")

# Supported currencies in the system
SUPPORTED_CURRENCIES = [
    "RUB", "USD", "EUR", "KZT", "UAH", "BYN", "GEL", "AED", "TRY", "GBP"
]

# Default base currency for conversions
BASE_CURRENCY = "RUB"

# Cache TTL: 24 hours
CACHE_TTL_SECONDS = 86400

# Free exchange rate API (exchangerate-api.com free tier)
EXCHANGE_RATE_API_URL = "https://api.exchangerate-api.com/v4/latest/{base}"

# Fallback rates relative to RUB (approximate, updated manually as backup)
# These are used when the API is unavailable
FALLBACK_RATES_TO_RUB: Dict[str, float] = {
    "RUB": 1.0,
    "USD": 90.0,     # 1 USD = 90 RUB (approximate)
    "EUR": 98.0,     # 1 EUR = 98 RUB (approximate)
    "KZT": 0.19,     # 1 KZT = 0.19 RUB
    "UAH": 2.4,      # 1 UAH = 2.4 RUB
    "BYN": 27.5,     # 1 BYN = 27.5 RUB
    "GEL": 33.0,     # 1 GEL = 33 RUB
    "AED": 24.5,     # 1 AED = 24.5 RUB
    "TRY": 2.6,      # 1 TRY = 2.6 RUB
    "GBP": 115.0,    # 1 GBP = 115 RUB
}


class CurrencyRateCache:
    """In-memory cache for exchange rates with TTL."""

    def __init__(self):
        self._rates: Dict[str, float] = {}
        self._base_currency: str = BASE_CURRENCY
        self._last_updated: Optional[datetime] = None
        self._is_fallback: bool = False

    @property
    def rates(self) -> Dict[str, float]:
        """Get cached rates. Returns empty dict if cache is invalid."""
        if self._is_cache_valid():
            return self._rates.copy()
        return {}

    @property
    def last_updated(self) -> Optional[datetime]:
        """Get timestamp of last successful update."""
        return self._last_updated

    @property
    def is_fallback(self) -> bool:
        """Whether current rates are fallback (not from API)."""
        return self._is_fallback

    @property
    def base_currency(self) -> str:
        """Get the base currency for the rates."""
        return self._base_currency

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL."""
        if not self._last_updated or not self._rates:
            return False
        elapsed = (datetime.utcnow() - self._last_updated).total_seconds()
        return elapsed < CACHE_TTL_SECONDS

    def update(
        self,
        rates: Dict[str, float],
        base_currency: str = BASE_CURRENCY,
        is_fallback: bool = False
    ) -> None:
        """Update cached rates."""
        self._rates = rates.copy()
        self._base_currency = base_currency
        self._last_updated = datetime.utcnow()
        self._is_fallback = is_fallback
        logger.info(
            f"Currency rates updated: {len(rates)} currencies, "
            f"base={base_currency}, fallback={is_fallback}"
        )

    def clear(self) -> None:
        """Clear the cache."""
        self._rates.clear()
        self._last_updated = None
        self._is_fallback = False


# Global cache instance
_cache = CurrencyRateCache()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True
)
async def _fetch_rates_request(url: str) -> Dict[str, float]:
    """Execute the API request with retry logic."""
    client = get_http_client()
    response = await client.get(url, timeout=10.0)
    response.raise_for_status()
    data = response.json()

    rates = data.get("rates", {})
    if not rates:
        raise ValueError("API returned empty rates")

    # Filter to only supported currencies
    filtered_rates = {
        currency: float(rate)
        for currency, rate in rates.items()
        if currency in SUPPORTED_CURRENCIES
    }

    return filtered_rates


async def fetch_rates_from_api(base: str = "USD") -> Optional[Dict[str, float]]:
    """
    Fetch exchange rates from external API.

    Args:
        base: Base currency for the rates

    Returns:
        Dictionary of currency -> rate mappings, or None if API fails
    """
    try:
        url = EXCHANGE_RATE_API_URL.format(base=base)
        filtered_rates = await _fetch_rates_request(url)
        logger.info(f"Fetched {len(filtered_rates)} exchange rates from API")
        return filtered_rates

    except httpx.TimeoutException:
        logger.warning("Exchange rate API request timed out after 3 retries")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"Exchange rate API returned status {e.response.status_code}")
        return None
    except ValueError as e:
        logger.warning(str(e))
        return None
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")
        return None


def _convert_rates_to_base(
    rates: Dict[str, float],
    from_base: str,
    to_base: str
) -> Dict[str, float]:
    """
    Convert rates from one base currency to another.

    The rates are in format "1 base = X target", e.g., if base is USD:
    - RUB: 90 means 1 USD = 90 RUB
    - EUR: 0.95 means 1 USD = 0.95 EUR

    We want to convert to format "1 currency = X new_base", e.g., if new base is RUB:
    - USD: 90 means 1 USD = 90 RUB
    - EUR: 94.7 means 1 EUR = 94.7 RUB

    Args:
        rates: Original rates with from_base as base (1 from_base = X currency)
        from_base: Original base currency
        to_base: Target base currency

    Returns:
        Rates in format (1 currency = X to_base)
    """
    if from_base == to_base:
        return rates.copy()

    if to_base not in rates:
        logger.warning(f"Target base currency {to_base} not in rates")
        return rates

    # Get the rate of to_base relative to from_base
    # e.g., if from_base=USD and to_base=RUB, this is 90 (1 USD = 90 RUB)
    to_base_rate = rates[to_base]

    # Convert all rates: new_rate = to_base_rate / old_rate
    # This converts from "1 from_base = X currency" to "1 currency = X to_base"
    converted = {}
    for currency, rate in rates.items():
        if rate == 0:
            converted[currency] = 0
        else:
            converted[currency] = to_base_rate / rate

    return converted


async def get_exchange_rates(
    base_currency: str = BASE_CURRENCY,
    force_refresh: bool = False
) -> Dict[str, float]:
    """
    Get exchange rates with caching.

    Rates are cached for 24 hours. If the API is unavailable,
    fallback rates are used.

    Args:
        base_currency: The base currency for returned rates (default: RUB)
        force_refresh: Force refresh from API even if cache is valid

    Returns:
        Dictionary mapping currency codes to their exchange rates
        relative to base_currency. Rate of 1.0 means equal to base.
        Rate > 1 means 1 unit of that currency = rate units of base.
    """
    # Check cache first (unless forcing refresh)
    cached_rates = _cache.rates
    if cached_rates and not force_refresh:
        # Convert cached rates to requested base if different
        if _cache.base_currency != base_currency:
            return _convert_rates_to_base(
                cached_rates, _cache.base_currency, base_currency
            )
        return cached_rates

    # Try to fetch from API (using USD as base for better precision)
    api_rates = await fetch_rates_from_api(base="USD")

    if api_rates:
        # Convert API rates (USD base) to our desired base
        rates_in_base = _convert_rates_to_base(api_rates, "USD", base_currency)
        _cache.update(rates_in_base, base_currency, is_fallback=False)
        return rates_in_base

    # Use fallback rates
    logger.warning("Using fallback exchange rates")
    fallback = FALLBACK_RATES_TO_RUB.copy()

    # Convert fallback rates to requested base
    if base_currency != "RUB":
        fallback = _convert_rates_to_base(fallback, "RUB", base_currency)

    _cache.update(fallback, base_currency, is_fallback=True)
    return fallback


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    rates: Dict[str, float]
) -> Optional[float]:
    """
    Convert an amount from one currency to another.

    Args:
        amount: The amount to convert
        from_currency: Source currency code
        to_currency: Target currency code
        rates: Exchange rates dictionary (from get_exchange_rates)

    Returns:
        Converted amount, or None if conversion is not possible

    Example:
        If rates are relative to RUB:
        - rates["USD"] = 90.0 means 1 USD = 90 RUB
        - To convert 100 USD to RUB: 100 * 90 = 9000 RUB
        - To convert 9000 RUB to USD: 9000 / 90 = 100 USD
    """
    if from_currency == to_currency:
        return amount

    if from_currency not in rates or to_currency not in rates:
        logger.warning(
            f"Cannot convert {from_currency} to {to_currency}: "
            f"currency not in rates"
        )
        return None

    try:
        # Using Decimal for precision
        amount_decimal = Decimal(str(amount))
        from_rate = Decimal(str(rates[from_currency]))
        to_rate = Decimal(str(rates[to_currency]))

        # Convert: amount_in_base = amount * from_rate, then amount_in_target = amount_in_base / to_rate
        # Simplified: result = amount * from_rate / to_rate
        result = amount_decimal * from_rate / to_rate

        # Round to 2 decimal places
        return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    except Exception as e:
        logger.error(f"Currency conversion error: {e}")
        return None


def convert_to_base(
    amount: float,
    from_currency: str,
    rates: Dict[str, float],
    base_currency: str = BASE_CURRENCY
) -> Optional[float]:
    """
    Convert an amount to the base currency.

    Args:
        amount: The amount to convert
        from_currency: Source currency code
        rates: Exchange rates dictionary
        base_currency: Target base currency (default: RUB)

    Returns:
        Amount converted to base currency, or None if not possible
    """
    return convert_currency(amount, from_currency, base_currency, rates)


def get_rate_info() -> Dict:
    """
    Get information about current cached rates.

    Returns:
        Dictionary with cache status information
    """
    return {
        "base_currency": _cache.base_currency,
        "last_updated": _cache.last_updated.isoformat() if _cache.last_updated else None,
        "is_fallback": _cache.is_fallback,
        "currencies_count": len(_cache.rates) if _cache.rates else 0,
        "supported_currencies": SUPPORTED_CURRENCIES,
    }


def clear_cache() -> None:
    """Clear the exchange rate cache (for testing purposes)."""
    _cache.clear()
