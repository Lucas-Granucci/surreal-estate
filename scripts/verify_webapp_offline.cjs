// Browser failure-path fixtures are test-only. Start the app before running.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const appUrl = process.env.APP_URL || "http://127.0.0.1:8765";
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let geocode = "empty",
    submit = "error",
    submissions = 0,
    status = "running";
  const id = "11111111-1111-4111-8111-111111111111";
  const job = () => ({
    id,
    address: "100 Fixture St, Pittsburgh, PA 15219",
    geography: "Pittsburgh, PA",
    channels: ["apis"],
    topics: [],
    created_at: "2026-01-01",
    status,
    message:
      status === "failed"
        ? "Research could not finish. Try again."
        : "Checking public sources",
    progress: {
      steps: [
        {
          id: "apis",
          label: "Public records & nearby places",
          state: status === "failed" ? "stopped" : "active",
        },
      ],
    },
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body,
      code = 200;
    if (path === "/api/capabilities")
      body = { apis: { available: true }, web: { available: false } };
    else if (path === "/api/geocode") {
      if (geocode === "error") {
        code = 502;
        body = {
          error: "Address lookup is unavailable. Please try again shortly.",
        };
      } else
        body = {
          candidates:
            geocode === "empty"
              ? []
              : [
                  {
                    confirmation: "fixture-match",
                    address: "100 FIXTURE ST, PITTSBURGH, PA 15219",
                    latitude: 40.4,
                    longitude: -80,
                  },
                ],
        };
    } else if (path === "/api/runs" && route.request().method() === "POST") {
      submissions++;
      assert.deepEqual(route.request().postDataJSON().channels, ["apis"]);
      assert.equal(
        route.request().postDataJSON().confirmation,
        "fixture-match",
      );
      if (submit === "error") {
        code = 500;
        body = { error: "Cannot save a run. Please try again." };
      } else {
        code = 202;
        body = job();
      }
    } else if (path === "/api/runs") body = { csrf: "fixture-csrf", runs: [] };
    else body = job();
    await route.fulfill({
      status: code,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  fs.mkdirSync(".impeccable/review/bench", { recursive: true });
  async function capture(name) {
    for (const theme of ["light", "dark"])
      for (const [size, width, height] of [
        ["desktop", 1440, 1000],
        ["mobile", 390, 844],
      ]) {
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        await page.setViewportSize({ width, height });
        await page.screenshot({
          path: `.impeccable/review/bench/${theme}-${size}-${name}.png`,
          fullPage: true,
        });
        assert(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        );
      }
  }
  await page.goto(appUrl + "/#entry");
  await page
    .getByLabel("Address", { exact: true })
    .fill("100 Fixture St, Pittsburgh, PA 15219");
  await page.getByLabel("Address", { exact: true }).press("Enter");
  await page.getByText(/No matching address found/).waitFor();
  await capture("no-address-match");
  await page.getByRole("button", { name: "Edit address" }).tap();
  assert.equal(
    await page.getByLabel("Address", { exact: true }).inputValue(),
    "100 Fixture St, Pittsburgh, PA 15219",
  );
  geocode = "error";
  await page.getByLabel("Address", { exact: true }).press("Enter");
  await page.getByRole("alert").waitFor();
  await capture("geocode-error");
  geocode = "match";
  await page.getByRole("button", { name: /Find address/ }).tap();
  await page.getByRole("radio").check();
  await page.getByRole("button", { name: "Confirm location" }).tap();
  await page
    .getByText("Local intelligence is unavailable for this session.")
    .waitFor();
  assert(await page.locator("[name=local]").isDisabled());
  assert(await page.locator("[name=dining]").isDisabled());
  await capture("web-unavailable");
  await page.getByRole("button", { name: "Generate report" }).tap();
  await page.getByRole("alert").waitFor();
  assert(await page.locator("[name=apis]").isChecked());
  await capture("generation-error");
  submit = "ok";
  await page.getByRole("button", { name: "Generate report" }).tap();
  await page.waitForURL(/progress\//);
  assert.equal(submissions, 2);
  status = "failed";
  await page.getByRole("heading", { name: "100 Fixture St" }).waitFor();
  await page.getByRole("button", { name: "Try again" }).waitFor();
  await capture("interrupted");
  await page.getByRole("button", { name: "Try again" }).tap();
  assert.equal(
    await page.getByLabel("Address", { exact: true }).inputValue(),
    job().address,
  );
  await page.reload();
  assert.equal(
    await page.getByLabel("Address", { exact: true }).inputValue(),
    job().address,
  );
  assert.deepEqual(errors, []);
  console.log(
    "Offline browser failure paths passed: empty/error geocode, unavailable web, submit retry, interrupted run, touch/keyboard, draft refresh.",
  );
  await browser.close();
})();
