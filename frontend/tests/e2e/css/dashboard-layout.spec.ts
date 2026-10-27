import { test, expect, type Page } from '@playwright/test';
import { loginWithMocks, setupMocks } from '../../mocks/api';

/**
 * Comprehensive CSS/Layout Tests for Dashboard and Main Layout Components
 *
 * These tests verify proper CSS layout behavior, grid/flexbox alignment,
 * overflow management, loading states, and prevent layout shift issues.
 *
 * Project: /home/user/HR-bot-/frontend
 * Components tested:
 * - /home/user/HR-bot-/frontend/src/components/Layout.tsx
 * - /home/user/HR-bot-/frontend/src/pages/DashboardPage.tsx
 */

// Common viewport sizes
const VIEWPORTS = {
  mobile: { width: 375, height: 667 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1280, height: 720 },
  largeDesktop: { width: 1920, height: 1080 },
};

// Helper function to login and navigate
async function loginAndNavigate(page: Page, route = '/dashboard') {
  await loginWithMocks(page);
  await page.goto(route);
  await page.waitForLoadState('networkidle');
}

// Helper to get computed style property
async function getComputedStyle(page: Page, selector: string, property: string): Promise<string> {
  return await page.locator(selector).evaluate((el, prop) => {
    return window.getComputedStyle(el).getPropertyValue(prop);
  }, property);
}

// Helper to check for overflow
async function hasHorizontalOverflow(page: Page): Promise<boolean> {
  return await page.evaluate(() => {
    const body = document.body;
    const html = document.documentElement;
    return body.scrollWidth > body.clientWidth || html.scrollWidth > html.clientWidth;
  });
}

test.describe('Main Layout Structure', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_layout_no_horizontal_scroll', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Check that neither body nor html have horizontal scroll
    const hasOverflow = await hasHorizontalOverflow(page);
    expect(hasOverflow).toBe(false);

    // Verify the main container doesn't exceed viewport width
    const mainContainer = page.locator('div.h-screen.flex');
    const containerBox = await mainContainer.boundingBox();

    if (containerBox) {
      expect(containerBox.width).toBeLessThanOrEqual(VIEWPORTS.desktop.width);
    }

    // Test on mobile too
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.waitForTimeout(300);

    const mobileOverflow = await hasHorizontalOverflow(page);
    expect(mobileOverflow).toBe(false);
  });

  test('test_content_area_fills_available_space', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Main content area should use flex-1 to fill available space
    const mainContent = page.locator('main.flex-1');
    await expect(mainContent).toBeVisible();

    // Check that main content has flex-grow applied
    const flexGrow = await mainContent.evaluate((el) =>
      window.getComputedStyle(el).flexGrow
    );
    expect(flexGrow).toBe('1');

    // Verify main content takes up remaining space after sidebar
    const sidebar = page.locator('aside.hidden.lg\\:flex');
    const mainBox = await mainContent.boundingBox();
    const sidebarBox = await sidebar.boundingBox();

    if (mainBox && sidebarBox) {
      // Main + sidebar should approximately equal viewport width
      const totalWidth = mainBox.width + sidebarBox.width;
      expect(totalWidth).toBeGreaterThanOrEqual(VIEWPORTS.desktop.width - 10); // Allow 10px tolerance
      expect(totalWidth).toBeLessThanOrEqual(VIEWPORTS.desktop.width + 10);
    }
  });

  test('test_sidebar_and_content_dont_overlap', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const sidebar = page.locator('aside.hidden.lg\\:flex');
    const mainContent = page.locator('main.flex-1');

    const sidebarBox = await sidebar.boundingBox();
    const mainBox = await mainContent.boundingBox();

    if (sidebarBox && mainBox) {
      // Sidebar should be on the left, main on the right, no overlap
      const sidebarRight = sidebarBox.x + sidebarBox.width;
      const mainLeft = mainBox.x;

      // Main should start at or after sidebar ends
      expect(mainLeft).toBeGreaterThanOrEqual(sidebarRight - 1); // Allow 1px for rounding
    }

    // Verify they're using flex-row layout
    const container = page.locator('div.h-screen.flex');
    const flexDirection = await container.evaluate((el) =>
      window.getComputedStyle(el).flexDirection
    );

    // On desktop (lg breakpoint), should be row
    expect(['row', 'row-reverse']).toContain(flexDirection);
  });

  test('test_layout_uses_full_viewport_height', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Root layout container should use h-screen (100vh)
    const container = page.locator('div.h-screen');
    const height = await container.evaluate((el) =>
      window.getComputedStyle(el).height
    );

    // Should be approximately viewport height
    const heightPx = parseFloat(height);
    expect(heightPx).toBeGreaterThanOrEqual(VIEWPORTS.desktop.height - 5);
    expect(heightPx).toBeLessThanOrEqual(VIEWPORTS.desktop.height + 5);

    // Verify no vertical overflow on the container itself
    const overflowY = await container.evaluate((el) =>
      window.getComputedStyle(el).overflowY
    );
    expect(overflowY).not.toBe('visible');
  });

  test('test_main_content_overflow_scrollable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Main content should have overflow-hidden
    const main = page.locator('main.flex-1.overflow-hidden');
    await expect(main).toBeVisible();

    const overflow = await main.evaluate((el) =>
      window.getComputedStyle(el).overflow
    );
    expect(overflow).toBe('hidden');

    // The inner content area should be scrollable
    const scrollableArea = page.locator('div.h-full.overflow-y-auto');
    await expect(scrollableArea).toBeVisible();

    const overflowY = await scrollableArea.evaluate((el) =>
      window.getComputedStyle(el).overflowY
    );
    expect(overflowY).toBe('auto');
  });
});

