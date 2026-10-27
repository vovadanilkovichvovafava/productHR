# Navigation and Layout CSS Tests

## Overview

This directory contains comprehensive CSS and layout tests for the HR-bot frontend navigation components. The tests validate visual consistency, CSS properties, layout behavior, and responsive design across different screen sizes and devices.

**Test File:** `navigation-layout.spec.ts`

## Test Statistics

- **Test Suites:** 11 describe blocks
- **Individual Tests:** 58 test cases
- **Total Test Runs:** ~306 (58 tests × 6 browser/device configurations)
- **Lines of Code:** 1,097

## Components Tested

### 1. Desktop Sidebar
- Full viewport height (100vh)
- Scrollable navigation area
- Consistent width (256px / w-64)
- Active item highlighting
- Icon alignment
- Text wrapping prevention
- Glass effect styling
- Border styling

### 2. Sidebar Collapse/Expand
- Hidden on mobile viewports
- Appears at desktop breakpoint (lg: 1024px)
- Content accessibility across all states

### 3. Mobile Header
- Fixed top positioning
- Full width spanning
- Vertical content centering
- Glass effect styling
- Accessible hamburger button size (44x44px minimum)

### 4. Mobile Menu Overlay
- Slides from right animation
- Full screen overlay coverage
- Smooth animation transitions
- Closes on outside tap
- Proper z-index stacking (z-50)

### 5. Bottom Navigation (Mobile)
- Fixed bottom positioning
- Full width spanning
- Safe area padding
- Equal width items
- Centered icons and text
- Text size consistency (text-xs = 12px)
- Active state highlighting
- Hidden on desktop

### 6. User Profile Section
- Non-distorted circular avatar (40x40px)
- Text truncation for long names
- Email truncation
- Accessible logout button
- Positioned at bottom of sidebar
- Proper flex layout

### 7. Navigation Items
- Consistent spacing (space-y-1 = 4px)
- Consistent padding across items
- Icon-text gap (gap-3 = 12px)
- Hover state styling
- Border radius (rounded-xl = 12px)
- Transition animations (duration-200)

## Running Tests

### Run all navigation/layout tests
```bash
npx playwright test tests/e2e/css/navigation-layout.spec.ts
```

### Run specific test suite
```bash
npx playwright test tests/e2e/css/navigation-layout.spec.ts -g "Sidebar - Desktop"
```

### Run in UI mode (interactive)
```bash
npx playwright test tests/e2e/css/navigation-layout.spec.ts --ui
```
