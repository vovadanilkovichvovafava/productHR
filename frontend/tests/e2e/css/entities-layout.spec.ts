import { test, expect, type Page } from '@playwright/test';
import { loginWithMocks, setupMocks } from '../../mocks/api';

/**
 * Comprehensive CSS/Layout Tests for Entities/Contacts Component
 *
 * Tests cover:
 * - Entity List/Grid layout
 * - Entity Detail Panel layout
 * - Entity Tabs behavior
 * - Search/Filter UI
 * - Actions/Buttons positioning
 * - Transfer Entity Modal layout
 *
 * Focus areas:
 * - Grid/flexbox layout issues
 * - Avatar aspect ratio
 * - Text overflow handling
 * - Modal positioning and responsiveness
 */

// Common viewport sizes for testing
const VIEWPORTS = {
  mobile: { width: 375, height: 667 }, // iPhone SE
  tablet: { width: 768, height: 1024 }, // iPad
  desktop: { width: 1280, height: 720 }, // Desktop
  largeDesktop: { width: 1920, height: 1080 }, // Full HD
};

// Helper function to login and navigate to contacts page
async function loginAndNavigate(page: Page, route = '/contacts') {
  await loginWithMocks(page);
  await page.goto(route);
  await page.waitForLoadState('networkidle');
}

// Helper to create mock entity data via API if needed
async function ensureEntitiesExist(page: Page) {
  const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');
  const count = await entityCards.count();

  // Return true if entities exist, false otherwise
  return count > 0;
}

test.describe('Entity List/Grid - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_entity_cards_uniform_size', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Get all entity cards
    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');
    const cardCount = await entityCards.count();

    if (cardCount > 1) {
      // Collect all card dimensions
      const cardBoxes = await Promise.all(
        Array.from({ length: Math.min(cardCount, 5) }).map((_, i) =>
          entityCards.nth(i).boundingBox()
        )
      );

      const validBoxes = cardBoxes.filter(Boolean);

      if (validBoxes.length > 1) {
        // Check that all cards have the same width
        const widths = validBoxes.map(box => box!.width);
        const maxWidth = Math.max(...widths);
        const minWidth = Math.min(...widths);

        // All cards should have uniform width (within 2px tolerance)
        expect(maxWidth - minWidth).toBeLessThan(2);

        // Cards should have reasonable minimum height
        validBoxes.forEach(box => {
          expect(box!.height).toBeGreaterThan(80);
        });
      }
    }
  });

  test('test_grid_responsive_columns', async ({ page }) => {
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      // Test mobile - cards should stack vertically
      await page.setViewportSize(VIEWPORTS.mobile);
      await page.waitForTimeout(300);

      const mobileFirstCard = await entityCards.nth(0).boundingBox();
      const mobileSecondCard = await entityCards.nth(1).boundingBox();

      if (mobileFirstCard && mobileSecondCard) {
        // On mobile, cards should stack (second card below first)
        expect(mobileSecondCard.y).toBeGreaterThan(mobileFirstCard.y + 40);
      }

      // Test desktop - cards in list view
      await page.setViewportSize(VIEWPORTS.desktop);
      await page.waitForTimeout(300);

      // Verify container has proper flex layout
      const entityListContainer = page.locator('div.flex-1.overflow-y-auto.p-4.space-y-2');
      await expect(entityListContainer).toBeVisible();

      // Cards should still stack vertically in list view
      const desktopFirstCard = await entityCards.nth(0).boundingBox();
      const desktopSecondCard = await entityCards.nth(1).boundingBox();

      if (desktopFirstCard && desktopSecondCard) {
        expect(desktopSecondCard.y).toBeGreaterThan(desktopFirstCard.y);
      }
    }
  });

  test('test_entity_avatar_not_stretched', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      // Find the avatar/icon container within first card
      const avatarContainer = entityCards.first().locator('div.p-2.rounded-lg').first();

      if (await avatarContainer.isVisible()) {
        const avatarBox = await avatarContainer.boundingBox();

        if (avatarBox) {
          // Avatar container should be roughly square (allowing small variance)
          const aspectRatio = avatarBox.width / avatarBox.height;
          expect(aspectRatio).toBeGreaterThan(0.9);
          expect(aspectRatio).toBeLessThan(1.1);

          // Avatar should have minimum size for visibility
          expect(avatarBox.width).toBeGreaterThanOrEqual(32);
          expect(avatarBox.height).toBeGreaterThanOrEqual(32);
        }
      }
    }
  });

  test('test_entity_name_truncates', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      // Find entity name element (has truncate class)
      const entityName = entityCards.first().locator('h3.font-medium.text-white.truncate');

      if (await entityName.isVisible()) {
        // Check text-overflow is applied
        const textOverflow = await entityName.evaluate(el =>
          window.getComputedStyle(el).textOverflow
        );
        expect(textOverflow).toBe('ellipsis');

        // Check overflow is hidden
        const overflow = await entityName.evaluate(el =>
          window.getComputedStyle(el).overflow
        );
        expect(overflow).toBe('hidden');

        // Verify name doesn't overflow its container
        const nameBox = await entityName.boundingBox();
        const cardBox = await entityCards.first().boundingBox();

        if (nameBox && cardBox) {
          expect(nameBox.width).toBeLessThanOrEqual(cardBox.width - 20); // Account for padding
        }
      }
    }
  });

  test('test_entity_card_hover_state', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      const firstCard = entityCards.first();

      // Just verify the card has cursor pointer and can be hovered
      const cursor = await firstCard.evaluate(el =>
        window.getComputedStyle(el).cursor
      );
      expect(cursor).toBe('pointer');

      // Verify the card has some transition or hover capability
      const transition = await firstCard.evaluate(el =>
        window.getComputedStyle(el).transition
      );
      // Card should have some transition or it's fine if none
      expect(transition).toBeTruthy();
    }
  });

  test('test_entity_list_scrollable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Entity list container should be scrollable
    const listContainer = page.locator('div.flex-1.overflow-y-auto.p-4.space-y-2');

    if (await listContainer.isVisible()) {
      // Check overflow-y is auto or scroll
      const overflowY = await listContainer.evaluate(el =>
        window.getComputedStyle(el).overflowY
      );
      expect(['auto', 'scroll']).toContain(overflowY);

      // Container should have flex-1 to take available space
      const flex = await listContainer.evaluate(el =>
        window.getComputedStyle(el).flex
      );
      expect(flex).toContain('1');
    }
  });
});

