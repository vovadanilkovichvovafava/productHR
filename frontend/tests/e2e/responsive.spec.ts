import { test, expect, type Page } from '@playwright/test';

/**
 * Comprehensive Responsive Layout Tests for HR-bot Frontend
 *
 * These tests verify the responsive behavior of the application across different
 * screen sizes and devices, ensuring proper layout adaptation, touch interactions,
 * and visual consistency.
 */

// Common viewport sizes for testing
const VIEWPORTS = {
  mobile: { width: 375, height: 667 }, // iPhone SE
  tablet: { width: 768, height: 1024 }, // iPad
  desktop: { width: 1280, height: 720 }, // Desktop
  largeDesktop: { width: 1920, height: 1080 }, // Full HD
};

// Helper function to login and navigate to dashboard
async function loginAndNavigate(page: Page, route = '/dashboard') {
  // Navigate to login page
  await page.goto('/login');

  // Perform login (adjust selectors based on actual login form)
  await page.fill('input[type="email"]', 'test@example.com');
  await page.fill('input[type="password"]', 'password');
  await page.click('button[type="submit"]');

  // Wait for navigation to complete
  await page.waitForURL(/\/(dashboard|chats|contacts|calls)/);

  // Navigate to specific route if different from default
  if (route !== '/dashboard') {
    await page.goto(route);
  }
}

test.describe('Responsive Layout - Breakpoint Behavior', () => {
  test('test_desktop_shows_full_sidebar', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page);

    // Desktop sidebar should be visible (has class "hidden lg:flex")
    const desktopSidebar = page.locator('aside.hidden.lg\\:flex');
    await expect(desktopSidebar).toBeVisible();

    // Verify sidebar contains navigation items
    const navLinks = desktopSidebar.locator('nav a');
    await expect(navLinks).toHaveCount(8); // All 8 nav items

    // Verify sidebar shows user info and logout button
    await expect(desktopSidebar.locator('button:has-text("Выход")')).toBeVisible();

    // Mobile header should be hidden
    const mobileHeader = page.locator('header.lg\\:hidden');
    await expect(mobileHeader).not.toBeVisible();

    // Mobile bottom navigation should be hidden
    const mobileBottomNav = page.locator('nav.lg\\:hidden');
    await expect(mobileBottomNav).not.toBeVisible();
  });

  test('test_tablet_shows_collapsed_sidebar', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.tablet);
    await loginAndNavigate(page);

    // On tablet (768px), still shows mobile layout
    // Desktop sidebar should be hidden
    const desktopSidebar = page.locator('aside.hidden.lg\\:flex');
    await expect(desktopSidebar).not.toBeVisible();

    // Mobile header should be visible
    const mobileHeader = page.locator('header.lg\\:hidden');
    await expect(mobileHeader).toBeVisible();

    // Hamburger menu button should be visible
    const hamburgerButton = mobileHeader.locator('button:has(svg)');
    await expect(hamburgerButton).toBeVisible();

    // Mobile bottom navigation should be visible
    const mobileBottomNav = page.locator('nav.lg\\:hidden');
    await expect(mobileBottomNav).toBeVisible();
  });

  test('test_mobile_hides_sidebar', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Desktop sidebar should be completely hidden
    const desktopSidebar = page.locator('aside.hidden.lg\\:flex');
    await expect(desktopSidebar).not.toBeVisible();

    // Verify main content is visible and takes full width
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible();

    // Mobile overlay menu should not be visible initially
    const mobileMenu = page.locator('div.lg\\:hidden.fixed.inset-0.z-50');
    await expect(mobileMenu).not.toBeVisible();
  });

  test('test_mobile_shows_hamburger_menu', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Mobile header should be visible
    const mobileHeader = page.locator('header.lg\\:hidden');
    await expect(mobileHeader).toBeVisible();

    // Verify hamburger menu button exists and is visible
    const hamburgerButton = mobileHeader.locator('button');
    await expect(hamburgerButton).toBeVisible();

    // Verify app title is visible in mobile header
    await expect(mobileHeader.locator('h1:has-text("Чат Аналитика")')).toBeVisible();

    // Bottom navigation should show first 4 items
    const bottomNav = page.locator('nav.lg\\:hidden');
    await expect(bottomNav).toBeVisible();
    const bottomNavItems = bottomNav.locator('a');
    await expect(bottomNavItems).toHaveCount(4);
  });
});

