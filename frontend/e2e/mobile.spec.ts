import { expect, test } from "@playwright/test";

test("mobile: no horizontal scroll and navigation drawer works", async ({ page }) => {
  for (const path of ["/", "/settings", "/compare"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    const vw = await page.evaluate(() => window.innerWidth);
    expect(sw, `${path} overflows`).toBeLessThanOrEqual(vw + 1);
  }
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("dialog").getByRole("link", { name: "Research reports" })).toBeVisible();
});