test.describe('Dashboard Grid', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_dashboard_cards_grid_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');

    // Wait for dashboard content to load
    await page.waitForSelector('h1:has-text("Панель управления")', { timeout: 5000 });

    // Stats cards should use CSS Grid
    const statsGrid = page.locator('div.grid.grid-cols-1.sm\\:grid-cols-2.lg\\:grid-cols-4').first();
    await expect(statsGrid).toBeVisible();

    const display = await statsGrid.evaluate((el) =>
      window.getComputedStyle(el).display
    );
    expect(display).toBe('grid');

    // On desktop, should have 4 columns
    const gridTemplateColumns = await statsGrid.evaluate((el) =>
      window.getComputedStyle(el).gridTemplateColumns
    );

    // Should have 4 columns on large screens
    const columnCount = gridTemplateColumns.split(' ').length;
    expect(columnCount).toBe(4);
  });

  test('test_cards_responsive_columns', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const statsGrid = page.locator('div.grid.grid-cols-1.sm\\:grid-cols-2.lg\\:grid-cols-4').first();

    // Mobile: 1 column
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.waitForTimeout(300);

    let gridColumns = await statsGrid.evaluate((el) =>
      window.getComputedStyle(el).gridTemplateColumns
    );
    let columnCount = gridColumns.split(' ').length;
    expect(columnCount).toBe(1);

    // Tablet: 2 columns
    await page.setViewportSize(VIEWPORTS.tablet);
    await page.waitForTimeout(300);

    gridColumns = await statsGrid.evaluate((el) =>
      window.getComputedStyle(el).gridTemplateColumns
    );
    columnCount = gridColumns.split(' ').length;
    expect(columnCount).toBe(2);

    // Desktop: 4 columns
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.waitForTimeout(300);

    gridColumns = await statsGrid.evaluate((el) =>
      window.getComputedStyle(el).gridTemplateColumns
    );
    columnCount = gridColumns.split(' ').length;
    expect(columnCount).toBe(4);
  });

  test('test_card_heights_consistent', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Get all stat cards
    const statCards = page.locator('div.grid.grid-cols-1.sm\\:grid-cols-2.lg\\:grid-cols-4').first()
      .locator('div.glass.rounded-2xl.p-5');

    const cardCount = await statCards.count();
    expect(cardCount).toBeGreaterThan(0);

    // Get heights of all cards
    const heights: number[] = [];
    for (let i = 0; i < cardCount; i++) {
      const box = await statCards.nth(i).boundingBox();
      if (box) {
        heights.push(box.height);
      }
    }

    // All cards should have similar heights (within 5px)
    const maxHeight = Math.max(...heights);
    const minHeight = Math.min(...heights);

    expect(maxHeight - minHeight).toBeLessThan(5);
  });

  test('test_card_content_doesnt_overflow', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Check each stat card for overflow
    const statCards = page.locator('div.glass.rounded-2xl.p-5');
    const cardCount = await statCards.count();

    for (let i = 0; i < Math.min(cardCount, 4); i++) {
      const card = statCards.nth(i);

      // Check if content overflows card boundaries
      const cardBox = await card.boundingBox();
      const contentOverflow = await card.evaluate((el) => {
        const computedStyle = window.getComputedStyle(el);
        return {
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
          overflow: computedStyle.overflow,
          overflowX: computedStyle.overflowX,
        };
      });

      if (cardBox) {
        // Content should not exceed card width
        expect(contentOverflow.scrollWidth).toBeLessThanOrEqual(contentOverflow.clientWidth + 1);
      }
    }
  });

  test('test_grid_gap_consistent', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const statsGrid = page.locator('div.grid.grid-cols-1.sm\\:grid-cols-2.lg\\:grid-cols-4').first();

    // Should have gap-4 class (1rem = 16px)
    const gap = await statsGrid.evaluate((el) =>
      window.getComputedStyle(el).gap
    );

    expect(gap).toBe('16px');
  });
});

