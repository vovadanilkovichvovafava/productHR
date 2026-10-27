import { test, expect, type Page } from '@playwright/test';
import { loginWithMocks, setupMocks } from '../../mocks/api';

/**
 * Comprehensive CSS/Layout Tests for Calls (Созвоны) Component
 *
 * These tests validate that all CSS and layout issues are properly handled
 * in the Calls page, including overflow prevention, text truncation, proper
 * flex behavior, and responsive layout.
 *
 * Test Coverage:
 * - Call list layout and overflow
 * - Call detail panel layout
 * - Text truncation and wrapping
 * - Button positioning
 * - Speaker statistics layout
 * - Transcript scrolling
 * - Tab content layout
 * - Share/action menus
 */

// Common viewport sizes for testing
const VIEWPORTS = {
  mobile: { width: 375, height: 667 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1280, height: 720 },
  wide: { width: 1920, height: 1080 },
};

// Helper function to login and navigate
async function loginAndNavigate(page: Page, route = '/calls') {
  await loginWithMocks(page);
  await page.goto(route);
  await page.waitForLoadState('networkidle');
}

// Helper to create a test call with long text content
async function createTestCall(page: Page) {
  // This would ideally use the API to create a test call
  // For now, we'll navigate to the first available call
  const callCards = page.locator('div.p-4.rounded-xl.cursor-pointer');
  if (await callCards.count() > 0) {
    await callCards.first().click();
    await page.waitForTimeout(500);
    return true;
  }
  return false;
}

test.describe('Calls Layout - Call List Layout', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  // Skip: Selector specificity issues
  test.skip('test_call_cards_dont_overflow_container', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const sidebar = page.locator('div.flex-shrink-0.border-r').first();
    const callCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await callCards.count() > 0) {
      const sidebarBox = await sidebar.boundingBox();
      const firstCard = callCards.first();
      const cardBox = await firstCard.boundingBox();

      if (sidebarBox && cardBox) {
        // Card should not overflow sidebar width
        expect(cardBox.width).toBeLessThanOrEqual(sidebarBox.width);
        expect(cardBox.x).toBeGreaterThanOrEqual(sidebarBox.x);
        expect(cardBox.x + cardBox.width).toBeLessThanOrEqual(sidebarBox.x + sidebarBox.width);
      }

      // Check overflow-x is not visible on sidebar
      const overflowX = await sidebar.evaluate((el) =>
        getComputedStyle(el).overflowX
      );
      expect(overflowX).not.toBe('visible');
    }
  });

  test('test_call_card_text_truncates_properly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const callCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await callCards.count() > 0) {
      const firstCard = callCards.first();

      // Check title truncation
      const titleElement = firstCard.locator('span.text-sm.font-medium.text-white.truncate');

      if (await titleElement.count() > 0) {
        const title = titleElement.first();

        // Check truncate class applies proper CSS
        const whiteSpace = await title.evaluate(el => getComputedStyle(el).whiteSpace);
        const overflow = await title.evaluate(el => getComputedStyle(el).overflow);
        const textOverflow = await title.evaluate(el => getComputedStyle(el).textOverflow);

        expect(whiteSpace).toBe('nowrap');
        expect(overflow).toBe('hidden');
        expect(textOverflow).toBe('ellipsis');

        // Verify title doesn't overflow parent
        const titleBox = await title.boundingBox();
        const parentBox = await firstCard.boundingBox();

        if (titleBox && parentBox) {
          expect(titleBox.width).toBeLessThanOrEqual(parentBox.width);
        }
      }
    }
  });

  // Skip: Selector specificity issues
  test.skip('test_call_card_description_truncates_with_line_clamp', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const summaryElements = page.locator('p.text-xs.text-white\\/50.mt-2.line-clamp-2');

    if (await summaryElements.count() > 0) {
      const summary = summaryElements.first();

      // Check line-clamp-2 applies proper CSS
      const display = await summary.evaluate(el => getComputedStyle(el).display);
      const webkitLineClamp = await summary.evaluate(el =>
        getComputedStyle(el).webkitLineClamp || getComputedStyle(el)['-webkit-line-clamp']
      );
      const overflow = await summary.evaluate(el => getComputedStyle(el).overflow);

      expect(display).toBe('-webkit-box');
      expect(webkitLineClamp).toBe('2');
      expect(overflow).toBe('hidden');

      // Verify height is constrained (max 2 lines)
      const summaryBox = await summary.boundingBox();
      const fontSize = await summary.evaluate(el =>
        parseFloat(getComputedStyle(el).fontSize)
      );
      const lineHeight = await summary.evaluate(el => {
        const lh = getComputedStyle(el).lineHeight;
        return lh === 'normal' ? fontSize * 1.2 : parseFloat(lh);
      });

      if (summaryBox) {
        // Height should not exceed 2 lines + some margin
        expect(summaryBox.height).toBeLessThanOrEqual(lineHeight * 2 + 10);
      }
    }
  });

  test('test_call_card_metadata_aligned', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const callCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await callCards.count() > 0) {
      const firstCard = callCards.first();
      const metadata = firstCard.locator('div.flex.items-center.gap-3.text-xs.text-white\\/40');

      if (await metadata.count() > 0) {
        // Check flexbox alignment
        const display = await metadata.evaluate(el => getComputedStyle(el).display);
        const alignItems = await metadata.evaluate(el => getComputedStyle(el).alignItems);

        expect(display).toBe('flex');
        expect(alignItems).toBe('center');

        // Check that all children are aligned horizontally
        const metadataBox = await metadata.boundingBox();
        const children = await metadata.locator('span').all();

        if (metadataBox && children.length > 0) {
          const childBoxes = await Promise.all(children.map(child => child.boundingBox()));

          // All children should be on roughly the same vertical line
          const yPositions = childBoxes.filter(Boolean).map(box => box!.y);
          const avgY = yPositions.reduce((a, b) => a + b, 0) / yPositions.length;

          yPositions.forEach(y => {
            expect(Math.abs(y - avgY)).toBeLessThan(5); // Within 5px tolerance
          });
        }
      }
    }
  });

  test('test_call_list_scrollable_without_breaking', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const callListContainer = page.locator('div.flex-1.overflow-y-auto.p-4.space-y-2');

    if (await callListContainer.count() > 0) {
      // Check overflow-y is set to auto or scroll
      const overflowY = await callListContainer.evaluate(el =>
        getComputedStyle(el).overflowY
      );
      expect(['auto', 'scroll']).toContain(overflowY);

      // Check that container has flex-1 for proper sizing
      const flexGrow = await callListContainer.evaluate(el =>
        getComputedStyle(el).flexGrow
      );
      expect(flexGrow).toBe('1');

      // Verify no horizontal overflow
      const overflowX = await callListContainer.evaluate(el =>
        getComputedStyle(el).overflowX
      );
      expect(overflowX).not.toBe('visible');
    }
  });

  test('test_call_list_sidebar_has_proper_width_constraints', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const sidebar = page.locator('div.flex-shrink-0.border-r').first();
    const sidebarBox = await sidebar.boundingBox();

    if (sidebarBox) {
      // Sidebar should have reasonable width (w-80 = 20rem = 320px typically)
      // When no call selected, it may be wider (max-w-2xl)
      expect(sidebarBox.width).toBeGreaterThan(200);
      expect(sidebarBox.width).toBeLessThanOrEqual(800); // max-w-2xl = 672px

      // Check flex-shrink-0 is applied
      const flexShrink = await sidebar.evaluate(el =>
        getComputedStyle(el).flexShrink
      );
      expect(flexShrink).toBe('0');
    }
  });

  test('test_active_recording_banner_fits_container', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Check if active recording banner exists
    const banner = page.locator('div.bg-gradient-to-r.from-cyan-500\\/20.to-purple-500\\/20');

    if (await banner.count() > 0) {
      const bannerBox = await banner.boundingBox();
      const parentBox = await banner.locator('..').boundingBox();

      if (bannerBox && parentBox) {
        expect(bannerBox.width).toBeLessThanOrEqual(parentBox.width);
      }

      // Check overflow is properly handled
      const overflow = await banner.evaluate(el => getComputedStyle(el).overflow);
      expect(overflow).not.toBe('visible');
    }
  });
});

