# Playwright Mock Setup for Tests

## Overview

The backend tests now include comprehensive mocking for Playwright, allowing tests to run without requiring actual browser installation or launching Chromium.

## What Was Changed

### 1. Added Playwright Mock in `conftest.py`

A new autouse fixture `mock_playwright` was added that:

- **Mocks the entire Playwright async API**
  - `playwright.async_api.async_playwright` - the main entry point
  - Returns mock browser, page, and element objects
  - All methods are AsyncMock objects for proper async/await support

- **Mock Structure:**
  ```python
  mock_element.text_content()  # Returns mock text
  mock_page.goto()             # Navigates (mocked)
  mock_page.wait_for_selector() # Waits for selector (mocked)
  mock_page.query_selector()    # Returns mock element
  mock_page.query_selector_all() # Returns list of mock elements
  mock_browser.new_page()       # Creates mock page
  mock_browser.close()          # Closes browser (mocked)
  mock_chromium.launch()        # Launches browser (mocked)
  ```

- **Auto-applied to all tests** via `autouse=True`
- **Safe for missing imports** - wrapped in try/except to handle when Playwright isn't imported

### 2. Added Comprehensive Tests in `test_external_links_service.py`

New test class `TestFirefliesProcessing` with tests for:

1. **Successful Playwright scraping** - Verifies the Playwright code path works with mocks
2. **Invalid URLs** - Tests error handling for malformed URLs
3. **Empty transcript handling** - Tests when scraping returns no content
4. **Playwright fallback** - Tests HTTP scraping fallback when Playwright isn't available

## Why This Approach?

1. **No browser installation required** - Tests can run in CI/CD without `playwright install chromium`
2. **Faster test execution** - No real browser launching/closing
3. **Consistent test behavior** - Mocked responses are predictable
4. **Follows existing patterns** - Uses same AsyncMock/MagicMock patterns as other fixtures

## How It Works

When `external_links.py` calls:
```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto(url)
    # ... etc
```

The mock intercepts this and returns mock objects that behave like real Playwright objects but don't actually launch a browser.

## Usage in Tests

### Using the Default Mock

Most tests don't need to do anything - the mock is auto-applied:

```python
@pytest.mark.asyncio
async def test_something(processor):
    # Playwright is automatically mocked
    result = await processor._process_fireflies(mock_call, url)
    assert result.status == CallStatus.done
```

### Customizing the Mock for Specific Tests

If a test needs specific Playwright behavior:

```python
@pytest.mark.asyncio
async def test_custom_behavior(processor, mock_call_recording):
    # Create custom mock element
    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="Custom text")

    # Create custom page mock
    mock_page = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[mock_element])

    # ... set up custom mock playwright context manager

    with patch('api.services.external_links.async_playwright', mock_async_playwright):
        result = await processor._process_fireflies(mock_call_recording, url)

    assert "Custom text" in result.transcript
```

## Testing the Mock

To verify the mock is working:

```bash
cd backend
pytest tests/test_external_links_service.py::TestFirefliesProcessing -v
```

This will run all the Fireflies Playwright tests without requiring a browser.

## Related Files

- `/home/user/HR-bot-/backend/tests/conftest.py` - Contains the `mock_playwright` fixture
- `/home/user/HR-bot-/backend/tests/test_external_links_service.py` - Contains Fireflies/Playwright tests
- `/home/user/HR-bot-/backend/api/services/external_links.py` - The actual Playwright usage