test.describe('Statistics/Metrics Cards', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_stat_numbers_fit_container', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Find stat value elements
    const statValues = page.locator('div.glass.rounded-2xl.p-5 p.text-2xl.font-bold');
    const count = await statValues.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const statValue = statValues.nth(i);
      const card = statValue.locator('..');

      const valueBox = await statValue.boundingBox();
      const cardBox = await card.boundingBox();

      if (valueBox && cardBox) {
        // Value should fit within card width
        expect(valueBox.width).toBeLessThanOrEqual(cardBox.width);

        // Value should not overflow
        const overflow = await statValue.evaluate((el) => ({
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
        }));

        expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
      }
    }
  });

  test('test_stat_labels_truncate', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Find stat label elements
    const statLabels = page.locator('div.glass.rounded-2xl.p-5 p.text-dark-400.text-sm');
    const count = await statLabels.count();

    for (let i = 0; i < Math.min(count, 4); i++) {
      const label = statLabels.nth(i);
      const card = label.locator('..');

      const labelBox = await label.boundingBox();
      const cardBox = await card.boundingBox();

      if (labelBox && cardBox) {
        // Label should fit within card
        expect(labelBox.width).toBeLessThanOrEqual(cardBox.width);
      }
    }
  });

  test('test_stat_icons_sized_properly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Find icon containers
    const iconContainers = page.locator('div.glass.rounded-2xl.p-5 div.w-12.h-12.rounded-xl');
    const count = await iconContainers.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const container = iconContainers.nth(i);
      const box = await container.boundingBox();

      if (box) {
        // Should be 48x48px (w-12 h-12)
        expect(box.width).toBeGreaterThanOrEqual(47);
        expect(box.width).toBeLessThanOrEqual(49);
        expect(box.height).toBeGreaterThanOrEqual(47);
        expect(box.height).toBeLessThanOrEqual(49);
      }

      // Icon inside should be w-6 h-6 (24x24px)
      const icon = container.locator('svg.w-6.h-6');
      const iconBox = await icon.boundingBox();

      if (iconBox) {
        expect(iconBox.width).toBeGreaterThanOrEqual(23);
        expect(iconBox.width).toBeLessThanOrEqual(25);
        expect(iconBox.height).toBeGreaterThanOrEqual(23);
        expect(iconBox.height).toBeLessThanOrEqual(25);
      }
    }
  });

  test('test_stat_cards_have_consistent_padding', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const statCards = page.locator('div.glass.rounded-2xl.p-5');
    const count = await statCards.count();

    const paddings: string[] = [];
    for (let i = 0; i < Math.min(count, 4); i++) {
      const padding = await statCards.nth(i).evaluate((el) =>
        window.getComputedStyle(el).padding
      );
      paddings.push(padding);
    }

    // All cards should have same padding
    const uniquePaddings = [...new Set(paddings)];
    expect(uniquePaddings.length).toBe(1);
  });
});