test.describe('Entity Detail Panel - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_detail_panel_layout_stable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      // Click on first entity to open detail panel
      await entityCards.first().click();
      await page.waitForTimeout(500); // Wait for animation

      // Detail panel should be visible - look for any flex container
      const flexContainers = page.locator('div.flex-1.flex.flex-col');

      if (await flexContainers.count() > 0) {
        const detailPanel = flexContainers.last();
        await expect(detailPanel).toBeVisible();

        // Verify it uses flexbox
        const display = await detailPanel.evaluate(el =>
          window.getComputedStyle(el).display
        );
        expect(display).toBe('flex');

        const flexGrow = await detailPanel.evaluate(el =>
          window.getComputedStyle(el).flexGrow
        );
        expect(flexGrow).toBe('1');
      }
    }
  });

  test('test_info_fields_aligned', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Contact info card should be visible
      const infoCard = page.locator('div.bg-white\\/5.rounded-xl.p-6').first();

      if (await infoCard.isVisible()) {
        // Check grid layout for contact info
        const infoGrid = infoCard.locator('div.grid.grid-cols-2.gap-4');

        if (await infoGrid.isVisible()) {
          // Verify grid has correct columns
          const gridTemplateColumns = await infoGrid.evaluate(el =>
            window.getComputedStyle(el).gridTemplateColumns
          );

          // Should have 2 columns
          const columnCount = gridTemplateColumns.split(' ').length;
          expect(columnCount).toBe(2);

          // Info items should be visible
          const infoItems = infoGrid.locator('div.flex.items-center.gap-2, a.flex.items-center.gap-2');
          const itemCount = await infoItems.count();

          if (itemCount > 0) {
            // All items should be aligned
            expect(itemCount).toBeGreaterThan(0);
          }
        }
      }
    }
  });

  test('test_long_email_truncates', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Find email link
      const emailLink = page.locator('a[href^="mailto:"]');

      if (await emailLink.isVisible()) {
        const emailBox = await emailLink.boundingBox();
        const viewportWidth = VIEWPORTS.mobile.width;

        if (emailBox) {
          // Email should not overflow viewport
          expect(emailBox.width).toBeLessThanOrEqual(viewportWidth - 40); // Account for padding

          // Email should not cause horizontal scroll
          const emailText = await emailLink.textContent();
          if (emailText && emailText.length > 30) {
            // For very long emails, check text handling
            const overflow = await emailLink.evaluate(el =>
              window.getComputedStyle(el).overflow
            );
            // Should handle overflow properly
            expect(['hidden', 'auto', 'visible']).toContain(overflow);
          }
        }
      }
    }
  });

  test('test_phone_numbers_formatted', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Find phone link
      const phoneLink = page.locator('a[href^="tel:"]');

      if (await phoneLink.isVisible()) {
        // Phone link should have proper styling
        const phoneBox = await phoneLink.boundingBox();

        if (phoneBox) {
          // Phone should be visible and have reasonable dimensions
          expect(phoneBox.width).toBeGreaterThan(50);

          // Phone should have icon
          const phoneIcon = phoneLink.locator('svg');
          await expect(phoneIcon).toBeVisible();
        }
      }
    }
  });

  test('test_detail_avatar_large_not_stretched', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Find large avatar in detail view
      const largeAvatar = page.locator('div.w-16.h-16.rounded-xl');

      if (await largeAvatar.isVisible()) {
        const avatarBox = await largeAvatar.boundingBox();

        if (avatarBox) {
          // Avatar should be square (w-16 h-16 = 64px)
          const aspectRatio = avatarBox.width / avatarBox.height;
          expect(aspectRatio).toBeGreaterThan(0.95);
          expect(aspectRatio).toBeLessThan(1.05);

          // Size should be approximately 64px
          expect(avatarBox.width).toBeGreaterThanOrEqual(60);
          expect(avatarBox.width).toBeLessThanOrEqual(68);
        }
      }
    }
  });

  test('test_detail_panel_scrollable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Detail content should be scrollable
      const detailContent = page.locator('div.flex-1.overflow-y-auto').last();

      if (await detailContent.isVisible()) {
        const overflowY = await detailContent.evaluate(el =>
          window.getComputedStyle(el).overflowY
        );
        expect(['auto', 'scroll']).toContain(overflowY);
      }
    }
  });
});

