# E2E Responsive Layout Tests

Comprehensive Playwright test suite for responsive and adaptive layout testing in the HR-bot frontend.

## Overview

This test suite validates the responsive behavior of the application across different screen sizes, devices, and orientations. It ensures proper layout adaptation, touch interactions, and visual consistency.

## Test Coverage

### 1. Breakpoint Behavior Tests

Tests that verify proper layout changes at different viewport sizes:

- **test_desktop_shows_full_sidebar** - Validates that the desktop sidebar is visible and functional at 1280px+
- **test_tablet_shows_collapsed_sidebar** - Ensures mobile layout is used on tablets (768-1024px)
- **test_mobile_hides_sidebar** - Confirms sidebar is hidden on mobile devices (<768px)
- **test_mobile_shows_hamburger_menu** - Verifies hamburger menu and mobile header appear on mobile

**Breakpoints tested:**
- Mobile: 375x667 (iPhone SE)
- Tablet: 768x1024 (iPad)
- Desktop: 1280x720
- Large Desktop: 1920x1080

### 2. Layout Stability Tests

Tests that ensure layouts remain stable and usable:

- **test_tabs_dont_overflow_container** - Validates that tabs/filters don't cause horizontal overflow
- **test_modals_fit_viewport** - Ensures modals are properly sized for the viewport
- **test_no_horizontal_scroll** - Confirms no unwanted horizontal scrolling
- **test_content_readable_at_all_sizes** - Verifies text remains readable at all breakpoints

### 3. Touch/Mobile Interaction Tests

Tests for mobile-specific interactions:

- **test_sidebar_opens_on_hamburger_tap** - Validates hamburger menu opens mobile sidebar
- **test_sidebar_closes_on_outside_tap** - Confirms tapping overlay closes the sidebar
- **test_swipe_navigation_works** - Tests bottom navigation interactions

### 4. Component Responsiveness Tests

Tests for responsive component behavior:

- **test_table_becomes_cards_on_mobile** - Validates data displays adapt to screen size
- **test_form_inputs_full_width_mobile** - Ensures form inputs expand properly on mobile
- **test_buttons_touchable_size** - Confirms buttons meet minimum 44px touch target size
- **test_responsive_grid_layout** - Validates grid layouts adapt correctly

### 5. Visual Regression Tests

Screenshot-based tests for visual consistency:

- **test_dashboard_desktop_screenshot** - Captures dashboard at 1920x1080
- **test_dashboard_tablet_screenshot** - Captures dashboard at 768x1024
- **test_dashboard_mobile_screenshot** - Captures dashboard at 375x667
- **test_contacts_page_responsive_screenshots** - Multi-viewport contact page screenshots
- **test_mobile_menu_open_screenshot** - Captures mobile menu in open state

### 6. Orientation Change Tests

Tests for different device orientations:

- **test_landscape_mobile_layout** - Validates mobile landscape mode (667x375)
- **test_tablet_portrait_layout** - Tests tablet portrait orientation
- **test_tablet_landscape_layout** - Tests tablet landscape orientation

### 7. Component-Specific Tests

Tests for specific component responsive behavior:

- **test_contact_detail_responsive_layout** - Tests contact detail view adaptation
- **test_modal_responsive_behavior** - Validates modal sizing across viewports
- **test_chart_responsive_behavior** - Tests chart/graph responsiveness
- **test_bottom_navigation_items_equal_width** - Validates navigation item sizing

### 8. Accessibility Tests

Tests for accessibility at different sizes:

- **test_focus_visible_on_mobile** - Validates keyboard navigation on mobile
- **test_text_contrast_at_all_sizes** - Ensures adequate text contrast

## Running the Tests

### Prerequisites

```bash
# Install dependencies
npm install

# Install Playwright browsers
npx playwright install
```

### Run All E2E Tests

```bash
npm run test:e2e
```

### Run Only Responsive Tests

```bash
npm run test:e2e:responsive
```

### Run with UI Mode (Recommended for Development)

```bash
npm run test:e2e:ui
```

### Run in Headed Mode (See Browser)

```bash
npm run test:e2e:headed
```

