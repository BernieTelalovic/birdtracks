const SVG_NS = "http://www.w3.org/2000/svg";
const activeEditorByGroup = new Map();
let activeGroupId = null;

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, String(value));
  }
  return element;
}

function undoIcon() {
  const icon = svgElement("svg", {
    viewBox: "0 0 32 32",
    class: "birdtracks-undo-icon",
    "aria-hidden": "true",
  });
  icon.append(
    svgElement("circle", { cx: 16, cy: 16, r: 14 }),
    svgElement("path", {
      d: "M14 10 L8 16 L14 22 M9 16 H19 C23 16 25 19 25 23",
    }),
  );
  return icon;
}

function drawExactCoefficient(layer, coefficient, termSign, geometry, x, y) {
  const numerator = BigInt(coefficient.numerator);
  const denominator = BigInt(coefficient.denominator);
  const fontSize = geometry.coefficient_font_size;
  const magnitude = numerator < 0n ? -numerator : numerator;
  const fractionFontSize = geometry.fraction_font_size || fontSize;
  const digitCount = Math.max(String(magnitude).length, String(denominator).length);
  const valueHalfWidth = denominator === 1n
    ? Math.max(fontSize * 0.3, String(magnitude).length * fontSize * 0.3)
    : Math.max(
        geometry.fraction_bar_width,
        digitCount * fractionFontSize * 0.6,
      ) / 2;
  const unitMagnitude = magnitude === 1n && denominator === 1n;
  // `x` is the centre of the complete prefactor slot. A signed non-unit
  // coefficient extends farther to the left because the sign precedes the
  // magnitude, so shift the magnitude right to centre the whole group.
  const valueX = x + (termSign && !unitMagnitude ? fontSize * 0.375 : 0);
  if (termSign) {
    const signX = unitMagnitude
      ? valueX
      : valueX - valueHalfWidth - fontSize * 0.5;
    const radius = fontSize * 0.25;
    layer.appendChild(svgElement("line", {
      x1: signX - radius,
      x2: signX + radius,
      y1: y,
      y2: y,
      class: "birdtracks-term-sign",
    }));
    if (termSign === "+") layer.appendChild(svgElement("line", {
      x1: signX,
      x2: signX,
      y1: y - radius,
      y2: y + radius,
      class: "birdtracks-term-sign",
    }));
  }
  if (unitMagnitude) return;
  const minus = (minusX) => layer.appendChild(svgElement("line", {
    x1: minusX - fontSize * 0.25,
    x2: minusX + fontSize * 0.25,
    y1: y,
    y2: y,
    class: "birdtracks-coefficient-minus",
  }));
  if (denominator === 1n) {
    if (numerator < 0n) minus(valueX - (magnitude === 1n ? 0 : fontSize * 0.35));
    if (magnitude === 1n && numerator < 0n) return;
    const text = svgElement("text", {
      x: numerator < 0n ? valueX + fontSize * 0.2 : valueX,
      y,
      class: "birdtracks-coefficient",
      "font-size": fontSize,
      "text-anchor": "middle",
      "dominant-baseline": "middle",
    });
    text.textContent = String(magnitude);
    layer.appendChild(text);
    return;
  }
  const barWidth = Math.max(
    geometry.fraction_bar_width,
    digitCount * fractionFontSize * 0.6,
  );
  if (numerator < 0n) minus(valueX - barWidth / 2 - fractionFontSize * 0.4);
  const bar = svgElement("line", {
    x1: valueX - barWidth / 2,
    x2: valueX + barWidth / 2,
    y1: y,
    y2: y,
    class: "birdtracks-fraction-bar",
  });
  const top = svgElement("text", {
    x: valueX,
    y: y - geometry.fraction_height / 2,
    class: "birdtracks-fraction-number",
    "font-size": fractionFontSize,
    "text-anchor": "middle",
    "dominant-baseline": "middle",
  });
  top.textContent = String(magnitude);
  const bottom = svgElement("text", {
    x: valueX,
    y: y + geometry.fraction_height / 2,
    class: "birdtracks-fraction-number",
    "font-size": fractionFontSize,
    "text-anchor": "middle",
    "dominant-baseline": "middle",
  });
  bottom.textContent = String(denominator);
  layer.append(bar, top, bottom);
}

function enableTermReordering({ model, el, svg }) {
  let drag = null;
  const dimOtherTerms = (dimmed) => {
    const row = el.closest(".birdtracks-equation-row");
    if (!row) return;
    row.querySelectorAll(":scope > .birdtracks-projector-widget").forEach((term) => {
      if (term !== el) term.classList.toggle("birdtracks-term-dimmed", dimmed);
    });
  };

  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target !== svg) return;
    const row = el.closest(".birdtracks-equation-row");
    const terms = row
      ? [...row.querySelectorAll(":scope > .birdtracks-projector-widget")]
      : [];
    if (terms.length < 2) return;
    drag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      target: terms.indexOf(el),
      started: false,
    };
    svg.setPointerCapture(event.pointerId);
  });

  svg.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (!drag.started) {
      if (Math.abs(dx) < 6 || Math.abs(dx) <= Math.abs(dy)) return;
      drag.started = true;
      dimOtherTerms(true);
    }
    event.preventDefault();
    const row = el.closest(".birdtracks-equation-row");
    const others = row
      ? [...row.querySelectorAll(":scope > .birdtracks-projector-widget")]
        .filter((term) => term !== el)
      : [];
    let target = others.findIndex((term) => {
      const box = term.getBoundingClientRect();
      return event.clientX < box.left + box.width / 2;
    });
    if (target < 0) target = others.length;
    drag.target = target;
  });

  const finish = (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const completed = drag;
    drag = null;
    dimOtherTerms(false);
    if (!completed.started) return;
    event.preventDefault();
    model.set("term_order_request", {
      target: completed.target,
      revision: Date.now(),
    });
    model.save_changes();
  };
  svg.addEventListener("pointerup", finish);
  svg.addEventListener("pointercancel", () => {
    drag = null;
    dimOtherTerms(false);
  });
}

function renderToolbar({ model, el }) {
  const groupId = model.get("group_id");
  el.classList.add("birdtracks-shared-toolbar");
  const toolbar = document.createElement("div");
  toolbar.className = "birdtracks-creator-toolbar";
  const status = document.createElement("div");
  status.className = "birdtracks-canvas-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");

  function updateStatus(event) {
    if (event.detail.groupId !== groupId) return;
    status.textContent = event.detail.message;
    status.scrollLeft = status.scrollWidth;
  }
  document.addEventListener("birdtracks-projector-status", updateStatus);

  function dispatch(action, payload = {}) {
    document.dispatchEvent(new CustomEvent("birdtracks-projector-tool", {
      detail: { groupId, action, ...payload },
    }));
  }

  function button(label, action) {
    const result = document.createElement("button");
    result.type = "button";
    result.title = label;
    result.setAttribute("aria-label", label);
    result.addEventListener("click", action);
    return result;
  }

  function operatorButton(kind) {
    const label = kind === "symmetriser" ? "Add symmetriser" : "Add antisymmetriser";
    const result = button(label, () => dispatch(`add-${kind}`));
    result.className = "birdtracks-operator-button";
    result.draggable = true;
    result.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("application/x-birdtracks-operator", kind);
      event.dataTransfer.effectAllowed = "copy";
    });
    const icon = svgElement("svg", { viewBox: "0 0 48 32", "aria-hidden": "true" });
    icon.append(
      svgElement("line", { x1: 2, y1: 10, x2: 46, y2: 10 }),
      svgElement("line", { x1: 2, y1: 22, x2: 46, y2: 22 }),
      svgElement("rect", {
        x: 17, y: 4, width: 14, height: 24,
        class: kind === "symmetriser" ? "palette-symmetriser" : "palette-antisymmetriser",
      }),
    );
    result.appendChild(icon);
    return result;
  }

  function iconButton(label, pathData, action) {
    const result = button(label, () => dispatch(action));
    result.className = "birdtracks-icon-button";
    const icon = svgElement("svg", { viewBox: "0 0 32 32", "aria-hidden": "true" });
    icon.appendChild(svgElement("path", { d: pathData }));
    result.appendChild(icon);
    return result;
  }

  function undoButton() {
    const result = button("Undo", () => {
      model.set("undo_request", {
        editor_id: activeEditorByGroup.get(groupId) || "",
        revision: Date.now(),
      });
      model.save_changes();
    });
    result.className = "birdtracks-icon-button birdtracks-undo-button";
    result.appendChild(undoIcon());
    return result;
  }

  const addSymmetriser = operatorButton("symmetriser");
  const addAntisymmetriser = operatorButton("antisymmetriser");
  function requestTerm(sign) {
    model.set("add_term_request", {
      sign,
      editor_id: activeEditorByGroup.get(groupId) || "",
      revision: Date.now(),
    });
    model.save_changes();
  }
  const addPositiveTerm = button("Insert positive term", () => requestTerm(1));
  addPositiveTerm.className = "birdtracks-icon-button birdtracks-add-term-button";
  addPositiveTerm.textContent = "+";
  const addNegativeTerm = button("Insert negative term", () => requestTerm(-1));
  addNegativeTerm.className = "birdtracks-icon-button birdtracks-add-term-button";
  addNegativeTerm.textContent = "−";
  const multiplier = document.createElement("div");
  multiplier.className = "birdtracks-multiplier";
  multiplier.hidden = true;
  const numerator = document.createElement("input");
  numerator.type = "text";
  numerator.inputMode = "numeric";
  numerator.value = "1";
  numerator.setAttribute("aria-label", "Multiplier numerator");
  const fractionBar = document.createElement("span");
  fractionBar.className = "birdtracks-multiplier-bar";
  const denominator = document.createElement("input");
  denominator.type = "text";
  denominator.inputMode = "numeric";
  denominator.value = "1";
  denominator.setAttribute("aria-label", "Multiplier denominator");
  multiplier.append(numerator, fractionBar, denominator);
  function confirmMultiplier() {
    if (!/^[+-]?\d+$/.test(numerator.value.trim())
        || !/^[+-]?\d+$/.test(denominator.value.trim())
        || BigInt(denominator.value.trim()) === 0n) {
      status.textContent = "Enter an integer numerator and a nonzero denominator.";
      return;
    }
    dispatch("multiply", {
      numerator: numerator.value.trim(),
      denominator: denominator.value.trim(),
      editorId: activeEditorByGroup.get(groupId) || "",
    });
    multiplier.hidden = true;
    numerator.value = "1";
    denominator.value = "1";
  }
  for (const input of [numerator, denominator]) {
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      confirmMultiplier();
    });
  }
  const multiply = button("Multiply by a fraction", () => {
    multiplier.hidden = !multiplier.hidden;
    if (!multiplier.hidden) numerator.focus();
  });
  multiply.className = "birdtracks-icon-button birdtracks-multiply-button";
  multiply.textContent = "×";
  const createTab = iconButton(
    "Create mode",
    "M7 25 L11 17 L25 3 L29 7 L15 21 Z M6 26 L14 22",
    "create",
  );
  const evaluateTab = iconButton(
    "Evaluate mode",
    "M6 3 H26 V29 H6 Z M10 7 H22 V12 H10 Z M10 17 H13 M17 17 H20 M10 22 H13 M17 22 H20",
    "evaluate",
  );
  const trace = button("Show trace", () => {
    model.set("trace_enabled", !Boolean(model.get("trace_enabled")));
    model.save_changes();
  });
  trace.className = "birdtracks-icon-button birdtracks-trace-button";
  const traceIcon = svgElement("svg", { viewBox: "0 0 32 32", "aria-hidden": "true" });
  const traceText = svgElement("text", {
    x: 16, y: 17,
    "text-anchor": "middle",
    "dominant-baseline": "middle",
  });
  traceText.textContent = "tr";
  traceIcon.appendChild(traceText);
  trace.appendChild(traceIcon);
  function updateTrace() {
    const enabled = Boolean(model.get("trace_enabled"));
    trace.classList.toggle("selected", enabled);
    trace.setAttribute("aria-pressed", String(enabled));
    trace.title = enabled ? "Hide trace" : "Show trace";
  }
  model.on("change:trace_enabled", updateTrace);
  updateTrace();
  const createTools = document.createElement("div");
  createTools.className = "birdtracks-toolbar-tools birdtracks-toolbar-left";
  createTools.append(
    addSymmetriser,
    addAntisymmetriser,
    addPositiveTerm,
    addNegativeTerm,
  );
  const evaluateTools = document.createElement("div");
  evaluateTools.className = "birdtracks-toolbar-tools birdtracks-toolbar-left";
  evaluateTools.append(trace);
  const rightTools = document.createElement("div");
  rightTools.className = "birdtracks-toolbar-tools birdtracks-toolbar-right";
  rightTools.append(
    createTab,
    evaluateTab,
    iconButton("Zoom in", "M8 14 H20 M14 8 V20 M19 19 L29 29 M14 24 A10 10 0 1 1 14 4 A10 10 0 1 1 14 24", "zoom-in"),
    iconButton("Zoom out", "M8 14 H20 M19 19 L29 29 M14 24 A10 10 0 1 1 14 4 A10 10 0 1 1 14 24", "zoom-out"),
    undoButton(),
  );
  let currentToolbarMode = model.get("mode") || "evaluate";
  function showMode(mode) {
    currentToolbarMode = mode;
    createTab.classList.toggle("selected", mode === "create");
    evaluateTab.classList.toggle("selected", mode === "evaluate");
    createTab.setAttribute("aria-pressed", String(mode === "create"));
    evaluateTab.setAttribute("aria-pressed", String(mode === "evaluate"));
    addSymmetriser.disabled = mode !== "create";
    addAntisymmetriser.disabled = mode !== "create";
    addPositiveTerm.disabled = mode !== "create";
    addNegativeTerm.disabled = mode !== "create";
    multiply.disabled = mode !== "create";
    createTools.hidden = mode !== "create";
    evaluateTools.hidden = mode !== "evaluate";
    if (mode !== "create") multiplier.hidden = true;
  }
  function chooseMode(mode) {
    showMode(mode);
    if (mode === "create" && model.get("trace_enabled")) {
      model.set("trace_enabled", false);
    }
    model.set("mode", mode);
    model.save_changes();
  }
  createTab.addEventListener("click", () => chooseMode("create"));
  evaluateTab.addEventListener("click", () => chooseMode("evaluate"));
  model.on("change:mode", () => showMode(model.get("mode")));
  showMode(model.get("mode") || "evaluate");
  toolbar.append(createTools, evaluateTools, status, rightTools);
  el.appendChild(toolbar);
  function openMultiplierFromKeyboard(event) {
    if (event.key !== "*" || currentToolbarMode !== "create") return;
    if (activeGroupId !== null && activeGroupId !== groupId) return;
    if (event.target instanceof HTMLInputElement
        || event.target instanceof HTMLTextAreaElement) return;
    event.preventDefault();
    multiplier.hidden = false;
    numerator.focus();
    numerator.select();
  }
  function addTermFromKeyboard(event) {
    if (currentToolbarMode !== "create") return;
    if (activeGroupId !== null && activeGroupId !== groupId) return;
    if (event.target instanceof HTMLInputElement
        || event.target instanceof HTMLTextAreaElement) return;
    if (event.key !== "+" && event.key !== "-") return;
    event.preventDefault();
    requestTerm(event.key === "+" ? 1 : -1);
  }
  document.addEventListener("keydown", addTermFromKeyboard);
  return () => {
    document.removeEventListener("birdtracks-projector-status", updateStatus);
    model.off("change:trace_enabled", updateTrace);
    document.removeEventListener("keydown", addTermFromKeyboard);
  };
}