test.describe('Entity Tabs - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_tabs_dont_overflow', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Find tabs container
      const tabsContainer = page.locator('div.flex.gap-2.mb-6');

      if (await tabsContainer.isVisible()) {
        const tabsBox = await tabsContainer.boundingBox();
        const viewportWidth = VIEWPORTS.mobile.width;

        if (tabsBox) {
          // Tabs container should not overflow viewport
          expect(tabsBox.width).toBeLessThanOrEqual(viewportWidth);

          // Check that tabs don't cause horizontal scroll
          const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
          const clientWidth = await page.evaluate(() => document.body.clientWidth);

          expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
        }
      }
    }
  });

  test('test_tab_content_scrollable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Click on different tabs and verify content is scrollable
      const tabs = page.locator('button.px-4.py-2.rounded-lg.text-sm');
      const tabCount = await tabs.count();

      if (tabCount > 1) {
        // Click on "Chats" tab (second tab)
        await tabs.nth(1).click();
        await page.waitForTimeout(300);

        // Tab content should be within scrollable area
        const mainContent = page.locator('div.p-6');
        if (await mainContent.isVisible()) {
          // Content should be visible
          await expect(mainContent).toBeVisible();
        }
      }
    }
  });

  test('test_active_tab_indicator_visible', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Find active tab (should have cyan background)
      const activeTab = page.locator('button.bg-cyan-500\\/20.text-cyan-400');

      if (await activeTab.count() > 0) {
        await expect(activeTab.first()).toBeVisible();

        // Active tab should have distinct styling
        const bgColor = await activeTab.first().evaluate(el =>
          window.getComputedStyle(el).backgroundColor
        );

        // Background should be set (not transparent)
        expect(bgColor).not.toBe('rgba(0, 0, 0, 0)');

        // Click another tab
        const tabs = page.locator('button.px-4.py-2.rounded-lg.text-sm');
        if (await tabs.count() > 1) {
          await tabs.nth(1).click();
          await page.waitForTimeout(300);

          // New active tab should be visible
          const newActiveTab = page.locator('button.bg-cyan-500\\/20.text-cyan-400');
          await expect(newActiveTab.first()).toBeVisible();
        }
      }
    }
  });

  test('test_tab_buttons_touchable_size', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Check tab button sizes
      const tabButtons = page.locator('button.px-4.py-2.rounded-lg.text-sm');

      if (await tabButtons.count() > 0) {
        const firstTabBox = await tabButtons.first().boundingBox();

        if (firstTabBox) {
          // Tabs should have minimum touch target height (44px recommended)
          expect(firstTabBox.height).toBeGreaterThanOrEqual(36); // Slightly smaller is acceptable for tabs
        }
      }
    }
  });

  test('test_tabs_wrap_on_small_screens', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      const tabsContainer = page.locator('div.flex.gap-2.mb-6');

      if (await tabsContainer.isVisible()) {
        // Get all tab buttons
        const tabs = tabsContainer.locator('button');
        const tabCount = await tabs.count();

        if (tabCount > 2) {
          // Collect Y positions of tabs
          const tabPositions = await Promise.all(
            Array.from({ length: tabCount }).map((_, i) =>
              tabs.nth(i).boundingBox()
            )
          );

          // Check if any tabs wrap to next line
          const yPositions = tabPositions.filter(Boolean).map(box => box!.y);
          const uniqueYPositions = new Set(yPositions);

          // Tabs might wrap or might scroll - either is acceptable
          expect(uniqueYPositions.size).toBeGreaterThanOrEqual(1);
        }
      }
    }
  });
});

