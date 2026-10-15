// Offline regression check for the saved-report Overview; no provider calls.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const categories = ["transit", "groceries", "schools", "pharmacies"];
const coverage = [
  { topic: "geocoding", status: "complete", reason: "Estimated street point" },
  {
    topic: "property_assessment",
    status: "blocked",
    reason: "A unique parcel is needed",
  },
  {
    topic: "building_permits",
    status: "blocked",
    reason: "Not searched without a unique parcel",
  },
  {
    topic: "mapped_amenities",
    status: "truncated",
    reason: "Transit results capped",
  },
  {
    topic: "street_closures",
    status: "empty",
    reason: "No matching permits within the search scope",
  },
  { topic: "restaurant_reviews", status: "error", reason: "Research failed" },
  {
    topic: "neighborhood_discussion",
    status: "not_implemented",
    reason: "Source unavailable",
  },
];
const evidence = [
  {
    id: "origin",
    provider: "census",
    title: "Address match",
    kind: "reported",
    excerpt: "Estimated street point",
    details: { latitude: 40.44, longitude: -80 },
  },
];
for (const [i, category] of categories.entries())
  evidence.push({
    id: category,
    provider: "openstreetmap",
    title: category,
    kind: "reported",
    excerpt: "Saved features",
    details: {
      category,
      query_radius_m: 1000,
      mapped_feature_count: 2,
      count_is_lower_bound: i === 0,
      members: [
        {
          name: `${category} fixture`,
          center: { lat: 40.441 + i * 0.001, lon: -79.998 },
          approximate_center_distance_m: 200,
          uri: "https://www.openstreetmap.org/node/1",
        },
        { name: "Missing coordinates", center: { lat: null, lon: null } },
      ],
    },
  });
