"""
API routes for currency exchange rates.
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Optional
from pydantic import BaseModel
import logging

from ..services.currency import (
    get_exchange_rates,
    convert_currency,
    get_rate_info,
    SUPPORTED_CURRENCIES,
    BASE_CURRENCY,
)

logger = logging.getLogger("hr-analyzer.currency")

router = APIRouter()


class ExchangeRatesResponse(BaseModel):
    """Response model for exchange rates endpoint."""
    rates: Dict[str, float]
    base_currency: str
    last_updated: Optional[str] = None
    is_fallback: bool
    supported_currencies: list[str]


class ConversionRequest(BaseModel):
    """Request model for currency conversion."""
    amount: float
    from_currency: str
    to_currency: str


class ConversionResponse(BaseModel):
    """Response model for currency conversion."""
    original_amount: float
    from_currency: str
    to_currency: str
    converted_amount: float
    rate: float


@router.get("/rates", response_model=ExchangeRatesResponse)
async def get_rates(
    base: str = Query(
        default=BASE_CURRENCY,
        description="Base currency for rates",
        pattern="^[A-Z]{3}$"
    ),
    refresh: bool = Query(
        default=False,
        description="Force refresh rates from API"
    )
):
    """
    Get current exchange rates.

    Returns exchange rates for all supported currencies relative to the base currency.
    Rates are cached for 24 hours.

    - **base**: Base currency code (e.g., RUB, USD, EUR)
    - **refresh**: Force refresh from external API (ignores cache)

    Returns:
        Exchange rates dictionary where each value represents how many units
        of the base currency equal 1 unit of that currency.
    """
    if base not in SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported currency: {base}. Supported: {', '.join(SUPPORTED_CURRENCIES)}"
        )

    rates = await get_exchange_rates(base_currency=base, force_refresh=refresh)
    info = get_rate_info()

    return ExchangeRatesResponse(
        rates=rates,
        base_currency=base,
        last_updated=info.get("last_updated"),
        is_fallback=info.get("is_fallback", False),
        supported_currencies=SUPPORTED_CURRENCIES,
    )


@router.post("/convert", response_model=ConversionResponse)
async def convert(request: ConversionRequest):
    """
    Convert an amount between two currencies.

    - **amount**: The amount to convert
    - **from_currency**: Source currency code (e.g., USD)
    - **to_currency**: Target currency code (e.g., RUB)

    Returns:
        The converted amount and the exchange rate used.
    """
    if request.from_currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source currency: {request.from_currency}"
        )

    if request.to_currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target currency: {request.to_currency}"
        )

    # Get rates
    rates = await get_exchange_rates()

    # Convert
    converted = convert_currency(
        request.amount,
        request.from_currency,
        request.to_currency,
        rates
    )

    if converted is None:
        raise HTTPException(
            status_code=500,
            detail="Currency conversion failed"
        )

    # Calculate the effective rate
    rate = converted / request.amount if request.amount != 0 else 0

    return ConversionResponse(
        original_amount=request.amount,
        from_currency=request.from_currency,
        to_currency=request.to_currency,
        converted_amount=converted,
        rate=round(rate, 6),
    )


@router.get("/supported")
async def get_supported_currencies():
    """
    Get list of supported currencies.

    Returns:
        List of supported currency codes with their descriptions.
    """
    currency_info = {
        "RUB": {"name": "Russian Ruble", "symbol": "\u20bd"},
        "USD": {"name": "US Dollar", "symbol": "$"},
        "EUR": {"name": "Euro", "symbol": "\u20ac"},
        "KZT": {"name": "Kazakhstani Tenge", "symbol": "\u20b8"},
        "UAH": {"name": "Ukrainian Hryvnia", "symbol": "\u20b4"},
        "BYN": {"name": "Belarusian Ruble", "symbol": "Br"},
        "GEL": {"name": "Georgian Lari", "symbol": "\u20be"},
        "AED": {"name": "UAE Dirham", "symbol": "\u062f.\u0625"},
        "TRY": {"name": "Turkish Lira", "symbol": "\u20ba"},
        "GBP": {"name": "British Pound", "symbol": "\u00a3"},
    }

    return {
        "currencies": [
            {
                "code": code,
                "name": currency_info.get(code, {}).get("name", code),
                "symbol": currency_info.get(code, {}).get("symbol", code),
            }
            for code in SUPPORTED_CURRENCIES
        ],
        "default_base": BASE_CURRENCY,
    }