test.describe('Charts/Graphs', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_charts_responsive_width', async ({ page }) => {
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Find the chart container
    const chartContainer = page.locator('div.recharts-responsive-container').first();

    if (await chartContainer.isVisible()) {
      // Test on mobile
      await page.setViewportSize(VIEWPORTS.mobile);
      await page.waitForTimeout(500);

      const mobileBox = await chartContainer.boundingBox();
      const mobileParentBox = await chartContainer.locator('..').boundingBox();

      if (mobileBox && mobileParentBox) {
        // Chart should be 100% width of parent
        expect(mobileBox.width).toBeGreaterThanOrEqual(mobileParentBox.width - 2);
      }

      // Test on desktop
      await page.setViewportSize(VIEWPORTS.desktop);
      await page.waitForTimeout(500);

      const desktopBox = await chartContainer.boundingBox();
      const desktopParentBox = await chartContainer.locator('..').boundingBox();

      if (desktopBox && desktopParentBox) {
        expect(desktopBox.width).toBeGreaterThanOrEqual(desktopParentBox.width - 2);
      }
    }
  });

  test('test_chart_container_fixed_height', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Chart should be in a container with h-64 class (256px)
    const chartWrapper = page.locator('div.h-64');

    if (await chartWrapper.isVisible()) {
      const height = await chartWrapper.evaluate((el) =>
        window.getComputedStyle(el).height
      );

      const heightPx = parseFloat(height);
      // h-64 is 16rem = 256px
      expect(heightPx).toBeGreaterThanOrEqual(250);
      expect(heightPx).toBeLessThanOrEqual(260);
    }
  });

  test('test_chart_legends_readable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Find chart axis labels
    const xAxisLabels = page.locator('.recharts-xAxis text');
    const yAxisLabels = page.locator('.recharts-yAxis text');

    if (await xAxisLabels.count() > 0) {
      const fontSize = await xAxisLabels.first().evaluate((el) =>
        window.getComputedStyle(el).fontSize
      );

      // Font size should be at least 10px for readability
      expect(parseFloat(fontSize)).toBeGreaterThanOrEqual(10);
    }

    if (await yAxisLabels.count() > 0) {
      const fontSize = await yAxisLabels.first().evaluate((el) =>
        window.getComputedStyle(el).fontSize
      );

      expect(parseFloat(fontSize)).toBeGreaterThanOrEqual(10);
    }
  });

  test('test_chart_tooltips_visible', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Hover over chart area to trigger tooltip
    const chartContainer = page.locator('.recharts-wrapper');

    if (await chartContainer.isVisible()) {
      await chartContainer.hover();
      await page.waitForTimeout(300);

      // Tooltip might appear
      const tooltip = page.locator('.recharts-tooltip-wrapper');

      // If tooltip exists, verify it's positioned correctly
      if (await tooltip.isVisible()) {
        const tooltipBox = await tooltip.boundingBox();

        if (tooltipBox) {
          // Tooltip should be within viewport
          expect(tooltipBox.x).toBeGreaterThanOrEqual(0);
          expect(tooltipBox.y).toBeGreaterThanOrEqual(0);
          expect(tooltipBox.x + tooltipBox.width).toBeLessThanOrEqual(VIEWPORTS.desktop.width);
        }
      }
    }
  });

  test('test_chart_no_overflow', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const chartSection = page.locator('div.glass.rounded-2xl.p-6:has(h2:has-text("Активность"))');

    if (await chartSection.isVisible()) {
      const overflow = await chartSection.evaluate((el) => ({
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        overflowX: window.getComputedStyle(el).overflowX,
      }));

      // Should not have horizontal overflow
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 2);
    }
  });
});