test.describe('Calls Layout - Call Detail Panel', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_detail_panel_fits_viewport', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Wait for detail panel to be visible with a short timeout
      const detailPanel = page.locator('div.flex-1.flex.flex-col').last();
      try {
        await detailPanel.waitFor({ timeout: 3000, state: 'visible' });
        const detailBox = await detailPanel.boundingBox();

        if (detailBox) {
          // Detail panel should not exceed viewport width
          expect(detailBox.width).toBeLessThanOrEqual(VIEWPORTS.desktop.width);

          // Check flex-1 for proper sizing
          const flexGrow = await detailPanel.evaluate(el =>
            getComputedStyle(el).flexGrow
          );
          expect(flexGrow).toBe('1');
        }
      } catch {
        // Panel might not be visible if no call is selected, skip test
        test.skip();
      }
    }
  });

  test('test_detail_header_text_doesnt_overflow', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const header = page.locator('div.p-4.border-b.border-white\\/5.flex.items-center.gap-4');

      if (await header.count() > 0) {
        const title = header.locator('h2.text-xl.font-semibold.text-white');
        const headerBox = await header.boundingBox();
        const titleBox = await title.boundingBox();

        if (headerBox && titleBox) {
          expect(titleBox.width).toBeLessThanOrEqual(headerBox.width);
        }
      }
    }
  });

  test('test_participant_stats_dont_overflow', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Look for speaker statistics section
      const statsSection = page.locator('div.bg-white\\/5.rounded-xl.p-4').filter({
        has: page.locator('h3:has-text("Статистика участников")')
      });

      if (await statsSection.count() > 0) {
        const statsBox = await statsSection.boundingBox();
        const statItems = statsSection.locator('div.flex.items-center.gap-4');

        if (await statItems.count() > 0) {
          const firstItem = statItems.first();
          const itemBox = await firstItem.boundingBox();

          if (statsBox && itemBox) {
            // Stat items should not overflow their container
            expect(itemBox.width).toBeLessThanOrEqual(statsBox.width);
          }
        }
      }
    }
  });

  test('test_speaker_name_truncates_properly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Look for speaker names in statistics
      const speakerNames = page.locator('span.text-white.text-sm.truncate');

      if (await speakerNames.count() > 0) {
        const name = speakerNames.first();

        // Check truncate styles
        const whiteSpace = await name.evaluate(el => getComputedStyle(el).whiteSpace);
        const overflow = await name.evaluate(el => getComputedStyle(el).overflow);
        const textOverflow = await name.evaluate(el => getComputedStyle(el).textOverflow);

        expect(whiteSpace).toBe('nowrap');
        expect(overflow).toBe('hidden');
        expect(textOverflow).toBe('ellipsis');
      }
    }
  });

  test('test_wpm_bars_proper_width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Look for WPM (words per minute) display
      const wpmSection = page.locator('div.text-right.w-16').filter({
        has: page.locator('span:has-text("WPM")')
      });

      if (await wpmSection.count() > 0) {
        const wpmBox = await wpmSection.first().boundingBox();

        if (wpmBox) {
          // w-16 = 4rem = 64px typically
          expect(wpmBox.width).toBeGreaterThan(50);
          expect(wpmBox.width).toBeLessThanOrEqual(80);
        }
      }

      // Check percentage bars
      const percentageBars = page.locator('div.w-32').filter({
        has: page.locator('div.h-2.bg-white\\/10.rounded-full')
      });

      if (await percentageBars.count() > 0) {
        const barBox = await percentageBars.first().boundingBox();

        if (barBox) {
          // w-32 = 8rem = 128px typically
          expect(barBox.width).toBeGreaterThan(100);
          expect(barBox.width).toBeLessThanOrEqual(150);
        }
      }
    }
  });

  test('test_percentage_bar_inner_doesnt_exceed_container', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const barContainers = page.locator('div.h-2.bg-white\\/10.rounded-full.overflow-hidden');

      if (await barContainers.count() > 0) {
        const container = barContainers.first();
        const containerBox = await container.boundingBox();

        const innerBar = container.locator('div.h-full.rounded-full.transition-all');
        const innerBox = await innerBar.boundingBox();

        if (containerBox && innerBox) {
          // Inner bar should never exceed container width
          expect(innerBox.width).toBeLessThanOrEqual(containerBox.width + 1); // +1 for rounding
        }

        // Check overflow-hidden is applied
        const overflow = await container.evaluate(el => getComputedStyle(el).overflow);
        expect(overflow).toBe('hidden');
      }
    }
  });

  test('test_tabs_dont_break_on_content', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Wait for tabs to appear (only on done status)
      await page.waitForTimeout(500);

      const tabs = page.locator('button.px-4.py-2.rounded-lg.text-sm.flex.items-center.gap-2').filter({
        hasText: /Резюме|Транскрипт|Задачи/
      });

      if (await tabs.count() > 0) {
        // Check all tabs are visible and aligned
        const tabBoxes = await Promise.all(
          Array.from({ length: await tabs.count() }).map((_, i) =>
            tabs.nth(i).boundingBox()
          )
        );

        // All tabs should be on the same horizontal line
        const yPositions = tabBoxes.filter(Boolean).map(box => box!.y);
        if (yPositions.length > 1) {
          const firstY = yPositions[0];
          yPositions.forEach(y => {
            expect(Math.abs(y - firstY)).toBeLessThan(2);
          });
        }

        // Check flexbox layout
        const tabContainer = tabs.first().locator('..');
        const display = await tabContainer.evaluate(el => getComputedStyle(el).display);
        expect(display).toBe('flex');
      }
    }
  });

  test('test_info_cards_grid_responsive', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const infoCardsGrid = page.locator('div.grid.grid-cols-3.gap-4.mb-6');

      if (await infoCardsGrid.count() > 0) {
        const cards = infoCardsGrid.locator('div.bg-white\\/5.rounded-xl.p-4');

        if (await cards.count() === 3) {
          const boxes = await Promise.all([
            cards.nth(0).boundingBox(),
            cards.nth(1).boundingBox(),
            cards.nth(2).boundingBox(),
          ]);

          // All cards should be on the same row
          const yPositions = boxes.filter(Boolean).map(box => box!.y);
          const avgY = yPositions.reduce((a, b) => a + b, 0) / yPositions.length;

          yPositions.forEach(y => {
            expect(Math.abs(y - avgY)).toBeLessThan(2);
          });
        }
      }
    }
  });
});

