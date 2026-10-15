// Live integration check: explicitly opt in because configured web providers may charge.
if (!process.argv.includes("--live")) {
  console.error("Usage: node scripts/verify_webapp.cjs --live");
  process.exit(2);
}
const { chromium } = require("playwright");
const appUrl = process.env.APP_URL || "http://127.0.0.1:8765";
require("fs").mkdirSync(".impeccable/review/bench", { recursive: true });
const assert = require("assert");
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const capture = async (screen) => {
    for (const theme of ["light", "dark"])
      for (const [name, width, height] of [
        ["desktop", 1440, 1000],
        ["mobile", 390, 844],
      ]) {
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        await page.setViewportSize({ width, height });
        await page.screenshot({
          path: `.impeccable/review/bench/${theme}-${name}-${screen}.png`,
          fullPage: true,
        });
        assert(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          `overflow ${screen}`,
        );
      }
  };
  await page.goto(appUrl + "/#entry");
  await page
    .getByLabel("Address", { exact: true })
    .fill("414 Grant Street, Pittsburgh, PA 15219");
  await page.getByRole("button", { name: /Find address/ }).click();
  await page.locator(".candidate").first().waitFor({ timeout: 60000 });
  const candidates = await page.locator(".candidate").allTextContents();
  assert(candidates.some((x) => x.includes("Grant")));
  console.log("Real Census candidates", candidates);
  await page.getByRole("radio").first().check();
  await capture("confirm");
  await page
    .getByRole("button", { name: "Confirm location", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "What should we research?" })
    .waitFor();
  await page.waitForTimeout(2500);
  const local = page.locator("[name=local]");
  if (await local.isEnabled()) {
    await local.check();
    await page.locator("[name=dining]").check();
    console.log("Live web channels available and selected");
  } else console.log("Web unavailable: checking public channels");
  await capture("channels");
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm location", exact: true })
    .click();
  assert(await page.locator("[name=apis]").isChecked());
  await page
    .getByRole("button", { name: "Generate report", exact: true })
    .click();
  await page.waitForURL(/progress\//, { timeout: 30000 });
  const id = page.url().split("/").pop();
  console.log("Live generation", id);
  await capture("progress");
  await page
    .getByRole("button", { name: "Explore report", exact: true })
    .waitFor({ timeout: 240000 });
  await page
    .getByRole("button", { name: "Explore report", exact: true })
    .click();
  await page.locator(".finding").first().waitFor();
  await capture("live-report");
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  assert((await page.locator(".source-row").count()) > 0);
  await capture("sources");
  await page
    .getByRole("button", { name: "Research scope", exact: true })
    .click();
  await capture("scope");
  await page.getByRole("button", { name: "Unresolved", exact: true }).click();
  await capture("unresolved");
  await page.reload();
  await page.locator(".finding").first().waitFor();
  await page.locator(".finding button").first().click();
  assert(await page.locator("dialog").isVisible());
  await page.keyboard.press("Escape");
  assert(!(await page.locator("dialog").isVisible()));
  await page
    .getByRole("button", { name: "Saved reports", exact: true })
    .click();
  await page.getByPlaceholder("Search by address").fill("no-such-address-xyz");
  await page.getByText(/No saved reports match/).waitFor();
  await capture("empty-saved");
  await page.getByRole("button", { name: "Clear search" }).click();
  await page.locator(".saved-row").first().waitFor();
  console.log("Browser workflow passed", JSON.stringify({ id, errors }));
  assert.deepEqual(errors, []);
  await browser.close();
})();