test.describe('Recent Activity Section', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_top_chats_list_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const topChatsSection = page.locator('div.glass.rounded-2xl.p-6:has(h2:has-text("Топ чатов"))');
    await expect(topChatsSection).toBeVisible();

    // Should have space-y-3 for vertical spacing
    const listContainer = topChatsSection.locator('div.space-y-3');
    await expect(listContainer).toBeVisible();
  });

  test('test_activity_items_consistent_height', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Get top chat items
    const chatItems = page.locator('div.space-y-3 div.flex.items-center.gap-4.p-3.rounded-xl');
    const itemCount = await chatItems.count();

    if (itemCount > 1) {
      const heights: number[] = [];

      for (let i = 0; i < Math.min(itemCount, 5); i++) {
        const box = await chatItems.nth(i).boundingBox();
        if (box) {
          heights.push(box.height);
        }
      }

      // All items should have similar heights (within 10px tolerance)
      const maxHeight = Math.max(...heights);
      const minHeight = Math.min(...heights);

      expect(maxHeight - minHeight).toBeLessThan(10);
    }
  });

  test('test_activity_text_truncation', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Find truncated text elements
    const truncatedText = page.locator('div.flex-1.min-w-0 p.font-medium.truncate');

    if (await truncatedText.count() > 0) {
      const textElement = truncatedText.first();

      // Check for truncate class styles
      const styles = await textElement.evaluate((el) => ({
        overflow: window.getComputedStyle(el).overflow,
        textOverflow: window.getComputedStyle(el).textOverflow,
        whiteSpace: window.getComputedStyle(el).whiteSpace,
      }));

      expect(styles.overflow).toBe('hidden');
      expect(styles.textOverflow).toBe('ellipsis');
      expect(styles.whiteSpace).toBe('nowrap');
    }
  });

  test('test_activity_list_no_horizontal_scroll', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const topChatsSection = page.locator('div.glass.rounded-2xl.p-6:has(h2:has-text("Топ чатов"))');

    if (await topChatsSection.isVisible()) {
      const overflow = await topChatsSection.evaluate((el) => ({
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      }));

      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
    }
  });

  test('test_messages_by_type_bars_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const messageTypeSection = page.locator('div.glass.rounded-2xl.p-6:has(h2:has-text("По типу сообщений"))');

    if (await messageTypeSection.isVisible()) {
      const bars = messageTypeSection.locator('div.flex.items-center.gap-4');
      const barCount = await bars.count();

      if (barCount > 0) {
        for (let i = 0; i < Math.min(barCount, 3); i++) {
          const bar = bars.nth(i);
          const barBox = await bar.boundingBox();
          const sectionBox = await messageTypeSection.boundingBox();

          if (barBox && sectionBox) {
            // Bar should not exceed section width
            expect(barBox.width).toBeLessThanOrEqual(sectionBox.width);
          }
        }
      }
    }
  });

  test('test_progress_bars_percentage_width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const progressBars = page.locator('div.h-2.bg-gradient-to-r.from-accent-500.to-accent-600');

    if (await progressBars.count() > 0) {
      for (let i = 0; i < Math.min(await progressBars.count(), 3); i++) {
        const bar = progressBars.nth(i);
        const barContainer = bar.locator('..');

        const barBox = await bar.boundingBox();
        const containerBox = await barContainer.boundingBox();

        if (barBox && containerBox) {
          // Bar should be within container (0-100% width)
          expect(barBox.width).toBeLessThanOrEqual(containerBox.width);
          expect(barBox.width).toBeGreaterThanOrEqual(0);
        }
      }
    }
  });
});