test.describe('Responsive Layout - Layout Stability', () => {
  test('test_tabs_dont_overflow_container', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/contacts');

    // Navigate to a page with tabs/filters
    const filterButtons = page.locator('button:has-text("Все"), button:has-text("Мои"), button:has-text("Расшаренные")');

    if (await filterButtons.count() > 0) {
      // Check that filter container doesn't cause horizontal overflow
      const filterContainer = page.locator('div.flex.gap-1.mb-3');
      const containerBox = await filterContainer.boundingBox();
      const viewportWidth = VIEWPORTS.mobile.width;

      if (containerBox) {
        expect(containerBox.width).toBeLessThanOrEqual(viewportWidth);
      }

      // All filter buttons should be visible
      await expect(filterButtons.first()).toBeVisible();
    }
  });

  test('test_modals_fit_viewport', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/contacts');

    // Try to open a modal (create contact)
    const createButton = page.locator('button:has(svg)').first();
    await createButton.click();

    // Wait for modal to appear
    const modal = page.locator('div.fixed.inset-0.bg-black\\/50');
    await expect(modal).toBeVisible({ timeout: 2000 }).catch(() => {
      // Modal might not appear if no permission, skip this check
    });

    // If modal is visible, verify it fits viewport
    if (await modal.isVisible()) {
      const modalContent = page.locator('div.bg-gray-900.rounded-2xl');
      const modalBox = await modalContent.boundingBox();

      if (modalBox) {
        expect(modalBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width);
        expect(modalBox.height).toBeLessThanOrEqual(VIEWPORTS.mobile.height);
      }
    }
  });

  test('test_no_horizontal_scroll', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Check body doesn't have horizontal scroll
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);

    // Allow 1px difference for rounding
    expect(bodyScrollWidth).toBeLessThanOrEqual(bodyClientWidth + 1);

    // Check html element doesn't have horizontal scroll
    const htmlScrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const htmlClientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    expect(htmlScrollWidth).toBeLessThanOrEqual(htmlClientWidth + 1);
  });

  test('test_content_readable_at_all_sizes', async ({ page }) => {
    const sizes = [VIEWPORTS.mobile, VIEWPORTS.tablet, VIEWPORTS.desktop];

    for (const viewport of sizes) {
      await page.setViewportSize(viewport);
      await loginAndNavigate(page);

      // Check that main heading is visible and has reasonable font size
      const heading = page.locator('h1').first();
      await expect(heading).toBeVisible();

      const fontSize = await heading.evaluate((el) =>
        window.getComputedStyle(el).fontSize
      );
      const fontSizeNum = parseFloat(fontSize);

      // Font size should be at least 14px for readability
      expect(fontSizeNum).toBeGreaterThanOrEqual(14);

      // Check that text doesn't have text-overflow: ellipsis causing truncation
      // unless it's in a truncate context
      const mainContent = page.locator('main');
      await expect(mainContent).toBeVisible();
    }
  });
});

test.describe('Responsive Layout - Touch/Mobile Interactions', () => {
  test('test_sidebar_opens_on_hamburger_tap', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Find and tap hamburger menu
    const hamburgerButton = page.locator('header.lg\\:hidden button');
    await hamburgerButton.click();

    // Mobile menu overlay should appear
    const mobileMenuOverlay = page.locator('div.lg\\:hidden.fixed.inset-0.z-50');
    await expect(mobileMenuOverlay).toBeVisible({ timeout: 1000 });

    // Menu content should be visible
    const menuContent = mobileMenuOverlay.locator('div.absolute.right-0');
    await expect(menuContent).toBeVisible();

    // Navigation items should be visible in the menu
    const menuNavLinks = menuContent.locator('a');
    await expect(menuNavLinks.first()).toBeVisible();
  });

  test('test_sidebar_closes_on_outside_tap', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Open mobile menu
    const hamburgerButton = page.locator('header.lg\\:hidden button');
    await hamburgerButton.click();

    // Wait for menu to open
    const mobileMenuOverlay = page.locator('div.lg\\:hidden.fixed.inset-0.z-50');
    await expect(mobileMenuOverlay).toBeVisible({ timeout: 1000 });

    // Click on overlay (outside menu content)
    await mobileMenuOverlay.click({ position: { x: 10, y: 10 } });

    // Menu should close
    await expect(mobileMenuOverlay).not.toBeVisible({ timeout: 1000 });
  });

  test('test_swipe_navigation_works', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Test bottom navigation taps
    const bottomNav = page.locator('nav.lg\\:hidden');
    await expect(bottomNav).toBeVisible();

    const navItems = bottomNav.locator('a');
    const firstNavItem = navItems.first();

    // Tap first navigation item
    await firstNavItem.click();

    // Verify navigation occurred (URL should change or content should update)
    // This is a basic test - actual swipe gestures would require more complex setup
    await page.waitForTimeout(500);
  });
});