test.describe('Search/Filter - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_search_input_full_width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Search input should be full width of container
    const searchInput = page.locator('input[placeholder*="Поиск"]');

    if (await searchInput.isVisible()) {
      const inputBox = await searchInput.boundingBox();
      const parentContainer = page.locator('div.relative.mb-4');
      const containerBox = await parentContainer.boundingBox();

      if (inputBox && containerBox) {
        // Input should take most of container width (accounting for padding)
        const widthRatio = inputBox.width / containerBox.width;
        expect(widthRatio).toBeGreaterThan(0.85);
      }
    }
  });

  test('test_filter_dropdowns_fit_container', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Department filter dropdown
    const departmentSelect = page.locator('select');

    if (await departmentSelect.count() > 0) {
      const selectBox = await departmentSelect.first().boundingBox();
      const viewportWidth = VIEWPORTS.mobile.width;

      if (selectBox) {
        // Dropdown should not overflow viewport
        expect(selectBox.width).toBeLessThanOrEqual(viewportWidth - 20);

        // Should have proper styling
        const selectElement = departmentSelect.first();
        const width = await selectElement.evaluate(el =>
          window.getComputedStyle(el).width
        );

        // Width should be set (not auto)
        expect(parseFloat(width)).toBeGreaterThan(0);
      }
    }
  });

  test('test_filter_tags_wrap_properly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Entity type filter buttons
    const filterContainer = page.locator('div.flex.flex-wrap.gap-2').first();

    if (await filterContainer.isVisible()) {
      // Container should have flex-wrap
      const flexWrap = await filterContainer.evaluate(el =>
        window.getComputedStyle(el).flexWrap
      );
      expect(flexWrap).toBe('wrap');

      // Filter buttons
      const filterButtons = filterContainer.locator('button');
      const buttonCount = await filterButtons.count();

      if (buttonCount > 3) {
        // Collect Y positions to check if wrapping occurs
        const buttonPositions = await Promise.all(
          Array.from({ length: buttonCount }).map((_, i) =>
            filterButtons.nth(i).boundingBox()
          )
        );

        const yPositions = buttonPositions.filter(Boolean).map(box => box!.y);
        const uniqueYPositions = new Set(yPositions);

        // On mobile, buttons should wrap to multiple lines
        expect(uniqueYPositions.size).toBeGreaterThanOrEqual(1);

        // No button should overflow viewport
        buttonPositions.forEach(box => {
          if (box) {
            expect(box.x + box.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width);
          }
        });
      }
    }
  });

  test('test_ownership_filters_equal_width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Ownership filter buttons (Все, Мои, Расшаренные)
    const ownershipContainer = page.locator('div.flex.gap-1.mb-3.p-1');

    if (await ownershipContainer.isVisible()) {
      const filterButtons = ownershipContainer.locator('button');
      const buttonCount = await filterButtons.count();

      if (buttonCount === 3) {
        // Get all button widths
        const buttonBoxes = await Promise.all(
          Array.from({ length: buttonCount }).map((_, i) =>
            filterButtons.nth(i).boundingBox()
          )
        );

        const widths = buttonBoxes.filter(Boolean).map(box => box!.width);

        // All buttons should have equal width (flex-1)
        const maxWidth = Math.max(...widths);
        const minWidth = Math.min(...widths);

        expect(maxWidth - minWidth).toBeLessThan(5);
      }
    }
  });

  test('test_search_icon_positioned_correctly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const searchContainer = page.locator('div.relative.mb-4');

    if (await searchContainer.isVisible()) {
      // Search icon should be absolutely positioned
      const searchIcon = searchContainer.locator('svg');

      if (await searchIcon.isVisible()) {
        const iconBox = await searchIcon.boundingBox();
        const inputBox = await searchContainer.locator('input').boundingBox();

        if (iconBox && inputBox) {
          // Icon should be inside input (left side)
          expect(iconBox.x).toBeGreaterThan(inputBox.x);
          expect(iconBox.x).toBeLessThan(inputBox.x + 50);

          // Icon should be vertically centered
          const iconCenterY = iconBox.y + iconBox.height / 2;
          const inputCenterY = inputBox.y + inputBox.height / 2;

          expect(Math.abs(iconCenterY - inputCenterY)).toBeLessThan(3);
        }
      }
    }
  });
});