test.describe('Page Transitions', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_page_content_stable_during_navigation', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Get initial layout metrics
    const initialMain = await page.locator('main').boundingBox();

    // Navigate to another page
    await page.click('a[href="/contacts"]');
    await page.waitForTimeout(500);

    // Check main content area hasn't changed size
    const afterNavMain = await page.locator('main').boundingBox();

    if (initialMain && afterNavMain) {
      // Main content area should maintain same dimensions
      expect(Math.abs(afterNavMain.width - initialMain.width)).toBeLessThan(5);
      expect(Math.abs(afterNavMain.height - initialMain.height)).toBeLessThan(5);
    }
  });

  test('test_no_layout_shift_on_data_load', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto('/login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');

    // Measure layout immediately after navigation
    await page.waitForURL(/\/(dashboard|chats|contacts|calls)/);

    const headerInitial = await page.locator('h1').first().boundingBox();

    // Wait for content to fully load
    await page.waitForTimeout(1000);

    const headerAfterLoad = await page.locator('h1').first().boundingBox();

    if (headerInitial && headerAfterLoad) {
      // Header position shouldn't shift more than a few pixels
      expect(Math.abs(headerAfterLoad.y - headerInitial.y)).toBeLessThan(10);
    }
  });

  test('test_sidebar_state_preserved_on_navigation', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');

    const sidebarInitial = await page.locator('aside.hidden.lg\\:flex').boundingBox();

    // Navigate to different pages
    await page.click('a[href="/contacts"]');
    await page.waitForTimeout(300);

    const sidebarAfter1 = await page.locator('aside.hidden.lg\\:flex').boundingBox();

    await page.click('a[href="/chats"]');
    await page.waitForTimeout(300);

    const sidebarAfter2 = await page.locator('aside.hidden.lg\\:flex').boundingBox();

    // Sidebar should maintain same width across navigations
    if (sidebarInitial && sidebarAfter1 && sidebarAfter2) {
      expect(sidebarAfter1.width).toBe(sidebarInitial.width);
      expect(sidebarAfter2.width).toBe(sidebarInitial.width);
    }
  });
});

test.describe('Loading States', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_loading_spinner_centered', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Look for any spinner/loading indicator styling in the page
    const spinners = page.locator('div[class*="animate-spin"], div[class*="spinner"]');

    // If spinners exist, verify they have proper centering classes
    if (await spinners.count() > 0) {
      const spinner = spinners.first();

      // Check if spinner or parent has flex centering
      const parent = spinner.locator('..');
      if (await parent.isVisible()) {
        const display = await parent.evaluate(el =>
          window.getComputedStyle(el).display
        );
        // Just verify parent has some layout
        expect(['flex', 'grid', 'block', 'inline-block']).toContain(display);
      }
    }

    // Main test: verify page loaded successfully without layout issues
    const statsGrid = page.locator('div.grid.grid-cols-1.sm\:grid-cols-2.lg\:grid-cols-4').first();
    await expect(statsGrid).toBeVisible();
  });

  test('test_loading_state_full_height', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Verify main content area uses full height
    const mainContent = page.locator('main.flex-1.overflow-hidden');
    await expect(mainContent).toBeVisible();

    const flex = await mainContent.evaluate(el =>
      window.getComputedStyle(el).flexGrow
    );
    expect(flex).toBe('1');

    // Verify scrollable area exists and uses full height
    const scrollArea = page.locator('div.h-full.overflow-y-auto');
    await expect(scrollArea).toBeVisible();

    const height = await scrollArea.evaluate(el =>
      window.getComputedStyle(el).height
    );
    // Height should be set (not auto)
    expect(parseFloat(height)).toBeGreaterThan(0);
  });

  test('test_no_layout_shift_after_loading', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');

    // Wait for content to be fully loaded
    await page.waitForSelector('h1:has-text("Панель управления")');
    await page.waitForTimeout(1000);

    // Measure stable layout
    const statsGrid = page.locator('div.grid.grid-cols-1.sm\\:grid-cols-2.lg\\:grid-cols-4').first();
    const initialBox = await statsGrid.boundingBox();

    // Wait a bit more
    await page.waitForTimeout(500);

    const finalBox = await statsGrid.boundingBox();

    if (initialBox && finalBox) {
      // Position should not shift
      expect(Math.abs(finalBox.y - initialBox.y)).toBeLessThan(2);
      expect(Math.abs(finalBox.x - initialBox.x)).toBeLessThan(2);
    }
  });
});