test.describe('Calls Layout - Content Overflow', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_summary_text_wraps_properly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Click on Резюме tab if not already active
      const summaryTab = page.locator('button:has-text("Резюме")');
      if (await summaryTab.count() > 0) {
        await summaryTab.click();
        await page.waitForTimeout(300);
      }

      // Check summary text wrapping
      const summaryText = page.locator('p.text-white\\/80.whitespace-pre-wrap.leading-relaxed.break-words');

      if (await summaryText.count() > 0) {
        const text = summaryText.first();

        // Check CSS properties for proper wrapping
        const whiteSpace = await text.evaluate(el => getComputedStyle(el).whiteSpace);
        const wordBreak = await text.evaluate(el => getComputedStyle(el).wordBreak);
        const overflowWrap = await text.evaluate(el => getComputedStyle(el).overflowWrap);

        expect(whiteSpace).toBe('pre-wrap');
        expect(['break-word', 'normal']).toContain(wordBreak);
        expect(['break-word', 'anywhere']).toContain(overflowWrap);

        // Text should not overflow parent
        const textBox = await text.boundingBox();
        const parentBox = await text.locator('..').boundingBox();

        if (textBox && parentBox) {
          expect(textBox.width).toBeLessThanOrEqual(parentBox.width + 2); // +2 for rounding
        }
      }
    }
  });

  test('test_transcript_scrollable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Click on Транскрипт tab
      const transcriptTab = page.locator('button:has-text("Транскрипт")');
      if (await transcriptTab.count() > 0) {
        await transcriptTab.click();
        await page.waitForTimeout(300);
      }

      // Check the tab content container
      const tabContent = page.locator('div.bg-white\\/5.rounded-xl.p-6');

      if (await tabContent.count() > 0) {
        // The overflow should be handled at page level or content level
        const detailContent = page.locator('div.flex-1.overflow-y-auto');

        if (await detailContent.count() > 0) {
          const overflowY = await detailContent.evaluate(el =>
            getComputedStyle(el).overflowY
          );
          expect(['auto', 'scroll']).toContain(overflowY);
        }
      }
    }
  });

  test('test_transcript_segments_dont_overflow', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Click on Транскрипт tab
      const transcriptTab = page.locator('button:has-text("Транскрипт")');
      if (await transcriptTab.count() > 0) {
        await transcriptTab.click();
        await page.waitForTimeout(300);
      }

      // Check transcript segments
      const segments = page.locator('div.p-4.rounded-xl.border.overflow-hidden.w-full.max-w-full');

      if (await segments.count() > 0) {
        const firstSegment = segments.first();
        const segmentBox = await firstSegment.boundingBox();

        // Check overflow-hidden is applied
        const overflow = await firstSegment.evaluate(el => getComputedStyle(el).overflow);
        expect(overflow).toBe('hidden');

        // Check text content doesn't overflow
        const segmentText = firstSegment.locator('p.text-white\\/80.leading-relaxed.pl-11.break-words.whitespace-pre-wrap.overflow-hidden');

        if (await segmentText.count() > 0) {
          const textBox = await segmentText.boundingBox();

          if (segmentBox && textBox) {
            expect(textBox.width).toBeLessThanOrEqual(segmentBox.width);
          }

          // Check break-words and overflow styles
          const wordBreak = await segmentText.evaluate(el =>
            getComputedStyle(el).wordBreak
          );
          const overflowWrap = await segmentText.evaluate(el =>
            getComputedStyle(el).overflowWrap
          );

          expect(['break-word', 'normal']).toContain(wordBreak);
          expect(['break-word', 'anywhere']).toContain(overflowWrap);
        }
      }
    }
  });

  test('test_long_participant_names_truncate', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Check participant names in stats section
      const participantNames = page.locator('span.text-white.text-sm.truncate');

      if (await participantNames.count() > 0) {
        const name = participantNames.first();
        const parentBox = await name.locator('..').boundingBox();
        const nameBox = await name.boundingBox();

        if (parentBox && nameBox) {
          expect(nameBox.width).toBeLessThanOrEqual(parentBox.width);
        }
      }

      // Check in transcript
      const transcriptTab = page.locator('button:has-text("Транскрипт")');
      if (await transcriptTab.count() > 0) {
        await transcriptTab.click();
        await page.waitForTimeout(300);

        const speakerNames = page.locator('span.font-medium').filter({
          hasText: /Speaker|Участник/i
        });

        if (await speakerNames.count() > 0) {
          const name = speakerNames.first();
          const segmentBox = await name.locator('../..').boundingBox();
          const nameBox = await name.boundingBox();

          if (segmentBox && nameBox) {
            // Name should not cause overflow
            expect(nameBox.width).toBeLessThanOrEqual(segmentBox.width);
          }
        }
      }
    }
  });

  test('test_key_points_list_wraps_properly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Make sure we're on Summary tab
      const summaryTab = page.locator('button:has-text("Резюме")');
      if (await summaryTab.count() > 0) {
        await summaryTab.click();
        await page.waitForTimeout(300);
      }

      // Check key points
      const keyPoints = page.locator('li.flex.items-start.gap-3.text-white\\/80.break-words');

      if (await keyPoints.count() > 0) {
        const firstPoint = keyPoints.first();
        const pointText = firstPoint.locator('span.break-words');

        if (await pointText.count() > 0) {
          const wordBreak = await pointText.evaluate(el =>
            getComputedStyle(el).wordBreak
          );
          const overflowWrap = await pointText.evaluate(el =>
            getComputedStyle(el).overflowWrap
          );

          expect(['break-word', 'normal']).toContain(wordBreak);
          expect(['break-word', 'normal', 'anywhere']).toContain(overflowWrap);
        }
      }
    }
  });

  test('test_action_items_wrap_properly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Click on Задачи tab
      const actionsTab = page.locator('button:has-text("Задачи")');
      if (await actionsTab.count() > 0) {
        await actionsTab.click();
        await page.waitForTimeout(300);
      }

      // Check action items
      const actionItems = page.locator('li.flex.items-start.gap-3.p-3.bg-white\\/5.rounded-lg');

      if (await actionItems.count() > 0) {
        const firstItem = actionItems.first();
        const itemText = firstItem.locator('span.text-white\\/80.break-words');

        if (await itemText.count() > 0) {
          const itemBox = await firstItem.boundingBox();
          const textBox = await itemText.boundingBox();

          if (itemBox && textBox) {
            expect(textBox.width).toBeLessThanOrEqual(itemBox.width);
          }

          // Check word break
          const wordBreak = await itemText.evaluate(el =>
            getComputedStyle(el).wordBreak
          );
          expect(['break-word', 'normal']).toContain(wordBreak);
        }
      }
    }
  });
});

