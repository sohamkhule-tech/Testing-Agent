"""
Template Manager for Code Generation

Provides templates for Playwright project files.
"""

from typing import Any

from app.logging import LoggerMixin


class TemplateManager(LoggerMixin):
    """
    Manages code templates for Playwright project generation.
    
    Responsibilities:
    - Provide templates for config files
    - Provide base class templates
    - Provide utility templates
    - Support template variable substitution
    - Ensure consistent code structure
    """

    def __init__(self) -> None:
        """Initialize template manager."""
        super().__init__()

    def get_package_json_template(self) -> str:
        """Get package.json template."""
        return """{
  "name": "playwright-test-automation",
  "version": "1.0.0",
  "description": "AI-generated Playwright test automation project",
  "scripts": {
    "test": "playwright test",
    "test:headed": "playwright test --headed",
    "test:debug": "playwright test --debug",
    "test:ui": "playwright test --ui",
    "test:chrome": "playwright test --project=chromium",
    "test:firefox": "playwright test --project=firefox",
    "test:webkit": "playwright test --project=webkit",
    "report": "playwright show-report",
    "codegen": "playwright codegen"
  },
  "keywords": ["playwright", "testing", "automation", "e2e"],
  "author": "AI Code Generation Agent",
  "license": "MIT",
  "devDependencies": {
    "@playwright/test": "^1.40.0",
    "@types/node": "^20.10.0",
    "typescript": "^5.3.0"
  },
  "engines": {
    "node": ">=18.0.0"
  }
}
"""

    def get_playwright_config_template(self) -> str:
        """Get playwright.config.ts template."""
        return """import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';

// Load environment variables
dotenv.config();

/**
 * Playwright Test Configuration
 * 
 * Production-ready configuration with:
 * - Multiple browser support
 * - Retries on failure
 * - Comprehensive reporting
 * - Screenshots and videos
 * - Trace on first retry
 */
export default defineConfig({
  testDir: './tests',
  
  /* Run tests in files in parallel */
  fullyParallel: true,
  
  /* Fail the build on CI if you accidentally left test.only in the source code */
  forbidOnly: !!process.env.CI,
  
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 1,
  
  /* Opt out of parallel tests on CI */
  workers: process.env.CI ? 1 : undefined,
  
  /* Reporter to use */
  reporter: [
    ['html', { outputFolder: 'reports/html', open: 'never' }],
    ['json', { outputFile: 'reports/results.json' }],
    ['junit', { outputFile: 'reports/junit.xml' }],
    ['list']
  ],
  
  /* Shared settings for all the projects below */
  use: {
    /* Base URL to use in actions like `await page.goto('/')` */
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    
    /* Collect trace when retrying the failed test */
    trace: 'on-first-retry',
    
    /* Screenshot on failure */
    screenshot: 'only-on-failure',
    
    /* Video on first retry */
    video: 'retain-on-failure',
    
    /* Maximum time each action can take */
    actionTimeout: 15000,
    
    /* Maximum time for navigation */
    navigationTimeout: 30000,
  },
  
  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    
    /* Test against mobile viewports */
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  
  /* Global timeout for each test */
  timeout: 60000,
  
  /* Expect timeout */
  expect: {
    timeout: 10000,
  },
  
  /* Folder for test artifacts */
  outputDir: 'test-results/',
});
"""

    def get_tsconfig_template(self) -> str:
        """Get tsconfig.json template."""
        return """{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "moduleResolution": "node",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "typeRoots": ["./node_modules/@types"],
    "types": ["node", "@playwright/test"],
    "outDir": "./dist",
    "rootDir": "./",
    "baseUrl": "./",
    "paths": {
      "@pages/*": ["pages/*"],
      "@tests/*": ["tests/*"],
      "@fixtures/*": ["fixtures/*"],
      "@utils/*": ["utils/*"],
      "@data/*": ["data/*"]
    }
  },
  "include": ["**/*.ts"],
  "exclude": ["node_modules", "dist", "reports", "test-results"]
}
"""

    def get_env_example_template(self) -> str:
        """Get .env.example template."""
        return """# Base URL for the application under test
BASE_URL=http://localhost:3000

# Test credentials (if authentication required)
TEST_USERNAME=testuser
TEST_PASSWORD=testpass123

# Browser settings
HEADLESS=true
BROWSER=chromium

# Timeouts (milliseconds)
ACTION_TIMEOUT=15000
NAVIGATION_TIMEOUT=30000

# Test configuration
PARALLEL_WORKERS=4
RETRIES=2

# Reporting
REPORT_OUTPUT=reports/
"""

    def get_base_page_template(self) -> str:
        """Get BasePage class template."""
        return """import { Page, Locator } from '@playwright/test';

/**
 * Base Page Object
 * 
 * Provides common functionality for all page objects.
 * All page objects should extend this base class.
 */
export abstract class BasePage {
  protected readonly page: Page;
  protected readonly baseURL: string;

  constructor(page: Page) {
    this.page = page;
    this.baseURL = process.env.BASE_URL || 'http://localhost:3000';
  }

  /**
   * Navigate to a specific path
   */
  async goto(path: string = '/'): Promise<void> {
    await this.page.goto(path);
  }

  /**
   * Wait for page to be fully loaded
   */
  async waitForPageLoad(): Promise<void> {
    await this.page.waitForLoadState('domcontentloaded');
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Get page title
   */
  async getTitle(): Promise<string> {
    return await this.page.title();
  }

  /**
   * Get current URL
   */
  getCurrentURL(): string {
    return this.page.url();
  }

  /**
   * Wait for element to be visible
   */
  async waitForElement(locator: Locator, timeout: number = 10000): Promise<void> {
    await locator.waitFor({ state: 'visible', timeout });
  }

  /**
   * Take screenshot
   */
  async takeScreenshot(name: string): Promise<void> {
    await this.page.screenshot({ path: `screenshots/${name}.png`, fullPage: true });
  }

  /**
   * Scroll to element
   */
  async scrollToElement(locator: Locator): Promise<void> {
    await locator.scrollIntoViewIfNeeded();
  }
}
"""

    def get_waits_utility_template(self) -> str:
        """Get waits.ts utility template."""
        return """import { Locator, Page } from '@playwright/test';

/**
 * Wait Utilities
 * 
 * Reusable wait functions for common scenarios.
 */

/**
 * Wait for element to be visible
 */
export async function waitForVisible(
  locator: Locator,
  timeout: number = 10000
): Promise<void> {
  await locator.waitFor({ state: 'visible', timeout });
}

/**
 * Wait for element to be hidden
 */
export async function waitForHidden(
  locator: Locator,
  timeout: number = 10000
): Promise<void> {
  await locator.waitFor({ state: 'hidden', timeout });
}

/**
 * Wait for element to be enabled
 */
export async function waitForEnabled(
  locator: Locator,
  timeout: number = 10000
): Promise<boolean> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await locator.isEnabled()) {
      return true;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  return false;
}

/**
 * Wait for page to reach specific URL
 */
export async function waitForURL(
  page: Page,
  urlPattern: string | RegExp,
  timeout: number = 10000
): Promise<void> {
  await page.waitForURL(urlPattern, { timeout });
}

/**
 * Wait for network to be idle
 */
export async function waitForNetworkIdle(
  page: Page,
  timeout: number = 10000
): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout });
}

/**
 * Wait with retry logic
 */
export async function waitWithRetry<T>(
  action: () => Promise<T>,
  maxRetries: number = 3,
  delay: number = 1000
): Promise<T> {
  let lastError: Error | undefined;
  
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await action();
    } catch (error) {
      lastError = error as Error;
      if (i < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
  
  throw lastError;
}
"""

    def get_helpers_utility_template(self) -> str:
        """Get helpers.ts utility template."""
        return """import { Page } from '@playwright/test';

/**
 * Helper Utilities
 * 
 * Common helper functions used across tests.
 */

/**
 * Generate random string
 */
export function generateRandomString(length: number = 10): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

/**
 * Generate random email
 */
export function generateRandomEmail(): string {
  return `test${Date.now()}@example.com`;
}

/**
 * Get timestamp
 */
export function getTimestamp(): string {
  return new Date().toISOString();
}

/**
 * Format date
 */
export function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}

/**
 * Sleep utility (use sparingly - prefer Playwright's built-in waits)
 */
export async function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Get element text content
 */
export async function getTextContent(page: Page, selector: string): Promise<string> {
  const element = page.locator(selector);
  return (await element.textContent()) || '';
}

/**
 * Check if element exists
 */
export async function elementExists(page: Page, selector: string): Promise<boolean> {
  return await page.locator(selector).count() > 0;
}
"""

    def get_constants_utility_template(self) -> str:
        """Get constants.ts utility template."""
        return """/**
 * Constants
 * 
 * Shared constants used across the test suite.
 */

export const TIMEOUTS = {
  SHORT: 5000,
  MEDIUM: 10000,
  LONG: 30000,
  VERY_LONG: 60000,
} as const;

export const SELECTORS = {
  // Common selectors
  BUTTON_SUBMIT: '[type="submit"]',
  BUTTON_CANCEL: '[type="button"]',
  INPUT_TEXT: 'input[type="text"]',
  INPUT_EMAIL: 'input[type="email"]',
  INPUT_PASSWORD: 'input[type="password"]',
  ALERT: '[role="alert"]',
  DIALOG: '[role="dialog"]',
  SPINNER: '[role="status"]',
} as const;

export const MESSAGES = {
  // Common messages
  SUCCESS: 'Success',
  ERROR: 'Error',
  LOADING: 'Loading...',
  REQUIRED_FIELD: 'This field is required',
} as const;

export const RETRY_CONFIG = {
  MAX_RETRIES: 3,
  RETRY_DELAY: 1000,
} as const;
"""

    def get_logger_utility_template(self) -> str:
        """Get logger.ts utility template."""
        return """/**
 * Logger Utility
 * 
 * Simple logging utility for tests.
 */

export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR',
}

class Logger {
  private static instance: Logger;
  private enabled: boolean = true;

  private constructor() {}

  static getInstance(): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger();
    }
    return Logger.instance;
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  private log(level: LogLevel, message: string, ...args: any[]): void {
    if (!this.enabled) return;

    const timestamp = new Date().toISOString();
    const logMessage = `[${timestamp}] [${level}] ${message}`;
    
    switch (level) {
      case LogLevel.DEBUG:
      case LogLevel.INFO:
        console.log(logMessage, ...args);
        break;
      case LogLevel.WARN:
        console.warn(logMessage, ...args);
        break;
      case LogLevel.ERROR:
        console.error(logMessage, ...args);
        break;
    }
  }

  debug(message: string, ...args: any[]): void {
    this.log(LogLevel.DEBUG, message, ...args);
  }

  info(message: string, ...args: any[]): void {
    this.log(LogLevel.INFO, message, ...args);
  }

  warn(message: string, ...args: any[]): void {
    this.log(LogLevel.WARN, message, ...args);
  }

  error(message: string, ...args: any[]): void {
    this.log(LogLevel.ERROR, message, ...args);
  }
}

export const logger = Logger.getInstance();
"""

    def get_base_fixture_template(self) -> str:
        """Get base.fixture.ts template."""
        return """import { test as base } from '@playwright/test';
import { BasePage } from '../pages/BasePage';

/**
 * Custom Fixtures
 * 
 * Extend Playwright test with custom fixtures for common setup.
 */

type CustomFixtures = {
  // Add custom fixtures here
  // Example: authenticatedPage: Page;
};

/**
 * Extended test with custom fixtures
 */
export const test = base.extend<CustomFixtures>({
  // Implement custom fixtures here
});

export { expect } from '@playwright/test';
"""

    def get_readme_template(self, project_name: str = "Playwright Test Automation") -> str:
        """Get README.md template."""
        return f"""# {project_name}

AI-generated Playwright test automation project using TypeScript and Page Object Model.

## Prerequisites

- Node.js 18 or higher
- npm or yarn

## Installation

```bash
npm install
```

## Project Structure

```
playwright/
├── pages/              # Page Object Model classes
├── tests/              # Test specifications
├── fixtures/           # Custom Playwright fixtures
├── utils/              # Utility functions
├── data/               # Test data files
├── reports/            # Test reports (generated)
├── screenshots/        # Screenshots (generated)
└── test-results/       # Test results (generated)
```

## Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update environment variables in `.env` as needed

## Running Tests

```bash
# Run all tests
npm test

# Run in headed mode
npm run test:headed

# Run in debug mode
npm run test:debug

# Run UI mode
npm run test:ui

# Run specific browser
npm run test:chrome
npm run test:firefox
npm run test:webkit

# View test report
npm run report
```

## Writing Tests

Tests are organized by module in the `tests/` directory.

Example test structure:

```typescript
import {{ test, expect }} from '@playwright/test';
import {{ HomePage }} from '../pages/HomePage';

test.describe('Home Page Tests', () => {{
  test('should display welcome message', async ({{ page }}) => {{
    const homePage = new HomePage(page);
    await homePage.goto();
    
    await expect(page.getByText('Welcome')).toBeVisible();
  }});
}});
```

## Page Objects

Page objects are located in the `pages/` directory.

All page objects extend `BasePage` and follow the Page Object Model pattern:
- Locators as private readonly properties
- Public methods for actions
- Public methods for assertions

## Debugging

```bash
# Run with Playwright Inspector
npm run test:debug

# Generate tests interactively
npm run codegen
```

## CI/CD

Tests are configured to run in CI with:
- Retry on failure
- Multiple reporters
- Screenshots and videos on failure
- Trace on first retry

## Best Practices

1. Use meaningful test names
2. Follow AAA pattern (Arrange, Act, Assert)
3. Use Page Object Model
4. Prefer Playwright's built-in waits
5. Use proper assertions
6. Keep tests independent
7. Use fixtures for setup

## Troubleshooting

### Install browsers

```bash
npx playwright install
```

### Clear test results

```bash
rm -rf test-results reports screenshots
```

## Documentation

- [Playwright Documentation](https://playwright.dev)
- [TypeScript Documentation](https://www.typescriptlang.org)

## License

MIT
"""

    def get_test_data_template(self) -> str:
        """Get test-data.json template."""
        return """{
  "users": {
    "valid": {
      "username": "testuser",
      "password": "testpass123",
      "email": "testuser@example.com"
    },
    "invalid": {
      "username": "invalid",
      "password": "wrong",
      "email": "invalid@example.com"
    }
  },
  "urls": {
    "home": "/",
    "login": "/login",
    "dashboard": "/dashboard"
  },
  "timeouts": {
    "short": 5000,
    "medium": 10000,
    "long": 30000
  }
}
"""

    def substitute_variables(self, template: str, variables: dict[str, Any]) -> str:
        """
        Substitute variables in template.

        Args:
            template: Template string with {variable} placeholders
            variables: Dictionary of variable names and values

        Returns:
            Template with substituted values
        """
        try:
            return template.format(**variables)
        except KeyError as e:
            self.logger.warning("template_variable_missing", variable=str(e))
            return template