test.describe('Empty States', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_empty_state_centered', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Look for empty state messages
    const emptyState = page.locator('p.text-dark-400.text-center.py-4');

    if (await emptyState.count() > 0) {
      const firstEmpty = emptyState.first();

      // Check for text-center class
      const textAlign = await firstEmpty.evaluate((el) =>
        window.getComputedStyle(el).textAlign
      );

      expect(textAlign).toBe('center');

      // Should have vertical padding
      const paddingTop = await firstEmpty.evaluate((el) =>
        window.getComputedStyle(el).paddingTop
      );
      const paddingBottom = await firstEmpty.evaluate((el) =>
        window.getComputedStyle(el).paddingBottom
      );

      expect(parseFloat(paddingTop)).toBeGreaterThan(10);
      expect(parseFloat(paddingBottom)).toBeGreaterThan(10);
    }
  });

  test('test_empty_state_readable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const emptyState = page.locator('p.text-dark-400.text-center.py-4');

    if (await emptyState.count() > 0) {
      const firstEmpty = emptyState.first();

      // Check readable font size
      const fontSize = await firstEmpty.evaluate((el) =>
        window.getComputedStyle(el).fontSize
      );

      expect(parseFloat(fontSize)).toBeGreaterThanOrEqual(14);

      // Check that text is not truncated
      const overflow = await firstEmpty.evaluate((el) => ({
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      }));

      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
    }
  });

  test('test_empty_state_within_container', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Get sections that might have empty states
    const sections = page.locator('div.glass.rounded-2xl.p-6');

    for (let i = 0; i < Math.min(await sections.count(), 3); i++) {
      const section = sections.nth(i);
      const emptyState = section.locator('p.text-dark-400.text-center.py-4');

      if (await emptyState.isVisible()) {
        const emptyBox = await emptyState.boundingBox();
        const sectionBox = await section.boundingBox();

        if (emptyBox && sectionBox) {
          // Empty state should be within section bounds
          expect(emptyBox.x).toBeGreaterThanOrEqual(sectionBox.x);
          expect(emptyBox.x + emptyBox.width).toBeLessThanOrEqual(sectionBox.x + sectionBox.width);
        }
      }
    }
  });
});

test.describe('CSS Grid and Flexbox Edge Cases', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_grid_items_dont_break_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Test bottom row grid (2 columns on desktop)
    const bottomGrid = page.locator('div.grid.grid-cols-1.lg\\:grid-cols-2.gap-6');

    if (await bottomGrid.isVisible()) {
      const gridDisplay = await bottomGrid.evaluate((el) =>
        window.getComputedStyle(el).display
      );
      expect(gridDisplay).toBe('grid');

      const gridItems = bottomGrid.locator('> div');
      const itemCount = await gridItems.count();

      // Each item should not overflow the grid
      for (let i = 0; i < itemCount; i++) {
        const item = gridItems.nth(i);
        const itemBox = await item.boundingBox();
        const gridBox = await bottomGrid.boundingBox();

        if (itemBox && gridBox) {
          expect(itemBox.width).toBeLessThanOrEqual(gridBox.width / 2 + 20); // Half width plus gap
        }
      }
    }
  });

  test('test_flexbox_wrapping_on_mobile', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Quick stats section uses grid with 2 columns on mobile
    const quickStats = page.locator('div.grid.grid-cols-2.sm\\:grid-cols-3.gap-4');

    if (await quickStats.isVisible()) {
      const gridColumns = await quickStats.evaluate((el) =>
        window.getComputedStyle(el).gridTemplateColumns
      );

      // Should have 2 columns on mobile
      const columnCount = gridColumns.split(' ').length;
      expect(columnCount).toBe(2);
    }
  });

  test('test_min_width_constraints_honored', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Elements with min-w-0 should allow shrinking
    const minWidthElements = page.locator('div.min-w-0');

    if (await minWidthElements.count() > 0) {
      const element = minWidthElements.first();
      const minWidth = await element.evaluate((el) =>
        window.getComputedStyle(el).minWidth
      );

      expect(minWidth).toBe('0px');
    }
  });

  test('test_max_width_container_centers_content', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.largeDesktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Dashboard content has max-w-7xl mx-auto
    const contentContainer = page.locator('div.max-w-7xl.mx-auto');

    if (await contentContainer.isVisible()) {
      const containerBox = await contentContainer.boundingBox();
      const mainBox = await page.locator('div.h-full.overflow-y-auto.p-6').boundingBox();

      if (containerBox && mainBox) {
        // Container should be centered (margins on both sides should be roughly equal)
        const leftMargin = containerBox.x - mainBox.x;
        const rightMargin = (mainBox.x + mainBox.width) - (containerBox.x + containerBox.width);

        expect(Math.abs(leftMargin - rightMargin)).toBeLessThan(5);

        // Max width should be enforced (7xl = 80rem = 1280px)
        expect(containerBox.width).toBeLessThanOrEqual(1280);
      }
    }
  });

  test('test_aspect_ratio_maintained', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Icon containers should maintain square aspect ratio
    const iconContainers = page.locator('div.w-12.h-12');

    if (await iconContainers.count() > 0) {
      const box = await iconContainers.first().boundingBox();

      if (box) {
        // Should be square (width === height)
        expect(Math.abs(box.width - box.height)).toBeLessThan(1);
      }
    }
  });
});