function renderCreator({ model, el }) {
  const widgetMode = model.get("mode") || "evaluate";
  let groupId = model.get("group_id");
  const updateGroupId = () => {
    const previousGroupId = groupId;
    groupId = model.get("group_id");
    if (activeEditorByGroup.get(previousGroupId) === editorId) {
      activeEditorByGroup.delete(previousGroupId);
      activeEditorByGroup.set(groupId, editorId);
    }
  };
  const editorId = model.model_id;
  model.on("change:group_id", updateGroupId);
  activeEditorByGroup.set(groupId, editorId);
  el.addEventListener("pointerdown", () => { activeGroupId = groupId; });
  el.classList.add(
    "birdtracks-projector-widget",
    "birdtracks-projector-creator",
    `birdtracks-projector-${widgetMode}`,
  );
  const template = model.get("graph");
  const displayGraph = template.display || {};
  const geometry = template.geometry;
  const spacing = geometry.level_spacing;
  const nodeWidth = geometry.node_width;
  const layerStep = geometry.layer_step;
  const INITIAL_LAYERS = 1;
  const INITIAL_LEVELS = 1;
  const savedPositions = structuredClone(model.get("positions") || {});
  const savedPortOrders = structuredClone(model.get("port_orders") || {});
  const savedBoundaryOrders = structuredClone(model.get("boundary_orders") || {
    input: template.boundary_labels || [],
    output: template.boundary_labels || [],
  });
  const savedFreeLevels = structuredClone(model.get("free_levels") || {});
  let coefficientNumerator = BigInt(template.coefficient.numerator);
  let coefficientDenominator = BigInt(template.coefficient.denominator);
  let nodes = (template.nodes || []).map((node) => {
    const position = savedPositions[String(node.index)];
    const orders = savedPortOrders[String(node.index)] || {};
    const inputOrder = [...(orders.input || node.input_labels || node.labels)];
    const outputOrder = [...(orders.output || node.output_labels || node.labels)];
    return {
      index: node.index,
      kind: node.kind,
      layer: node.layer,
      level: position
        ? Math.max(0, Math.round(
          (position.y - geometry.top_margin) / spacing
            - (node.labels.length - 1) / 2,
        ))
        : 0,
      labels: [...node.labels],
      inputOrder,
      outputOrder,
      initialInputOrder: [...inputOrder],
      initialOutputOrder: [...outputOrder],
      mapping: node.mapping ? structuredClone(node.mapping) : null,
    };
  }).sort((left, right) => left.index - right.index);

  function xForLayer(layer) {
    if (!nodes.length || nodes.some((node) => node.kind !== "permutation")) {
      return geometry.first_layer_x + layer * layerStep;
    }
    const layers = Math.max(...nodes.map((node) => node.layer)) + 1;
    return geometry.left_boundary
      + 2 * geometry.step * (layer + 1) / (layers + 1);
  }
  const boundaryLevel = (side, label) => {
    const order = savedBoundaryOrders[side] || template.boundary_labels || [];
    const level = order.indexOf(label);
    return level < 0 ? (template.boundary_labels || []).indexOf(label) : level;
  };
  const routeFor = (label) => Object.fromEntries(
    Object.entries(savedFreeLevels)
      .filter(([_layer, assignments]) => assignments[String(label)] !== undefined)
      .map(([layer, assignments]) => [layer, assignments[String(label)]]),
  );
  let connections = [
    ...(template.connections || []).map((connection) => ({
      source: { type: "port", side: "output", ...connection.source },
      target: { type: "port", side: "input", ...connection.target },
      boundaryLabel: connection.boundary_label,
      route: routeFor(connection.boundary_label),
    })),
    ...(template.external_inputs || []).map((boundary) => ({
      source: {
        type: "right-anchor",
        level: boundaryLevel("input", boundary.boundary_label),
      },
      target: { type: "port", side: "input", ...boundary.port },
      boundaryLabel: boundary.boundary_label,
      route: routeFor(boundary.boundary_label),
    })),
    ...(template.external_outputs || []).map((boundary) => ({
      source: { type: "port", side: "output", ...boundary.port },
      target: {
        type: "left-anchor",
        level: boundaryLevel("output", boundary.boundary_label),
      },
      boundaryLabel: boundary.boundary_label,
      route: routeFor(boundary.boundary_label),
    })),
  ];
  if (!nodes.length && !connections.length) connections = [{
    source: { type: "right-anchor", level: 0 },
    target: { type: "left-anchor", level: 0 },
    route: {},
  }];
  let nextLabel = Math.max(0, ...nodes.flatMap((node) => node.labels)) + 1;
  let controlDown = false;
  let draft = null;
  let lineDragActive = false;
  let lastNodePointerDown = null;
  let suppressCanvasDoubleClickUntil = 0;
  let interactionMode = widgetMode;
  let zoom = Number(model.get("zoom") || 1);
  const undoStack = [];

  function snapshotEditorState() {
    return {
      nodes: structuredClone(nodes),
      connections: structuredClone(connections),
      nextLabel,
      coefficientNumerator,
      coefficientDenominator,
      termNegative: model.get("term_sign") === "-",
    };
  }

  function rememberEditorState(snapshot = snapshotEditorState()) {
    undoStack.push(snapshot);
    localUndo.disabled = false;
  }

  function undoEditorOperation() {
    const previous = undoStack.pop();
    if (!previous) return false;
    const modeBeforeUndo = interactionMode;
    nodes = previous.nodes;
    connections = previous.connections;
    nextLabel = previous.nextLabel;
    coefficientNumerator = previous.coefficientNumerator;
    coefficientDenominator = previous.coefficientDenominator;
    if ((model.get("term_sign") === "-") !== previous.termNegative) {
      setTermNegative(previous.termNegative);
    }
    compactEmptyLayers();
    normalizeCreatorLayers();
    syncPortOrders();
    redraw();
    saveProjector();
    // Synchronising the exact value is not a mode transition. Reassert the
    // live mode so toolbar operator actions remain enabled after create undo.
    interactionMode = modeBeforeUndo;
    model.set("mode", modeBeforeUndo);
    model.save_changes();
    return true;
  }

  for (const [name, value] of Object.entries({
    background: geometry.background_color,
    border: geometry.border_color,
    line: geometry.line_color,
    symmetriser: geometry.symmetriser_color,
    antisymmetriser: geometry.antisymmetriser_color,
    "port-handle": geometry.port_handle_color,
    "free-handle": geometry.free_line_handle_color,
    "handle-line-width": geometry.handle_line_width,
    "add-line-width": geometry.handle_line_width / 2,
    "line-width": geometry.line_width,
    "operator-line-width": geometry.operator_line_width,
  })) el.style.setProperty(`--birdtracks-${name}`, value);

  const svg = svgElement("svg", {
    role: "img",
    "aria-label": "Create a birdtrack projector diagram",
    preserveAspectRatio: "xMinYMid meet",
  });
  enableTermReordering({ model, el, svg });
  const message = {
    set textContent(value) {
      document.dispatchEvent(new CustomEvent("birdtracks-projector-status", {
        detail: { groupId, message: String(value) },
      }));
    },
  };
  const save = document.createElement("button");
  save.type = "button";
  save.textContent = "Save";
  save.addEventListener("click", () => saveProjector());
  save.className = "birdtracks-save-button";
  const workspace = document.createElement("div");
  workspace.className = "birdtracks-creator-workspace";
  const localUndo = document.createElement("button");
  localUndo.type = "button";
  localUndo.className = "birdtracks-local-undo";
  localUndo.title = "Undo last change to this projector";
  localUndo.setAttribute("aria-label", "Undo last change to this projector");
  localUndo.appendChild(undoIcon());
  localUndo.disabled = false;
  localUndo.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    undoEditorOperation();
  });
  const localMultiply = document.createElement("button");
  localMultiply.type = "button";
  localMultiply.className = "birdtracks-local-prefactor";
  localMultiply.title = "Multiply this projector by a fraction";
  localMultiply.setAttribute("aria-label", "Multiply this projector by a fraction");
  localMultiply.textContent = "·";
  const localFraction = document.createElement("div");
  localFraction.className = "birdtracks-local-fraction";
  localFraction.hidden = true;
  const localNumerator = document.createElement("input");
  localNumerator.type = "text";
  localNumerator.inputMode = "numeric";
  localNumerator.value = "1";
  localNumerator.setAttribute("aria-label", "Projector multiplier numerator");
  const localBar = document.createElement("span");
  localBar.className = "birdtracks-multiplier-bar";
  const localDenominator = document.createElement("input");
  localDenominator.type = "text";
  localDenominator.inputMode = "numeric";
  localDenominator.value = "1";
  localDenominator.setAttribute("aria-label", "Projector multiplier denominator");
  localFraction.append(localNumerator, localBar, localDenominator);
  function setLocalFractionOpen(open) {
    localFraction.hidden = !open;
    workspace.classList.toggle("fraction-open", open);
  }
  function applyLocalMultiplier() {
    if (!/^[+-]?\d+$/.test(localNumerator.value.trim())
        || !/^[+-]?\d+$/.test(localDenominator.value.trim())
        || BigInt(localDenominator.value.trim()) === 0n) {
      message.textContent = "Enter an integer numerator and a nonzero denominator.";
      return false;
    }
    multiplyCoefficient(localNumerator.value.trim(), localDenominator.value.trim());
    saveProjector();
    setLocalFractionOpen(false);
    return true;
  }
  localMultiply.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    setLocalFractionOpen(localFraction.hidden);
    if (!localFraction.hidden) {
      localNumerator.focus();
      localNumerator.select();
    }
  });
  for (const input of [localNumerator, localDenominator]) {
    input.addEventListener("pointerdown", (event) => event.stopPropagation());
    input.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (input === localNumerator && event.key === "/") {
        event.preventDefault();
        localDenominator.focus();
        localDenominator.select();
        return;
      }
      if (event.key !== "Enter") return;
      event.preventDefault();
      applyLocalMultiplier();
    });
  }
  function closeLocalFractionOnOutsideClick(event) {
    if (localFraction.hidden || localFraction.contains(event.target)) return;
    applyLocalMultiplier();
  }
  document.addEventListener("pointerdown", closeLocalFractionOnOutsideClick);
  let localUndoX = null;
  let localControlY = null;
  function positionLocalUndo() {
    if (localUndoX === null || localControlY === null) return;
    const matrix = svg.getScreenCTM();
    if (!matrix) return;
    const point = svg.createSVGPoint();
    point.x = localUndoX;
    point.y = localControlY;
    const screenPoint = point.matrixTransform(matrix);
    const workspaceBox = workspace.getBoundingClientRect();
    const left = `${screenPoint.x - workspaceBox.left}px`;
    const top = `${screenPoint.y - workspaceBox.top}px`;
    localUndo.style.left = left;
    localUndo.style.top = top;
    localMultiply.style.left = left;
    localMultiply.style.top = top;
    localFraction.style.left = left;
    localFraction.style.top = `calc(${top} + 2.25rem)`;
  }
  const canvasViewport = document.createElement("div");
  canvasViewport.className = "birdtracks-canvas-viewport";
  canvasViewport.appendChild(svg);
  const activateEditor = (event) => {
    activeEditorByGroup.set(groupId, editorId);
    document.dispatchEvent(new CustomEvent("birdtracks-projector-selected", {
      detail: { groupId, editorId },
    }));
  };
  svg.addEventListener("pointerdown", activateEditor, true);
  svg.addEventListener("dragover", (event) => {
    if (interactionMode !== "create"
        || !Array.from(event.dataTransfer.types).includes(
          "application/x-birdtracks-operator",
        )) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  svg.addEventListener("drop", (event) => {
    const kind = event.dataTransfer.getData("application/x-birdtracks-operator");
    if (kind !== "symmetriser" && kind !== "antisymmetriser") return;
    event.preventDefault();
    const point = eventPoint(event);
    const layer = Math.max(0, Math.round(
      (point.x - geometry.first_layer_x) / layerStep,
    ));
    const level = Math.max(0, Math.round((point.y - geometry.top_margin) / spacing));
    addNode(kind, layer, level);
  });
  svg.addEventListener("dblclick", (event) => {
    if (performance.now() < suppressCanvasDoubleClickUntil) {
      event.preventDefault();
      return;
    }
    if (interactionMode !== "create") return;
    const blocked = event.target.closest?.(
      ".birdtracks-node, .birdtracks-creator-endpoint, "
      + ".birdtracks-add-line-control, .birdtracks-line-control-hit",
    );
    if (blocked) return;
    event.preventDefault();
    const point = eventPoint(event);
    let layer = 0;
    if (nodes.length) {
      const nearest = [...nodes].sort((left, right) => {
        const leftX = xForLayer(left.layer);
        const rightX = xForLayer(right.layer);
        return Math.abs(point.x - leftX) - Math.abs(point.x - rightX);
      })[0];
      const centreX = xForLayer(nearest.layer);
      if (point.x < centreX - nodeWidth / 2) {
        layer = nearest.layer;
        insertCreatorLayer(layer);
      } else if (point.x > centreX + nodeWidth / 2) {
        layer = nearest.layer + 1;
        insertCreatorLayer(layer);
      } else {
        layer = nearest.layer;
      }
    }
    const level = Math.max(
      0,
      Math.floor((point.y - geometry.top_margin) / spacing),
    );
    addNode("symmetriser", layer, level);
  });
  workspace.append(canvasViewport, localUndo, localMultiply, localFraction);
  el.append(workspace, save);

  function setMode(mode) {
    const permittedMode = model.get("active_line") ? mode : "evaluate";
    const previousMode = interactionMode;
    interactionMode = permittedMode;
    el.dataset.mode = permittedMode;
    model.set("mode", permittedMode);
    model.save_changes();
    if (permittedMode === "evaluate" && previousMode !== "evaluate") {
      saveProjector();
    }
    updateLocalControls();
    message.textContent = permittedMode === "create" ? "Create mode" : "Evaluate mode";
    redraw();
  }

  function setZoom(value) {
    zoom = Math.max(0.5, Math.min(3, value));
    model.set("zoom", zoom);
    model.save_changes();
    redraw();
  }

  function boundaryLevelCount() {
    const levels = connections.flatMap((connection) =>
      [connection.source, connection.target]
        .filter((endpoint) => endpoint.type && endpoint.type.includes("anchor"))
        .map((endpoint) => endpoint.level + 1)
    );
    return Math.max(INITIAL_LEVELS, ...levels);
  }

  function addFullLine(remember = true) {
    if (interactionMode !== "create") return;
    if (remember) rememberEditorState();
    const level = boundaryLevelCount();
    connections.push({
      source: { type: "right-anchor", level },
      target: { type: "left-anchor", level },
      route: {},
    });
    redraw();
  }

  function ensureLine(level) {
    while (boundaryLevelCount() <= level) addFullLine(false);
  }

  function connectionAt(layer, level) {
    return connections.find((connection) =>
      endpointLayer(connection.source) > layer
      && endpointLayer(connection.target) < layer
      && routeLevel(connection, layer) === level
    );
  }

  function spliceNodeIntoLines(node) {
    node.labels.forEach((label, offset) => {
      if (connections.some((connection) =>
        (connection.target.type === "port"
          && connection.target.node === node.index
          && connection.target.label === label)
        || (connection.source.type === "port"
          && connection.source.node === node.index
          && connection.source.label === label)
      )) return;
      const level = node.level + offset;
      let connection = connectionAt(node.layer, level);
      if (!connection) {
        const available = connections
          .filter((item) =>
            endpointLayer(item.source) > node.layer
            && endpointLayer(item.target) < node.layer
          )
          .sort((left, right) =>
            Math.abs(routeLevel(left, node.layer) - level)
              - Math.abs(routeLevel(right, node.layer) - level)
          );
        connection = available[0];
      }
      if (!connection) {
        const newLevel = boundaryLevelCount();
        ensureLine(newLevel);
        connection = connectionAt(node.layer, newLevel);
      }
      if (!connection) return;
      const index = connections.indexOf(connection);
      const input = { type: "port", side: "input", node: node.index, label };
      const output = { type: "port", side: "output", node: node.index, label };
      connections.splice(index, 1,
        { source: connection.source, target: input, route: { ...connection.route } },
        { source: output, target: connection.target, route: { ...connection.route } },
      );
    });
  }

  function bypassNode(node, layer = node.layer, level = node.level) {
    node.labels.forEach((label, offset) => {
      const entering = connections.find((connection) =>
        connection.target.type === "port"
        && connection.target.node === node.index
        && connection.target.label === label
      );
      const leaving = connections.find((connection) =>
        connection.source.type === "port"
        && connection.source.node === node.index
        && connection.source.label === label
      );
      connections = connections.filter((connection) =>
        connection !== entering && connection !== leaving
      );
      if (entering && leaving) connections.push({
        source: entering.source,
        target: leaving.target,
        route: {
          ...entering.route,
          ...leaving.route,
          [String(layer)]: level + offset,
        },
      });
    });
  }

  function disconnectEndpoint(endpoint) {
    const key = endpointKey(endpoint);
    const before = connections.length;
    const previous = snapshotEditorState();
    connections = connections.filter((connection) =>
      endpointKey(connection.source) !== key && endpointKey(connection.target) !== key
    );
    if (connections.length !== before) {
      rememberEditorState(previous);
      message.textContent = "Line disconnected from operator port.";
      redraw();
    }
  }

  function reorderCreatorLayer(layer, movingItem, requestedLevel) {
    const units = layerUnits(layer);
    const movingIndex = units.findIndex((unit) =>
      unit.kind === "node"
        ? unit.node === movingItem
        : unit.connections.includes(movingItem)
    );
    if (movingIndex < 0) return;
    const [moving] = units.splice(movingIndex, 1);
    const originalCentre = moving.start + (moving.width - 1) / 2;
    const requestedCentre = requestedLevel + (moving.width - 1) / 2;
    const movingHalfSpan = (moving.width - 1) / 2;
    const movingUp = requestedCentre < originalCentre;
    const insertionProbe = movingUp
      ? requestedCentre - movingHalfSpan
      : requestedCentre + movingHalfSpan;
    const insertion = units.findIndex((unit) => {
      const centre = unit.start + (unit.width - 1) / 2;
      return movingUp ? insertionProbe <= centre : insertionProbe < centre;
    });
    units.splice(insertion < 0 ? units.length : insertion, 0, moving);
    assignLayerLevels(layer, units);
  }

  function layerUnits(layer) {
    const units = nodes
      .filter((node) => node.layer === layer)
      .map((node) => ({
        kind: "node", node, width: node.labels.length, start: node.level,
      }));
    const logicalLines = new Map();
    for (const [connectionIndex, connection] of connections.entries()) {
      if (endpointLayer(connection.source) > layer
          && endpointLayer(connection.target) < layer) {
        const key = connection.boundaryLabel === undefined
          ? `connection:${connectionIndex}`
          : `strand:${connection.boundaryLabel}`;
        const existing = logicalLines.get(key);
        if (existing) existing.connections.push(connection);
        else logicalLines.set(key, {
          kind: "line",
          key,
          connections: [connection],
          width: 1,
          start: routeLevel(connection, layer),
        });
      }
    }
    units.push(...logicalLines.values());
    units.sort((left, right) =>
      left.start - right.start
      || (left.kind === "node" ? -1 : 1)
      - (right.kind === "node" ? -1 : 1)
      || (left.kind === "node"
        ? left.node.index - right.node.index
        : left.key.localeCompare(right.key))
    );
    return units;
  }

  function assignLayerLevels(layer, units) {
    let cursor = 0;
    for (const unit of units) {
      if (unit.kind === "node") unit.node.level = cursor;
      else for (const connection of unit.connections) {
        connection.route[String(layer)] = cursor;
      }
      cursor += unit.width;
    }
  }

  function normalizeCreatorLayers() {
    const layers = new Set(nodes.map((node) => node.layer));
    for (const connection of connections) {
      for (
        let layer = endpointLayer(connection.source) - 1;
        layer > endpointLayer(connection.target);
        layer -= 1
      ) layers.add(layer);
    }
    for (const layer of [...layers].sort((left, right) => left - right)) {
      assignLayerLevels(layer, layerUnits(layer));
    }
  }

  function addNode(kind, requestedLayer = null, requestedLevel = 0) {
    if (interactionMode !== "create") return;
    rememberEditorState();
    const index = nodes.length;
    const rightmost = nodes.reduce((maximum, node) => Math.max(maximum, node.layer), -1);
    const labels = [nextLabel++, nextLabel++];
    const node = {
      index,
      kind,
      layer: requestedLayer === null ? rightmost + 1 : Math.max(0, requestedLayer),
      level: Math.max(0, requestedLevel),
      labels,
      inputOrder: [...labels],
      outputOrder: [...labels],
      initialInputOrder: [...labels],
      initialOutputOrder: [...labels],
    };
    nodes.push(node);
    spliceNodeIntoLines(node);
    reorderCreatorLayer(node.layer, node, node.level);
    compactEmptyLayers();
    message.textContent = "";
    redraw();
  }

  function insertCreatorLayer(layer) {
    for (const node of nodes) {
      if (node.layer >= layer) node.layer += 1;
    }
    for (const connection of connections) {
      const shifted = {};
      for (const [layerKey, level] of Object.entries(connection.route || {})) {
        const oldLayer = Number(layerKey);
        shifted[String(oldLayer >= layer ? oldLayer + 1 : oldLayer)] = level;
      }
      connection.route = shifted;
    }
  }

  function compactEmptyLayers() {
    const occupied = [...new Set(nodes.map((node) => node.layer))]
      .sort((left, right) => left - right);
    if (!occupied.length) return;
    const compactedLayer = new Map(
      occupied.map((layer, index) => [layer, index]),
    );
    for (const node of nodes) node.layer = compactedLayer.get(node.layer);
    for (const connection of connections) {
      connection.route = Object.fromEntries(
        Object.entries(connection.route || {})
          .filter(([layer]) => compactedLayer.has(Number(layer)))
          .map(([layer, level]) => [
            String(compactedLayer.get(Number(layer))),
            level,
          ]),
      );
    }
  }

  function collapseFreeLineLayers() {
    const operatorLayers = new Set(
      nodes
        .filter((node) => node.kind !== "permutation")
        .map((node) => node.layer),
    );
    if (!operatorLayers.size) return;
    const collapsible = nodes
      .filter((node) => node.kind === "permutation")
      .sort((left, right) => right.index - left.index);
    for (const node of collapsible) {
      const strands = node.labels.map((input) => {
        const output = node.mapping
          ? node.mapping.find(([candidate]) => candidate === input)?.[1]
          : input;
        const incoming = connections.find((connection) =>
          connection.target.type === "port"
          && connection.target.node === node.index
          && connection.target.label === input
        );
        const outgoing = connections.find((connection) =>
          connection.source.type === "port"
          && connection.source.node === node.index
          && connection.source.label === output
        );
        return { incoming, outgoing };
      });
      // A boundary-to-boundary strand still needs this node as its anchor in
      // the Python graph representation.  All other permutation strands can
      // become ordinary, independently movable free lines in this layer.
      if (strands.some(({ incoming, outgoing }) =>
        !incoming || !outgoing
        || (incoming.source.type === "right-anchor"
          && outgoing.target.type === "left-anchor")
      )) continue;
      const replacements = [];
      for (const { incoming, outgoing } of strands) {
        replacements.push({
          source: incoming.source,
          target: outgoing.target,
          route: { ...(incoming.route || {}), ...(outgoing.route || {}) },
        });
        connections = connections.filter((connection) =>
          connection !== incoming && connection !== outgoing
        );
      }
      connections.push(...replacements);
      nodes.splice(node.index, 1);
      for (const connection of connections) {
        for (const endpoint of [connection.source, connection.target]) {
          if (endpoint.type === "port" && endpoint.node > node.index) {
            endpoint.node -= 1;
          }
        }
      }
      nodes.forEach((item, index) => { item.index = index; });
    }
  }

  function levelCount() {
    if (usesCompiledDisplay()) {
      return Math.max(
        boundaryLevelCount(),
        ...nodes
          .filter((node) => node.kind !== "permutation")
          .map((node) => node.level + node.labels.length),
      );
    }
    const routedLevels = connections.flatMap((connection) =>
      Object.values(connection.route || {}).map((level) => Number(level) + 1)
    );
    return Math.max(
      boundaryLevelCount(),
      ...nodes.map((node) => node.level + node.labels.length),
      ...routedLevels,
    );
  }

  function usesPurePermutationDisplay() {
    // `displayGraph` describes the last Python-synchronised exact graph. During
    // creation `nodes` is newer, so stale pure-permutation metadata must never
    // constrain live editor bounds or hide newly inserted S/A nodes.
    return !template.creator
      && interactionMode === "evaluate"
      && displayGraph.pure_permutation
      && nodes.length > 0
      && nodes.every((node) => node.kind === "permutation");
  }

  function usesCompiledDisplay() {
    if (template.creator
        || interactionMode !== "evaluate"
        || !Array.isArray(displayGraph.strands)) {
      return false;
    }
    const columns = displayGraph.operator_columns || [];
    if (!Array.isArray(columns)
        || columns.some((column) => !Array.isArray(column) || !column.length)) {
      return false;
    }
    const planned = new Set(
      columns.flat().map((index) => Number(index)),
    );
    const live = nodes
      .filter((node) => node.kind !== "permutation")
      .map((node) => node.index);
    const endpointExists = (endpoint) => {
      if (endpoint.kind === "right_boundary") {
        return boundaryLevel("input", endpoint.label) >= 0;
      }
      if (endpoint.kind === "left_boundary") {
        return boundaryLevel("output", endpoint.label) >= 0;
      }
      const node = nodes[Number(endpoint.node)];
      if (!node || node.kind === "permutation") return false;
      const order = endpoint.kind === "operator_input"
        ? node.inputOrder : node.outputOrder;
      return order.includes(endpoint.label);
    };
    const validStrands = displayGraph.strands.every((strand) =>
      strand && endpointExists(strand.source) && endpointExists(strand.target)
    );
    return validStrands
      && live.length === planned.size
      && live.every((index) => planned.has(index));
  }

  function displayColumn(nodeIndex) {
    return (displayGraph.operator_columns || []).findIndex((column) =>
      column.includes(nodeIndex)
    );
  }

  function xForNode(node) {
    const column = usesCompiledDisplay() ? displayColumn(node.index) : -1;
    if (column < 0) return xForLayer(node.layer);
    const corridorWidths = displayGraph.corridor_widths || [];
    let x = geometry.left_boundary + (corridorWidths[0] ?? geometry.step / 2)
      + nodeWidth / 2;
    for (let index = 1; index <= column; index += 1) {
      x += nodeWidth + (corridorWidths[index] ?? geometry.step);
    }
    return x;
  }

  function bounds() {
    const compiled = usesCompiledDisplay();
    const layers = compiled
      ? Math.max(INITIAL_LAYERS, (displayGraph.operator_columns || []).length)
      : Math.max(INITIAL_LAYERS, ...nodes.map((node) => node.layer + 1));
    const rightBoundary = compiled && Number.isFinite(geometry.right_boundary)
      ? geometry.right_boundary
      : usesPurePermutationDisplay()
      && Number.isFinite(displayGraph.corridor_width)
      ? geometry.left_boundary + displayGraph.corridor_width
      : geometry.first_layer_x + (layers - 1) * layerStep + geometry.step;
    // Fixed margins make a logical level occupy the same screen y-coordinate
    // in every term; cropping must not depend on where an S/A happens to sit.
    const contentTop = yFor(0) - geometry.operator_padding;
    const contentBottom = yFor(levelCount() - 1)
      + geometry.operator_padding
      + (interactionMode === "create" ? spacing * 0.65 : 0);
    const top = contentTop - spacing / 3;
    const bottom = contentBottom + spacing / 3;
    // The coefficient/sign already lives inside `coefficient_space`. Starting
    // at zero halves the old whitespace before +/- without overlapping the
    // preceding term.
    const left = 0;
    const right = usesCompiledDisplay()
      ? rightBoundary
      : rightBoundary + geometry.step / 2;
    return {
      left,
      width: right - left,
      top,
      height: bottom - top,
      layers,
      rightBoundary,
    };
  }

  function coordinates(endpoint) {
    const box = bounds();
    if (endpoint.type === "right-anchor") {
      return { x: box.rightBoundary, y: yFor(endpoint.level) };
    }
    if (endpoint.type === "left-anchor") {
      return { x: geometry.left_boundary, y: yFor(endpoint.level) };
    }
    const node = nodes[endpoint.node];
    const order = endpoint.side === "input" ? node.inputOrder : node.outputOrder;
    const row = order.indexOf(endpoint.label);
    const centreX = xForNode(node);
    return {
      x: centreX + (endpoint.side === "input" ? nodeWidth / 2 : -nodeWidth / 2),
      y: yFor(node.level + row),
    };
  }

  function yFor(level) {
    return geometry.top_margin + level * spacing;
  }

  function endpointKey(endpoint) {
    if (endpoint.type.includes("anchor")) return `${endpoint.type}:${endpoint.level}`;
    return `${endpoint.side}:${endpoint.node}:${endpoint.label}`;
  }

  function isSource(endpoint) {
    return endpoint.type === "right-anchor" || endpoint.side === "output";
  }

  function endpointData(endpoint) {
    return encodeURIComponent(JSON.stringify(endpoint));
  }

  function endpointLayer(endpoint) {
    if (endpoint.type === "right-anchor") return bounds().layers;
    if (endpoint.type === "left-anchor") return -1;
    return nodes[endpoint.node].layer;
  }

  function routeLevel(connection, layer) {
    connection.route ||= {};
    if (connection.route[String(layer)] === undefined) {
      const start = coordinates(connection.source);
      const end = coordinates(connection.target);
      const startLayer = endpointLayer(connection.source);
      const endLayer = endpointLayer(connection.target);
      const fraction = (startLayer - layer) / (startLayer - endLayer);
      const y = start.y + (end.y - start.y) * fraction;
      connection.route[String(layer)] = Math.max(
        0, Math.min(levelCount() - 1, Math.round((y - geometry.top_margin) / spacing)),
      );
    }
    return connection.route[String(layer)];
  }

  function routePoints(connection) {
    const points = [coordinates(connection.source)];
    for (
      let layer = endpointLayer(connection.source) - 1;
      layer > endpointLayer(connection.target);
      layer -= 1
    ) {
      const x = xForLayer(layer);
      const y = yFor(routeLevel(connection, layer));
      points.push(
        { x: x + nodeWidth / 2, y },
        { x: x - nodeWidth / 2, y },
      );
    }
    points.push(coordinates(connection.target));
    return points;
  }

  function routedPath(points) {
    let path = `M ${points[0].x} ${points[0].y}`;
    for (let index = 1; index < points.length; index += 1) {
      const start = points[index - 1];
      const end = points[index];
      if (start.y === end.y) path += ` L ${end.x} ${end.y}`;
      else {
        const middle = (start.x + end.x) / 2;
        path += ` C ${middle} ${start.y}, ${middle} ${end.y}, ${end.x} ${end.y}`;
      }
    }
    return path;
  }

  function displayEndpoint(endpoint) {
    if (endpoint.kind === "right_boundary") {
      return {
        type: "right-anchor",
        level: boundaryLevel("input", endpoint.label),
      };
    }
    if (endpoint.kind === "left_boundary") {
      return {
        type: "left-anchor",
        level: boundaryLevel("output", endpoint.label),
      };
    }
    return {
      type: "port",
      side: endpoint.kind === "operator_input" ? "input" : "output",
      node: endpoint.node,
      label: endpoint.label,
    };
  }

  function drawCompiledDisplayStrands(lines, handles) {
    const strands = displayGraph.strands || [];
    const freeLevelAtColumn = (column, requested) => {
      const occupied = new Set();
      for (const nodeIndex of displayGraph.operator_columns[column] || []) {
        const operator = nodes[nodeIndex];
        if (!operator || operator.kind === "permutation") continue;
        for (let offset = 0; offset < operator.labels.length; offset += 1) {
          occupied.add(operator.level + offset);
        }
      }
      if (!occupied.has(requested)) return requested;
      const count = levelCount();
      for (let distance = 1; distance < count; distance += 1) {
        const below = requested + distance;
        if (below < count && !occupied.has(below)) return below;
        const above = requested - distance;
        if (above >= 0 && !occupied.has(above)) return above;
      }
      return requested;
    };
    for (const strand of strands) {
      const sourceEndpoint = displayEndpoint(strand.source);
      const targetEndpoint = displayEndpoint(strand.target);
      const overlapNodeBorder = (endpoint, point) => {
        if (endpoint.type !== "port") return point;
        const inward = nodeWidth * 0.025;
        return {
          ...point,
          x: point.x + (endpoint.side === "input" ? -inward : inward),
        };
      };
      // Nodes are painted after strands. Extend connected paths slightly
      // underneath their border so antialiasing cannot leave a visible gap.
      const start = overlapNodeBorder(
        sourceEndpoint, coordinates(sourceEndpoint),
      );
      const end = overlapNodeBorder(
        targetEndpoint, coordinates(targetEndpoint),
      );
      const sourceColumn = strand.source.kind === "right_boundary"
        ? (displayGraph.operator_columns || []).length
        : displayColumn(strand.source.node);
      const targetColumn = strand.target.kind === "left_boundary"
        ? -1
        : displayColumn(strand.target.node);
      const points = [start];
      for (let column = sourceColumn - 1; column > targetColumn; column -= 1) {
        const nodeIndex = displayGraph.operator_columns[column][0];
        const node = nodes[nodeIndex];
        const liveConnection = connections.find((connection) =>
          Number(connection.boundaryLabel) === Number(strand.strand_label)
          && Object.hasOwn(connection.route || {}, String(node.layer))
        );
        const assigned = liveConnection
          ? routeLevel(liveConnection, node.layer)
          : template.free_levels?.[String(node.layer)]?.[
              String(strand.strand_label)
            ];
        const fraction = (sourceColumn - column) / (sourceColumn - targetColumn);
        const requestedLevel = Math.round(assigned === undefined
          ? (start.y + (end.y - start.y) * fraction - geometry.top_margin) / spacing
          : Number(assigned));
        const level = freeLevelAtColumn(column, requestedLevel);
        const x = xForNode(node);
        const y = yFor(level);
        points.push(
          { x: x + nodeWidth / 2, y },
          { x: x - nodeWidth / 2, y },
        );
        if (liveConnection) {
          drawRouteHandle(handles, liveConnection, node.layer, {
            displayX: x,
            displayColumn: column,
            strandLabel: strand.strand_label,
          });
        }
      }
      points.push(end);
      lines.appendChild(svgElement("path", {
        d: routedPath(points),
        class: "birdtracks-line birdtracks-display-strand",
      }));
    }
  }

  function redraw() {
    const box = bounds();
    const operatorXs = nodes
      .filter((node) => node.kind !== "permutation")
      .map((node) => xForNode(node));
    const undoX = operatorXs.length
      ? (Math.min(...operatorXs) + Math.max(...operatorXs)) / 2
      : (geometry.left_boundary + box.rightBoundary) / 2;
    localUndoX = undoX;
    localControlY = (yFor(0) + yFor(levelCount() - 1)) / 2;
    requestAnimationFrame(positionLocalUndo);
    svg.setAttribute("viewBox", `${box.left} ${box.top} ${box.width} ${box.height}`);
    svg.replaceChildren();
    const lines = svgElement("g", { class: "birdtracks-lines" });
    const guides = svgElement("g", { class: "birdtracks-level-guides" });
    const nodeLayer = svgElement("g", { class: "birdtracks-nodes" });
    const handles = svgElement("g", { class: "birdtracks-port-handles" });
    const annotations = svgElement("g", { class: "birdtracks-annotations" });
    const interactions = svgElement("g", { class: "birdtracks-interactions" });
    svg.append(guides, lines, nodeLayer, handles, annotations, interactions);

    for (let level = 0; level < levelCount(); level += 1) {
      guides.appendChild(svgElement("line", {
        x1: geometry.left_boundary,
        x2: box.rightBoundary,
        y1: yFor(level),
        y2: yFor(level),
        class: "birdtracks-level-guide",
      }));
    }

    const compiledDisplay = usesCompiledDisplay();
    if (compiledDisplay) drawCompiledDisplayStrands(lines, handles);
    connections.forEach((connection, connectionIndex) => {
      if (compiledDisplay) return;
      const path = routedPath(routePoints(connection));
      const visible = svgElement("path", {
        d: path,
        class: "birdtracks-line",
      });
      const hitTarget = svgElement("path", {
        d: path,
        class: "birdtracks-line-hit",
        "data-free-connection": connectionIndex,
        "aria-label": "Connection; right-click to delete",
      });
      hitTarget.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        if (interactionMode !== "create") return;
        rememberEditorState();
        connections.splice(connectionIndex, 1);
        redraw();
      });
      lines.append(visible, hitTarget);
      for (
        let layer = endpointLayer(connection.source) - 1;
        layer > endpointLayer(connection.target);
        layer -= 1
      ) drawRouteHandle(handles, connection, layer);
    });
    if (draft) {
      const start = coordinates(draft.source);
      lines.appendChild(svgElement("path", {
        d: `M ${start.x} ${start.y} L ${draft.x} ${draft.y}`,
        class: "birdtracks-line birdtracks-draft-line",
      }));
    }

    for (let level = 0; level < levelCount(); level += 1) {
      drawEndpoint(handles, { type: "right-anchor", level });
      drawEndpoint(handles, { type: "left-anchor", level });
    }
    if (interactionMode === "create") {
      drawAddLineControl(handles, "left");
      drawAddLineControl(handles, "right");
    }
    for (const node of nodes) {
      if (!compiledDisplay || node.kind !== "permutation") {
        drawNode(nodeLayer, handles, interactions, node);
      }
    }
    if (interactionMode === "create") {
      const prefactorY = yFor(Math.max(0, levelCount() - 1) / 2);
      const prefactorTarget = svgElement("rect", {
        x: 0,
        y: prefactorY - spacing / 2,
        width: geometry.left_boundary,
        height: spacing,
        class: "birdtracks-prefactor-delete-target",
        "aria-label": "Projector prefactor; right-click to delete projector",
      });
      prefactorTarget.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        model.set(
          "term_delete_request",
          model.get("term_delete_request") + 1,
        );
        model.save_changes();
      });
      annotations.appendChild(prefactorTarget);
    }
    drawExactCoefficient(
      annotations,
      currentGraphCoefficient(),
      displayedTermSign(),
      geometry,
      geometry.left_boundary / 2,
      yFor(Math.max(0, levelCount() - 1) / 2),
    );
    // Measure the actual rendered prefactor. If it outgrows its coefficient
    // slot, keep its right edge against the diagram and enlarge the viewBox
    // by precisely the measured left overflow.
    const annotationBox = annotations.getBBox();
    const annotationRight = annotationBox.x + annotationBox.width;
    const annotationShift = Math.min(0, geometry.left_boundary - annotationRight);
    if (annotationShift) {
      annotations.setAttribute("transform", `translate(${annotationShift} 0)`);
    }
    const measuredLeft = Math.min(box.left, annotationBox.x + annotationShift);
    const measuredWidth = box.left + box.width - measuredLeft;
    svg.setAttribute(
      "viewBox", `${measuredLeft} ${box.top} ${measuredWidth} ${box.height}`,
    );
    const viewportWidth = zoom * 2.5 * measuredWidth / spacing;
    const viewportHeight = zoom * 2.5 * box.height / spacing;
    canvasViewport.style.width = `${viewportWidth}rem`;
    canvasViewport.style.height = `${viewportHeight}rem`;
    canvasViewport.style.flex = `0 0 ${viewportWidth}rem`;
    el.style.width = `${viewportWidth}rem`;
    if (Math.abs(Number(model.get("rendered_width") || 0) - viewportWidth) > 0.001) {
      model.set("rendered_width", viewportWidth);
      model.save_changes();
    }
  }

  function drawAddLineControl(layer, side) {
    const box = bounds();
    const x = side === "left"
      ? geometry.left_boundary
      : box.rightBoundary;
    const y = yFor(levelCount() - 1) + spacing * 0.65;
    const control = svgElement("g", {
      class: "birdtracks-add-line-control",
      role: "button",
      "aria-label": `Add line at ${side} boundary`,
    });
    const radius = Math.min(nodeWidth, spacing) * 0.08;
    control.append(
      svgElement("ellipse", {
        cx: x,
        cy: y,
        rx: Math.min(nodeWidth, spacing) * 0.38,
        ry: Math.min(nodeWidth, spacing) * 0.2,
        class: "birdtracks-add-line-control-hit",
      }),
      svgElement("line", { x1: x - radius, x2: x + radius, y1: y, y2: y }),
      svgElement("line", { x1: x, x2: x, y1: y - radius, y2: y + radius }),
    );
    control.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      addFullLine();
    });
    layer.appendChild(control);
  }

  function drawEndpoint(layer, endpoint) {
    const point = coordinates(endpoint);
    const group = svgElement("g", { class: "birdtracks-creator-endpoint" });
    const hitTarget = svgElement("circle", {
      cx: point.x,
      cy: point.y,
      r: geometry.handle_radius * (lineDragActive ? 3.25 : 1.4),
      fill: "transparent",
      stroke: "none",
      "pointer-events": "fill",
      class: `birdtracks-creator-port ${isSource(endpoint) ? "source" : "target"} ${
        interactionMode === "evaluate"
          && endpoint.type === "port"
          && nodes[endpoint.node].kind !== "permutation"
          ? "evaluate-order"
          : ""
      }`,
      "data-endpoint": endpointData(endpoint),
      "aria-label": endpoint.type === "port"
        ? `${endpointKey(endpoint)}; right-click to disconnect`
        : endpointKey(endpoint),
    });
    const visible = svgElement("circle", {
      cx: point.x,
      cy: point.y,
      r: geometry.handle_radius,
      class: "birdtracks-creator-port-visual",
    });
    hitTarget.addEventListener("pointerenter", () => visible.classList.add("active"));
    hitTarget.addEventListener("pointerleave", () => visible.classList.remove("active"));
    hitTarget.addEventListener("pointerdown", (event) => {
      if (interactionMode === "evaluate"
          && endpoint.type === "port"
          && nodes[endpoint.node].kind !== "permutation") {
        startPortReorder(event, endpoint);
      } else {
        startConnection(event);
      }
    });
    if (endpoint.type === "port") {
      hitTarget.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (interactionMode === "create") disconnectEndpoint(endpoint);
      });
    }
    group.append(hitTarget, visible);
    layer.appendChild(group);
  }

  function orderIsOdd(current, initial) {
    const rank = new Map(initial.map((label, index) => [label, index]));
    const values = current.map((label) => rank.get(label));
    let inversions = 0;
    for (let left = 0; left < values.length; left += 1) {
      for (let right = left + 1; right < values.length; right += 1) {
        if (values[left] > values[right]) inversions += 1;
      }
    }
    return inversions % 2 === 1;
  }

  function portParityIsOdd() {
    let odd = false;
    for (const node of nodes) {
      if (node.kind !== "antisymmetriser") continue;
      if (orderIsOdd(node.inputOrder, node.initialInputOrder)) odd = !odd;
      if (orderIsOdd(node.outputOrder, node.initialOutputOrder)) odd = !odd;
    }
    return odd;
  }

  function displayedTermSign() {
    const initiallyNegative = model.get("term_sign") === "-";
    const negative = initiallyNegative !== portParityIsOdd();
    if (negative) return "-";
    return model.get("term_leading") ? "" : "+";
  }

  function setTermNegative(negative) {
    model.set("term_sign", negative ? "-" : model.get("term_leading") ? "" : "+");
    model.set(
      "term_sign_flip_request",
      model.get("term_sign_flip_request") + 1,
    );
  }

  function currentGraphCoefficient() {
    const coefficient = {
      numerator: String(coefficientNumerator),
      denominator: String(coefficientDenominator),
    };
    if (portParityIsOdd()) {
      coefficient.numerator = String(-BigInt(coefficient.numerator));
    }
    return coefficient;
  }

  function multiplyCoefficient(numeratorValue, denominatorValue) {
    rememberEditorState();
    let multiplierTop = BigInt(numeratorValue);
    let multiplierBottom = BigInt(denominatorValue);
    const flipsSign = (multiplierTop < 0n) !== (multiplierBottom < 0n);
    if (multiplierTop < 0n) multiplierTop = -multiplierTop;
    if (multiplierBottom < 0n) multiplierBottom = -multiplierBottom;
    let top = multiplierTop;
    let bottom = multiplierBottom;
    if (flipsSign && top !== 0n) {
      setTermNegative(model.get("term_sign") !== "-");
    }
    const gcd = (left, right) => {
      left = left < 0n ? -left : left;
      while (right !== 0n) [left, right] = [right, left % right];
      return left;
    };
    const divisor = gcd(top, bottom);
    coefficientNumerator = divisor === 0n ? 0n : top / divisor;
    coefficientDenominator = divisor === 0n ? 1n : bottom / divisor;
    syncPortOrders();
    redraw();
  }

  function syncPortOrders() {
    const state = Object.fromEntries(nodes.map((node) => [String(node.index), {
      input: [...node.inputOrder],
      output: [...node.outputOrder],
    }]));
    model.set("port_orders", state);
    model.set("effective_coefficient", currentGraphCoefficient());
    model.save_changes();
  }

  function startPortReorder(event, endpoint) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const node = nodes[endpoint.node];
    const order = endpoint.side === "input" ? node.inputOrder : node.outputOrder;
    const origin = order.indexOf(endpoint.label);
    const before = snapshotEditorState();
    let changed = false;

    function move(moveEvent) {
      const point = eventPoint(moveEvent);
      const relative = (point.y - yFor(node.level)) / spacing;
      const nearest = relative < origin
        ? Math.ceil(relative - 0.5)
        : Math.floor(relative + 0.5);
      const desired = Math.max(
        0,
        Math.min(order.length - 1, nearest),
      );
      const current = order.indexOf(endpoint.label);
      if (current === desired) return;
      if (!changed) {
        rememberEditorState(before);
        changed = true;
      }
      order.splice(current, 1);
      order.splice(desired, 0, endpoint.label);
      syncPortOrders();
      redraw();
    }

    function finish() {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", finish);
      document.removeEventListener("pointercancel", finish);
      syncPortOrders();
      redraw();
    }
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", finish);
    document.addEventListener("pointercancel", finish);
  }

  function displayStrandPosition(strand, column) {
    const source = strand.source.kind === "right_boundary"
      ? (displayGraph.operator_columns || []).length
      : displayColumn(strand.source.node);
    const target = strand.target.kind === "left_boundary"
      ? -1
      : displayColumn(strand.target.node);
    return source > column && target < column;
  }

  function reorderDisplayColumn(
    column, movingKind, movingValue, originLevel, requestedLevel,
  ) {
    const nodeIndices = displayGraph.operator_columns[column] || [];
    if (!nodeIndices.length) return;
    const exactLayer = nodes[nodeIndices[0]].layer;
    const freeLabels = [...new Set(
      (displayGraph.strands || [])
        .filter((strand) => displayStrandPosition(strand, column))
        .map((strand) => Number(strand.strand_label)),
    )];
    const units = nodeIndices.map((index) => ({
      kind: "node", value: index, start: nodes[index].level,
      width: nodes[index].labels.length,
    }));
    for (const label of freeLabels) {
      const routed = connections.find((connection) =>
        Number(connection.boundaryLabel) === label
        && Object.hasOwn(connection.route || {}, String(exactLayer))
      );
      if (routed) units.push({
        kind: "free", value: label,
        start: routeLevel(routed, exactLayer), width: 1,
      });
    }
    units.sort((left, right) => left.start - right.start
      || (left.kind === "node" ? -1 : 1) - (right.kind === "node" ? -1 : 1));
    const movingIndex = units.findIndex((unit) =>
      unit.kind === movingKind && unit.value === Number(movingValue)
    );
    if (movingIndex < 0) return;
    const [moving] = units.splice(movingIndex, 1);
    const movingUp = requestedLevel < originLevel;
    const insertionProbe = movingUp
      ? requestedLevel
      : requestedLevel + moving.width - 1;
    const insertion = units.findIndex((unit) => {
      const centre = unit.start + (unit.width - 1) / 2;
      return movingUp ? insertionProbe <= centre : insertionProbe < centre;
    });
    units.splice(insertion < 0 ? units.length : insertion, 0, moving);
    let cursor = 0;
    for (const unit of units) {
      if (unit.kind === "node") nodes[unit.value].level = cursor;
      else for (const connection of connections) {
        if (Number(connection.boundaryLabel) === unit.value) {
          connection.route[String(exactLayer)] = cursor;
        }
      }
      cursor += unit.width;
    }
    // Apply the same whole-layer seatbelt used by ordinary creator rows.
    // This also canonicalizes legacy/first-row states whose logical strand
    // segments may have arrived with duplicate levels.
    normalizeCreatorLayers();
  }

  function drawRouteHandle(layerGroup, connection, layer, display = null) {
    const x = display?.displayX ?? xForLayer(layer);
    const group = svgElement("g", { class: "birdtracks-creator-endpoint" });
    const hitTarget = svgElement("circle", {
      cx: x,
      cy: yFor(routeLevel(connection, layer)),
      r: geometry.handle_radius * 2.25,
      fill: "transparent",
      stroke: "none",
      "pointer-events": "fill",
      class: "birdtracks-route-handle",
      "data-free-connection": connections.indexOf(connection),
      "data-free-layer": layer,
      "aria-label": `Move connection at layer ${layer}`,
    });
    const visible = svgElement("circle", {
      cx: x,
      cy: yFor(routeLevel(connection, layer)),
      r: geometry.handle_radius,
      class: "birdtracks-creator-port-visual",
    });
    hitTarget.addEventListener("pointerenter", () => visible.classList.add("active"));
    hitTarget.addEventListener("pointerleave", () => visible.classList.remove("active"));
    hitTarget.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const before = snapshotEditorState();
      const originLevel = routeLevel(connection, layer);
      let snappedLevel = originLevel;
      function move(moveEvent) {
        const point = eventPoint(moveEvent);
        const displacement = (point.y - yFor(originLevel)) / spacing;
        const steps = Math.abs(displacement) < 0.2
          ? 0
          : Math.sign(displacement) * Math.floor(Math.abs(displacement) + 0.8);
        snappedLevel = Math.max(
          0,
          Math.min(levelCount() - 1, originLevel + steps),
        );
        if (display?.strandLabel !== undefined) {
          for (const routed of connections) {
            if (Number(routed.boundaryLabel) === Number(display.strandLabel)) {
              routed.route[String(layer)] = snappedLevel;
            }
          }
        } else {
          connection.route[String(layer)] = snappedLevel;
        }
        redraw();
      }
      function finish() {
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", finish);
        document.removeEventListener("pointercancel", finish);
        // Reordering needs the pre-drag slot to determine direction. During
        // pointermove the route is only a visual preview.
        if (display?.displayColumn !== undefined) {
          for (const routed of connections) {
            if (Number(routed.boundaryLabel) === Number(display.strandLabel)) {
              routed.route[String(layer)] = originLevel;
            }
          }
          reorderDisplayColumn(
            display.displayColumn, "free", display.strandLabel,
            originLevel, snappedLevel,
          );
        } else {
          connection.route[String(layer)] = originLevel;
          reorderCreatorLayer(layer, connection, snappedLevel);
        }
        rememberEditorState(before);
        redraw();
      }
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", finish);
      document.addEventListener("pointercancel", finish);
    });
    group.append(hitTarget, visible);
    layerGroup.appendChild(group);
  }

  function drawNode(nodeLayer, handles, interactions, node) {
    const centreX = xForNode(node);
    const top = yFor(node.level) - geometry.operator_padding;
    const height = (node.labels.length - 1) * spacing + 2 * geometry.operator_padding;
    const group = svgElement("g", { class: "birdtracks-node", "data-node": node.index });
    if (node.kind === "permutation" && node.mapping) {
      for (const [input, output] of node.mapping) {
        const startY = yFor(node.level + node.inputOrder.indexOf(input));
        const endY = yFor(node.level + node.outputOrder.indexOf(output));
        const startX = centreX + nodeWidth / 2;
        const endX = centreX - nodeWidth / 2;
        const middleX = (startX + endX) / 2;
        group.appendChild(svgElement("path", {
          d: `M ${startX} ${startY} C ${middleX} ${startY}, ${middleX} ${endY}, ${endX} ${endY}`,
          class: "birdtracks-line birdtracks-permutation-line",
        }));
      }
    }
    group.appendChild(svgElement("rect", {
      x: centreX - nodeWidth / 2,
      y: top,
      width: nodeWidth,
      height,
      class: node.kind === "permutation"
        ? "birdtracks-permutation-node"
        : node.kind === "antisymmetriser"
        ? "birdtracks-antisymmetriser"
        : "birdtracks-symmetriser",
    }));
    group.addEventListener("pointerdown", (event) => {
      const now = performance.now();
      const isDoubleClick = lastNodePointerDown
        && lastNodePointerDown.node === node.index
        && now - lastNodePointerDown.time < 450
        && Math.hypot(
          event.clientX - lastNodePointerDown.x,
          event.clientY - lastNodePointerDown.y,
        ) < 6;
      if (isDoubleClick) {
        event.preventDefault();
        event.stopPropagation();
        lastNodePointerDown = null;
        suppressCanvasDoubleClickUntil = now + 450;
        if (model.get("active_line")
            && interactionMode === "evaluate"
            && node.kind !== "permutation") {
          saveProjector(node.index);
        } else if (interactionMode === "create" && node.kind !== "permutation") {
          rememberEditorState();
          node.kind = node.kind === "symmetriser"
            ? "antisymmetriser"
            : "symmetriser";
          message.textContent = node.kind === "symmetriser"
            ? "Operator changed to symmetriser."
            : "Operator changed to antisymmetriser.";
          redraw();
        }
        return;
      }
      lastNodePointerDown = {
        node: node.index,
        time: now,
        x: event.clientX,
        y: event.clientY,
      };
      dragNode(event, node);
    });
    group.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (interactionMode !== "create") return;
      deleteNode(node.index);
    });
    node.labels.forEach((label) => {
      drawEndpoint(handles, { type: "port", side: "input", node: node.index, label });
      drawEndpoint(handles, { type: "port", side: "output", node: node.index, label });
    });
    if (node.kind !== "permutation"
        && (interactionMode === "create" || model.get("active_line"))) {
      for (const edge of ["top", "bottom"]) {
        const lineY = edge === "top" ? top : top + height;
        const recursiveControl = interactionMode === "evaluate";
        const pointsUp = edge === "top" ? !controlDown : controlDown;
        const radius = Math.min(nodeWidth, spacing) * 0.085;
        const points = pointsUp
          ? `${centreX},${lineY - radius} ${centreX - radius},${lineY + radius} ${centreX + radius},${lineY + radius}`
          : `${centreX},${lineY + radius} ${centreX - radius},${lineY - radius} ${centreX + radius},${lineY - radius}`;
        const activate = (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (recursiveControl) {
            if (node.labels.length >= 2 && model.get("active_line")) {
              saveProjector(node.index, edge);
            }
          } else {
            resizeNode(node, edge, controlDown ? -1 : 1);
          }
        };
        const hitTarget = recursiveControl
          ? svgElement("rect", {
              x: centreX - nodeWidth / 2,
              y: lineY - spacing * 0.18,
              width: nodeWidth,
              height: spacing * 0.36,
              class: "birdtracks-recursion-control-hit",
            })
          : svgElement("circle", {
              cx: centreX,
              cy: lineY,
              r: Math.min(nodeWidth, spacing) * 0.28,
              class: "birdtracks-line-control-hit",
            });
        hitTarget.setAttribute("role", "button");
        hitTarget.setAttribute(
          "aria-label",
          recursiveControl
            ? `Recursively expand from the ${edge} line`
            : `${controlDown ? "Remove" : "Add"} ${edge} line`,
        );
        const control = recursiveControl
          ? svgElement("path", {
              d: `M ${centreX - radius * 1.35} ${lineY - radius * 1.35}
                  L ${centreX - radius * 0.95} ${lineY - radius * 0.68}
                  L ${centreX - radius * 1.45} ${lineY}
                  L ${centreX - radius} ${lineY + radius * 0.68}
                  L ${centreX - radius * 1.35} ${lineY + radius * 1.35}
                  M ${centreX + radius * 1.35} ${lineY - radius * 1.35}
                  L ${centreX + radius * 0.95} ${lineY - radius * 0.68}
                  L ${centreX + radius * 1.45} ${lineY}
                  L ${centreX + radius} ${lineY + radius * 0.68}
                  L ${centreX + radius * 1.35} ${lineY + radius * 1.35}`,
              class: "birdtracks-recursion-control",
              "aria-hidden": "true",
            })
          : svgElement("polygon", {
              points,
              class: "birdtracks-line-control",
              "aria-hidden": "true",
            });
        hitTarget.addEventListener("pointerdown", activate);
        control.addEventListener("pointerdown", activate);
        hitTarget.addEventListener("pointerenter", () => {
          control.classList.add("active");
        });
        hitTarget.addEventListener("pointerleave", () => {
          control.classList.remove("active");
        });
        if (recursiveControl) interactions.append(hitTarget, control);
        else group.append(hitTarget, control);
      }
    }
    nodeLayer.appendChild(group);
  }

  function deleteNode(index) {
    rememberEditorState();
    const node = nodes[index];
    bypassNode(node);
    nodes.splice(index, 1);
    for (const connection of connections) {
      for (const endpoint of [connection.source, connection.target]) {
        if (endpoint.type === "port" && endpoint.node > index) endpoint.node -= 1;
      }
    }
    nodes.forEach((node, nodeIndex) => { node.index = nodeIndex; });
    cleanupAfterNodeDeletion();
    compactEmptyLayers();
    normalizeCreatorLayers();
    message.textContent = "Operator deleted; its strands were reconnected.";
    redraw();
  }

  function cleanupAfterNodeDeletion() {
    const validPort = (endpoint) => endpoint.type !== "port"
      || Boolean(nodes[endpoint.node]?.labels.includes(endpoint.label));
    connections = connections.filter((connection) =>
      validPort(connection.source) && validPort(connection.target)
    );

    // Complete only an unambiguous same-level boundary pair. Remaining
    // operator ports are deliberately never reconnected by guesswork.
    const sourceKeys = new Set(connections.map((item) => endpointKey(item.source)));
    const targetKeys = new Set(connections.map((item) => endpointKey(item.target)));
    const levels = Math.max(
      boundaryLevelCount(),
      ...nodes.map((node) => node.level + node.labels.length),
    );
    for (let level = 0; level < levels; level += 1) {
      const source = { type: "right-anchor", level };
      const target = { type: "left-anchor", level };
      if (!sourceKeys.has(endpointKey(source))
          && !targetKeys.has(endpointKey(target))) {
        connections.push({ source, target, route: {} });
      }
    }
  }

  function resizeNode(node, edge, delta) {
    if (interactionMode !== "create") return;
    rememberEditorState();
    if (delta > 0) {
      const label = nextLabel++;
      if (edge === "top") {
        node.labels.unshift(label);
        node.inputOrder.unshift(label);
        node.outputOrder.unshift(label);
        node.initialInputOrder.unshift(label);
        node.initialOutputOrder.unshift(label);
        if (node.level > 0) node.level -= 1;
        else {
          for (const connection of connections) {
            for (const endpoint of [connection.source, connection.target]) {
              if (endpoint.type && endpoint.type.includes("anchor")) endpoint.level += 1;
            }
            for (const layer of Object.keys(connection.route || {})) {
              connection.route[layer] += 1;
            }
          }
          for (const other of nodes) if (other !== node) other.level += 1;
          connections.push({
            source: { type: "right-anchor", level: 0 },
            target: { type: "left-anchor", level: 0 },
            route: {},
          });
        }
      } else {
        node.labels.push(label);
        node.inputOrder.push(label);
        node.outputOrder.push(label);
        node.initialInputOrder.push(label);
        node.initialOutputOrder.push(label);
      }
      spliceNodeIntoLines(node);
    } else if (node.labels.length === 2) {
      const removedIndex = node.index;
      bypassNode(node);
      nodes.splice(removedIndex, 1);
      for (const connection of connections) {
        for (const endpoint of [connection.source, connection.target]) {
          if (endpoint.type === "port" && endpoint.node > removedIndex) {
            endpoint.node -= 1;
          }
        }
      }
      nodes.forEach((item, index) => { item.index = index; });
      compactEmptyLayers();
      message.textContent = "One-line operator replaced by a free line.";
      redraw();
      return;
    } else if (node.labels.length > 2) {
      const label = edge === "top" ? node.labels.shift() : node.labels.pop();
      node.inputOrder.splice(node.inputOrder.indexOf(label), 1);
      node.outputOrder.splice(node.outputOrder.indexOf(label), 1);
      node.initialInputOrder.splice(node.initialInputOrder.indexOf(label), 1);
      node.initialOutputOrder.splice(node.initialOutputOrder.indexOf(label), 1);
      const entering = connections.find((connection) =>
        connection.target.type === "port"
        && connection.target.node === node.index
        && connection.target.label === label
      );
      const leaving = connections.find((connection) =>
        connection.source.type === "port"
        && connection.source.node === node.index
        && connection.source.label === label
      );
      connections = connections.filter((connection) => connection !== entering && connection !== leaving);
      if (entering && leaving) connections.push({
        source: entering.source,
        target: leaving.target,
        route: { ...entering.route, ...leaving.route },
      });
      if (edge === "top") node.level += 1;
    }
    reorderCreatorLayer(node.layer, node, node.level);
    redraw();
  }

  function dragNode(event, node) {
    if (event.button !== 0) return;
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const origin = { layer: node.layer, level: node.level };
    const before = snapshotEditorState();
    const matrix = svg.getScreenCTM();
    const sx = matrix ? matrix.a : 1;
    const sy = matrix ? matrix.d : 1;
    function move(moveEvent) {
      if (Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) >= 6) {
        lastNodePointerDown = null;
      }
      if (interactionMode === "create") {
        node.layer = Math.max(
          0,
          Math.round(origin.layer + (moveEvent.clientX - startX) / sx / layerStep),
        );
      }
      node.level = Math.max(0, Math.round(origin.level + (moveEvent.clientY - startY) / sy / spacing));
      redraw();
    }
    function finish() {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", finish);
      document.removeEventListener("pointercancel", finish);
      if (node.layer === origin.layer) {
        const requestedLevel = node.level;
        // As with free lines, restore the origin before the insertion move;
        // otherwise upward and downward drags look stationary to the sorter.
        node.level = origin.level;
        const column = usesCompiledDisplay() ? displayColumn(node.index) : -1;
        if (column >= 0) {
          reorderDisplayColumn(
            column, "node", node.index, origin.level, requestedLevel,
          );
        } else {
          reorderCreatorLayer(node.layer, node, requestedLevel);
        }
      } else {
        const destinationLayer = node.layer;
        const destinationLevel = node.level;
        bypassNode(node, origin.layer, origin.level);
        node.layer = destinationLayer;
        node.level = destinationLevel;
        const oldLayerUnits = [
          ...nodes.filter((item) => item.layer === origin.layer),
          ...connections.filter((connection) =>
            endpointLayer(connection.source) > origin.layer
            && endpointLayer(connection.target) < origin.layer
          ),
        ];
        if (oldLayerUnits.length) {
          const first = oldLayerUnits[0];
          const start = first.labels
            ? first.level
            : routeLevel(first, origin.layer);
          reorderCreatorLayer(origin.layer, first, start);
        }
        spliceNodeIntoLines(node);
        reorderCreatorLayer(node.layer, node, node.level);
      }
      if (JSON.stringify(snapshotEditorState()) !== JSON.stringify(before)) {
        rememberEditorState(before);
      }
      compactEmptyLayers();
      redraw();
    }
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", finish);
    document.addEventListener("pointercancel", finish);
  }

  function eventPoint(event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const matrix = svg.getScreenCTM();
    return matrix ? point.matrixTransform(matrix.inverse()) : point;
  }

  function startConnection(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const raw = event.currentTarget.getAttribute("data-endpoint");
    const endpoint = JSON.parse(decodeURIComponent(raw));
    const attached = connections.find((item) =>
      endpointKey(item.source) === endpointKey(endpoint)
      || endpointKey(item.target) === endpointKey(endpoint)
    );
    if (attached) {
      startAttachedConnection(event, endpoint, attached);
      return;
    }
    if (interactionMode !== "create") return;
    const before = snapshotEditorState();
    const initial = eventPoint(event);
    lineDragActive = true;
    draft = { source: endpoint, x: initial.x, y: initial.y };
    redraw();
    function move(moveEvent) {
      const point = eventPoint(moveEvent);
      draft = { source: endpoint, x: point.x, y: point.y };
      redraw();
    }
    function finish(upEvent) {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", finish);
      document.removeEventListener("pointercancel", cancel);
      const candidate = document.elementFromPoint(upEvent.clientX, upEvent.clientY);
      const encoded = candidate && candidate.getAttribute("data-endpoint");
      if (encoded) {
        const other = JSON.parse(decodeURIComponent(encoded));
        const source = isSource(endpoint) ? endpoint : other;
        const target = isSource(endpoint) ? other : endpoint;
        const sourceKey = endpointKey(source);
        const targetKey = endpointKey(target);
        const sourcePoint = coordinates(source);
        const targetPoint = coordinates(target);
        if (isSource(source)
            && !isSource(target)
            && sourcePoint.x > targetPoint.x
            && !connections.some((item) => endpointKey(item.source) === sourceKey)
            && !connections.some((item) => endpointKey(item.target) === targetKey)) {
          connections.push({ source, target });
          rememberEditorState(before);
        }
      }
      lineDragActive = false;
      draft = null;
      redraw();
    }
    function cancel() {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", finish);
      document.removeEventListener("pointercancel", cancel);
      lineDragActive = false;
      draft = null;
      redraw();
    }
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", finish);
    document.addEventListener("pointercancel", cancel);
  }

  function validConnection(source, target) {
    return isSource(source)
      && !isSource(target)
      && coordinates(source).x > coordinates(target).x;
  }

  function routeBetween(source, target, levelAt) {
    const route = {};
    for (
      let layer = endpointLayer(source) - 1;
      layer > endpointLayer(target);
      layer -= 1
    ) {
      const level = levelAt(layer);
      if (level !== undefined) route[String(layer)] = level;
    }
    return route;
  }

  function startAttachedConnection(event, endpoint, attached) {
    if (interactionMode !== "create") return;
    const before = snapshotEditorState();
    const endpointWasSource = endpointKey(attached.source) === endpointKey(endpoint);
    const fixed = endpointWasSource ? attached.target : attached.source;
    connections.splice(connections.indexOf(attached), 1);
    const initial = eventPoint(event);
    lineDragActive = true;
    draft = { source: fixed, x: initial.x, y: initial.y };
    redraw();

    function move(moveEvent) {
      const point = eventPoint(moveEvent);
      draft = { source: fixed, x: point.x, y: point.y };
      redraw();
    }

    function finish(upEvent) {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", finish);
      document.removeEventListener("pointercancel", cancel);
      const candidateElement = document.elementFromPoint(upEvent.clientX, upEvent.clientY);
      const encoded = candidateElement && candidateElement.getAttribute("data-endpoint");
      const freeIndexRaw = candidateElement
        && candidateElement.getAttribute("data-free-connection");
      let connected = false;
      if (encoded) {
        const candidate = JSON.parse(decodeURIComponent(encoded));
        if (isSource(candidate) === endpointWasSource) {
          const candidateKey = endpointKey(candidate);
          const displaced = connections.find((connection) =>
            endpointKey(endpointWasSource ? connection.source : connection.target) === candidateKey
          );
          const replacement = endpointWasSource
            ? { ...attached, source: candidate }
            : { ...attached, target: candidate };
          const swapped = displaced && (endpointWasSource
            ? { ...displaced, source: endpoint }
            : { ...displaced, target: endpoint });
          if (validConnection(replacement.source, replacement.target)
              && (!swapped || validConnection(swapped.source, swapped.target))) {
            connections.push(replacement);
            if (swapped) connections.splice(connections.indexOf(displaced), 1, swapped);
            connected = true;
          }
        }
      } else if (freeIndexRaw !== null) {
        const explicitLayer = candidateElement.getAttribute("data-free-layer");
        const dropPoint = eventPoint(upEvent);
        const freeLayer = explicitLayer === null
          ? Math.max(0, Math.round(
            (dropPoint.x - geometry.first_layer_x) / layerStep,
            ))
          : Number(explicitLayer);
        const freeConnection = connections[Number(freeIndexRaw)];
        const sameLayer = endpoint.type !== "port"
          || nodes[endpoint.node].layer === freeLayer;
        const crossesLayer = freeConnection
          && endpointLayer(freeConnection.source) > freeLayer
          && endpointLayer(freeConnection.target) < freeLayer;
        if (freeConnection && sameLayer && crossesLayer) {
          const freeLevel = routeLevel(freeConnection, freeLayer);
          const portConnection = endpointWasSource
            ? {
                source: endpoint,
                target: freeConnection.target,
              }
            : {
                source: freeConnection.source,
                target: endpoint,
              };
          const movedConnection = endpointWasSource
            ? {
                source: freeConnection.source,
                target: attached.target,
              }
            : {
                source: attached.source,
                target: freeConnection.target,
              };
          portConnection.route = routeBetween(
            portConnection.source,
            portConnection.target,
            (layer) => freeConnection.route[String(layer)],
          );
          movedConnection.route = routeBetween(
            movedConnection.source,
            movedConnection.target,
            (layer) => {
              if (layer === freeLayer) return freeLevel;
              if (endpointWasSource) {
                return layer > freeLayer
                  ? freeConnection.route[String(layer)]
                  : attached.route?.[String(layer)];
              }
              return layer > freeLayer
                ? attached.route?.[String(layer)]
                : freeConnection.route[String(layer)];
            },
          );
          if (validConnection(portConnection.source, portConnection.target)
              && validConnection(movedConnection.source, movedConnection.target)) {
            connections.splice(Number(freeIndexRaw), 1, portConnection, movedConnection);
            reorderCreatorLayer(freeLayer, movedConnection, freeLevel);
            connected = true;
          }
        }
      }
      message.textContent = connected
        ? "Line reconnected."
        : "Line disconnected from endpoint.";
      if (connected) rememberEditorState(before);
      lineDragActive = false;
      draft = null;
      redraw();
    }

    function cancel() {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", finish);
      document.removeEventListener("pointercancel", cancel);
      connections.push(attached);
      lineDragActive = false;
      draft = null;
      redraw();
    }
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", finish);
    document.addEventListener("pointercancel", cancel);
  }

  function validationError() {
    if (!nodes.length) return "Add at least one symmetriser or antisymmetriser.";
    const sources = new Set(connections.map((item) => endpointKey(item.source)));
    const targets = new Set(connections.map((item) => endpointKey(item.target)));
    const expectedSources = [];
    const expectedTargets = [];
    for (let level = 0; level < levelCount(); level += 1) {
      expectedSources.push(endpointKey({ type: "right-anchor", level }));
      expectedTargets.push(endpointKey({ type: "left-anchor", level }));
    }
    for (const node of nodes) for (const label of node.labels) {
      expectedSources.push(endpointKey({ type: "port", side: "output", node: node.index, label }));
      expectedTargets.push(endpointKey({ type: "port", side: "input", node: node.index, label }));
    }
    if (sources.size !== connections.length || targets.size !== connections.length) {
      return "Illegal connection: a node or anchor has two lines entering or leaving it.";
    }
    if (connections.some((item) =>
      (item.source.type === "right-anchor" && item.target.type === "left-anchor")
      || (item.source.type === "port" && item.target.type === "port"
        && nodes[item.source.node].layer <= nodes[item.target.node].layer)
    )) return "Connections must run right-to-left through operator nodes.";
    if (expectedSources.some((key) => !sources.has(key)) || expectedTargets.some((key) => !targets.has(key))) {
      return "Every node port and every left/right anchor must have exactly one line.";
    }
    return null;
  }

  function saveProjector(expandNode = null, recursiveEdge = null) {
    // Normalize presentation first, then preserve it. Serialization needs
    // concrete identity nodes for boundary-to-boundary strands, but those
    // nodes must never leak back into the live first-row editor.
    collapseFreeLineLayers();
    compactEmptyLayers();
    normalizeCreatorLayers();
    const livePresentation = snapshotEditorState();
    // Pure boundary-to-boundary strands need invisible identity nodes because
    // Python's exact graph represents boundaries through concrete node ports.
    for (const connection of [...connections]) {
      if (connection.source.type !== "right-anchor"
          || connection.target.type !== "left-anchor") continue;
      const label = nextLabel++;
      const node = {
        index: nodes.length,
        kind: "permutation",
        layer: 0,
        level: connection.source.level,
        labels: [label],
        inputOrder: [label],
        outputOrder: [label],
        initialInputOrder: [label],
        initialOutputOrder: [label],
        mapping: [[label, label]],
      };
      nodes.push(node);
      connections = connections.filter((item) => item !== connection);
      connections.push(
        {
          source: connection.source,
          target: { type: "port", side: "input", node: node.index, label },
          route: { ...(connection.route || {}) },
        },
        {
          source: { type: "port", side: "output", node: node.index, label },
          target: connection.target,
          route: { ...(connection.route || {}) },
        },
      );
    }
    collapseFreeLineLayers();
    compactEmptyLayers();
    normalizeCreatorLayers();
    const error = validationError();
    if (error) {
      message.textContent = error;
      window.alert(error);
      return;
    }
    const ordered = [...nodes].sort((a, b) => a.layer - b.layer || a.level - b.level || a.index - b.index);
    const indexMap = new Map(ordered.map((node, index) => [node.index, index]));
    const boundaryLabels = Array.from({ length: levelCount() }, (_, index) => index + 1);
    const outgoing = new Map(connections.map((connection) => [
      endpointKey(connection.source), connection,
    ]));
    const inputStrandLabel = new Map();
    const outputStrandLabel = new Map();
    const connectionStrandLabel = new Map();
    for (let level = 0; level < levelCount(); level += 1) {
      const label = level + 1;
      let currentConnection = outgoing.get(endpointKey({
        type: "right-anchor", level,
      }));
      while (currentConnection) {
        connectionStrandLabel.set(currentConnection, label);
        const current = currentConnection.target;
        if (!current || current.type !== "port") break;
        inputStrandLabel.set(`${current.node}:${current.label}`, label);
        const currentNode = nodes[current.node];
        const outputLabel = currentNode.kind === "permutation"
          ? currentNode.mapping.find(([input]) => input === current.label)?.[1]
          : current.label;
        outputStrandLabel.set(`${current.node}:${outputLabel}`, label);
        currentConnection = outgoing.get(endpointKey({
          type: "port", side: "output", node: current.node, label: outputLabel,
        }));
      }
    }
    const savedInputLabel = (node, label) =>
      inputStrandLabel.get(`${node}:${label}`);
    const savedOutputLabel = (node, label) =>
      outputStrandLabel.get(`${node}:${label}`);
    const graphNodes = ordered.map((node, index) => ({
      index,
      layer: node.layer,
      kind: node.kind,
      labels: node.labels.map((label) => savedInputLabel(node.index, label)),
      input_labels: node.inputOrder.map((label) =>
        savedInputLabel(node.index, label)),
      output_labels: node.outputOrder.map((label) =>
        savedOutputLabel(node.index, label)),
      mapping: node.mapping
        ? node.mapping.map(([input, output]) => [
          savedInputLabel(node.index, input),
          savedOutputLabel(node.index, output),
        ])
        : null,
    }));
    const remapPort = (endpoint, side) => ({
      node: indexMap.get(endpoint.node),
      label: side === "input"
        ? savedInputLabel(endpoint.node, endpoint.label)
        : savedOutputLabel(endpoint.node, endpoint.label),
    });
    const internal = connections.filter((item) =>
      item.source.type === "port" && item.target.type === "port"
    );
    const externalInputs = connections
      .filter((item) => item.source.type === "right-anchor")
      .map((item) => ({
        boundary_label: item.source.level + 1,
        port: remapPort(item.target, "input"),
      }));
    const externalOutputs = connections
      .filter((item) => item.target.type === "left-anchor")
      .map((item) => ({
        boundary_label: item.target.level + 1,
        port: remapPort(item.source, "output"),
      }));
    const savedFreeLevels = {};
    const savedLayerCount = Math.max(
      1, ...nodes.map((node) => node.layer + 1),
    );
    for (let layer = 0; layer < savedLayerCount; layer += 1) {
      const assignments = {};
      for (const connection of connections) {
        if (endpointLayer(connection.source) <= layer
            || endpointLayer(connection.target) >= layer) continue;
        const label = connectionStrandLabel.get(connection);
        if (label !== undefined) {
          assignments[String(label)] = routeLevel(connection, layer);
        }
      }
      savedFreeLevels[String(layer)] = assignments;
    }
    const effectiveCoefficient = currentGraphCoefficient();
    const savedGraph = {
      ...template,
      creator: false,
      created: true,
      nodes: graphNodes,
      connections: internal.map((item) => ({
        source: remapPort(item.source, "output"),
        target: remapPort(item.target, "input"),
      })),
      external_inputs: externalInputs,
      external_outputs: externalOutputs,
      boundary_labels: boundaryLabels,
      layer_count: Math.max(...ordered.map((node) => node.layer)) + 1,
      coefficient: effectiveCoefficient,
      base_coefficient: {
        numerator: String(coefficientNumerator),
        denominator: String(coefficientDenominator),
      },
      free_levels: savedFreeLevels,
    };
    // Display strands are derived from exact topology. Never persist the
    // template's potentially stale routing cache after editing the graph.
    delete savedGraph.display;
    const positions = Object.fromEntries(ordered.map((node, index) => [String(index), {
      x: geometry.first_layer_x + node.layer * layerStep,
      y: yFor(node.level + (node.labels.length - 1) / 2),
    }]));
    const portOrders = Object.fromEntries(graphNodes.map((node) => [String(node.index), {
      input: [...node.input_labels], output: [...node.output_labels],
    }]));
    const boundaryOrders = { input: boundaryLabels, output: boundaryLabels };
    const revision = model.get("save_request") + 1;
    model.set("graph", savedGraph);
    model.set("positions", positions);
    model.set("port_orders", portOrders);
    model.set("free_levels", savedFreeLevels);
    model.set("boundary_orders", boundaryOrders);
    model.set("effective_coefficient", effectiveCoefficient);
    model.set("save_request", revision);
    model.set("save_snapshot", {
      revision, graph: savedGraph, positions, port_orders: portOrders,
      free_levels: savedFreeLevels, boundary_orders: boundaryOrders,
      effective_coefficient: effectiveCoefficient,
    });
    if (expandNode !== null) {
      model.set("expand_node_request", {
        node: indexMap.get(expandNode),
        ...(recursiveEdge === null ? {} : { recursive_edge: recursiveEdge }),
        revision: Date.now(),
      });
    }
    model.save_changes();
    nodes = livePresentation.nodes;
    connections = livePresentation.connections;
    nextLabel = livePresentation.nextLabel;
    message.textContent = expandNode === null ? "Projector saved." : "Operator expanded.";
  }

  function updateModifier(event) {
    if (controlDown === event.ctrlKey) return;
    controlDown = event.ctrlKey;
    updateLocalControls();
  }
  function updateLocalControls() {
    localUndo.classList.toggle("visible", controlDown && interactionMode === "evaluate");
    localMultiply.classList.toggle("visible", controlDown && interactionMode === "create");
  }
  function clearModifier() {
    if (!controlDown) return;
    controlDown = false;
    localUndo.classList.remove("visible");
    localMultiply.classList.remove("visible");
  }
  function applySharedTool(event) {
    if (event.detail.groupId !== groupId) return;
    const action = event.detail.action;
    if (action === "create") setMode("create");
    else if (action === "evaluate") setMode("evaluate");
    else if (action === "zoom-in") setZoom(zoom * 1.2);
    else if (action === "zoom-out") setZoom(zoom / 1.2);
    else if (activeEditorByGroup.get(groupId) === editorId) {
      if (model.get("active_line") && action === "add-symmetriser") {
        addNode("symmetriser");
      } else if (model.get("active_line") && action === "add-antisymmetriser") {
        addNode("antisymmetriser");
      } else if (model.get("active_line") && action === "multiply"
          && event.detail.editorId === editorId) {
        multiplyCoefficient(event.detail.numerator, event.detail.denominator);
      }
    }
  }
  document.addEventListener("keydown", updateModifier);
  document.addEventListener("keyup", updateModifier);
  window.addEventListener("blur", clearModifier);
  document.addEventListener("birdtracks-projector-tool", applySharedTool);
  const saveFromPython = () => saveProjector();
  const localUndoFromPython = () => undoEditorOperation();
  const redrawTermSign = () => redraw();
  const redrawActiveLine = () => {
    if (!model.get("active_line")) interactionMode = "evaluate";
    redraw();
  };
  model.on("change:save_command", saveFromPython);
  model.on("change:local_undo_command", localUndoFromPython);
  model.on("change:term_sign change:term_leading", redrawTermSign);
  model.on("change:active_line", redrawActiveLine);
  const localUndoResizeObserver = typeof ResizeObserver === "undefined"
    ? null
    : new ResizeObserver(positionLocalUndo);
  localUndoResizeObserver?.observe(canvasViewport);
  collapseFreeLineLayers();
  compactEmptyLayers();
  normalizeCreatorLayers();
  setMode(widgetMode);
  setZoom(1);
  return () => {
    document.removeEventListener("keydown", updateModifier);
    document.removeEventListener("keyup", updateModifier);
    window.removeEventListener("blur", clearModifier);
    document.removeEventListener("birdtracks-projector-tool", applySharedTool);
    document.removeEventListener("pointerdown", closeLocalFractionOnOutsideClick);
    model.off("change:save_command", saveFromPython);
    model.off("change:local_undo_command", localUndoFromPython);
    model.off("change:term_sign change:term_leading", redrawTermSign);
    model.off("change:active_line", redrawActiveLine);
    model.off("change:group_id", updateGroupId);
    localUndoResizeObserver?.disconnect();
    if (activeEditorByGroup.get(groupId) === editorId) {
      activeEditorByGroup.delete(groupId);
    }
  };
}