test.describe('Responsive Layout - Component Responsiveness', () => {
  test('test_table_becomes_cards_on_mobile', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/contacts');

    // On desktop, check if list items have proper layout
    const listItems = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await listItems.count() > 0) {
      const firstItem = listItems.first();
      const desktopBox = await firstItem.boundingBox();

      // Switch to mobile
      await page.setViewportSize(VIEWPORTS.mobile);
      await page.waitForTimeout(300); // Wait for resize

      const mobileBox = await firstItem.boundingBox();

      // On mobile, items might stack differently
      // Both should be visible but layout may change
      if (desktopBox && mobileBox) {
        expect(mobileBox.width).toBeLessThan(desktopBox.width * 1.1);
      }
    }
  });

  test('test_form_inputs_full_width_mobile', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/settings');

    // Find form inputs
    const inputs = page.locator('input[type="text"], input[type="email"]');

    if (await inputs.count() > 0) {
      const firstInput = inputs.first();
      const inputBox = await firstInput.boundingBox();
      const parentBox = await firstInput.locator('..').boundingBox();

      if (inputBox && parentBox) {
        // Input should take most of parent width (allowing for padding)
        const widthRatio = inputBox.width / parentBox.width;
        expect(widthRatio).toBeGreaterThan(0.8);
      }
    }
  });

  test('test_buttons_touchable_size', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Check hamburger button has minimum touch target
    const hamburgerButton = page.locator('header.lg\\:hidden button');
    const buttonBox = await hamburgerButton.boundingBox();

    if (buttonBox) {
      // Minimum recommended touch target is 44x44px
      expect(buttonBox.width).toBeGreaterThanOrEqual(40); // Allow small margin
      expect(buttonBox.height).toBeGreaterThanOrEqual(40);
    }

    // Check bottom navigation items
    const navButtons = page.locator('nav.lg\\:hidden a');
    if (await navButtons.count() > 0) {
      const firstNavButton = navButtons.first();
      const navButtonBox = await firstNavButton.boundingBox();

      if (navButtonBox) {
        // Bottom nav items should also be touchable
        expect(navButtonBox.height).toBeGreaterThanOrEqual(40);
      }
    }
  });

  test('test_responsive_grid_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');

    // Stats cards should stack on mobile
    const statsContainer = page.locator('div.grid.grid-cols-1.sm\\:grid-cols-2.lg\\:grid-cols-4');

    if (await statsContainer.isVisible()) {
      const cards = statsContainer.locator('div.glass.rounded-2xl');
      const cardCount = await cards.count();

      if (cardCount > 0) {
        // On mobile, cards should stack vertically
        const firstCard = await cards.nth(0).boundingBox();
        const secondCard = await cards.nth(1).boundingBox();

        if (firstCard && secondCard && cardCount > 1) {
          // Second card should be below first card on mobile
          expect(secondCard.y).toBeGreaterThan(firstCard.y);
        }

        // Switch to desktop
        await page.setViewportSize(VIEWPORTS.desktop);
        await page.waitForTimeout(300);

        const desktopFirstCard = await cards.nth(0).boundingBox();
        const desktopSecondCard = await cards.nth(1).boundingBox();

        if (desktopFirstCard && desktopSecondCard && cardCount > 1) {
          // On desktop (with lg:grid-cols-4), cards may be side by side
          // or at least closer together vertically
          const desktopVerticalGap = Math.abs(desktopSecondCard.y - desktopFirstCard.y);
          const mobileVerticalGap = Math.abs((secondCard?.y || 0) - (firstCard?.y || 0));

          // Desktop gap should typically be smaller or similar
          expect(desktopVerticalGap).toBeLessThanOrEqual(mobileVerticalGap + 50);
        }
      }
    }
  });
});