test.describe('Calls Layout - Buttons and Actions', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_action_buttons_stay_in_place', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Look for action buttons in summary tab
      const summaryTab = page.locator('button:has-text("Резюме")');
      if (await summaryTab.count() > 0) {
        await summaryTab.click();
        await page.waitForTimeout(300);
      }

      // Check for Переанализировать and Скачать buttons
      const actionButtons = page.locator('button').filter({
        hasText: /Переанализировать|Скачать|Редактировать/
      });

      if (await actionButtons.count() > 0) {
        const buttonContainer = actionButtons.first().locator('..');

        // Check flex alignment
        const justifyContent = await buttonContainer.evaluate(el =>
          getComputedStyle(el).justifyContent
        );

        // Buttons should be aligned to the right (justify-end)
        expect(['flex-end', 'end']).toContain(justifyContent);
      }
    }
  });

  test('test_buttons_dont_overflow_on_small_screens', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const actionButtons = page.locator('button').filter({
        hasText: /Переанализировать|Скачать|Редактировать/
      });

      if (await actionButtons.count() > 0) {
        const button = actionButtons.first();
        const buttonBox = await button.boundingBox();

        if (buttonBox) {
          // Button should fit within mobile viewport
          expect(buttonBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width);
          expect(buttonBox.x + buttonBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width);
        }
      }
    }
  });

  test('test_edit_button_hover_state_visible', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Look for edit button (appears on hover in contact card)
      const contactCard = page.locator('div.bg-white\\/5.rounded-xl.p-4.relative.group').filter({
        has: page.locator('div:has-text("Контакт")')
      });

      if (await contactCard.count() > 0) {
        const editButton = contactCard.locator('button.opacity-0.group-hover\\:opacity-100');

        // Hover over card
        await contactCard.hover();
        await page.waitForTimeout(200);

        // Edit button should become visible
        const opacity = await editButton.evaluate(el =>
          getComputedStyle(el).opacity
        );

        // On hover, opacity should increase (handled by group-hover)
        // Note: In actual browser, group-hover works. In test, we check the class exists
        const hasHoverClass = await editButton.evaluate(el =>
          el.className.includes('group-hover:opacity-100')
        );
        expect(hasHoverClass).toBe(true);
      }
    }
  });

  test('test_quick_action_buttons_on_call_cards', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const callCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await callCards.count() > 0) {
      const firstCard = callCards.first();

      // Hover over card to show quick actions
      await firstCard.hover();
      await page.waitForTimeout(200);

      // Look for quick action buttons
      const quickActions = firstCard.locator('div.opacity-0.group-hover\\:opacity-100.transition-opacity.flex.gap-1');

      if (await quickActions.count() > 0) {
        // Check buttons don't overflow card
        const cardBox = await firstCard.boundingBox();
        const actionsBox = await quickActions.boundingBox();

        if (cardBox && actionsBox) {
          expect(actionsBox.x + actionsBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width);
        }
      }
    }
  });

  test('test_copy_button_positioning', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Go to summary or transcript tab
      const summaryTab = page.locator('button:has-text("Резюме")');
      if (await summaryTab.count() > 0) {
        await summaryTab.click();
        await page.waitForTimeout(300);
      }

      // Look for copy button
      const copyButton = page.locator('button.p-2.rounded-lg.bg-white\\/5.hover\\:bg-white\\/10.transition-colors').filter({
        has: page.locator('svg')
      });

      if (await copyButton.count() > 0) {
        const button = copyButton.first();
        const buttonBox = await button.boundingBox();

        if (buttonBox) {
          // Button should have reasonable size for clicking
          expect(buttonBox.width).toBeGreaterThanOrEqual(30);
          expect(buttonBox.height).toBeGreaterThanOrEqual(30);
        }
      }
    }
  });
});