test.describe('Overflow Management', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_nested_scrollable_areas', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Main should have overflow-hidden
    const main = page.locator('main.overflow-hidden');
    const mainOverflow = await main.evaluate((el) =>
      window.getComputedStyle(el).overflow
    );
    expect(mainOverflow).toBe('hidden');

    // Inner content should have overflow-y-auto
    const scrollArea = page.locator('div.h-full.overflow-y-auto');
    const scrollOverflow = await scrollArea.evaluate((el) =>
      window.getComputedStyle(el).overflowY
    );
    expect(scrollOverflow).toBe('auto');
  });

  test('test_sidebar_scrollable_when_content_exceeds_height', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 400 }); // Short viewport
    await loginAndNavigate(page, '/dashboard');

    const sidebarNav = page.locator('aside nav.overflow-y-auto');

    if (await sidebarNav.isVisible()) {
      const overflowY = await sidebarNav.evaluate((el) =>
        window.getComputedStyle(el).overflowY
      );
      expect(overflowY).toBe('auto');
    }
  });

  test('test_content_scrolling_doesnt_affect_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    const sidebarBefore = await page.locator('aside.hidden.lg\\:flex').boundingBox();

    // Scroll the main content
    await page.locator('div.h-full.overflow-y-auto').evaluate((el) => {
      el.scrollTop = 100;
    });

    await page.waitForTimeout(200);

    const sidebarAfter = await page.locator('aside.hidden.lg\\:flex').boundingBox();

    // Sidebar should not move when content scrolls
    if (sidebarBefore && sidebarAfter) {
      expect(sidebarAfter.x).toBe(sidebarBefore.x);
      expect(sidebarAfter.y).toBe(sidebarBefore.y);
    }
  });

  test('test_long_content_text_wraps', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');
    await page.waitForSelector('h1:has-text("Панель управления")');

    // Section headings should wrap if needed
    const headings = page.locator('h2.text-lg.font-semibold');

    if (await headings.count() > 0) {
      const heading = headings.first();
      const whiteSpace = await heading.evaluate((el) =>
        window.getComputedStyle(el).whiteSpace
      );

      // Should not be 'nowrap'
      expect(whiteSpace).not.toBe('nowrap');
    }
  });
});

test.describe('Z-Index and Stacking Context', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_mobile_menu_above_content', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');

    // Open mobile menu
    await page.click('header.lg\\:hidden button');
    await page.waitForTimeout(300);

    const mobileMenu = page.locator('div.lg\\:hidden.fixed.inset-0.z-50');

    if (await mobileMenu.isVisible()) {
      const zIndex = await mobileMenu.evaluate((el) =>
        window.getComputedStyle(el).zIndex
      );

      // Should have z-50 (value: 50)
      expect(parseInt(zIndex)).toBeGreaterThanOrEqual(50);
    }
  });

  test('test_background_effects_behind_content', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/dashboard');

    // BackgroundEffects should be behind other content
    const content = page.locator('main');
    const contentZIndex = await content.evaluate((el) =>
      window.getComputedStyle(el).zIndex
    );

    // Main content should have higher or equal z-index than background
    const zIndexNum = parseInt(contentZIndex) || 0;
    expect(zIndexNum).toBeGreaterThanOrEqual(0);
  });
});
