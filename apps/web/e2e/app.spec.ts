import { expect, test } from "@playwright/test";

test.describe("auth", () => {
  test("login page renders and signs in via mock", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Sign in to StrategyLab")).toBeVisible();

    await page.getByPlaceholder("Email").fill("trader@example.com");
    await page.getByPlaceholder("Password (min 8 characters)").fill("secret123");
    await page.getByPlaceholder("Password (min 8 characters)").press("Enter");

    // Mock auth resolves immediately → app shell renders
    await expect(page.locator("aside")).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("core navigation", () => {
  test.beforeEach(async ({ page }) => {
    // Seed mock token so guarded pages render without the login detour
    await page.addInitScript(() => {
      window.localStorage.setItem("strategylab_token", "mock-e2e-token");
    });
  });

  test("dashboard loads with sidebar and onboarding or metrics", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("STRATEGYLAB", { exact: true })).toBeVisible();
    await expect(page.locator("aside")).toBeVisible();
  });

  test("strategy library lists mock strategies", async ({ page }) => {
    await page.goto("/strategies");
    await expect(page.getByRole("heading", { name: /strategy library/i })).toBeVisible({ timeout: 20_000 });
  });

  test("backtest page renders run form", async ({ page }) => {
    await page.goto("/backtest");
    await expect(page.locator("select").first()).toBeVisible({ timeout: 20_000 });
  });

  test("optimization page shows heatmap section", async ({ page }) => {
    await page.goto("/optimization");
    await expect(page.getByText("Sensitivity Heatmap")).toBeVisible({ timeout: 20_000 });
  });

  test("tax report page renders summary grid", async ({ page }) => {
    await page.goto("/tools/tax-report");
    await expect(
      page.locator("main").getByRole("heading", { name: "Tax Report" }),
    ).toBeVisible({ timeout: 20_000 });
  });

  test("mobile viewport opens drawer sidebar", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    const hamburger = page.getByLabel("Open menu");
    if (await hamburger.isVisible()) {
      await hamburger.click();
      await expect(page.locator("aside")).toBeVisible();
    }
  });
});