### Debug Mode

```bash
npm run test:e2e:debug
```

### Run Specific Test

```bash
npx playwright test -g "test_desktop_shows_full_sidebar"
```

### Run on Specific Browser

```bash
npx playwright test --project=chromium
npx playwright test --project="Mobile Chrome"
npx playwright test --project=iPad
```

## Test Results

After running tests:

- **HTML Report**: `npx playwright show-report`
- **Screenshots**: `test-results/` directory
- **Videos**: `test-results/` directory (on failure)
- **Traces**: `test-results/` directory (on retry)

## Visual Regression Testing

Visual regression tests capture screenshots and compare them against baselines:

1. **First run**: Generates baseline screenshots
2. **Subsequent runs**: Compares against baselines
3. **Update baselines**: `npx playwright test --update-snapshots`

Screenshots are stored in:
- `tests/e2e/responsive.spec.ts-snapshots/`

## CI/CD Integration

The test suite is configured to run in CI environments:

- Automatic retries (2x) on CI
- Sequential execution on CI
- GitHub Actions reporter
- Failure screenshots and videos

## Debugging Failed Tests

1. **View HTML Report**:
   ```bash
   npx playwright show-report
   ```

2. **Use Trace Viewer**:
   ```bash
   npx playwright show-trace test-results/.../trace.zip
   ```

3. **Run in Debug Mode**:
   ```bash
   npm run test:e2e:debug
   ```

4. **Use UI Mode** (Best for debugging):
   ```bash
   npm run test:e2e:ui
   ```

## Known Limitations

Many tests will initially fail as they document expected behavior. They serve as:

- **Documentation** of responsive design requirements
- **Regression prevention** once features are implemented
- **Specification** for responsive behavior

## Customization

### Add New Viewport

Edit `responsive.spec.ts`:

```typescript
const VIEWPORTS = {
  // ... existing viewports
  customDevice: { width: 414, height: 896 }, // iPhone 11
};
```

### Add New Test

```typescript
test('test_my_responsive_feature', async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.mobile);
  await loginAndNavigate(page);

  // Your test assertions
  await expect(page.locator('...')).toBeVisible();
});
```

### Update Login Helper

The `loginAndNavigate()` helper function may need to be updated based on your authentication implementation:

```typescript
async function loginAndNavigate(page: Page, route = '/dashboard') {
  await page.goto('/login');
  await page.fill('input[type="email"]', 'test@example.com');
  await page.fill('input[type="password"]', 'password');
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(dashboard|chats|contacts|calls)/);
  if (route !== '/dashboard') {
    await page.goto(route);
  }
}
```

## Best Practices

1. **Use semantic selectors**: Prefer data-testid attributes over CSS selectors
2. **Wait for content**: Use `waitForSelector` or `waitForURL` for dynamic content
3. **Isolate tests**: Each test should be independent
4. **Clean up**: Close modals/dialogs after testing them
5. **Screenshot naming**: Use descriptive names for visual regression tests

## Contributing

When adding new responsive features:

1. Add corresponding test cases
2. Update this README
3. Run tests locally before committing
4. Update visual regression baselines if needed

## Resources

- [Playwright Documentation](https://playwright.dev)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Visual Regression Testing](https://playwright.dev/docs/test-snapshots)
- [Tailwind Breakpoints](https://tailwindcss.com/docs/responsive-design)

## Tailwind Breakpoints Reference

The application uses these Tailwind breakpoints:

| Breakpoint | Min Width | Prefix | Example |
|------------|-----------|--------|---------|
| Mobile     | 0px       | (none) | `flex` |
| sm         | 640px     | `sm:` | `sm:grid-cols-2` |
| md         | 768px     | `md:` | `md:w-1/2` |
| lg         | 1024px    | `lg:` | `lg:flex` |
| xl         | 1280px    | `xl:` | `xl:grid-cols-4` |
| 2xl        | 1536px    | `2xl:` | `2xl:container` |

## Support

For issues or questions:
1. Check test output and screenshots
2. Review Playwright documentation
3. Use debug mode to step through tests
4. Check component implementation