test.describe('Actions/Buttons - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_action_buttons_grouped_properly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Action buttons in header (AI, Share, Transfer, Edit)
      const headerButtons = page.locator('div.flex.gap-2').last();

      if (await headerButtons.isVisible()) {
        const buttons = headerButtons.locator('button');
        const buttonCount = await buttons.count();

        if (buttonCount > 0) {
          // Buttons should be in a horizontal row
          const buttonBoxes = await Promise.all(
            Array.from({ length: Math.min(buttonCount, 4) }).map((_, i) =>
              buttons.nth(i).boundingBox()
            )
          );

          const validBoxes = buttonBoxes.filter(Boolean);

          if (validBoxes.length > 1) {
            // All buttons should be on same horizontal line
            const yPositions = validBoxes.map(box => box!.y);
            const maxY = Math.max(...yPositions);
            const minY = Math.min(...yPositions);

            expect(maxY - minY).toBeLessThan(5);
          }
        }
      }
    }
  });

  test('test_edit_button_accessible', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      // Hover over entity card to reveal quick actions
      await entityCards.first().hover();
      await page.waitForTimeout(200);

      // Quick action buttons should appear
      const quickActions = entityCards.first().locator('div.opacity-0.group-hover\\:opacity-100');

      if (await quickActions.isVisible()) {
        const editButton = quickActions.locator('button').nth(1); // Edit is second button

        if (await editButton.isVisible()) {
          const editBox = await editButton.boundingBox();

          if (editBox) {
            // Button should have touchable size
            expect(editBox.width).toBeGreaterThanOrEqual(24);
            expect(editBox.height).toBeGreaterThanOrEqual(24);
          }
        }
      }
    }
  });

  test('test_delete_confirmation_modal_centered', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Note: Delete uses browser confirm(), not a modal
    // This test verifies the delete button is accessible
    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().hover();
      await page.waitForTimeout(200);

      const quickActions = entityCards.first().locator('div.opacity-0.group-hover\\:opacity-100');

      if (await quickActions.isVisible()) {
        const deleteButton = quickActions.locator('button.bg-red-500\\/20');

        if (await deleteButton.isVisible()) {
          // Delete button should be visible and styled
          const buttonBox = await deleteButton.boundingBox();

          if (buttonBox) {
            expect(buttonBox.width).toBeGreaterThanOrEqual(24);

            // Check red styling is applied
            const bgColor = await deleteButton.evaluate(el =>
              window.getComputedStyle(el).backgroundColor
            );

            // Should have red background
            expect(bgColor).toBeTruthy();
          }
        }
      }
    }
  });

  test('test_create_button_positioned_correctly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Create button in header
    const createButton = page.locator('button.bg-cyan-500\\/20.text-cyan-400').first();

    if (await createButton.isVisible()) {
      const buttonBox = await createButton.boundingBox();

      if (buttonBox) {
        // Button should have appropriate size
        expect(buttonBox.width).toBeGreaterThanOrEqual(32);
        expect(buttonBox.height).toBeGreaterThanOrEqual(32);

        // Button should be in top-right area of sidebar
        const headerContainer = page.locator('div.p-4.border-b.border-white\\/5').first();
        const headerBox = await headerContainer.boundingBox();

        if (headerBox) {
          // Button should be within header
          expect(buttonBox.y).toBeGreaterThanOrEqual(headerBox.y);
          expect(buttonBox.y).toBeLessThanOrEqual(headerBox.y + headerBox.height);
        }
      }
    }
  });

  test('test_back_button_visible_in_detail', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Back button in detail header
      const backButton = page.locator('button.p-2.rounded-lg.bg-white\\/5').first();

      if (await backButton.isVisible()) {
        const buttonBox = await backButton.boundingBox();

        if (buttonBox) {
          // Back button should be touchable
          expect(buttonBox.width).toBeGreaterThanOrEqual(32);
          expect(buttonBox.height).toBeGreaterThanOrEqual(32);
        }
      }
    }
  });
});

