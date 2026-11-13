  <script>
    const IR = JSON.parse(document.getElementById("graph-data").textContent);
    function graphPayload(ir) {
      const dependencyNodes = ir.nodes.filter((node) => node.kind === "repo_path");
      const directoryNodes = ir.nodes.filter((node) => node.kind === "directory");
      const dependencyEdges = ir.edges.filter((edge) => edge.relation !== "contains");
      const containmentEdges = ir.edges.filter((edge) => edge.relation === "contains");
      return {
        summary: ir.summary,
        nodes: dependencyNodes.map((node) => ({
          id: String(node.id),
          group: String(node.group),
          label: String(node.display.label),
          parentLabel: String(node.display.parent),
          incoming: Number(node.incoming),
          outgoing: Number(node.outgoing),
          degree: Number(node.degree),
          broken: Boolean(node.broken),
        })),
        edges: dependencyEdges.map((edge) => edge.payload_json),
        directoryTree: {
          nodes: directoryNodes.map((node) => ({
            id: String(node.id),
            path: String(node.payload_json.path),
            group: String(node.group),
            label: String(node.display.label),
            parentLabel: String(node.display.parent),
            degree: Number(node.degree),
          })),
          edges: containmentEdges.map((edge) => edge.payload_json),
        },
        directions: ir.directions,
        kinds: ir.kinds,
        highDegree: ir.highDegree,
        cycles: ir.cycles,
        brokenTargets: ir.brokenTargets,
        views: ir.views,
      };
    }
    const DATA = graphPayload(IR);
    const NODE_W = 210;
    const NODE_H = 46;
    const COL_GAP = 250;
    const ROW_GAP = 72;
    const state = {
      query: "",
      focus: "",
      depth: 1,
      scale: 1,
      directions: new Set(DATA.directions),
      kinds: new Set(DATA.kinds),
      selected: null,
    };

    const nodeRecords = DATA.nodes.map((node) => ({ ...node, search: node.id.toLowerCase() }));
    const edgeRecords = DATA.edges.map((edge, index) => ({
      ...edge,
      index,
      sourceSearch: edge.source.toLowerCase(),
      targetSearch: edge.target.toLowerCase(),
    }));
    const byId = new Map(nodeRecords.map((node) => [node.id, node]));
    const incidentById = new Map();
    let lastGraphSize = { width: 900, height: 540 };
    const svg = document.getElementById("graph");
    const inspector = document.getElementById("inspector-content");
    const resultCount = document.getElementById("result-count");

    function addListValue(map, key, value) {
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(value);
    }

    edgeRecords.forEach((edge) => {
      addListValue(incidentById, edge.source, edge);
      if (edge.target !== edge.source) addListValue(incidentById, edge.target, edge);
    });

    function el(name, attrs = {}) {
      const node = document.createElement(name);
      for (const [key, value] of Object.entries(attrs)) {
        if (key === "className") node.className = value;
        else node.setAttribute(key, value);
      }
      return node;
    }

    function svgEl(name, attrs = {}) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", name);
      for (const [key, value] of Object.entries(attrs)) {
        node.setAttribute(key, value);
      }
      return node;
    }

    function shortLabel(value, limit = 34) {
      return value.length > limit ? `${value.slice(0, limit - 3)}...` : value;
    }

    function displayNode(node) {
      return {
        label: node.label || shortLabel(node.id),
        parent: node.parentLabel || node.group,
      };
    }

    function setText(node, value) {
      node.textContent = value;
      return node;
    }

    function setupStaticZoom() {
      const graph = document.getElementById("static-graph");
      const zoom = document.getElementById("static-zoom");
      const zoomValue = document.getElementById("static-zoom-value");
      if (!graph || !zoom) return;
      const baseWidth = Number.parseFloat(graph.dataset.baseWidth || "900");
      const baseHeight = Number.parseFloat(graph.dataset.baseHeight || "540");
      const view = {
        scale: Number.parseFloat(zoom.value || "1"),
        centerX: baseWidth / 2,
        centerY: baseHeight / 2,
      };
      let drag = null;

      function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
      }

      function currentViewBoxSize() {
        return {
          width: baseWidth / view.scale,
          height: baseHeight / view.scale,
        };
      }

      function applyStaticView() {
        const size = currentViewBoxSize();
        const halfW = size.width / 2;
        const halfH = size.height / 2;
        view.centerX = clamp(view.centerX, halfW, baseWidth - halfW);
        view.centerY = clamp(view.centerY, halfH, baseHeight - halfH);
        const x = view.centerX - halfW;
        const y = view.centerY - halfH;
        graph.setAttribute("viewBox", `${x} ${y} ${size.width} ${size.height}`);
        zoom.value = `${view.scale}`;
        if (zoomValue) zoomValue.value = `${view.scale.toFixed(1)}x`;
      }

      function applyStaticZoom(value) {
        view.scale = clamp(Number.parseFloat(value || "1"), 1, 8);
        applyStaticView();
      }

      zoom.addEventListener("input", (event) => {
        applyStaticZoom(event.target.value);
      });
      document.querySelectorAll("[data-static-zoom]").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.preventDefault();
          zoom.value = button.dataset.staticZoom;
          applyStaticZoom(zoom.value);
        });
      });
      const reset = document.getElementById("static-reset");
      if (reset) {
        reset.addEventListener("click", () => {
          view.scale = 1;
          view.centerX = baseWidth / 2;
          view.centerY = baseHeight / 2;
          applyStaticView();
        });
      }
      graph.addEventListener("pointerdown", (event) => {
        graph.setPointerCapture(event.pointerId);
        graph.classList.add("dragging");
        drag = {
          x: event.clientX,
          y: event.clientY,
          centerX: view.centerX,
          centerY: view.centerY,
        };
      });
      graph.addEventListener("pointermove", (event) => {
        if (!drag) return;
        const size = currentViewBoxSize();
        const bounds = graph.getBoundingClientRect();
        const dx = (event.clientX - drag.x) * size.width / bounds.width;
        const dy = (event.clientY - drag.y) * size.height / bounds.height;
        view.centerX = drag.centerX - dx;
        view.centerY = drag.centerY - dy;
        applyStaticView();
      });
      graph.addEventListener("pointerup", (event) => {
        graph.releasePointerCapture(event.pointerId);
        graph.classList.remove("dragging");
        drag = null;
      });
      graph.addEventListener("wheel", (event) => {
        event.preventDefault();
        const next = view.scale * (event.deltaY < 0 ? 1.18 : 0.85);
        applyStaticZoom(next);
      }, { passive: false });
      applyStaticView();
    }

    function buildCheckboxes(containerId, values, activeSet, onChange) {
      const container = document.getElementById(containerId);
      container.textContent = "";
      values.forEach((value) => {
        const label = el("label", { className: "check-row" });
        const input = el("input", { type: "checkbox" });
        input.checked = activeSet.has(value);
        input.addEventListener("change", () => {
          if (input.checked) activeSet.add(value);
          else activeSet.delete(value);
          onChange();
        });
        label.append(input, setText(el("span"), value));
        container.append(label);
      });
    }

    /* AGENT_CANON_MODEL_BEGIN */
    function buildAdjacency(edges) {
      const adjacency = new Map();
      edges.forEach((edge) => {
        addListValue(adjacency, edge.source, edge.target);
        addListValue(adjacency, edge.target, edge.source);
      });
      return adjacency;
    }

    function graphNeighborhood(focus, depth, adjacency) {
      const seen = new Set([focus]);
      let frontier = new Set([focus]);
      for (let step = 0; step < depth; step += 1) {
        const next = new Set();
        frontier.forEach((node) => {
          (adjacency.get(node) || []).forEach((neighbor) => {
            if (!seen.has(neighbor)) next.add(neighbor);
          });
        });
        next.forEach((node) => seen.add(node));
        frontier = next;
      }
      return seen;
    }

    function visibleModel() {
      const query = state.query.toLowerCase();
      let edges = edgeRecords.filter(
        (edge) => state.directions.has(edge.direction) && state.kinds.has(edge.kind),
      );
      if (query) {
        edges = edges.filter(
          (edge) => edge.sourceSearch.includes(query) || edge.targetSearch.includes(query),
        );
      }
      let allowed = null;
      if (state.focus && byId.has(state.focus)) {
        allowed = graphNeighborhood(state.focus, state.depth, buildAdjacency(edges));
        edges = edges.filter((edge) => allowed.has(edge.source) && allowed.has(edge.target));
      }
      const nodeIds = new Set();
      edges.forEach((edge) => {
        nodeIds.add(edge.source);
        nodeIds.add(edge.target);
      });
      if (query) {
        nodeRecords
          .filter((node) => node.search.includes(query))
          .forEach((node) => nodeIds.add(node.id));
      }
      if (allowed) {
        allowed.forEach((node) => nodeIds.add(node));
      }
      if (!query && !allowed) {
        nodeRecords.forEach((node) => nodeIds.add(node.id));
      }
      const nodes = nodeRecords
        .filter((node) => nodeIds.has(node.id))
        .sort((left, right) => left.group.localeCompare(right.group) || left.id.localeCompare(right.id));
      return { nodes, edges };
    }
    /* AGENT_CANON_MODEL_END */

    function layout(nodes) {
      const groups = [...new Set(nodes.map((node) => node.group))].sort();
      const groupIndex = new Map(groups.map((group, index) => [group, index]));
      const rowIndex = new Map(groups.map((group) => [group, 0]));
      const points = new Map();
      nodes.forEach((node) => {
        const column = groupIndex.get(node.group) || 0;
        const row = rowIndex.get(node.group) || 0;
        rowIndex.set(node.group, row + 1);
        points.set(node.id, {
          x: 40 + column * COL_GAP,
          y: 54 + row * ROW_GAP,
        });
      });
      const maxRows = Math.max(1, ...rowIndex.values());
      return {
        points,
        width: Math.max(900, groups.length * COL_GAP + 80),
        height: Math.max(540, maxRows * ROW_GAP + 110),
      };
    }

    function renderInspector(nodeId) {
      inspector.textContent = "";
      const node = byId.get(nodeId);
      if (!node) {
        inspector.append(setText(el("p", { className: "muted" }), "Select a node"));
        return;
      }
      const summary = el("div", { className: "inspector-section" });
      const title = setText(el("h2"), "Node");
      const path = setText(el("code"), node.id);
      summary.append(title, path);
      const metrics = setText(
        el("p", { className: "muted" }),
        `${node.group} / in ${node.incoming} / out ${node.outgoing}${node.broken ? " / missing target" : ""}`,
      );
      summary.append(metrics);
      inspector.append(summary);

      const incident = incidentById.get(nodeId) || [];
      const section = el("div", { className: "inspector-section" });
      section.append(setText(el("h2"), "Incident Edges"));
      const list = el("ol", { className: "edge-list" });
      incident.forEach((edge) => {
        const item = el("li");
        setText(item, `${edge.direction}/${edge.kind}: ${edge.source} -> ${edge.target}`);
        list.append(item);
      });
      section.append(list);
      inspector.append(section);
    }

    function applyScale() {
      svg.style.width = `${lastGraphSize.width * state.scale}px`;
      svg.style.height = `${lastGraphSize.height * state.scale}px`;
    }

    function renderGraph() {
      const model = visibleModel();
      const graphLayout = layout(model.nodes);
      lastGraphSize = { width: graphLayout.width, height: graphLayout.height };
      svg.textContent = "";
      svg.setAttribute("viewBox", `0 0 ${graphLayout.width} ${graphLayout.height}`);
      applyScale();

      const defs = svgEl("defs");
      const marker = svgEl("marker", {
        id: "arrow",
        viewBox: "0 0 10 10",
        refX: "9",
        refY: "5",
        markerWidth: "5",
        markerHeight: "5",
        orient: "auto-start-reverse",
      });
      marker.append(svgEl("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#8191a2" }));
      defs.append(marker);
      svg.append(defs);

      const edgeLayer = svgEl("g");
      model.edges.forEach((edge) => {
        const source = graphLayout.points.get(edge.source);
        const target = graphLayout.points.get(edge.target);
        if (!source || !target) return;
        const startX = source.x + NODE_W;
        const startY = source.y + NODE_H / 2;
        const endX = target.x;
        const endY = target.y + NODE_H / 2;
        const curve = Math.max(48, Math.abs(endX - startX) / 2);
        const path = svgEl("path", {
          class: `edge ${edge.kind}`,
          d: `M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}`,
        });
        path.append(setText(svgEl("title"), `${edge.direction}/${edge.kind}: ${edge.source} -> ${edge.target}`));
        edgeLayer.append(path);
      });
      svg.append(edgeLayer);

      const nodeLayer = svgEl("g");
      model.nodes.forEach((node) => {
        const point = graphLayout.points.get(node.id);
        if (!point) return;
        const display = displayNode(node);
        const group = svgEl("g", {
          class: `node${node.broken ? " broken" : ""}${state.selected === node.id ? " selected" : ""}`,
          transform: `translate(${point.x} ${point.y})`,
          tabindex: "0",
          role: "button",
          "aria-label": `Inspect ${node.id}`,
        });
        group.append(svgEl("rect", { width: NODE_W, height: NODE_H }));
        group.append(setText(svgEl("text", { x: "12", y: "19", class: "label" }), shortLabel(display.label)));
        group.append(setText(svgEl("text", { x: "12", y: "36", class: "sub" }), `${shortLabel(display.parent, 24)} / degree ${node.degree}`));
        group.append(setText(svgEl("title"), node.id));
        const activateNode = () => {
          state.selected = node.id;
          document.getElementById("focus").value = node.id;
          renderInspector(node.id);
        };
        group.addEventListener("click", activateNode);
        group.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            activateNode();
          }
        });
        nodeLayer.append(group);
      });
      svg.append(nodeLayer);

      resultCount.textContent = `${model.nodes.length} nodes / ${model.edges.length} edges visible`;
      if (!state.selected || !model.nodes.some((node) => node.id === state.selected)) {
        renderInspector(model.nodes[0] ? model.nodes[0].id : "");
        state.selected = model.nodes[0] ? model.nodes[0].id : null;
      }
    }

    function setup() {
      setupStaticZoom();
      const focusList = document.getElementById("focus-list");
      nodeRecords.forEach((node) => {
        const option = el("option", { value: node.id });
        focusList.append(option);
      });
      buildCheckboxes("direction-filters", DATA.directions, state.directions, renderGraph);
      buildCheckboxes("kind-filters", DATA.kinds, state.kinds, renderGraph);
      document.getElementById("query").addEventListener("input", (event) => {
        state.query = event.target.value;
        renderGraph();
      });
      document.getElementById("focus").addEventListener("change", (event) => {
        state.focus = event.target.value;
        state.selected = state.focus || state.selected;
        renderGraph();
      });
      document.getElementById("depth").addEventListener("change", (event) => {
        state.depth = Math.max(0, Number.parseInt(event.target.value || "0", 10));
        renderGraph();
      });
      document.getElementById("zoom").addEventListener("input", (event) => {
        state.scale = Number.parseFloat(event.target.value || "1");
        applyScale();
      });
      renderGraph();
    }

    setup();
  </script>