function renderConfigured({ model, el }) {
  const mode = model.get("mode") || "evaluate";
  el.classList.add("birdtracks-projector-widget", `birdtracks-projector-${mode}`);
  const graph = model.get("graph");
  const LINE_SPACING = graph.geometry.level_spacing;
  const OPERATOR_PADDING = graph.geometry.operator_padding;
  const TOP_LINE_LEVEL = graph.geometry.top_line_level;
  const NODE_WIDTH = graph.geometry.node_width;
  const STEP = graph.geometry.step;
  const LAYER_STEP = graph.geometry.layer_step;
  const FIRST_LAYER_X = graph.geometry.first_layer_x;
  const LEFT_BOUNDARY = graph.geometry.left_boundary;
  const RIGHT_BOUNDARY = graph.geometry.right_boundary;
  const viewWidth = RIGHT_BOUNDARY + STEP / 2;
  const viewHeight = 2 * graph.geometry.top_margin
    + LINE_SPACING * Math.max(1, graph.boundary_labels.length - 1);
  el.style.setProperty("--birdtracks-background", graph.geometry.background_color);
  el.style.setProperty("--birdtracks-border", graph.geometry.border_color);
  el.style.setProperty("--birdtracks-line", graph.geometry.line_color);
  el.style.setProperty("--birdtracks-symmetriser", graph.geometry.symmetriser_color);
  el.style.setProperty("--birdtracks-antisymmetriser", graph.geometry.antisymmetriser_color);
  el.style.setProperty("--birdtracks-port-handle", graph.geometry.port_handle_color);
  el.style.setProperty("--birdtracks-free-handle", graph.geometry.free_line_handle_color);
  el.style.setProperty("--birdtracks-handle-line-width", graph.geometry.handle_line_width);
  el.style.setProperty("--birdtracks-line-width", graph.geometry.line_width);
  el.style.setProperty("--birdtracks-operator-line-width", graph.geometry.operator_line_width);
  el.style.setProperty("--birdtracks-fraction-line-width", graph.geometry.fraction_line_width);
  const svg = svgElement("svg", {
    viewBox: `0 0 ${viewWidth} ${viewHeight}`,
    role: "img",
    "aria-label": "Interactive birdtrack projector diagram",
  });
  enableTermReordering({ model, el, svg });
  const lineLayer = svgElement("g", { class: "birdtracks-lines" });
  const nodeLayer = svgElement("g", { class: "birdtracks-nodes" });
  const handleLayer = svgElement("g", { class: "birdtracks-port-handles" });
  const annotationLayer = svgElement("g", { class: "birdtracks-annotations" });
  svg.append(lineLayer, nodeLayer, handleLayer, annotationLayer);
  el.appendChild(svg);
  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "birdtracks-save-button";
  saveButton.textContent = mode === "evaluate" ? "Save Step" : "Save Projector";
  saveButton.addEventListener("click", () => {
    const revision = model.get("save_request") + 1;
    // Send one authoritative snapshot. This avoids saving a mixture of stale
    // Python traits when the button is clicked immediately after a drag.
    model.set("positions", structuredClone(positions));
    model.set("port_orders", structuredClone(portOrders));
    model.set("free_levels", structuredClone(freeLevels));
    model.set("boundary_orders", structuredClone(boundaryOrders));
    const coefficient = effectiveCoefficient();
    model.set("effective_coefficient", coefficient);
    model.set("save_request", revision);
    model.set("save_snapshot", {
      revision,
      positions: structuredClone(positions),
      port_orders: structuredClone(portOrders),
      free_levels: structuredClone(freeLevels),
      boundary_orders: structuredClone(boundaryOrders),
      effective_coefficient: coefficient,
    });
    model.save_changes();
    saveButton.textContent = "Saving…";
  });
  function updateSaveStatus() {
    if (model.get("saved_revision") === model.get("save_request")) {
      saveButton.textContent = mode === "evaluate" ? "Step saved" : "Projector saved";
    }
  }
  model.on("change:saved_revision", updateSaveStatus);
  el.appendChild(saveButton);

  let positions = structuredClone(model.get("positions"));
  let portOrders = structuredClone(model.get("port_orders"));
  let freeLevels = structuredClone(model.get("free_levels"));
  let boundaryOrders = structuredClone(model.get("boundary_orders"));
  let dragOverride = null;
  let freeDragOverride = null;
  let boundaryDragOverride = null;
  const nodes = new Map(graph.nodes.map((node) => [node.index, node]));

  function drawCoefficient(coefficient) {
    annotationLayer.replaceChildren();
    const numerator = BigInt(coefficient.numerator);
    const denominator = BigInt(coefficient.denominator);
    const middleLevel = TOP_LINE_LEVEL
      + Math.max(0, graph.boundary_labels.length - 1) * LINE_SPACING / 2;
    const x = LEFT_BOUNDARY / 2;
    const fontSize = 0.75 * LINE_SPACING;
    if (mode === "create") {
      const hitTarget = svgElement("rect", {
        x: 0,
        y: middleLevel - LINE_SPACING / 2,
        width: LEFT_BOUNDARY,
        height: LINE_SPACING,
        class: "birdtracks-prefactor-delete-target",
      });
      hitTarget.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        model.set(
          "term_delete_request",
          model.get("term_delete_request") + 1,
        );
        model.save_changes();
      });
      annotationLayer.appendChild(hitTarget);
    }
    const termSign = model.get("term_sign") || "";
    if (termSign) {
      const signX = numerator === 1n && denominator === 1n
        ? x : x - fontSize * 0.9;
      const radius = fontSize * 0.42;
      annotationLayer.appendChild(svgElement("line", {
        x1: signX - radius,
        x2: signX + radius,
        y1: middleLevel,
        y2: middleLevel,
        class: "birdtracks-term-sign",
      }));
      if (termSign === "+") {
        annotationLayer.appendChild(svgElement("line", {
          x1: signX,
          x2: signX,
          y1: middleLevel - radius,
          y2: middleLevel + radius,
          class: "birdtracks-term-sign",
        }));
      }
    }
    if (numerator === 1n && denominator === 1n) return;
    function drawMinus(signX, signY) {
      annotationLayer.appendChild(svgElement("line", {
        x1: signX - fontSize * 0.25,
        x2: signX + fontSize * 0.25,
        y1: signY,
        y2: signY,
        class: "birdtracks-coefficient-minus",
      }));
    }
    if (denominator === 1n) {
      const negative = numerator < 0n;
      const magnitude = negative ? -numerator : numerator;
      if (negative) drawMinus(x - (magnitude === 1n ? 0 : fontSize * 0.35), middleLevel);
      if (magnitude === 1n && negative) return;
      const text = svgElement("text", {
        x: negative ? x + fontSize * 0.2 : x,
        y: middleLevel,
        class: "birdtracks-coefficient",
        "font-size": fontSize,
        "text-anchor": "middle",
        "dominant-baseline": "middle",
      });
      text.textContent = String(magnitude);
      annotationLayer.appendChild(text);
      return;
    }

    const magnitude = numerator < 0n ? -numerator : numerator;
    const fractionFontSize = 0.75 * LINE_SPACING;
    const digitCount = Math.max(String(magnitude).length, String(denominator).length);
    const barWidth = Math.max(
      graph.geometry.fraction_bar_width,
      digitCount * fractionFontSize * 0.6,
    );
    if (numerator < 0n) {
      drawMinus(x - barWidth / 2 - fractionFontSize * 0.4, middleLevel);
    }
    const bar = svgElement("line", {
      x1: x - barWidth / 2,
      x2: x + barWidth / 2,
      y1: middleLevel,
      y2: middleLevel,
      class: "birdtracks-fraction-bar",
      "stroke-width": graph.geometry.line_width,
    });
    const top = svgElement("text", {
      x,
      y: middleLevel - graph.geometry.fraction_height / 2,
      class: "birdtracks-fraction-number",
      "font-size": fractionFontSize,
      "text-anchor": "middle",
      "dominant-baseline": "middle",
    });
    top.textContent = String(magnitude);
    const bottom = svgElement("text", {
      x,
      y: middleLevel + graph.geometry.fraction_height / 2,
      class: "birdtracks-fraction-number",
      "font-size": fractionFontSize,
      "text-anchor": "middle",
      "dominant-baseline": "middle",
    });
    bottom.textContent = String(denominator);
    annotationLayer.append(bar, top, bottom);
  }

  function nodeHeight(node) {
    return Math.max(0, node.labels.length - 1) * LINE_SPACING
      + 2 * OPERATOR_PADDING;
  }

  function portPoint(port, side) {
    const node = nodes.get(port.node);
    const position = positions[String(port.node)];
    const labels = portOrders[String(node.index)][side];
    const labelIndex = labels.indexOf(port.label);
    const overridden = dragOverride
      && dragOverride.node === port.node
      && dragOverride.side === side
      && dragOverride.label === port.label;
    return {
      x: position.x + (side === "input" ? NODE_WIDTH / 2 : -NODE_WIDTH / 2),
      y: overridden
        ? dragOverride.y
        : position.y + (labelIndex - (labels.length - 1) / 2) * LINE_SPACING,
    };
  }

  function curvedPath(start, end) {
    const bend = Math.max(STEP / 2, Math.abs(start.x - end.x) * 0.45);
    return `M ${start.x} ${start.y} C ${start.x - bend} ${start.y}, ${end.x + bend} ${end.y}, ${end.x} ${end.y}`;
  }

  function routedPath(points) {
    let path = `M ${points[0].x} ${points[0].y}`;
    for (let index = 1; index < points.length; index += 1) {
      const start = points[index - 1];
      const end = points[index];
      if (start.y === end.y) {
        path += ` L ${end.x} ${end.y}`;
        continue;
      }
      const bend = Math.max(STEP / 2, Math.abs(start.x - end.x) * 0.45);
      path += ` C ${start.x - bend} ${start.y}, ${end.x + bend} ${end.y}, ${end.x} ${end.y}`;
    }
    return path;
  }

  function layerPoint(layer, boundaryLabel) {
    const overridden = freeDragOverride
      && freeDragOverride.layer === layer
      && freeDragOverride.label === boundaryLabel;
    const level = freeLevels[String(layer)][String(boundaryLabel)];
    return {
      x: FIRST_LAYER_X + LAYER_STEP * layer,
      y: overridden
        ? freeDragOverride.y
        : TOP_LINE_LEVEL + level * LINE_SPACING,
    };
  }

  function intermediatePoints(fromLayer, toLayer, boundaryLabel) {
    const points = [];
    for (let layer = fromLayer - 1; layer > toLayer; layer -= 1) {
      const point = layerPoint(layer, boundaryLabel);
      // A strand which is free in this layer stays level across the entire
      // operator column; any vertical transition happens in the step gap.
      points.push(
        { x: point.x + NODE_WIDTH / 2, y: point.y },
        { x: point.x - NODE_WIDTH / 2, y: point.y },
      );
    }
    return points;
  }

  function boundaryPoint(label, side) {
    const overridden = boundaryDragOverride
      && boundaryDragOverride.side === side
      && boundaryDragOverride.label === label;
    return {
      x: side === "input" ? RIGHT_BOUNDARY : LEFT_BOUNDARY,
      y: overridden
        ? boundaryDragOverride.y
        : TOP_LINE_LEVEL + boundaryOrders[side].indexOf(label) * LINE_SPACING,
    };
  }

  function drawLines() {
    lineLayer.replaceChildren();
    for (const node of graph.nodes) {
      if (node.kind !== "permutation") continue;
      for (const [inputLabel, outputLabel] of node.mapping) {
        lineLayer.appendChild(svgElement("path", {
          d: curvedPath(
            portPoint({ node: node.index, label: inputLabel }, "input"),
            portPoint({ node: node.index, label: outputLabel }, "output"),
          ),
          class: "birdtracks-line birdtracks-permutation-line",
        }));
      }
    }
    for (const connection of graph.connections) {
      const start = portPoint(connection.source, "output");
      const end = portPoint(connection.target, "input");
      const sourceLayer = nodes.get(connection.source.node).layer;
      const targetLayer = nodes.get(connection.target.node).layer;
      const points = [
        start,
        ...intermediatePoints(
          sourceLayer,
          targetLayer,
          connection.boundary_label,
        ),
        end,
      ];
      lineLayer.appendChild(svgElement("path", {
        d: routedPath(points),
        class: "birdtracks-line",
      }));
    }
    for (const boundary of graph.external_inputs) {
      const end = portPoint(boundary.port, "input");
      const start = boundaryPoint(boundary.boundary_label, "input");
      const targetLayer = nodes.get(boundary.port.node).layer;
      const points = [
        start,
        ...intermediatePoints(
          graph.layer_count,
          targetLayer,
          boundary.boundary_label,
        ),
        end,
      ];
      lineLayer.appendChild(svgElement("path", {
        d: routedPath(points),
        class: "birdtracks-line",
      }));
    }
    for (const boundary of graph.external_outputs) {
      const start = portPoint(boundary.port, "output");
      const end = boundaryPoint(boundary.boundary_label, "output");
      const sourceLayer = nodes.get(boundary.port.node).layer;
      const points = [
        start,
        ...intermediatePoints(
          sourceLayer,
          -1,
          boundary.boundary_label,
        ),
        end,
      ];
      lineLayer.appendChild(svgElement("path", {
        d: routedPath(points),
        class: "birdtracks-line",
      }));
    }
  }

  function isOdd(order, canonical) {
    const rank = new Map(canonical.map((label, index) => [label, index]));
    const values = order.map((label) => rank.get(label));
    let inversions = 0;
    for (let left = 0; left < values.length; left += 1) {
      for (let right = left + 1; right < values.length; right += 1) {
        if (values[left] > values[right]) inversions += 1;
      }
    }
    return inversions % 2 === 1;
  }

  function effectiveCoefficient() {
    let sign = 1n;
    for (const node of graph.nodes) {
      if (node.kind !== "antisymmetriser") continue;
      if (isOdd(portOrders[String(node.index)].input, node.input_labels)) sign = -sign;
      if (isOdd(portOrders[String(node.index)].output, node.output_labels)) sign = -sign;
    }
    return {
      numerator: String(BigInt(graph.base_coefficient.numerator) * sign),
      denominator: graph.base_coefficient.denominator,
    };
  }

  function savePortState() {
    const coefficient = effectiveCoefficient();
    model.set("port_orders", structuredClone(portOrders));
    model.set("effective_coefficient", coefficient);
    model.save_changes();
    drawCoefficient(coefficient);
  }

  function saveFreeLevelState() {
    model.set("free_levels", structuredClone(freeLevels));
    model.save_changes();
  }

  function saveBoundaryState() {
    model.set("boundary_orders", structuredClone(boundaryOrders));
    model.save_changes();
  }

  function updateNode(group, node) {
    const position = positions[String(node.index)];
    group.setAttribute("transform", `translate(${position.x} ${position.y})`);
  }

  function reorderLayer(layer, movingKey, requestedY) {
    const units = [];
    for (const node of graph.nodes.filter((item) => item.layer === layer)) {
      const width = Math.max(1, node.labels.length);
      units.push({
        key: `node:${node.index}`,
        kind: "node",
        node,
        width,
        start: (positions[String(node.index)].y - TOP_LINE_LEVEL) / LINE_SPACING
          - (width - 1) / 2,
      });
    }
    for (const [labelKey, level] of Object.entries(freeLevels[String(layer)] || {})) {
      units.push({
        key: `free:${labelKey}`,
        kind: "free",
        labelKey,
        width: 1,
        start: Number(level),
      });
    }
    units.sort((left, right) => left.start - right.start || left.key.localeCompare(right.key));
    const movingIndex = units.findIndex((unit) => unit.key === movingKey);
    if (movingIndex < 0) return;
    const [moving] = units.splice(movingIndex, 1);
    const requestedLevel = (requestedY - TOP_LINE_LEVEL) / LINE_SPACING;
    const originalCentre = moving.start + (moving.width - 1) / 2;
    const movingHalfSpan = (moving.width - 1) / 2;
    const movingUp = requestedLevel < originalCentre;
    const insertionProbe = movingUp
      ? requestedLevel - movingHalfSpan
      : requestedLevel + movingHalfSpan;
    const insertion = units.findIndex((unit) => {
      const centre = unit.start + (unit.width - 1) / 2;
      return movingUp ? insertionProbe <= centre : insertionProbe < centre;
    });
    units.splice(insertion < 0 ? units.length : insertion, 0, moving);
    let cursor = 0;
    for (const unit of units) {
      if (unit.kind === "node") {
        positions[String(unit.node.index)] = {
          x: FIRST_LAYER_X + LAYER_STEP * layer,
          y: TOP_LINE_LEVEL + (cursor + (unit.width - 1) / 2) * LINE_SPACING,
        };
      } else {
        freeLevels[String(layer)][unit.labelKey] = cursor;
      }
      cursor += unit.width;
    }
  }

  function normalizeConfiguredLayers() {
    const layers = new Set([
      ...graph.nodes.map((node) => node.layer),
      ...Object.keys(freeLevels).map(Number),
    ]);
    for (const layer of layers) {
      const units = [];
      for (const node of graph.nodes.filter((item) => item.layer === layer)) {
        const width = Math.max(1, node.labels.length);
        units.push({
          kind: "node", node, width,
          start: (positions[String(node.index)].y - TOP_LINE_LEVEL) / LINE_SPACING
            - (width - 1) / 2,
          key: `node:${node.index}`,
        });
      }
      for (const [labelKey, level] of Object.entries(freeLevels[String(layer)] || {})) {
        units.push({
          kind: "free", labelKey, width: 1, start: Number(level),
          key: `free:${labelKey}`,
        });
      }
      units.sort((left, right) => left.start - right.start || left.key.localeCompare(right.key));
      let cursor = 0;
      for (const unit of units) {
        if (unit.kind === "node") {
          positions[String(unit.node.index)] = {
            x: FIRST_LAYER_X + LAYER_STEP * layer,
            y: TOP_LINE_LEVEL + (cursor + (unit.width - 1) / 2) * LINE_SPACING,
          };
        } else {
          freeLevels[String(layer)][unit.labelKey] = cursor;
        }
        cursor += unit.width;
      }
    }
  }

  normalizeConfiguredLayers();

  const nodesByPaintOrder = [...graph.nodes].sort((left, right) =>
    right.labels.length - left.labels.length || left.index - right.index
  );
  for (const node of nodesByPaintOrder) {
    const group = svgElement("g", {
      class: "birdtracks-node",
      "data-node": node.index,
    });
    const height = nodeHeight(node);
    group.appendChild(svgElement("rect", {
      x: -NODE_WIDTH / 2,
      y: -height / 2,
      width: NODE_WIDTH,
      height,
      class: node.kind === "permutation"
        ? "birdtracks-permutation-node"
        : node.kind === "antisymmetriser"
        ? "birdtracks-antisymmetriser"
        : "birdtracks-symmetriser",
    }));
    updateNode(group, node);
    nodeLayer.appendChild(group);

    for (const side of ["input", "output"]) {
      for (const label of node.labels) {
        const handle = svgElement("circle", {
          r: graph.geometry.handle_radius,
          class: "birdtracks-port-handle",
          "aria-label": `${side} port ${label} on node ${node.index}`,
        });
        handleLayer.appendChild(handle);

        function updateHandle() {
          const point = portPoint({ node: node.index, label }, side);
          handle.setAttribute("cx", point.x);
          handle.setAttribute("cy", point.y);
        }
        updateHandle();

        handle.addEventListener("pointerdown", (event) => {
          event.preventDefault();
          event.stopPropagation();
          handle.setPointerCapture(event.pointerId);
          const matrix = svg.getScreenCTM();
          const scaleY = matrix ? matrix.d : 1;
          const startClientY = event.clientY;
          const startY = portPoint({ node: node.index, label }, side).y;

          function move(moveEvent) {
            const y = startY + (moveEvent.clientY - startClientY) / scaleY;
            dragOverride = { node: node.index, side, label, y };
            const order = portOrders[String(node.index)][side];
            const relative = (y - positions[String(node.index)].y) / LINE_SPACING
              + (order.length - 1) / 2;
            const desired = Math.max(0, Math.min(order.length - 1, Math.round(relative)));
            const current = order.indexOf(label);
            if (desired !== current) {
              order.splice(current, 1);
              order.splice(desired, 0, label);
              savePortState();
            }
            updateAllHandles();
            drawLines();
          }

          function finish() {
            handle.removeEventListener("pointermove", move);
            handle.removeEventListener("pointerup", finish);
            handle.removeEventListener("pointercancel", finish);
            dragOverride = null;
            updateAllHandles();
            drawLines();
            savePortState();
          }

          handle.addEventListener("pointermove", move);
          handle.addEventListener("pointerup", finish);
          handle.addEventListener("pointercancel", finish);
        });

        handle._birdtracksUpdate = updateHandle;
      }
    }

    group.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      group.setPointerCapture(event.pointerId);
      const startY = event.clientY;
      const origin = { ...positions[String(node.index)] };
      const matrix = svg.getScreenCTM();
      const scaleY = matrix ? matrix.d : 1;

      function move(moveEvent) {
        positions[String(node.index)] = {
          x: FIRST_LAYER_X + LAYER_STEP * node.layer,
          y: origin.y + (moveEvent.clientY - startY) / scaleY,
        };
        updateNode(group, node);
        updateAllHandles();
        drawLines();
      }

      function finish() {
        group.removeEventListener("pointermove", move);
        group.removeEventListener("pointerup", finish);
        group.removeEventListener("pointercancel", finish);
        const requestedY = positions[String(node.index)].y;
        positions[String(node.index)] = origin;
        reorderLayer(node.layer, `node:${node.index}`, requestedY);
        for (const child of nodeLayer.children) {
          const childNode = nodes.get(Number(child.getAttribute("data-node")));
          if (childNode) updateNode(child, childNode);
        }
        updateAllHandles();
        drawLines();
        model.set("positions", structuredClone(positions));
        model.set("free_levels", structuredClone(freeLevels));
        model.save_changes();
      }

      group.addEventListener("pointermove", move);
      group.addEventListener("pointerup", finish);
      group.addEventListener("pointercancel", finish);
    });
    if (mode === "evaluate" && node.kind !== "permutation") {
      group.addEventListener("dblclick", (event) => {
        event.preventDefault();
        event.stopPropagation();
        model.set("expand_node_request", {
          node: node.index,
          revision: Date.now(),
        });
        model.save_changes();
      });
    }
  }

  for (const [layerKey, assignments] of Object.entries(freeLevels)) {
    const layer = Number(layerKey);
    for (const labelKey of Object.keys(assignments)) {
      const label = Number(labelKey);
      for (const side of ["input", "output"]) {
        const handle = svgElement("circle", {
          r: graph.geometry.handle_radius,
          class: "birdtracks-free-line-handle",
          "aria-label": `${side} port for free line ${label} in layer ${layer}`,
        });
        handleLayer.appendChild(handle);

        function updateHandle() {
          const point = layerPoint(layer, label);
          handle.setAttribute("cx", point.x + (side === "input" ? NODE_WIDTH / 2 : -NODE_WIDTH / 2));
          handle.setAttribute("cy", point.y);
        }
        updateHandle();

        handle.addEventListener("pointerdown", (event) => {
          event.preventDefault();
          event.stopPropagation();
          handle.setPointerCapture(event.pointerId);
          const matrix = svg.getScreenCTM();
          const scaleY = matrix ? matrix.d : 1;
          const startClientY = event.clientY;
          const startY = layerPoint(layer, label).y;
          let requestedY = startY;

          function move(moveEvent) {
            requestedY = startY + (moveEvent.clientY - startClientY) / scaleY;
            freeDragOverride = { layer, label, y: requestedY };
            updateAllHandles();
            drawLines();
          }

          function finish() {
            handle.removeEventListener("pointermove", move);
            handle.removeEventListener("pointerup", finish);
            handle.removeEventListener("pointercancel", finish);
            reorderLayer(layer, `free:${labelKey}`, requestedY);
            freeDragOverride = null;
            for (const child of nodeLayer.children) {
              const childNode = nodes.get(Number(child.getAttribute("data-node")));
              if (childNode) updateNode(child, childNode);
            }
            updateAllHandles();
            drawLines();
            model.set("positions", structuredClone(positions));
            saveFreeLevelState();
          }

          handle.addEventListener("pointermove", move);
          handle.addEventListener("pointerup", finish);
          handle.addEventListener("pointercancel", finish);
        });

        handle._birdtracksUpdate = updateHandle;
      }
    }
  }

  for (const side of ["input", "output"]) {
    for (const label of graph.boundary_labels) {
      const handle = svgElement("circle", {
        r: graph.geometry.handle_radius,
        class: "birdtracks-boundary-handle",
        "aria-label": `${side} boundary line ${label}`,
      });
      handleLayer.appendChild(handle);

      function updateHandle() {
        const point = boundaryPoint(label, side);
        handle.setAttribute("cx", point.x);
        handle.setAttribute("cy", point.y);
      }
      updateHandle();

      handle.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        event.stopPropagation();
        handle.setPointerCapture(event.pointerId);
        const matrix = svg.getScreenCTM();
        const scaleY = matrix ? matrix.d : 1;
        const startClientY = event.clientY;
        const startY = boundaryPoint(label, side).y;
        let requestedY = startY;

        function move(moveEvent) {
          requestedY = startY + (moveEvent.clientY - startClientY) / scaleY;
          boundaryDragOverride = {
            side,
            label,
            y: requestedY,
          };
          updateAllHandles();
          drawLines();
        }

        function finish() {
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", finish);
          handle.removeEventListener("pointercancel", finish);
          const order = boundaryOrders[side];
          const desired = Math.max(
            0,
            Math.min(
              order.length - 1,
              Math.round(
                (requestedY - TOP_LINE_LEVEL) / LINE_SPACING,
              ),
            ),
          );
          const current = order.indexOf(label);
          order.splice(current, 1);
          order.splice(desired, 0, label);
          boundaryDragOverride = null;
          updateAllHandles();
          drawLines();
          saveBoundaryState();
        }

        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", finish);
        handle.addEventListener("pointercancel", finish);
      });

      handle._birdtracksUpdate = updateHandle;
    }
  }

  function updateAllHandles() {
    for (const handle of handleLayer.children) {
      handle._birdtracksUpdate();
    }
  }

  drawCoefficient(model.get("effective_coefficient"));
  drawLines();
  const redrawTermSign = () => drawCoefficient(model.get("effective_coefficient"));
  model.on("change:term_sign change:term_leading", redrawTermSign);
}

export default {
  render(context) {
    if (context.model.get("widget_role") === "toolbar") renderToolbar(context);
    else renderCreator(context);
  },
};