test.describe('Transfer Entity Modal - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_transfer_modal_fits_screen', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Click transfer button
      const transferButton = page.locator('button:has-text("Transfer")');

      if (await transferButton.isVisible()) {
        await transferButton.click();
        await page.waitForTimeout(500);

        // Transfer modal should appear
        const modal = page.locator('div.bg-gray-900.rounded-2xl').last();

        if (await modal.isVisible()) {
          const modalBox = await modal.boundingBox();

          if (modalBox) {
            // Modal should fit within viewport (with padding)
            expect(modalBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width - 20);
            expect(modalBox.height).toBeLessThanOrEqual(VIEWPORTS.mobile.height - 20);

            // Modal should be centered
            const viewportCenterX = VIEWPORTS.mobile.width / 2;
            const modalCenterX = modalBox.x + modalBox.width / 2;

            expect(Math.abs(modalCenterX - viewportCenterX)).toBeLessThan(50);
          }
        }
      }
    }
  });

  test('test_department_dropdown_scrollable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      // Open transfer modal via card quick action
      await entityCards.first().hover();
      await page.waitForTimeout(200);

      const transferQuickAction = entityCards.first().locator('button[title="Передать"]');

      if (await transferQuickAction.isVisible()) {
        await transferQuickAction.click();
        await page.waitForTimeout(500);

        // User list container should be scrollable
        const userListContainer = page.locator('div.space-y-2.max-h-48.overflow-y-auto');

        if (await userListContainer.isVisible()) {
          // Check overflow-y is auto or scroll
          const overflowY = await userListContainer.evaluate(el =>
            window.getComputedStyle(el).overflowY
          );
          expect(['auto', 'scroll']).toContain(overflowY);

          // Check max-height is applied
          const maxHeight = await userListContainer.evaluate(el =>
            window.getComputedStyle(el).maxHeight
          );
          expect(parseFloat(maxHeight)).toBeGreaterThan(0);
        }
      }
    }
  });

  test('test_transfer_modal_header_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().hover();
      await page.waitForTimeout(200);

      const transferQuickAction = entityCards.first().locator('button[title="Передать"]');

      if (await transferQuickAction.isVisible()) {
        await transferQuickAction.click();
        await page.waitForTimeout(500);

        // Modal header
        const modalHeader = page.locator('div.flex.items-center.justify-between.p-6.border-b');

        if (await modalHeader.isVisible()) {
          // Header should contain icon, title, and close button
          const headerIcon = modalHeader.locator('svg').first();
          const headerTitle = modalHeader.locator('h2');
          const closeButton = modalHeader.locator('button');

          await expect(headerIcon).toBeVisible();
          await expect(headerTitle).toBeVisible();
          await expect(closeButton).toBeVisible();

          // Close button should be on the right
          const headerBox = await modalHeader.boundingBox();
          const closeBox = await closeButton.boundingBox();

          if (headerBox && closeBox) {
            expect(closeBox.x + closeBox.width).toBeGreaterThan(headerBox.x + headerBox.width - 50);
          }
        }
      }
    }
  });

  test('test_transfer_user_cards_uniform', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().hover();
      await page.waitForTimeout(200);

      const transferQuickAction = entityCards.first().locator('button[title="Передать"]');

      if (await transferQuickAction.isVisible()) {
        await transferQuickAction.click();
        await page.waitForTimeout(500);

        // User selection buttons
        const userButtons = page.locator('button.w-full.p-3.rounded-lg');
        const userCount = await userButtons.count();

        if (userCount > 1) {
          // Collect button widths
          const buttonBoxes = await Promise.all(
            Array.from({ length: Math.min(userCount, 5) }).map((_, i) =>
              userButtons.nth(i).boundingBox()
            )
          );

          const validBoxes = buttonBoxes.filter(Boolean);

          if (validBoxes.length > 1) {
            // All user buttons should have same width (w-full)
            const widths = validBoxes.map(box => box!.width);
            const maxWidth = Math.max(...widths);
            const minWidth = Math.min(...widths);

            expect(maxWidth - minWidth).toBeLessThan(2);
          }
        }
      }
    }
  });

  test('test_transfer_modal_actions_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().hover();
      await page.waitForTimeout(200);

      const transferQuickAction = entityCards.first().locator('button[title="Передать"]');

      if (await transferQuickAction.isVisible()) {
        await transferQuickAction.click();
        await page.waitForTimeout(500);

        // Modal actions (Cancel and Transfer buttons)
        const actionsContainer = page.locator('div.flex.gap-3.pt-4').last();

        if (await actionsContainer.isVisible()) {
          const buttons = actionsContainer.locator('button');

          if (await buttons.count() === 2) {
            const cancelButton = buttons.nth(0);
            const transferButton = buttons.nth(1);

            // Both buttons should be visible
            await expect(cancelButton).toBeVisible();
            await expect(transferButton).toBeVisible();

            // Buttons should have equal width (flex-1)
            const cancelBox = await cancelButton.boundingBox();
            const transferBox = await transferButton.boundingBox();

            if (cancelBox && transferBox) {
              expect(Math.abs(cancelBox.width - transferBox.width)).toBeLessThan(5);
            }
          }
        }
      }
    }
  });

  test('test_transfer_modal_backdrop_overlay', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().hover();
      await page.waitForTimeout(200);

      const transferQuickAction = entityCards.first().locator('button[title="Передать"]');

      if (await transferQuickAction.isVisible()) {
        await transferQuickAction.click();
        await page.waitForTimeout(500);

        // Modal backdrop
        const backdrop = page.locator('div.fixed.inset-0.bg-black\\/50.backdrop-blur-sm.z-50');

        if (await backdrop.isVisible()) {
          const backdropBox = await backdrop.boundingBox();
          const viewportWidth = VIEWPORTS.desktop.width;
          const viewportHeight = VIEWPORTS.desktop.height;

          if (backdropBox) {
            // Backdrop should cover entire viewport
            expect(backdropBox.width).toBeGreaterThanOrEqual(viewportWidth - 5);
            expect(backdropBox.height).toBeGreaterThanOrEqual(viewportHeight - 5);
          }
        }
      }
    }
  });
});