const bench = {
  case: { address: "100 Fixture Street, Pittsburgh, PA", as_of: "2026-10-14" },
  demo: true,
  evidence,
  coverage,
  web: [],
  findings: coverage.map((c, i) => ({
    id: `finding-${i}`,
    topic: c.topic,
    title: c.topic.replaceAll("_", " "),
    section: c.topic === "mapped_amenities" ? "Surroundings" : "Records",
    statements: [c.reason],
    qualifier: "Public records",
    evidence_ids: i === 0 ? ["origin"] : i === 3 ? categories : [],
    web_indices: [],
    coverage: [c],
    unresolved: ["blocked", "truncated", "error"].includes(c.status),
  })),
};
(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
  });
  const page = await browser.newPage();
  let savedRuns = [],
    deletionFails = false,
    deleteCount = 0;
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("http://overview.test/**", (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "DELETE") {
      deleteCount++;
      assert.equal(route.request().headers()["x-csrf-token"], "offline");
      if (deletionFails)
        return route.fulfill({
          status: 500,
          json: { error: "Could not delete fixture report." },
        });
      savedRuns = savedRuns.filter((r) => !url.pathname.endsWith("/" + r.id));
      return route.fulfill({ json: { deleted: true } });
    }
    let data;
    if (url.pathname.endsWith("/bench.json")) data = bench;
    else if (url.pathname === "/api/runs")
      data = { runs: savedRuns, csrf: "offline" };
    else if (url.pathname === "/api/capabilities")
      data = { apis: { available: true }, web: { available: false } };
    if (data) return route.fulfill({ json: data });
    const filename = path.join(
      root,
      "surreal_estate/webapp/static",
      url.pathname === "/"
        ? "index.html"
        : url.pathname.replace(/^\/static\//, ""),
    );
    return route.fulfill({ path: filename });
  });
  await page.goto("http://overview.test/#report/fixture");
  await page.getByRole("heading", { name: "Location overview" }).waitFor();
  assert.equal(await page.locator("#inspector .evidence-title").count(), 0);
  assert.equal(
    await page.locator('.legend-row[aria-pressed="true"]').count(),
    0,
  );
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const headerBefore = await page.locator(".report-heading").boundingBox();
  await page.getByRole("button", { name: "Records", exact: true }).click();
  assert.equal(
    await page
      .locator(".report-view")
      .evaluate((e) => getComputedStyle(e).animationName),
    "none",
  );
  const headerAfter = await page.locator(".report-heading").boundingBox();
  assert.equal(headerBefore.x, headerAfter.x);
  assert.equal(headerBefore.y, headerAfter.y);
  const finding = page.locator(".finding").first();
  const box = await finding.boundingBox();
  await page.mouse.click(box.x + box.width - 35, box.y + box.height - 12);
  assert.equal(
    await finding.locator(".finding-select").getAttribute("aria-pressed"),
    "true",
  );
  await page.getByLabel("Close evidence", { exact: true }).click();
  await finding.locator(".finding-select").focus();
  await page.keyboard.press("Enter");
  assert.equal(
    await finding.locator(".finding-select").getAttribute("aria-pressed"),
    "true",
  );
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  assert.equal(await page.locator("#inspector .evidence-title").count(), 0);
  await page.getByRole("button", { name: "Findings", exact: true }).click();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  assert.equal(
    await page.locator(".spatial-plot svg g[clip-path] > g").count(),
    4,
  );
  assert.equal(
    await page.getByRole("button", { name: "All topics", exact: true }).count(),
    0,
  );
  assert.equal(
    await page
      .getByRole("button", { name: "Surroundings", exact: true })
      .count(),
    0,
  );
  await page.getByRole("button", { name: "Show transit on map" }).click();
  assert.match(
    await page.locator(".map-summary").innerText(),
    /At least 2 mapped features.*Results capped/s,
  );
  assert.match(await page.locator("#inspector").innerText(), /transit fixture/);
  assert(!(await page.locator("#detail-dialog").isVisible()));
  await page.getByRole("button", { name: "Show pharmacies on map" }).click();
  assert.doesNotMatch(
    await page.locator(".map-summary").innerText(),
    /pharmacies fixture/,
  );
  assert.match(
    await page.locator("#inspector").innerText(),
    /pharmacies fixture/,
  );
  assert.doesNotMatch(
    await page.locator("#inspector").innerText(),
    /groceries fixture/,
  );
  assert.equal(
    await page.locator(".spatial-plot svg g[clip-path] > g").count(),
    1,
  );
  await page.getByRole("button", { name: "Show all places" }).click();
  assert.equal(await page.locator("#inspector .evidence-title").count(), 0);
  await page.getByLabel("Filter research status").selectOption("Blocked");
  assert.equal(await page.locator(".research-table tbody tr").count(), 2);
  await page.locator(".research-table button").first().click();
  await page.locator("#inspector .evidence-title").waitFor();
  await page.getByLabel("Close evidence", { exact: true }).click();
  await page.getByLabel("Filter research status").selectOption("Complete");
  assert.match(
    await page.locator(".research-table").innerText(),
    /No records found/,
  );
  await page.getByLabel("Filter research status").selectOption("All statuses");
  fs.mkdirSync(path.join(root, ".impeccable/review/overview"), {
    recursive: true,
  });
  for (const colorScheme of ["light", "dark"])
    for (const width of [1440, 390]) {
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      await page.setViewportSize({ width, height: 900 });
      await page.getByRole("button", { name: "Show transit on map" }).click();
      const plot = await page.locator(".spatial-plot").boundingBox();
      assert(plot.width <= 421);
      const card = await page.locator(".spatial-card").boundingBox();
      const area = await page.locator("#spatial-overview").boundingBox();
      assert(Math.abs(card.width - area.width) < 2);
      if (width > 720) {
        const context = await page.locator(".map-context").boundingBox();
        assert(context.x >= plot.x + plot.width - 1);
        await page.evaluate(() => window.scrollTo(0, 0));
        const visiblePlot = await page.locator(".spatial-plot").boundingBox();
        assert(visiblePlot.y + visiblePlot.height < 900);
      } else {
        assert(!(await page.locator("#detail-dialog").isVisible()));
        await page
          .locator(".map-summary")
          .getByRole("button", { name: "View locations & source" })
          .click();
        assert(await page.locator("#detail-dialog").isVisible());
        assert.match(
          await page.locator("#detail-dialog").innerText(),
          /transit fixture/,
        );
        await page.keyboard.press("Escape");
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: path.join(
          root,
          `.impeccable/review/overview/${colorScheme}-${width}.png`,
        ),
        fullPage: true,
      });
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      );
      assert.equal(
        await page.locator(".mobile-status-list").isVisible(),
        width === 390,
      );
      await page.getByRole("button", { name: "Records", exact: true }).click();
      await page.locator(".finding-select").first().focus();
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: path.join(
          root,
          `.impeccable/review/overview/findings-${colorScheme}-${width}.png`,
        ),
        fullPage: true,
      });
      await page.getByRole("button", { name: "Overview", exact: true }).click();
      assert.equal(await page.locator("#inspector .evidence-title").count(), 0);
      assert.equal(
        await page.locator('.legend-row[aria-pressed="true"]').count(),
        0,
      );
      const style = await page
        .locator(".report-rail [aria-current]")
        .evaluate((e) => ({
          weight: getComputedStyle(e).fontWeight,
          bg: getComputedStyle(e).backgroundColor,
          border: getComputedStyle(e).borderLeftWidth,
        }));
      assert.equal(style.weight, "600");
      assert.equal(style.bg, "rgba(0, 0, 0, 0)");
      assert.equal(style.border, "1px");
    }
  await page.locator(".mobile-topic").first().click();
  assert(await page.locator("#detail-dialog").isVisible());
  await page.keyboard.press("Escape");
  bench.evidence[0].details = {};
  await page.reload();
  await page
    .getByText("Saved coordinates are unavailable for this report.", {
      exact: false,
    })
    .waitFor();
  assert.equal(await page.locator(".spatial-plot").count(), 0);
  savedRuns = [
    {
      id: "saved-fixture",
      address: "100 Fixture Street",
      status: "complete",
      created_at: "2026-10-14",
    },
    {
      id: "running-fixture",
      address: "200 In Progress Street",
      status: "running",
      created_at: "2026-10-14",
    },
  ];
  await page.goto("http://overview.test/#saved");
  await page
    .getByRole("heading", { name: "Saved reports", exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Delete report for 100 Fixture Street" })
    .waitFor();
  assert.equal(await page.locator(".delete-report").count(), 1);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.screenshot({
      path: path.join(
        root,
        `.impeccable/review/overview/saved-delete-${width}.png`,
      ),
      fullPage: true,
    });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
  }
  await page
    .getByRole("button", { name: "Delete report for 100 Fixture Street" })
    .click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(deleteCount, 0);
  deletionFails = true;
  await page
    .getByRole("button", { name: "Delete report for 100 Fixture Street" })
    .click();
  await page
    .getByRole("button", { name: "Delete report", exact: true })
    .click();
  await page.getByText("Could not delete fixture report.").waitFor();
  assert.equal(savedRuns.length, 2);
  deletionFails = false;
  await page
    .getByRole("button", { name: "Delete report", exact: true })
    .click();
  await page.waitForFunction(
    () => !document.getElementById("detail-dialog").open,
  );
  assert.equal(await page.locator(".saved-row").count(), 1);
  assert.match(await page.locator(".saved-row").innerText(), /200 In Progress/);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "Overview passed: saved coordinates, filters, status distinctions, evidence, missing coordinates, desktop/mobile and light/dark.",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