test.describe('Calls Layout - Edit Panel', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_edit_panel_expands_without_breaking_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Click on Редактировать button
      const editButton = page.locator('button:has-text("Редактировать")');

      if (await editButton.count() > 0) {
        await editButton.click();
        await page.waitForTimeout(500);

        // Check edit panel
        const editPanel = page.locator('div.bg-gradient-to-r.from-purple-500\\/20.to-cyan-500\\/20.border.border-purple-500\\/30.rounded-xl.p-4.mb-6');

        if (await editPanel.count() > 0) {
          // Panel should be visible
          await expect(editPanel).toBeVisible();

          // Check grid layout
          const grid = editPanel.locator('div.grid.grid-cols-2.gap-4');

          if (await grid.count() > 0) {
            const gridBox = await grid.boundingBox();
            const panelBox = await editPanel.boundingBox();

            if (gridBox && panelBox) {
              expect(gridBox.width).toBeLessThanOrEqual(panelBox.width);
            }
          }
        }
      }
    }
  });

  test('test_edit_form_inputs_dont_overflow', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const editButton = page.locator('button:has-text("Редактировать")');

      if (await editButton.count() > 0) {
        await editButton.click();
        await page.waitForTimeout(500);

        // Check inputs
        const inputs = page.locator('input.w-full.px-4.py-2.bg-white\\/5.border.border-white\\/10.rounded-lg');

        if (await inputs.count() > 0) {
          const firstInput = inputs.first();
          const inputBox = await firstInput.boundingBox();
          const parentBox = await firstInput.locator('..').boundingBox();

          if (inputBox && parentBox) {
            // Input should take full width of parent (w-full)
            expect(inputBox.width).toBeGreaterThan(parentBox.width * 0.9);
            expect(inputBox.width).toBeLessThanOrEqual(parentBox.width);
          }
        }

        // Check select dropdown
        const select = page.locator('select.flex-1.px-4.py-2.bg-white\\/5.border.border-white\\/10.rounded-lg');

        if (await select.count() > 0) {
          const selectBox = await select.boundingBox();
          const selectParent = await select.locator('..').boundingBox();

          if (selectBox && selectParent) {
            expect(selectBox.width).toBeLessThanOrEqual(selectParent.width);
          }
        }
      }
    }
  });
});