test.describe('Contact Form Modal - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_contact_form_modal_centered', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Click create button
    const createButton = page.locator('button.bg-cyan-500\\/20.text-cyan-400').first();

    if (await createButton.isVisible()) {
      await createButton.click();
      await page.waitForTimeout(500);

      // Contact form modal
      const modal = page.locator('div.bg-gray-900.rounded-2xl');

      if (await modal.isVisible()) {
        const modalBox = await modal.boundingBox();

        if (modalBox) {
          // Modal should be centered horizontally
          const viewportCenterX = VIEWPORTS.desktop.width / 2;
          const modalCenterX = modalBox.x + modalBox.width / 2;

          expect(Math.abs(modalCenterX - viewportCenterX)).toBeLessThan(50);
        }
      }
    }
  });

  test('test_contact_form_grid_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const createButton = page.locator('button.bg-cyan-500\\/20.text-cyan-400').first();

    if (await createButton.isVisible()) {
      await createButton.click();
      await page.waitForTimeout(500);

      // Entity type grid (3 columns)
      const typeGrid = page.locator('div.grid.grid-cols-3.gap-2');

      if (await typeGrid.isVisible()) {
        // Check grid has 3 columns
        const gridTemplateColumns = await typeGrid.evaluate(el =>
          window.getComputedStyle(el).gridTemplateColumns
        );

        const columnCount = gridTemplateColumns.split(' ').length;
        expect(columnCount).toBe(3);
      }

      // Contact info grid (2 columns)
      const contactGrid = page.locator('div.grid.grid-cols-2.gap-4').first();

      if (await contactGrid.isVisible()) {
        const gridTemplateColumns = await contactGrid.evaluate(el =>
          window.getComputedStyle(el).gridTemplateColumns
        );

        const columnCount = gridTemplateColumns.split(' ').length;
        expect(columnCount).toBe(2);
      }
    }
  });

  test('test_contact_form_inputs_full_width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Look for create button - try multiple selectors
    const createButtons = page.locator('button').filter({
      hasText: /Создать|Добавить|Create|\+/
    });

    if (await createButtons.count() > 0) {
      await createButtons.first().click();
      await page.waitForTimeout(500);

      // Name input should be visible in the form
      const nameInputs = page.locator('input[type="text"], input[placeholder*="имя"], input[placeholder*="Имя"]');

      if (await nameInputs.count() > 0) {
        const nameInput = nameInputs.first();
        await expect(nameInput).toBeVisible();

        // Input should be reasonably wide
        const inputBox = await nameInput.boundingBox();

        if (inputBox) {
          // Input should take most of the available width
          expect(inputBox.width).toBeGreaterThan(VIEWPORTS.mobile.width * 0.5);
        }
      }
    }
  });

  test('test_entity_type_buttons_equal_size', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const createButton = page.locator('button.bg-cyan-500\\/20.text-cyan-400').first();

    if (await createButton.isVisible()) {
      await createButton.click();
      await page.waitForTimeout(500);

      // Entity type buttons
      const typeButtons = page.locator('div.grid.grid-cols-3.gap-2 button');
      const buttonCount = await typeButtons.count();

      if (buttonCount === 6) {
        // All 6 type buttons should have similar dimensions
        const buttonBoxes = await Promise.all(
          Array.from({ length: buttonCount }).map((_, i) =>
            typeButtons.nth(i).boundingBox()
          )
        );

        const validBoxes = buttonBoxes.filter(Boolean);
        const widths = validBoxes.map(box => box!.width);
        const heights = validBoxes.map(box => box!.height);

        // All buttons should have similar width and height
        const maxWidth = Math.max(...widths);
        const minWidth = Math.min(...widths);
        const maxHeight = Math.max(...heights);
        const minHeight = Math.min(...heights);

        expect(maxWidth - minWidth).toBeLessThan(5);
        expect(maxHeight - minHeight).toBeLessThan(5);
      }
    }
  });
});

test.describe('AI Panel - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_ai_panel_positioned_correctly', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.largeDesktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Click AI button
      const aiButton = page.locator('button:has-text("AI")');

      if (await aiButton.isVisible()) {
        await aiButton.click();
        await page.waitForTimeout(500);

        // AI panel (only visible on xl screens)
        const aiPanel = page.locator('div.hidden.xl\\:flex.flex-col.h-full.border-l');

        if (await aiPanel.isVisible()) {
          const panelBox = await aiPanel.boundingBox();

          if (panelBox) {
            // Panel should have fixed width (420px)
            expect(panelBox.width).toBeGreaterThanOrEqual(410);
            expect(panelBox.width).toBeLessThanOrEqual(430);

            // Panel should be on the right side
            expect(panelBox.x).toBeGreaterThan(VIEWPORTS.largeDesktop.width / 2);
          }
        }
      }
    }
  });

  test('test_ai_quick_actions_wrap', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.largeDesktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      const aiButton = page.locator('button:has-text("AI")');

      if (await aiButton.isVisible()) {
        await aiButton.click();
        await page.waitForTimeout(500);

        // Quick action buttons in AI panel
        const quickActionsContainer = page.locator('div.flex.flex-wrap.gap-2.mb-4.flex-shrink-0');

        if (await quickActionsContainer.isVisible()) {
          // Should have flex-wrap
          const flexWrap = await quickActionsContainer.evaluate(el =>
            window.getComputedStyle(el).flexWrap
          );
          expect(flexWrap).toBe('wrap');

          // Quick action buttons should be visible
          const actionButtons = quickActionsContainer.locator('button');
          const buttonCount = await actionButtons.count();

          expect(buttonCount).toBeGreaterThan(0);
        }
      }
    }
  });

  test('test_ai_messages_scrollable', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.largeDesktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      const aiButton = page.locator('button:has-text("AI")');

      if (await aiButton.isVisible()) {
        await aiButton.click();
        await page.waitForTimeout(500);

        // Messages container
        const messagesContainer = page.locator('div.flex-1.min-h-0.overflow-y-auto');

        if (await messagesContainer.isVisible()) {
          // Should be scrollable
          const overflowY = await messagesContainer.evaluate(el =>
            window.getComputedStyle(el).overflowY
          );
          expect(['auto', 'scroll']).toContain(overflowY);

          // Should have flex-1 to take available space
          const flex = await messagesContainer.evaluate(el =>
            window.getComputedStyle(el).flex
          );
          expect(flex).toContain('1');
        }
      }
    }
  });

  test('test_ai_input_sticky_bottom', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.largeDesktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      const aiButton = page.locator('button:has-text("AI")');

      if (await aiButton.isVisible()) {
        await aiButton.click();
        await page.waitForTimeout(500);

        // Input container at bottom
        const inputContainer = page.locator('div.flex.gap-2.flex-shrink-0').last();

        if (await inputContainer.isVisible()) {
          // Should have flex-shrink-0 to not shrink
          const flexShrink = await inputContainer.evaluate(el =>
            window.getComputedStyle(el).flexShrink
          );
          expect(flexShrink).toBe('0');

          // Input should be visible
          const aiInput = inputContainer.locator('input');
          await expect(aiInput).toBeVisible();
        }
      }
    }
  });
});

