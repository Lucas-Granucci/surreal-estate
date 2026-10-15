# Architecture diagrams

The main README embeds the SVGs exported with Excalidraw 0.18.1. Each diagram
leads with component responsibilities and shows the supporting technologies beneath them.

To edit, open either `.excalidraw` file in Excalidraw or drag it onto the canvas.
Each component's shape and text are grouped. Export as SVG with a white background
and replace the matching file here. No fonts or images need to be downloaded to
display these SVGs.

- `research-channels`: location confirmation and scope, structured research, web
  research, and a locally saved evidence report.
- `local-intelligence`: cloud retrieval, local planning and extraction, cloud
  writing, local citation validation, and the source-cited brief. The two-way arrow between
  Tavily and Nemotron represents queries and returned source material. The lower
  loop shows the optional targeted factual check and local reassessment before
  final writing.