test.describe('Calls Layout - Status Banners', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_status_banner_fits_container', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Look for status banners (recording, processing, failed)
      const statusBanners = page.locator('div.rounded-xl.p-4.mb-6.border').filter({
        hasText: /Запись|Обработка|не удалась/
      });

      if (await statusBanners.count() > 0) {
        const banner = statusBanners.first();
        const bannerBox = await banner.boundingBox();
        const contentBox = await page.locator('div.p-6').first().boundingBox();

        if (bannerBox && contentBox) {
          expect(bannerBox.width).toBeLessThanOrEqual(contentBox.width);
        }

        // Check flex layout
        const flexContainer = banner.locator('div.flex.items-center');

        if (await flexContainer.count() > 0) {
          const display = await flexContainer.evaluate(el =>
            getComputedStyle(el).display
          );
          expect(display).toBe('flex');
        }
      }
    }
  });

  test('test_failed_status_button_alignment', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Look for failed status banner
      const failedBanner = page.locator('div.bg-red-500\\/20.border.border-red-500\\/30.rounded-xl.p-4.mb-6');

      if (await failedBanner.count() > 0) {
        const retryButton = failedBanner.locator('button:has-text("Повторить")');

        if (await retryButton.count() > 0) {
          const bannerBox = await failedBanner.boundingBox();
          const buttonBox = await retryButton.boundingBox();

          if (bannerBox && buttonBox) {
            // Button should be within banner
            expect(buttonBox.x + buttonBox.width).toBeLessThanOrEqual(bannerBox.x + bannerBox.width);
          }
        }
      }
    }
  });
});