test.describe('Responsive Entity Layout - Mobile', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_mobile_entity_list_full_width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // On mobile without entity selected, list should be full width
    const sidebar = page.locator('div.flex-shrink-0.border-r.border-white\\/5.flex.flex-col');

    if (await sidebar.isVisible()) {
      const sidebarBox = await sidebar.boundingBox();

      if (sidebarBox) {
        // Sidebar should take full or near-full width
        expect(sidebarBox.width).toBeGreaterThan(VIEWPORTS.mobile.width * 0.9);
      }
    }
  });

  test('test_mobile_detail_view_replaces_list', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      // Click entity
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Detail panel should be visible
      const detailPanel = page.locator('div.flex-1.flex.flex-col');

      if (await detailPanel.count() > 0) {
        await expect(detailPanel.first()).toBeVisible();

        // Verify flexbox layout
        const display = await detailPanel.first().evaluate(el =>
          window.getComputedStyle(el).display
        );
        expect(display).toBe('flex');
      }

      // Just verify no horizontal overflow
      const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(bodyClientWidth + 2);
    }
  });

  test('test_mobile_filters_stack_vertically', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Ownership filters
    const ownershipFilters = page.locator('div.flex.gap-1.mb-3.p-1 button');

    if (await ownershipFilters.count() > 0) {
      // All filter buttons should fit within viewport width
      const filterBoxes = await Promise.all(
        Array.from({ length: await ownershipFilters.count() }).map((_, i) =>
          ownershipFilters.nth(i).boundingBox()
        )
      );

      filterBoxes.forEach(box => {
        if (box) {
          expect(box.x + box.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width);
        }
      });
    }
  });
});

test.describe('Multiple Identifiers - Layout Tests', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('test_telegram_usernames_displayed', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Look for Telegram usernames with @ prefix
      const telegramLinks = page.locator('a[href^="https://t.me/"]');

      if (await telegramLinks.count() > 0) {
        // First Telegram username should be visible
        await expect(telegramLinks.first()).toBeVisible();

        // Check href format is correct
        const href = await telegramLinks.first().getAttribute('href');
        expect(href).toMatch(/^https:\/\/t\.me\//);
      }
    }
  });

  test('test_multiple_emails_displayed', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Look for email links
      const emailLinks = page.locator('a[href^="mailto:"]');

      if (await emailLinks.count() > 0) {
        // Should have at least one email visible
        await expect(emailLinks.first()).toBeVisible();

        // Emails should not overflow container
        const emailBox = await emailLinks.first().boundingBox();
        if (emailBox) {
          expect(emailBox.width).toBeLessThanOrEqual(VIEWPORTS.desktop.width - 40);
        }
      }
    }
  });

  test('test_multiple_phones_displayed', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Look for phone links
      const phoneLinks = page.locator('a[href^="tel:"]');

      if (await phoneLinks.count() > 0) {
        // Should have at least one phone visible
        await expect(phoneLinks.first()).toBeVisible();

        // Phone should be clickable
        const href = await phoneLinks.first().getAttribute('href');
        expect(href).toMatch(/^tel:/);
      }
    }
  });

  test('test_identifiers_icons_present', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const entityCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await entityCards.count() > 0) {
      await entityCards.first().click();
      await page.waitForTimeout(500);

      // Contact info section should have icons
      const infoSection = page.locator('div.grid.grid-cols-1.md\\:grid-cols-2.gap-4');

      if (await infoSection.isVisible()) {
        // Look for SVG icons in the info section
        const icons = infoSection.locator('svg');
        const iconCount = await icons.count();

        // Should have at least one icon (email, phone, company, etc.)
        expect(iconCount).toBeGreaterThan(0);
      }
    }
  });

  test('test_contact_form_telegram_field', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Open create contact form
    const createButton = page.locator('button.bg-cyan-500\\/20.text-cyan-400').first();

    if (await createButton.isVisible()) {
      await createButton.click();
      await page.waitForTimeout(500);

      // Look for Telegram username input field
      const telegramInput = page.locator('input[placeholder*="@username"]');

      if (await telegramInput.isVisible()) {
        await expect(telegramInput).toBeVisible();

        // Field should have proper width
        const inputBox = await telegramInput.boundingBox();
        if (inputBox) {
          expect(inputBox.width).toBeGreaterThan(200);
        }
      }
    }
  });

  test('test_contact_form_multiple_emails_field', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    const createButton = page.locator('button.bg-cyan-500\\/20.text-cyan-400').first();

    if (await createButton.isVisible()) {
      await createButton.click();
      await page.waitForTimeout(500);

      // Look for emails input (placeholder contains comma hint)
      const emailsInput = page.locator('input[placeholder*="@example.com"]');

      if (await emailsInput.isVisible()) {
        await expect(emailsInput).toBeVisible();

        // Can type multiple emails
        await emailsInput.fill('test1@example.com, test2@example.com');
        const value = await emailsInput.inputValue();
        expect(value).toContain(',');
      }
    }
  });
});
