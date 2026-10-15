# README media

These assets show research for `121 S Highland Ave, Pittsburgh, PA 15206`.
The recording uses live public-data, Tavily, Ollama/Nemotron, and Gemini requests.
It has no narration, synthetic progress, mocked API responses, or edited findings.
Source availability and research output can differ on later runs.

- `location-overview.png`: the reviewed East Liberty public showcase report.
- `local-intelligence.png`: the recorded run's local discussion brief and sources.
- `pipeline-walkthrough.mp4`: the edited browser recording.
- `walkthrough-chapters.json`: playback timestamps and editing details.

The live run completed both web briefs, but its map source was unavailable. That
gap remains visible in the video. The map screenshot comes from the separately
reviewed showcase sample for the same address. Report reading was recorded in a
second take by reopening the same completed run; no second research run was made.
The generation interval (11–225 seconds in the original take) plays at 20× speed.
The other sections play at normal speed.

GitHub renders the screenshots and SVG diagrams directly in the main README.
The MP4 link opens or downloads the recording depending on the browser.

## Record again

Install Playwright in a tooling directory and its Chromium and FFmpeg dependencies.
Start the configured application in a separate terminal:

```sh
.venv/bin/surreal-estate app --port 8765 --data-dir exports/readme-recording
```

Then run:

```sh
node scripts/record_walkthrough.cjs --live
```

Set `NODE_PATH` if Playwright is installed outside the project. Optional variables:
`APP_URL`, `CHROMIUM_PATH`, `RECORDING_DIR`, and `RECORDING_ADDRESS`.
The `--live` flag is required because a recording starts research and can incur
normal provider charges. Use a fresh output directory to review a new take before
replacing the README assets. Review screenshots and the completed video before
publishing; generated source content and findings vary between runs.

To record an existing report without starting research, use
`node scripts/record_walkthrough.cjs --resume REPORT_ID`. The script produces WebM
recordings; the published take was joined and converted to H.264 MP4 with FFmpeg,
with the generation interval accelerated as described above.