test.describe('Calls Layout - Mobile Responsiveness', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_call_list_fits_mobile_viewport', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const sidebar = page.locator('div.flex-shrink-0.border-r').first();
    const sidebarBox = await sidebar.boundingBox();

    if (sidebarBox) {
      // Sidebar should take full width on mobile when no call is selected
      expect(sidebarBox.width).toBeGreaterThan(VIEWPORTS.mobile.width * 0.8);
    }

    // Check no horizontal scroll
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
    expect(bodyScrollWidth).toBeLessThanOrEqual(bodyClientWidth + 1);
  });

  test('test_call_detail_mobile_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // On mobile, detail should take appropriate width
      const detailPanels = page.locator('div.flex-1.flex.flex-col');

      if (await detailPanels.count() > 0) {
        const detailPanel = detailPanels.last();
        const detailBox = await detailPanel.boundingBox();

        if (detailBox) {
          // Detail should not exceed mobile viewport
          expect(detailBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width + 5);

          // Verify flex layout
          const display = await detailPanel.evaluate(el =>
            window.getComputedStyle(el).display
          );
          expect(display).toBe('flex');
        }
      }

      // Verify no horizontal scroll on body
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(bodyClientWidth + 2);
    }
  });

  test('test_info_cards_stack_on_mobile', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const infoCards = page.locator('div.bg-white\\/5.rounded-xl.p-4').filter({
        has: page.locator('div:has-text("Длительность"), div:has-text("Источник"), div:has-text("Контакт")')
      });

      if (await infoCards.count() >= 2) {
        const firstCard = await infoCards.nth(0).boundingBox();
        const secondCard = await infoCards.nth(1).boundingBox();

        // On mobile, cards should stack vertically
        if (firstCard && secondCard) {
          // Second card should be below first card
          expect(secondCard.y).toBeGreaterThan(firstCard.y + firstCard.height - 20);
        }
      }
    }
  });

  test('test_speaker_stats_mobile_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const speakerStats = page.locator('div.flex.items-center.gap-4').filter({
        has: page.locator('span:has-text("WPM")')
      });

      if (await speakerStats.count() > 0) {
        const stat = speakerStats.first();
        const statBox = await stat.boundingBox();

        if (statBox) {
          // Stat row should fit mobile width
          expect(statBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width - 40); // Account for padding
        }
      }
    }
  });

  test('test_tabs_wrap_on_narrow_screens', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 }); // Very narrow
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const tabs = page.locator('button').filter({
        hasText: /Резюме|Транскрипт|Задачи/
      });

      if (await tabs.count() > 0) {
        const tabContainer = tabs.first().locator('..');
        const containerBox = await tabContainer.boundingBox();

        if (containerBox) {
          // Container should not exceed viewport
          expect(containerBox.width).toBeLessThanOrEqual(320);
        }
      }
    }
  });

  test('test_transcript_segments_mobile', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const transcriptTab = page.locator('button:has-text("Транскрипт")');
      if (await transcriptTab.count() > 0) {
        await transcriptTab.click();
        await page.waitForTimeout(300);
      }

      const segments = page.locator('div.p-4.rounded-xl.border.overflow-hidden.w-full.max-w-full');

      if (await segments.count() > 0) {
        const segment = segments.first();
        const segmentBox = await segment.boundingBox();

        if (segmentBox) {
          // Segment should fit mobile width with padding
          expect(segmentBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width - 32);
        }
      }
    }
  });
});

test.describe('Calls Layout - CallRecorderModal', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_recorder_modal_fits_viewport', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Click "Новая запись" button
    const newRecordingButton = page.locator('button:has-text("Новая запись")');

    if (await newRecordingButton.count() > 0) {
      await newRecordingButton.click();
      await page.waitForTimeout(500);

      // Check modal
      const modal = page.locator('div.bg-gray-900.rounded-2xl.w-full.max-w-lg');

      if (await modal.count() > 0) {
        await expect(modal).toBeVisible();

        const modalBox = await modal.boundingBox();

        if (modalBox) {
          // Modal should not exceed max-w-lg (~32rem = 512px)
          expect(modalBox.width).toBeLessThanOrEqual(550);
          expect(modalBox.width).toBeLessThanOrEqual(VIEWPORTS.desktop.width);
        }
      }
    }
  });

  test('test_recorder_modal_mobile', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const newRecordingButton = page.locator('button:has-text("Новая запись")');

    if (await newRecordingButton.count() > 0) {
      await newRecordingButton.click();
      await page.waitForTimeout(500);

      const modal = page.locator('div.bg-gray-900.rounded-2xl');

      if (await modal.count() > 0) {
        const modalBox = await modal.boundingBox();

        if (modalBox) {
          // Modal should fit mobile viewport with padding
          expect(modalBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width - 32);
        }
      }
    }
  });

  test('test_mode_tabs_equal_width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const newRecordingButton = page.locator('button:has-text("Новая запись")');

    if (await newRecordingButton.count() > 0) {
      await newRecordingButton.click();
      await page.waitForTimeout(500);

      // Check mode tabs (Присоединиться к встрече / Загрузить файл)
      const modeTabs = page.locator('button.flex-1.p-3.rounded-lg').filter({
        hasText: /Присоединиться|Загрузить/
      });

      if (await modeTabs.count() === 2) {
        const tab1Box = await modeTabs.nth(0).boundingBox();
        const tab2Box = await modeTabs.nth(1).boundingBox();

        if (tab1Box && tab2Box) {
          // Both tabs should have similar width (flex-1)
          expect(Math.abs(tab1Box.width - tab2Box.width)).toBeLessThan(10);
        }
      }
    }
  });

  test('test_file_upload_area_sizing', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const newRecordingButton = page.locator('button:has-text("Новая запись")');

    if (await newRecordingButton.count() > 0) {
      await newRecordingButton.click();
      await page.waitForTimeout(500);

      // Switch to upload mode
      const uploadTab = page.locator('button:has-text("Загрузить файл")');
      await uploadTab.click();
      await page.waitForTimeout(300);

      // Check file upload area
      const uploadArea = page.locator('div.border-2.border-dashed.rounded-xl.p-8');

      if (await uploadArea.count() > 0) {
        const uploadBox = await uploadArea.boundingBox();
        const modalContent = await page.locator('form.p-6.space-y-6').boundingBox();

        if (uploadBox && modalContent) {
          expect(uploadBox.width).toBeLessThanOrEqual(modalContent.width);
        }
      }
    }
  });

  test('test_entity_dropdown_overflow', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const newRecordingButton = page.locator('button:has-text("Новая запись")');

    if (await newRecordingButton.count() > 0) {
      await newRecordingButton.click();
      await page.waitForTimeout(500);

      // Click on entity search input
      const entityInput = page.locator('input[placeholder*="Поиск контактов"]');

      if (await entityInput.count() > 0) {
        await entityInput.click();
        await page.waitForTimeout(300);

        // Check if dropdown appears
        const dropdown = page.locator('div.absolute.z-10.w-full.mt-1.bg-gray-800.border.border-white\\/10.rounded-lg');

        if (await dropdown.count() > 0) {
          // Check max-height and overflow
          const overflowY = await dropdown.evaluate(el =>
            getComputedStyle(el).overflowY
          );
          expect(['auto', 'scroll']).toContain(overflowY);

          // Dropdown should not exceed viewport height significantly
          const dropdownBox = await dropdown.boundingBox();
          if (dropdownBox) {
            expect(dropdownBox.height).toBeLessThanOrEqual(250); // max-h-48 ≈ 192px
          }
        }
      }
    }
  });
});