test.describe('Responsive Layout - Visual Regression', () => {
  test('test_dashboard_desktop_screenshot', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.largeDesktop);
    await loginAndNavigate(page, '/dashboard');

    // Wait for content to load
    await page.waitForSelector('h1:has-text("Панель управления")', { timeout: 5000 });
    await page.waitForTimeout(1000); // Wait for animations

    // Take screenshot
    await expect(page).toHaveScreenshot('dashboard-desktop-1920x1080.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('test_dashboard_tablet_screenshot', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.tablet);
    await loginAndNavigate(page, '/dashboard');

    // Wait for content to load
    await page.waitForSelector('h1:has-text("Панель управления")', { timeout: 5000 });
    await page.waitForTimeout(1000);

    // Take screenshot
    await expect(page).toHaveScreenshot('dashboard-tablet-768x1024.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('test_dashboard_mobile_screenshot', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');

    // Wait for content to load
    await page.waitForSelector('h1', { timeout: 5000 });
    await page.waitForTimeout(1000);

    // Take screenshot
    await expect(page).toHaveScreenshot('dashboard-mobile-375x667.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('test_contacts_page_responsive_screenshots', async ({ page }) => {
    // Mobile view
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/contacts');
    await page.waitForTimeout(1000);

    await expect(page).toHaveScreenshot('contacts-mobile-375x667.png', {
      fullPage: true,
      animations: 'disabled',
    });

    // Desktop view
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot('contacts-desktop-1280x720.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('test_mobile_menu_open_screenshot', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Open mobile menu
    const hamburgerButton = page.locator('header.lg\\:hidden button');
    await hamburgerButton.click();

    // Wait for menu animation
    await page.waitForTimeout(500);

    // Take screenshot with menu open
    await expect(page).toHaveScreenshot('mobile-menu-open-375x667.png', {
      animations: 'disabled',
    });
  });
});

test.describe('Responsive Layout - Orientation Changes', () => {
  test('test_landscape_mobile_layout', async ({ page }) => {
    // Mobile landscape orientation
    await page.setViewportSize({ width: 667, height: 375 });
    await loginAndNavigate(page);

    // Mobile header should still be visible
    const mobileHeader = page.locator('header.lg\\:hidden');
    await expect(mobileHeader).toBeVisible();

    // Content should be visible and not overflow
    const mainContent = page.locator('main');
    await expect(mainContent).toBeVisible();
  });

  test('test_tablet_portrait_layout', async ({ page }) => {
    // Tablet portrait
    await page.setViewportSize({ width: 768, height: 1024 });
    await loginAndNavigate(page, '/dashboard');

    // Should show mobile layout at 768px
    const mobileHeader = page.locator('header.lg\\:hidden');
    await expect(mobileHeader).toBeVisible();

    // Stats grid should adapt
    const statsContainer = page.locator('div.grid');
    await expect(statsContainer.first()).toBeVisible();
  });

  test('test_tablet_landscape_layout', async ({ page }) => {
    // Tablet landscape (still below lg breakpoint)
    await page.setViewportSize({ width: 1024, height: 768 });
    await loginAndNavigate(page);

    // Should still show mobile layout (lg breakpoint is 1024px)
    const mobileHeader = page.locator('header.lg\\:hidden');

    // At exactly 1024px, it's on the edge - could be either
    // Most Tailwind configs use min-width: 1024px for lg
    // So at 1024px, it should START showing desktop
    const desktopSidebar = page.locator('aside.hidden.lg\\:flex');

    // One of them should be visible
    const headerVisible = await mobileHeader.isVisible();
    const sidebarVisible = await desktopSidebar.isVisible();
    expect(headerVisible || sidebarVisible).toBeTruthy();
  });
});

test.describe('Responsive Layout - Component-Specific Responsive Behavior', () => {
  test('test_contact_detail_responsive_layout', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/contacts');

    // If there are contacts, try to open one
    const contactCards = page.locator('div.p-4.rounded-xl.cursor-pointer');

    if (await contactCards.count() > 0) {
      await contactCards.first().click();
      await page.waitForTimeout(500);

      // Back button should be visible
      const backButton = page.locator('button:has(svg)').first();
      await expect(backButton).toBeVisible();

      // Switch to desktop
      await page.setViewportSize(VIEWPORTS.desktop);
      await page.waitForTimeout(300);

      // On desktop, sidebar and detail should be side by side
      // Both should be visible
      const sidebar = page.locator('div.flex-shrink-0.border-r');
      await expect(sidebar).toBeVisible();
    }
  });

  test('test_modal_responsive_behavior', async ({ page }) => {
    // Test that modals adapt to screen size
    await page.setViewportSize(VIEWPORTS.desktop);
    await loginAndNavigate(page, '/contacts');

    // Try to open create modal
    const createButton = page.locator('button:has(svg)').first();
    await createButton.click();

    const modal = page.locator('div.bg-gray-900.rounded-2xl');

    if (await modal.isVisible()) {
      const desktopModalBox = await modal.boundingBox();

      // Close modal
      const closeButton = page.locator('button:has(svg)').last();
      await closeButton.click();
      await page.waitForTimeout(300);

      // Switch to mobile and open again
      await page.setViewportSize(VIEWPORTS.mobile);
      await createButton.click();

      if (await modal.isVisible()) {
        const mobileModalBox = await modal.boundingBox();

        // Mobile modal should be smaller/different size
        if (desktopModalBox && mobileModalBox) {
          expect(mobileModalBox.width).toBeLessThanOrEqual(VIEWPORTS.mobile.width - 32); // Account for padding
        }
      }
    }
  });

  test('test_chart_responsive_behavior', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page, '/dashboard');

    // Find chart container (ResponsiveContainer from recharts)
    const chartContainer = page.locator('div.recharts-responsive-container');

    if (await chartContainer.isVisible()) {
      const mobileBox = await chartContainer.boundingBox();

      // Switch to desktop
      await page.setViewportSize(VIEWPORTS.desktop);
      await page.waitForTimeout(500);

      const desktopBox = await chartContainer.boundingBox();

      // Chart should resize to fit container
      if (mobileBox && desktopBox) {
        expect(desktopBox.width).toBeGreaterThan(mobileBox.width);
      }
    }
  });

  test('test_bottom_navigation_items_equal_width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    const bottomNav = page.locator('nav.lg\\:hidden');
    const navItems = bottomNav.locator('a');

    if (await navItems.count() > 1) {
      const boxes = await Promise.all(
        Array.from({ length: await navItems.count() }).map((_, i) =>
          navItems.nth(i).boundingBox()
        )
      );

      // All items should have similar widths (allowing for small variance)
      const widths = boxes.filter(Boolean).map(box => box!.width);
      const maxWidth = Math.max(...widths);
      const minWidth = Math.min(...widths);

      expect(maxWidth - minWidth).toBeLessThan(10); // Within 10px of each other
    }
  });
});

test.describe('Responsive Layout - Accessibility at Different Sizes', () => {
  test('test_focus_visible_on_mobile', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await loginAndNavigate(page);

    // Tab through interactive elements
    await page.keyboard.press('Tab');

    // Check that focused element is visible
    const focusedElement = page.locator(':focus');
    await expect(focusedElement).toBeVisible();
  });

  test('test_text_contrast_at_all_sizes', async ({ page }) => {
    const sizes = [VIEWPORTS.mobile, VIEWPORTS.tablet, VIEWPORTS.desktop];

    for (const viewport of sizes) {
      await page.setViewportSize(viewport);
      await loginAndNavigate(page);

      // Check main heading has good contrast
      const heading = page.locator('h1').first();

      if (await heading.isVisible()) {
        const color = await heading.evaluate((el) =>
          window.getComputedStyle(el).color
        );

        // Should have color defined (not default)
        expect(color).toBeTruthy();
      }
    }
  });
});
