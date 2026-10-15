// Record the real app workflow. Requires Playwright and a running configured app.
// This starts live research and may incur normal search/model charges.
// Usage: NODE_PATH=/path/to/node_modules node scripts/record_walkthrough.cjs --live
const resumeIndex = process.argv.indexOf("--resume");
const resume = resumeIndex >= 0 ? process.argv[resumeIndex + 1] : null;
if (!process.argv.includes("--live") && !resume) {
  console.error("Usage: node scripts/record_walkthrough.cjs --live | --resume REPORT_ID");
  process.exit(2);
}
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const appUrl = process.env.APP_URL || "http://127.0.0.1:8765";
const output = path.resolve(process.env.RECORDING_DIR || "docs/media");
const address = process.env.RECORDING_ADDRESS || "121 S Highland Ave, Pittsburgh, PA 15206";

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    colorScheme: "light",
    recordVideo: { dir: path.join(output, "raw"), size: { width: 1440, height: 1000 } },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const start = Date.now();
  const chapters = [];
  const chapter = title => {
    const seconds = Math.round((Date.now() - start) / 1000);
    chapters.push({ seconds, title });
    console.log(`${seconds}s: ${title}`);
  };
  const pause = () => page.waitForTimeout(2000);
  const nav = name => page.locator("#report-sidebar").getByRole("button", { name, exact: true }).click();
  let successful = false;
  try {
    if (!resume) {
      await page.goto(appUrl + "/#entry");
      await page.getByLabel("Address", { exact: true }).waitFor();
      chapter("Enter an address");
      await pause();
      await page.getByLabel("Address", { exact: true }).pressSequentially(address, { delay: 45 });
      await pause();
      await page.getByRole("button", { name: /Find address/ }).click();
      await page.getByRole("radio").first().waitFor({ timeout: 60000 });
      await page.getByRole("radio").first().check();
      chapter("Confirm the Census address match");
      await pause();
      await page.getByRole("button", { name: "Confirm location", exact: true }).click();
      await page.locator("[name=local]:enabled").waitFor();
      await page.locator("[name=apis]").check();
      await page.locator("[name=local]").check();
      await page.locator("[name=dining]").check();
      chapter("Select public records and both local intelligence topics");
      await pause();
      await page.getByRole("button", { name: "Generate report", exact: true }).click();
      await page.waitForURL(/progress\//);
      chapter("Run the live research pipeline");
      console.log("Run ID:", page.url().split("/").pop());
      await page.getByRole("button", { name: "Explore report", exact: true }).waitFor({ timeout: 360000 });
      chapter("Report ready");
      await pause();
      await page.getByRole("button", { name: "Explore report", exact: true }).click();
    } else {
      await page.goto(appUrl + "/#report/" + encodeURIComponent(resume));
    }
    await page.getByRole("heading", { name: "Location overview", exact: true }).waitFor();
    await page.evaluate(() => document.fonts.ready);
    chapter("Explore mapped surroundings");
    await pause();
    const mappedPlaces = page.getByRole("button", { name: "Show groceries on map" });
    await page.screenshot({ path: path.join(output, await mappedPlaces.count() ? "location-overview.png" : "run-location-overview.png") });
    if (await mappedPlaces.count()) {
      await mappedPlaces.click();
      await pause();
      await page.getByRole("button", { name: "Show transit on map" }).click();
      await pause();
    } else {
      chapter("Map source unavailable; review the report's coverage notice");
      await pause();
    }
    await nav("Local intelligence");
    await page.locator(".research-title").waitFor();
    chapter("Read local discussions and inspect a cited paragraph");
    await pause();
    const paragraph = page.getByRole("button", { name: "View paragraph sources", exact: true }).first();
    if (await paragraph.count()) {
      await paragraph.click();
      await pause();
      await page.screenshot({ path: path.join(output, "local-intelligence.png") });
    } else throw new Error("No cited brief is available to record.");
    await page.getByRole("button", { name: "Dining reviews", exact: true }).click();
    chapter("Read dining research");
    await pause();
    await page.mouse.wheel(0, 440);
    await pause();
    await nav("Sources");
    chapter("Inspect source provenance");
    await pause();
    await nav("Findings");
    await page.getByRole("button", { name: "Report coverage", exact: true }).click();
    chapter("Review coverage and limitations");
    await pause();
    await page.getByRole("button", { name: "Location overview", exact: true }).click();
    await pause();
    if (errors.length) throw new Error(errors.join("\n"));
    successful = true;
  } finally {
    const video = page.video();
    await context.close();
    await video.saveAs(path.join(output, successful ? (resume ? "report-walkthrough.webm" : "pipeline-walkthrough.webm") : "incomplete-walkthrough.webm"));
    await video.delete();
    fs.writeFileSync(path.join(output, resume ? "report-chapters.json" : "walkthrough-chapters.json"), JSON.stringify({ address, successful, chapters, errors }, null, 2) + "\n");
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