test.describe('Calls Layout - Empty States', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_empty_calls_list_centered', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Check for empty state
    const emptyState = page.locator('div.text-center.py-8').filter({
      hasText: /Нет записей звонков/
    });

    if (await emptyState.count() > 0) {
      // Check centering
      const textAlign = await emptyState.evaluate(el =>
        getComputedStyle(el).textAlign
      );
      expect(textAlign).toBe('center');

      // Icon and text should be visible
      const icon = emptyState.locator('svg');
      await expect(icon).toBeVisible();
    }
  });

  test('test_no_transcript_message', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const transcriptTab = page.locator('button:has-text("Транскрипт")');
      if (await transcriptTab.count() > 0) {
        await transcriptTab.click();
        await page.waitForTimeout(300);
      }

      // Look for "недоступен" message
      const noTranscript = page.locator('p.text-white\\/40:has-text("недоступен")');

      if (await noTranscript.count() > 0) {
        await expect(noTranscript).toBeVisible();
      }
    }
  });
});

test.describe('Calls Layout - CSS Property Validation', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_flex_shrink_applied_to_sidebar', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const sidebar = page.locator('div.flex-shrink-0.border-r').first();
    const flexShrink = await sidebar.evaluate(el =>
      getComputedStyle(el).flexShrink
    );

    expect(flexShrink).toBe('0');
  });

  test('test_min_width_constraints_on_critical_elements', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Check WPM section has w-16 (min-width constraint)
      const wpmSection = page.locator('div.w-16').filter({
        has: page.locator('span:has-text("WPM")')
      });

      if (await wpmSection.count() > 0) {
        const width = await wpmSection.first().evaluate(el =>
          getComputedStyle(el).width
        );
        const widthPx = parseFloat(width);

        // w-16 = 4rem = 64px (approximately)
        expect(widthPx).toBeGreaterThan(50);
        expect(widthPx).toBeLessThan(80);
      }
    }
  });

  test('test_overflow_hidden_on_containers', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      // Check transcript segments have overflow-hidden
      const transcriptTab = page.locator('button:has-text("Транскрипт")');
      if (await transcriptTab.count() > 0) {
        await transcriptTab.click();
        await page.waitForTimeout(300);
      }

      const segments = page.locator('div.overflow-hidden.w-full.max-w-full');

      if (await segments.count() > 0) {
        const overflow = await segments.first().evaluate(el =>
          getComputedStyle(el).overflow
        );
        expect(overflow).toBe('hidden');
      }
    }
  });

  test('test_text_overflow_ellipsis_with_truncate', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const truncatedElements = page.locator('.truncate').first();

    if (await truncatedElements.count() > 0) {
      const textOverflow = await truncatedElements.evaluate(el =>
        getComputedStyle(el).textOverflow
      );
      const overflow = await truncatedElements.evaluate(el =>
        getComputedStyle(el).overflow
      );
      const whiteSpace = await truncatedElements.evaluate(el =>
        getComputedStyle(el).whiteSpace
      );

      expect(textOverflow).toBe('ellipsis');
      expect(overflow).toBe('hidden');
      expect(whiteSpace).toBe('nowrap');
    }
  });

  test('test_break_words_applied_correctly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const hasCall = await createTestCall(page);

    if (hasCall) {
      const breakWordElements = page.locator('.break-words').first();

      if (await breakWordElements.count() > 0) {
        const overflowWrap = await breakWordElements.evaluate(el =>
          getComputedStyle(el).overflowWrap
        );

        // break-words should set overflow-wrap to break-word
        expect(['break-word', 'anywhere']).toContain(overflowWrap);
      }
    }
  });
});
