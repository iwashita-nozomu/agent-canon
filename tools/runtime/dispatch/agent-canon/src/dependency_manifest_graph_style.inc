  <style>
    :root {
      color-scheme: light;
      --ink: #17212b;
      --muted: #667789;
      --panel: #ffffff;
      --canvas: #f6f8fb;
      --line: #c9d4df;
      --accent: #1d7c83;
      --accent-soft: #d9eff0;
      --warn: #b75d38;
      --warn-soft: #f8e4d8;
      --design: #3268a8;
      --implementation: #467b3b;
      --environment: #7a5ca3;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: #eef3f6;
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      padding: 18px 20px 12px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 24px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .metrics {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .metric {
      min-width: 112px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f9fbfd;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    .metric strong {
      display: block;
      margin-top: 2px;
      font-size: 18px;
    }
    .app-shell {
      display: grid;
      grid-template-columns: minmax(220px, 280px) minmax(420px, 1fr) minmax(240px, 320px);
      min-height: calc(100vh - 100px);
    }
    .controls, .inspector {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 14px;
      overflow: auto;
    }
    .inspector {
      border-right: 0;
      border-left: 1px solid var(--line);
    }
    .graph-pane {
      min-width: 0;
      display: grid;
      grid-template-rows: auto 1fr;
      background: var(--canvas);
    }
    .graph-toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .graph-canvas {
      min-height: 560px;
      overflow: auto;
      padding: 12px;
    }
    svg {
      display: block;
      min-width: 900px;
      min-height: 540px;
      background: white;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .graph-workbench {
      padding: 14px 20px 18px;
      border-bottom: 1px solid var(--line);
      background: #f8fbfd;
    }
    .graph-workbench h2 {
      margin: 0 0 6px;
      font-size: 18px;
      line-height: 1.25;
      letter-spacing: 0;
    }
    .graph-workbench p {
      margin: 0 0 12px;
      max-width: 920px;
    }
    .graph-stage-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
      align-items: stretch;
    }
    .overview-pane, .fullgraph-pane {
      min-width: 0;
    }
    .overview-pane h3, .fullgraph-pane h3 {
      margin: 0 0 8px;
      font-size: 14px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .territory-map-wrap {
      height: min(42vh, 430px);
      min-height: 320px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }
    .territory-map {
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      border: 0;
      border-radius: 0;
    }
    .territory-cell {
      stroke: #ffffff;
      stroke-width: 3;
    }
    .territory-edge {
      fill: none;
      stroke: #596b7c;
      opacity: 0.36;
      marker-end: url(#territory-arrow);
    }
    .territory-edge.design { stroke: var(--design); }
    .territory-edge.implementation { stroke: var(--implementation); }
    .territory-edge.environment { stroke: var(--environment); }
    .territory-label {
      text-anchor: middle;
      font-size: 12px;
      font-weight: 800;
      fill: var(--ink);
      paint-order: stroke;
      stroke: rgba(255, 255, 255, 0.82);
      stroke-width: 4px;
      stroke-linejoin: round;
    }
    .territory-label .sub {
      font-size: 10px;
      font-weight: 700;
      fill: var(--muted);
    }
    .overview-edge {
      fill: none;
      stroke: #8191a2;
      opacity: 0.34;
    }
    .overview-edge.design { stroke: var(--design); }
    .overview-edge.implementation { stroke: var(--implementation); }
    .overview-edge.environment { stroke: var(--environment); }
    .overview-node rect {
      fill: #ffffff;
      stroke: #7f91a3;
      rx: 8;
    }
    .overview-node .label {
      font-size: 12px;
      font-weight: 800;
      fill: var(--ink);
    }
    .overview-node .sub {
      font-size: 10px;
      fill: var(--muted);
    }
    .static-graph-wrap {
      height: min(72vh, 760px);
      min-height: 520px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }
    .static-toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin: 0 0 12px;
    }
    .static-toolbar label {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-weight: 700;
    }
    .static-toolbar output {
      min-width: 44px;
      font-variant-numeric: tabular-nums;
    }
    .static-toolbar button,
    .static-zoom-link {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 5px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
      font: inherit;
      cursor: pointer;
      text-decoration: none;
    }
    .static-toolbar button:hover,
    .static-zoom-link:hover {
      border-color: var(--accent);
    }
    .static-zoom-state {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }
    .static-graph {
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      border: 0;
      border-radius: 0;
      cursor: grab;
      touch-action: none;
    }
    .static-graph.dragging {
      cursor: grabbing;
    }
    .static-graph-content {
      transition: transform 120ms ease;
    }
    .static-group-block rect {
      fill: #f9fbfd;
      stroke: #d5dee7;
      rx: 10;
    }
    .static-group {
      font-size: 15px;
      font-weight: 800;
      fill: var(--ink);
    }
    .static-group-sub {
      font-size: 11px;
      fill: var(--muted);
    }
    .static-edge {
      fill: none;
      stroke: #8191a2;
      stroke-width: 1.2;
      opacity: 0.32;
      marker-end: url(#static-arrow);
    }
    .static-edge.design { stroke: var(--design); }
    .static-edge.implementation { stroke: var(--implementation); }
    .static-edge.environment { stroke: var(--environment); }
    .static-edge path, marker path { fill: #8191a2; }
    .static-node rect {
      fill: #ffffff;
      stroke: #7f91a3;
      stroke-width: 1;
      rx: 6;
    }
    .static-node .label {
      font-size: 9.5px;
      font-weight: 700;
      fill: var(--ink);
    }
    .static-node .sub {
      font-size: 8px;
      fill: var(--muted);
    }
    .static-node.broken rect {
      fill: var(--warn-soft);
      stroke: var(--warn);
    }
    details.edge-table {
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }
    details.edge-table summary {
      cursor: pointer;
      padding: 10px 12px;
      font-weight: 700;
    }
    details.edge-table .table-wrap {
      max-height: 440px;
      overflow: auto;
      border-top: 1px solid var(--line);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
    }
    th, td {
      padding: 7px 9px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f4f7fa;
      font-size: 12px;
    }
    fieldset {
      margin: 0 0 14px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    legend {
      padding: 0 4px;
      font-weight: 700;
    }
    label {
      display: block;
      margin: 8px 0;
      color: var(--ink);
    }
    input[type="search"], input[type="text"], input[type="number"] {
      width: 100%;
      min-height: 34px;
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
    }
    input[type="range"] { width: 160px; }
    .check-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 7px 0;
    }
    .check-row input { margin: 0; }
    .muted { color: var(--muted); }
    code {
      font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      overflow-wrap: anywhere;
    }
    .edge {
      fill: none;
      stroke: #8191a2;
      stroke-width: 1.6;
      opacity: 0.7;
      marker-end: url(#arrow);
    }
    .edge.design { stroke: var(--design); }
    .edge.implementation { stroke: var(--implementation); }
    .edge.environment { stroke: var(--environment); }
    .node rect {
      fill: #ffffff;
      stroke: #7f91a3;
      stroke-width: 1.2;
      rx: 8;
    }
    .node text { pointer-events: none; }
    .node .label {
      font-size: 12px;
      font-weight: 700;
      fill: var(--ink);
    }
    .node .sub {
      font-size: 10px;
      fill: var(--muted);
    }
    .node.broken rect {
      fill: var(--warn-soft);
      stroke: var(--warn);
    }
    .node.selected rect {
      fill: var(--accent-soft);
      stroke: var(--accent);
      stroke-width: 2;
    }
    .inspector-section {
      margin-bottom: 14px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }
    .edge-list {
      margin: 8px 0 0;
      padding-left: 18px;
    }
    .edge-list li {
      margin-bottom: 6px;
      overflow-wrap: anywhere;
    }
    @media (max-width: 980px) {
      .graph-stage-grid { grid-template-columns: 1fr; }
      .app-shell { grid-template-columns: 1fr; }
      .controls, .inspector {
        border-left: 0;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .graph-canvas { min-height: 460px; }
    }
  </style>
