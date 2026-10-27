import { test, expect } from '@playwright/test';

/**
 * Visual Regression Tests
 * Captures screenshots to detect unintended visual changes
 */

test.describe('Visual Regression Tests', () => {
  test('login page visual regression', async ({ page }) => {
    // Navigate to login page
    await page.goto('/login');

    // Wait for the page to be fully loaded
    await page.waitForLoadState('networkidle');

    // Take a screenshot and compare with baseline
    // On first run, this creates the baseline screenshot
    // On subsequent runs, it compares against the baseline
    await expect(page).toHaveScreenshot('login-page.png', {
      fullPage: true,
      // Allow small differences in rendering
      maxDiffPixels: 100,
    });
  });

  test('login page mobile visual regression', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });

    // Navigate to login page
    await page.goto('/login');

    // Wait for the page to be fully loaded
    await page.waitForLoadState('networkidle');

    // Take a screenshot for mobile view
    await expect(page).toHaveScreenshot('login-page-mobile.png', {
      fullPage: true,
      maxDiffPixels: 100,
    });
  });
});
