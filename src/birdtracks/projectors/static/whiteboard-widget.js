const MATHML_NS = "http://www.w3.org/1998/Math/MathML";
const SVG_NS = "http://www.w3.org/2000/svg";

const SYMBOLS = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ϵ",
  varepsilon: "ε", zeta: "ζ", eta: "η", theta: "θ", vartheta: "ϑ",
  iota: "ι", kappa: "κ", lambda: "λ", mu: "μ", nu: "ν", xi: "ξ",
  pi: "π", varpi: "ϖ", rho: "ρ", sigma: "σ", tau: "τ", upsilon: "υ",
  phi: "ϕ", varphi: "φ", chi: "χ", psi: "ψ", omega: "ω",
  Gamma: "Γ", Delta: "Δ", Theta: "Θ", Lambda: "Λ", Xi: "Ξ", Pi: "Π",
  Sigma: "Σ", Phi: "Φ", Psi: "Ψ", Omega: "Ω",
  cdot: "⋅", times: "×", pm: "±", mp: "∓", leq: "≤", geq: "≥",
  neq: "≠", infty: "∞", to: "→", mapsto: "↦", partial: "∂", nabla: "∇",
  sum: "∑", prod: "∏", int: "∫", oplus: "⊕", otimes: "⊗",
};

const COMMAND_VARIANTS = {
  mathbb: "double-struck",
  mathcal: "script",
  mathfrak: "fraktur",
  mathrm: "normal",
  mathbf: "bold",
};
const PROJECTOR_COMMAND = "birdtracks";
const PROJECTOR_COMPLETION = "birdtracks";
const PAIR_COMMAND = "pair";
const DEFINITION_COMMAND = "def";
const OPERATOR_SPACING = { lspace: "0.2em", rspace: "0.2em" };
const PAIR_OPERATOR_SPACING = {
  lspace: "0.1em", rspace: "0.1em", class: "birdtracks-pair-operator",
};
const DEFINITION_OPERATOR = {
  lspace: "0em", rspace: "0em", class: "birdtracks-whiteboard-definition-operator",
};

function mathElement(name, children = [], attributes = {}) {
  const tagName = name === "math" || name.startsWith("m") ? name : `m${name}`;
  const element = document.createElementNS(MATHML_NS, tagName);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, String(value));
  }
  for (const child of children) element.appendChild(child);
  return element;
}

function textElement(name, text, attributes = {}) {
  const element = mathElement(name, [], attributes);
  element.textContent = text;
  return element;
}

function pairOperatorElement(operation, sourceStart, sourceEnd) {
  const wrapper = document.createElement("span");
  wrapper.className = "birdtracks-whiteboard-pair-operator";
  wrapper.dataset.sourceStart = String(sourceStart);
  wrapper.dataset.sourceEnd = String(sourceEnd);
  wrapper.setAttribute(
    "aria-label", operation === "sum" ? "Direct sum" : "Tensor product",
  );
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 28 28");
  svg.setAttribute("aria-hidden", "true");
  const circle = document.createElementNS(SVG_NS, "circle");
  circle.setAttribute("cx", "14");
  circle.setAttribute("cy", "14");
  circle.setAttribute("r", "10");
  const lines = operation === "sum"
    ? [[4, 14, 24, 14], [14, 4, 14, 24]]
    : [[14 - 10 / Math.sqrt(2), 14 - 10 / Math.sqrt(2),
      14 + 10 / Math.sqrt(2), 14 + 10 / Math.sqrt(2)],
      [14 - 10 / Math.sqrt(2), 14 + 10 / Math.sqrt(2),
        14 + 10 / Math.sqrt(2), 14 - 10 / Math.sqrt(2)]];
  svg.appendChild(circle);
  for (const [x1, y1, x2, y2] of lines) {
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", String(x1));
    line.setAttribute("y1", String(y1));
    line.setAttribute("x2", String(x2));
    line.setAttribute("y2", String(y2));
    svg.appendChild(line);
  }
  wrapper.appendChild(svg);
  return wrapper;
}

class LatexParser {
  constructor(source) {
    // The whiteboard accepts the escaped spelling people commonly use when
    // entering notation in Markdown: P\_{1} and P_{1} mean the same thing.
    const normalized = [];
    this.sourceOffsets = [0];
    let originalIndex = 0;
    while (originalIndex < source.length) {
      if (source.startsWith("\\_", originalIndex)) {
        normalized.push("_");
        originalIndex += 2;
      } else {
        normalized.push(source[originalIndex]);
        originalIndex += 1;
      }
      this.sourceOffsets.push(originalIndex);
    }
    this.source = normalized.join("");
    this.index = 0;
  }

  markSourceRange(element, start, end) {
    element.setAttribute(
      "data-source-start",
      String(this.sourceOffsets[start] ?? start),
    );
    element.setAttribute(
      "data-source-end",
      String(this.sourceOffsets[end] ?? end),
    );
    return element;
  }

  parse() {
    const result = this.sequence();
    if (this.index < this.source.length) {
      throw new Error(`unexpected '${this.source[this.index]}'`);
    }
    return result;
  }

  sequence(stopAtBrace = false) {
    const children = [];
    while (this.index < this.source.length) {
      const whitespaceStart = this.index;
      this.skipSpaces();
      if (this.index > whitespaceStart && !stopAtBrace) {
        children.push(this.markSourceRange(
          mathElement("space", [], { width: "0.25em" }),
          whitespaceStart, this.index,
        ));
      }
      if (this.index >= this.source.length) break;
      if (this.source[this.index] === "}") {
        if (!stopAtBrace) throw new Error("unexpected '}'");
        this.index += 1;
        break;
      }
      children.push(this.scriptedAtom());
    }
    return mathElement("row", children);
  }

  scriptedAtom() {
    const start = this.index;
    let atom = this.atom();
    const atomEnd = this.index;
    this.markSourceRange(atom, start, atomEnd);
    let subscript = null;
    let superscript = null;
    while (this.index < this.source.length) {
      const marker = this.source[this.index];
      if (marker !== "^" && marker !== "_") break;
      this.index += 1;
      const script = this.scriptArgument();
      if (marker === "^") {
        if (superscript) throw new Error("duplicate superscript");
        superscript = script;
      } else {
        if (subscript) throw new Error("duplicate subscript");
        subscript = script;
      }
    }
    if (subscript && superscript) {
      return this.markSourceRange(
        mathElement("subsup", [atom, subscript, superscript]),
        start,
        this.index,
      );
    }
    if (subscript) {
      return this.markSourceRange(
        mathElement("sub", [atom, subscript]),
        start,
        this.index,
      );
    }
    if (superscript) {
      return this.markSourceRange(
        mathElement("sup", [atom, superscript]),
        start,
        this.index,
      );
    }
    return atom;
  }

  scriptArgument() {
    this.skipSpaces();
    if (this.index >= this.source.length) return mathElement("row");
    if (this.source[this.index] === "{") return this.group();
    return this.atom();
  }

  atom() {
    const character = this.source[this.index];
    if (character === "{") return this.group();
    if (character === "\\") return this.command();
    if (/[0-9]/.test(character)) return this.number();
    if (character === ":" && this.source[this.index + 1] === "=") {
      this.index += 2;
      return textElement("o", ":=", DEFINITION_OPERATOR);
    }
    this.index += 1;
    if (/[A-Za-z]/.test(character)) return textElement("i", character);
    if (character === "=" || character === "+" || character === "-") {
      return textElement(
        "o",
        character === "-" ? "−" : character,
        OPERATOR_SPACING,
      );
    }
    return textElement("o", character);
  }

  group() {
    this.index += 1;
    return this.sequence(true);
  }

  command() {
    this.index += 1;
    const start = this.index;
    while (this.index < this.source.length && /[A-Za-z]/.test(this.source[this.index])) {
      this.index += 1;
    }
    if (start === this.index) {
      if (this.index >= this.source.length) throw new Error("incomplete command");
      return textElement("o", this.source[this.index++]);
    }
    const command = this.source.slice(start, this.index);
    if (command === "def") return textElement("o", "≔", DEFINITION_OPERATOR);
    if (command === "frac") {
      const fractionPart = () => {
        this.skipSpaces();
        const partStart = this.index;
        const part = mathElement(
          "mstyle",
          [this.requiredGroup()],
          { mathsize: "100%", scriptlevel: "0" },
        );
        return this.markSourceRange(part, partStart, this.index);
      };
      return mathElement("frac", [fractionPart(), fractionPart()]);
    }
    if (command === "sqrt") return mathElement("sqrt", [this.requiredGroup()]);
    if (command === "text" || command === "mathrmtext") {
      return textElement("text", this.rawGroup());
    }
    if (COMMAND_VARIANTS[command]) {
      const argument = this.requiredGroup();
      argument.setAttribute("mathvariant", COMMAND_VARIANTS[command]);
      return argument;
    }
    if (command === "left" || command === "right") {
      this.skipSpaces();
      if (this.index >= this.source.length) throw new Error(`\\${command} needs a delimiter`);
      return textElement("o", this.source[this.index++]);
    }
    if (command === "tr") {
      return textElement("mi", "tr", { mathvariant: "normal" });
    }
    if (command === "quad" || command === "qquad") {
      return mathElement("space", [], { width: command === "quad" ? "1em" : "2em" });
    }
    if (SYMBOLS[command]) {
      const value = SYMBOLS[command];
      return /[A-Za-zΑ-Ωα-ω]/.test(value)
        ? textElement("i", value)
        : textElement(
          "o", value,
          command === "oplus" || command === "otimes"
            ? PAIR_OPERATOR_SPACING : {},
        );
    }
    throw new Error(`unsupported command \\${command}`);
  }

  requiredGroup() {
    this.skipSpaces();
    if (this.source[this.index] !== "{") return mathElement("row");
    return this.group();
  }

  rawGroup() {
    this.skipSpaces();
    if (this.source[this.index] !== "{") throw new Error("text argument must be braced");
    this.index += 1;
    const start = this.index;
    let depth = 1;
    while (this.index < this.source.length && depth) {
      if (this.source[this.index] === "{") depth += 1;
      if (this.source[this.index] === "}") depth -= 1;
      this.index += 1;
    }
    if (depth) throw new Error("unclosed text group");
    return this.source.slice(start, this.index - 1);
  }

  number() {
    const start = this.index;
    while (this.index < this.source.length && /[0-9.,]/.test(this.source[this.index])) {
      this.index += 1;
    }
    return textElement("n", this.source.slice(start, this.index));
  }

  skipSpaces() {
    while (this.index < this.source.length && /\s/.test(this.source[this.index])) this.index += 1;
  }
}

function splitMathSegments(source) {
  const trimmed = source.trim();
  if ((trimmed.startsWith("$$") && trimmed.endsWith("$$"))
      || (trimmed.startsWith("\\[") && trimmed.endsWith("\\]"))) {
    const offset = trimmed.startsWith("$$") ? 2 : 2;
    const end = trimmed.startsWith("$$") ? 2 : 2;
    const trimmedStart = source.indexOf(trimmed);
    const sourceStart = trimmedStart + offset;
    return [{
      display: true,
      source: trimmed.slice(offset, -end),
      sourceStart,
      sourceEnd: trimmedStart + trimmed.length - end,
    }];
  }
  const segments = [];
  let index = 0;
  while (index < source.length) {
    const dollar = source.indexOf("$", index);
    const paren = source.indexOf("\\(", index);
    const start = [dollar, paren].filter((value) => value >= 0).sort((a, b) => a - b)[0];
    if (start === undefined) {
      if (index < source.length) {
        // A block without explicit math delimiters is itself a math block.
        // This is the normal whiteboard case: `P_1` should be typeset even
        // though mixed prose such as `let $P_1$` still keeps its prose text.
        const segment = index === 0 && segments.length === 0
          ? { display: false, source: source.slice(index), sourceStart: index, sourceEnd: source.length }
          : { display: false, text: source.slice(index), sourceStart: index, sourceEnd: source.length };
        segments.push(segment);
      }
      break;
    }
    if (start > index) segments.push({
      display: false,
      text: source.slice(index, start),
      sourceStart: index,
      sourceEnd: start,
    });
    const opener = source.startsWith("\\(", start) ? "\\(" : "$";
    const closer = opener === "$" ? "$" : "\\)";
    const end = source.indexOf(closer, start + opener.length);
    if (end < 0) throw new Error(`unclosed ${opener} expression`);
    segments.push({
      display: false,
      source: source.slice(start + opener.length, end),
      sourceStart: start + opener.length,
      sourceEnd: end,
    });
    index = end + closer.length;
  }
  return segments.length ? segments : [{
    display: false,
    source,
    sourceStart: 0,
    sourceEnd: source.length,
  }];
}

function projectorCommandSuggestion(source) {
  const match = source.match(/\\([A-Za-z]*)$/);
  if (!match) return null;
  const command = PROJECTOR_COMMAND.startsWith(match[1])
    ? PROJECTOR_COMMAND : PAIR_COMMAND.startsWith(match[1])
      ? PAIR_COMMAND : DEFINITION_COMMAND.startsWith(match[1])
        ? DEFINITION_COMMAND : null;
  if (!command) return null;
  const completion = command === PROJECTOR_COMMAND
    ? PROJECTOR_COMPLETION : command === PAIR_COMMAND
      ? PAIR_COMMAND : DEFINITION_COMMAND;
  return {
    start: match.index,
    typed: match[0],
    completion: completion.slice(match[1].length),
  };
}

function groupEnd(source, start) {
  if (source[start] !== "{") return null;
  let depth = 0;
  for (let index = start; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] !== "}") continue;
    depth -= 1;
    if (depth === 0) return index + 1;
  }
  return null;
}

export function fractionRangeAt(source, caretIndex) {
  const pattern = /\\frac\b/g;
  let match;
  while ((match = pattern.exec(source)) !== null) {
    const start = match.index;
    let index = pattern.lastIndex;
    while (index < source.length && /\s/.test(source[index])) index += 1;
    const numeratorEnd = groupEnd(source, index);
    if (numeratorEnd === null) {
      if (caretIndex >= start && caretIndex <= source.length) {
        return { start, end: source.length };
      }
      continue;
    }
    index = numeratorEnd;
    while (index < source.length && /\s/.test(source[index])) index += 1;
    const denominatorEnd = groupEnd(source, index);
    const end = denominatorEnd ?? source.length;
    const inside = denominatorEnd === null
      ? caretIndex >= start && caretIndex <= end
      : caretIndex >= start && caretIndex < end;
    if (inside) return { start, end };
  }
  return null;
}

function numericPrefactorBefore(source, markerStart) {
  let end = markerStart;
  while (end > 0 && /\s/.test(source[end - 1])) end -= 1;
  const prefix = source.slice(0, end);
  const match = prefix.match(
    /[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:_\d+)?(?:\s*\/\s*\d+(?:[.,]\d*)?)?$/,
  ) || prefix.match(/[+-]?\\frac\s*\{\s*\d+\s*\}\s*\{\s*\d+\s*\}$/);
  if (!match) return null;
  const start = match.index;
  if (start > 0 && /[A-Za-z0-9_._^/]/.test(prefix[start - 1])) return null;
  return {
    start,
    end,
    sign: match[0][0] === "-" || match[0][0] === "+" ? match[0][0] : "",
    negative: match[0].startsWith("-"),
  };
}

export function flipNumericPrefactor(source, markerStart) {
  const prefactor = numericPrefactorBefore(source, markerStart);
  if (!prefactor) return null;
  const before = source.slice(0, prefactor.start);
  const operator = before.match(/([+-])(\s*)$/);
  const unarySign = prefactor.negative ? -1 : 1;
  const operatorSign = operator?.[1] === "-" ? -1 : 1;
  const flippedSign = -(unarySign * operatorSign);
  const magnitudeStart = prefactor.start + (prefactor.sign ? 1 : 0);
  if (operator?.index !== undefined) {
    return source.slice(0, operator.index)
      + (flippedSign < 0 ? "-" : "+")
      + operator[2]
      + source.slice(magnitudeStart);
  }
  return source.slice(0, prefactor.start)
    + (flippedSign < 0 ? "-" : "")
    + source.slice(magnitudeStart);
}

function permutationIsOdd(order, initial) {
  const rank = new Map(initial.map((label, index) => [label, index]));
  const values = order.map((label) => rank.get(label));
  let inversions = 0;
  for (let left = 0; left < values.length; left += 1) {
    for (let right = left + 1; right < values.length; right += 1) {
      if (values[left] > values[right]) inversions += 1;
    }
  }
  return inversions % 2 === 1;
}

export function projectorOrientationSign(graph, portOrders) {
  let sign = 1;
  for (const node of graph?.nodes || []) {
    if (node.kind !== "antisymmetriser") continue;
    const orders = portOrders?.[String(node.index)] || {};
    for (const [side, initialKey] of [["input", "input_labels"], ["output", "output_labels"]]) {
      const initial = node[initialKey] || node.labels || [];
      const order = orders[side] || initial;
      if (permutationIsOdd(order, initial)) sign = -sign;
    }
  }
  return sign;
}

function renderCommandSuggestion(source, target, sourceOffset = 0) {
  const suggestion = projectorCommandSuggestion(source);
  if (!suggestion) return false;
  const prefix = source.slice(0, suggestion.start);
  if (prefix) {
    const prefixTarget = document.createElement("span");
    renderLatex(prefix, prefixTarget, sourceOffset);
    target.appendChild(prefixTarget);
  }
  const typed = document.createElement("span");
  typed.textContent = suggestion.typed;
  typed.dataset.sourceStart = String(sourceOffset + suggestion.start);
  typed.dataset.sourceEnd = String(sourceOffset + suggestion.start + suggestion.typed.length);
  const completion = document.createElement("span");
  completion.className = "birdtracks-whiteboard-command-suggestion";
  completion.textContent = suggestion.completion;
  target.append(typed, completion);
  return true;
}

function offsetSourceRanges(target, sourceOffset) {
  if (!sourceOffset) return;
  target.querySelectorAll("[data-source-start]").forEach((element) => {
    element.dataset.sourceStart = String(
      Number(element.dataset.sourceStart) + sourceOffset,
    );
    element.dataset.sourceEnd = String(
      Number(element.dataset.sourceEnd) + sourceOffset,
    );
  });
}

function renderLatexInto(source, target, sourceOffset, editingIndex) {
  for (const segment of splitMathSegments(source)) {
    const segmentOffset = sourceOffset + (segment.sourceStart || 0);
    if (segment.text !== undefined) {
      if (renderCommandSuggestion(segment.text, target, segmentOffset)) continue;
      const text = document.createElement("span");
      text.textContent = segment.text;
      text.dataset.sourceStart = String(segmentOffset);
      text.dataset.sourceEnd = String(segmentOffset + segment.text.length);
      target.appendChild(text);
      continue;
    }
    const segmentCaret = editingIndex === null
      ? null : editingIndex - segmentOffset;
    const pairOperator = segment.source.match(/\\(oplus|otimes)\b/);
    if (pairOperator) {
      const operatorStart = pairOperator.index;
      const operatorEnd = operatorStart + pairOperator[0].length;
      if (operatorStart > 0) {
        renderLatexInto(
          segment.source.slice(0, operatorStart),
          target,
          segmentOffset,
          editingIndex,
        );
      }
      target.appendChild(pairOperatorElement(
        pairOperator[1] === "oplus" ? "sum" : "tensor",
        segmentOffset + operatorStart,
        segmentOffset + operatorEnd,
      ));
      if (operatorEnd < segment.source.length) {
        renderLatexInto(
          segment.source.slice(operatorEnd),
          target,
          segmentOffset + operatorEnd,
          editingIndex,
        );
      }
      continue;
    }
    const fraction = segmentCaret === null
      ? null : fractionRangeAt(segment.source, segmentCaret);
    if (fraction) {
      if (fraction.start) {
        renderLatexInto(
          segment.source.slice(0, fraction.start),
          target,
          segmentOffset,
        );
      }
      const syntax = document.createElement("span");
      syntax.className = "birdtracks-whiteboard-fraction-source";
      syntax.textContent = segment.source.slice(fraction.start, fraction.end);
      syntax.dataset.sourceStart = String(segmentOffset + fraction.start);
      syntax.dataset.sourceEnd = String(segmentOffset + fraction.end);
      target.appendChild(syntax);
      if (fraction.end < segment.source.length) {
        renderLatexInto(
          segment.source.slice(fraction.end),
          target,
          segmentOffset + fraction.end,
        );
      }
      continue;
    }
    if (renderCommandSuggestion(segment.source, target, segmentOffset)) continue;
    const math = mathElement("math", [new LatexParser(segment.source).parse()], {
      display: segment.display ? "block" : "inline",
    });
    offsetSourceRanges(math, segmentOffset);
    target.appendChild(math);
  }
}

export function renderLatex(source, target, sourceOffset = 0, editingIndex = null) {
  if (typeof source !== "string") throw new Error("math source must be text");
  target.replaceChildren();
  renderLatexInto(source, target, sourceOffset, editingIndex);
}

async function renderWorkspace({ model, el, host, signal }) {
  const root = document.createElement("div");
  root.className = "birdtracks-whiteboard-workspace";
  const content = document.createElement("div");
  content.className = "birdtracks-whiteboard-document";
  root.appendChild(content);
  el.replaceChildren(root);

  let childCleanup = null;
  let titleListeners = [];
  let mountRevision = 0;

  const clearTitleListeners = () => {
    for (const [childModel, listener] of titleListeners) {
      childModel.off("change:title", listener);
    }
    titleListeners = [];
  };

  const mountActiveDocument = async () => {
    const revision = ++mountRevision;
    clearTitleListeners();
    childCleanup?.();
    childCleanup = null;
    content.replaceChildren();

    const references = model.get("documents") || [];
    if (!references.length || !host?.getModel) return;
    const childModels = await Promise.all(
      references.map((reference) => host.getModel(reference)),
    );
    if (revision !== mountRevision) return;
    const activeIndex = Math.max(
      0, Math.min(Number(model.get("active_index") || 0), references.length - 1),
    );
    childCleanup = renderWhiteboard({
      model: childModels[activeIndex],
      el: content,
      host,
      signal,
    });
    if (revision !== mountRevision) {
      childCleanup?.();
      childCleanup = null;
      return;
    }

    const heading = content.querySelector(".birdtracks-whiteboard-heading");
    const activeTitle = content.querySelector(".birdtracks-whiteboard-title");
    if (!heading || !activeTitle) return;
    const tabs = document.createElement("div");
    tabs.className = "birdtracks-whiteboard-tabs";
    childModels.forEach((childModel, index) => {
      const tab = document.createElement("div");
      tab.className = "birdtracks-whiteboard-tab";
      if (index === activeIndex) {
        tab.classList.add("active");
        tab.appendChild(activeTitle);
      } else {
        const select = document.createElement("button");
        select.type = "button";
        select.className = "birdtracks-whiteboard-tab-select";
        const updateLabel = () => {
          select.textContent = childModel.get("title") || "Untitled";
        };
        updateLabel();
        childModel.on("change:title", updateLabel);
        titleListeners.push([childModel, updateLabel]);
        select.addEventListener("click", () => {
          model.set("active_index", index);
          model.save_changes();
        });
        tab.appendChild(select);
      }
      const close = document.createElement("button");
      close.type = "button";
      close.className = "birdtracks-whiteboard-close-tab";
      close.textContent = "×";
      close.title = `Close ${childModel.get("title") || "Untitled"}`;
      close.setAttribute("aria-label", close.title);
      close.addEventListener("click", () => {
        model.set("close_document_request", index);
        model.set("close_document_revision", Number(model.get("close_document_revision") || 0) + 1);
        model.save_changes();
      });
      tab.appendChild(close);
      tabs.appendChild(tab);
    });
    const addTab = document.createElement("button");
    addTab.type = "button";
    addTab.className = "birdtracks-whiteboard-tab birdtracks-whiteboard-add-tab";
    addTab.textContent = "+";
    addTab.title = "New whiteboard";
    addTab.setAttribute("aria-label", "New whiteboard");
    addTab.addEventListener("click", () => {
      model.set(
        "new_document_request", Number(model.get("new_document_request") || 0) + 1,
      );
      model.save_changes();
    });
    tabs.appendChild(addTab);
    heading.appendChild(tabs);
  };

  model.on("change:documents", mountActiveDocument);
  model.on("change:active_index", mountActiveDocument);
  await mountActiveDocument();
  return () => {
    mountRevision += 1;
    clearTitleListeners();
    childCleanup?.();
    model.off("change:documents", mountActiveDocument);
    model.off("change:active_index", mountActiveDocument);
  };
}

function renderWhiteboard({ model, el, host, signal }) {
  let activeEditorId = null;
  let pendingFocusBlockId = null;
  let pendingFocusAtEnd = false;
  let pendingFocusTimer = null;
  let pendingRestoreBlockId = null;
  let pendingCalculationViewport = null;
  let pendingRevealBlockId = null;
  let pendingRevealScroller = null;
  let pendingRevealScrollTop = null;
  let locallyUpdatingBlockId = null;
  let calculationRequestRevision = Number(model.get('simplify_request')?.revision || 0);
  const cancelledCalculationGroups = new Set();
  const embeddedModels = new Map();
  const embeddedAnchors = new Map();
  const embeddedProjectorSigns = new Map();
  const root = document.createElement("section");
  root.className = "birdtracks-whiteboard-section";
  root.classList.add("paintbrush-active");
  const paintbrushState = {
    active: true,
    color: "#000000",
    recent: [],
    record: null,
  };
  root._birdtracksPaintbrush = paintbrushState;
  const heading = document.createElement("div");
  heading.className = "birdtracks-whiteboard-heading birdtracks-whiteboard-toolbar";
  const title = document.createElement("input");
  title.type = "text";
  title.className = "birdtracks-whiteboard-title";
  title.placeholder = "Untitled Whiteboard";
  title.value = model.get("title") || "";
  title.setAttribute("aria-label", "Whiteboard session name");
  title.addEventListener("change", () => {
    model.set("title", title.value);
    model.save_changes();
  });
  const updateTitle = () => {
    if (title.value !== (model.get("title") || "")) {
      title.value = model.get("title") || "";
    }
  };
  model.on("change:title", updateTitle);
  const paintbrushBar = document.createElement("div");
  paintbrushBar.className = "birdtracks-whiteboard-edit-bar";
  const paintbrushButton = document.createElement("button");
  paintbrushButton.type = "button";
  paintbrushButton.className = "birdtracks-whiteboard-paintbrush";
  paintbrushButton.setAttribute("aria-label", "Paintbrush color");
  paintbrushButton.setAttribute("aria-pressed", "true");
  paintbrushButton.classList.add("selected");
  paintbrushButton.title = "Choose a color and paint lines or pair boxes";
  const paintbrushIcon = document.createElementNS(SVG_NS, "svg");
  paintbrushIcon.setAttribute("viewBox", "0 0 32 36");
  paintbrushIcon.setAttribute("aria-hidden", "true");
  const paintbrushHandle = document.createElementNS(SVG_NS, "path");
  paintbrushHandle.setAttribute("d", "M14 3 Q16 2 17 4 L16 20 Q16 21 14 21 L12 20 Z");
  paintbrushHandle.classList.add("birdtracks-paintbrush-handle");
  const paintbrushTip = document.createElementNS(SVG_NS, "path");
  paintbrushTip.setAttribute("d", "M13.5 24 C10.5 24 9 26 9 29 C9 32 10.5 34 13 34 C12.2 31.8 12.5 30.8 14 30.6 C15.8 32.4 18 33.2 20.5 33 C18 31.5 17 29.5 17 27.3 C17 25.4 15.5 24 13.5 24 Z");
  paintbrushTip.classList.add("birdtracks-paintbrush-tip");
  const paintbrushFerrule = document.createElementNS(SVG_NS, "path");
  paintbrushFerrule.setAttribute("d", "M12 20 Q14 19 16 20 L17 23 Q16 24 13 23 L11 22 Z");
  paintbrushFerrule.classList.add("birdtracks-paintbrush-ferrule");
  paintbrushIcon.append(paintbrushHandle, paintbrushFerrule, paintbrushTip);
  paintbrushButton.appendChild(paintbrushIcon);
  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "birdtracks-whiteboard-action";
  saveButton.textContent = "Save";
  const loadButton = document.createElement("button");
  loadButton.type = "button";
  loadButton.className = "birdtracks-whiteboard-action";
  loadButton.textContent = "Load";
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = ".whiteboard,.json,.whiteboard.json,application/json";
  fileInput.hidden = true;
  const exportButton = document.createElement("button");
  exportButton.type = "button";
  exportButton.className = "birdtracks-whiteboard-action birdtracks-whiteboard-export";
  exportButton.setAttribute("aria-label", "Export to LaTeX");
  exportButton.disabled = true;
  exportButton.title = "LaTeX export is not available in this release";
  exportButton.append("Export to ");
  const latexLogo = document.createElement("span");
  latexLogo.className = "birdtracks-latex-logo";
  latexLogo.setAttribute("aria-hidden", "true");
  const latexA = document.createElement("span");
  latexA.className = "birdtracks-latex-logo-a";
  latexA.textContent = "A";
  const latexE = document.createElement("span");
  latexE.className = "birdtracks-latex-logo-e";
  latexE.textContent = "E";
  latexLogo.append("L", latexA, "T", latexE, "X");
  exportButton.append(latexLogo);
  const colorPanel = document.createElement("div");
  colorPanel.className = "birdtracks-whiteboard-color-panel";
  colorPanel.hidden = true;
  colorPanel.setAttribute("aria-label", "Line color selection");
  const recentLabel = document.createElement("span");
  recentLabel.className = "birdtracks-whiteboard-color-label";
  recentLabel.textContent = "Recent colors";
  const recentColors = document.createElement("div");
  recentColors.className = "birdtracks-whiteboard-recent-colors";
  const pickerButton = document.createElement("label");
  pickerButton.className = "birdtracks-whiteboard-picker-button";
  const colorInput = document.createElement("input");
  colorInput.type = "color";
  colorInput.value = paintbrushState.color;
  colorInput.setAttribute("aria-label", "Choose color with a color wheel");
  colorInput.className = "birdtracks-whiteboard-color-wheel";
  pickerButton.append("Choose color", colorInput);
  const rgbFields = document.createElement("div");
  rgbFields.className = "birdtracks-whiteboard-rgb-fields";
  const rgbInputs = {};
  for (const channel of ["r", "g", "b"]) {
    const label = document.createElement("label");
    label.textContent = channel.toUpperCase();
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "255";
    input.step = "1";
    input.inputMode = "numeric";
    input.setAttribute("aria-label", `${channel.toUpperCase()} color value`);
    label.appendChild(input);
    rgbFields.appendChild(label);
    rgbInputs[channel] = input;
  }
  colorPanel.append(recentLabel, recentColors, pickerButton, rgbFields);
  paintbrushBar.append(paintbrushButton, saveButton, loadButton, exportButton, fileInput, colorPanel);

  loadButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    model.set("load_document_request", {
      name: file.name,
      content: await file.text(),
      revision: Date.now(),
    });
    model.save_changes();
    fileInput.value = "";
  });

  function hexToRgb(hex) {
    const value = hex.replace("#", "");
    return {
      r: parseInt(value.slice(0, 2), 16),
      g: parseInt(value.slice(2, 4), 16),
      b: parseInt(value.slice(4, 6), 16),
    };
  }

  function rgbToHex() {
    const values = ["r", "g", "b"].map((channel) => {
      const value = Math.max(0, Math.min(255, Number.parseInt(rgbInputs[channel].value, 10) || 0));
      rgbInputs[channel].value = String(value);
      return value.toString(16).padStart(2, "0");
    });
    return `#${values.join("")}`;
  }

  function updateRecentColors() {
    recentColors.replaceChildren();
    for (const color of paintbrushState.recent) {
      const recent = document.createElement("button");
      recent.type = "button";
      recent.className = "birdtracks-whiteboard-recent-color";
      recent.style.backgroundColor = color;
      recent.title = color;
      recent.setAttribute("aria-label", `Use recent color ${color}`);
      recent.addEventListener("click", () => setPaintbrushColor(color, true));
      recentColors.appendChild(recent);
    }
  }

  function setPaintbrushColor(color, remember = false) {
    if (!/^#[0-9a-f]{6}$/i.test(color)) return;
    const normalized = color.toLowerCase();
    paintbrushState.color = normalized;
    colorInput.value = normalized;
    const rgb = hexToRgb(normalized);
    for (const channel of ["r", "g", "b"]) rgbInputs[channel].value = String(rgb[channel]);
    paintbrushTip.style.fill = normalized;
    if (remember) {
      paintbrushState.recent = [normalized, ...paintbrushState.recent.filter((item) => item !== normalized)].slice(0, 5);
      updateRecentColors();
    }
  }

  function setPaintbrushActive(active) {
    paintbrushState.active = active;
    root.classList.toggle("paintbrush-active", active);
    paintbrushButton.classList.toggle("selected", active);
    paintbrushButton.setAttribute("aria-pressed", String(active));
    colorPanel.hidden = !active;
    if (active) paintbrushButton.focus();
  }

  paintbrushState.record = (color) => setPaintbrushColor(color, true);
  paintbrushButton.addEventListener("click", () => {
    colorPanel.hidden = false;
  });
  colorInput.addEventListener("input", () => setPaintbrushColor(colorInput.value));
  for (const input of Object.values(rgbInputs)) {
    input.addEventListener("change", () => setPaintbrushColor(rgbToHex(), true));
  }
  setPaintbrushColor(paintbrushState.color);
  updateRecentColors();

  function captureState() {
    const snapshots = {projectors: {}, pairs: {}};
    for (const [id, child] of embeddedModels) {
      if (id.includes(":projector:")) {
        child.set("save_command", Number(child.get("save_command") || 0) + 1);
        child.save_changes();
        const snapshot = child.get("save_snapshot");
        if (snapshot) snapshots.projectors[id] = structuredClone(snapshot);
      } else if (id.includes(":pair:")) {
        const expression = child.get("pair_expression");
        if (expression) snapshots.pairs[id] = structuredClone(expression);
      }
    }
    const blocks = (model.get("blocks") || []).map((block) => {
      const updated = {...block};
      const projectorPrefix = `${block.id}:projector:`;
      const pairPrefix = `${block.id}:pair:`;
      for (const [id, snapshot] of Object.entries(snapshots.projectors)) {
        if (!id.startsWith(projectorPrefix)) continue;
        updated.projector_snapshots = structuredClone(updated.projector_snapshots || {});
        updated.projector_snapshots[id.slice(projectorPrefix.length)] = snapshot;
      }
      for (const [id, expression] of Object.entries(snapshots.pairs)) {
        if (!id.startsWith(pairPrefix)) continue;
        updated.pair_snapshots = structuredClone(updated.pair_snapshots || {});
        updated.pair_snapshots[id.slice(pairPrefix.length)] = expression;
      }
      return updated;
    });
    model.set("blocks", blocks);
    model.save_changes();
  }

  function requestSave() {
    captureState();
    model.set("save_request", Number(model.get("save_request") || 0) + 1);
    model.save_changes();
  }

  saveButton.addEventListener("click", requestSave);
  const downloadExport = () => {
    const source = model.get("export_content");
    if (typeof source !== "string" || !source) return;
    const link = document.createElement("a");
    link.download = `${(model.get("title") || "whiteboard").trim() || "whiteboard"}.tex`;
    const url = URL.createObjectURL(new Blob([source], {type: "text/x-tex"}));
    link.href = url;
    link.click();
    // Chromium/WebView may not begin the download until the current event
    // loop turn has completed.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  model.on("change:export_content", downloadExport);
  const list = document.createElement("div");
  list.className = "birdtracks-whiteboard-blocks";
  heading.append(paintbrushBar, title);
  root.append(heading, list);
  el.replaceChildren(root);
  const view = root.ownerDocument.defaultView;
  let toolbarFrame = null;
  const updateToolbarPosition = () => {
    toolbarFrame = null;
    const rootBounds = root.getBoundingClientRect();
    const maximumOffset = Math.max(0, rootBounds.height - heading.offsetHeight);
    const offset = Math.min(maximumOffset, Math.max(0, -rootBounds.top));
    heading.style.transform = `translateY(${offset}px)`;
  };
  const queueToolbarPositionUpdate = () => {
    if (toolbarFrame === null) {
      toolbarFrame = view.requestAnimationFrame(updateToolbarPosition);
    }
  };
  document.addEventListener("scroll", queueToolbarPositionUpdate, true);
  view.addEventListener("resize", queueToolbarPositionUpdate);
  queueToolbarPositionUpdate();
  const selectProjector = (event) => {
    const anchor = event.target.closest?.(
      ".birdtracks-whiteboard-embedded-projector, .birdtracks-whiteboard-embedded-pair",
    );
    for (const item of embeddedAnchors.values()) {
      if (item.classList.contains("topology-editing") && item !== anchor) {
        item.closest(".birdtracks-whiteboard-block")
          ?._birdtracksCommitEmbeddedState?.();
      }
      item.classList.toggle("topology-editing", item === anchor);
    }
    if (anchor && root.contains(anchor)
        && !event.target.closest("input, textarea, button")) anchor.focus();
  };
  const calculationShortcut = (event) => {
    if (!event.shiftKey || !["Enter", "Backspace"].includes(event.key)) return;
    const wrapper = event.target.closest?.(".birdtracks-whiteboard-block");
    if (!wrapper || !root.contains(wrapper)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    wrapper._requestCalculation?.(event.key === "Enter" ? "evaluate" : "restore");
  };
  const operatorExpansion = (event) => {
    const wrapper = event.composedPath().find(
      (item) => item?.classList?.contains("birdtracks-whiteboard-block"),
    );
    if (wrapper && root.contains(wrapper)) {
      beginGeneratedBlockViewport(wrapper.dataset.blockId, wrapper);
    }
  };
  root.addEventListener("birdtracks-operator-expansion", operatorExpansion);
  document.addEventListener("pointerdown", selectProjector, true);
  document.addEventListener("keydown", calculationShortcut, true);
  const closeColorPanel = (event) => {
    const path = event.composedPath?.() || [];
    const insidePaintbrushBar = path.includes(paintbrushBar)
      || paintbrushBar.contains(event.target);
    if (!colorPanel.hidden && !insidePaintbrushBar) {
      colorPanel.hidden = true;
    }
  };
  document.addEventListener("pointerdown", closeColorPanel, true);
  let feedbackTimer = null;

  function showCalculationFeedback() {
    // AnyWidget uses Backbone's ``(model, value, options)`` callback shape.
    // Read the synchronized attribute directly so this also remains correct
    // for local model shims and future transport changes.
    const feedback = model.get("calculation_feedback") || {};
    const wrapper = [...list.querySelectorAll(".birdtracks-whiteboard-block")]
      .find((item) => item.dataset.blockId === feedback.line_id);
    if (!wrapper) return;
    const pending = wrapper.querySelector(".birdtracks-whiteboard-calculation-pending");
    const pendingText = pending?.querySelector("span");
    const cancel = pending?.querySelector(".birdtracks-whiteboard-cancel-calculation");
    const log = pending?.querySelector(".birdtracks-whiteboard-calculation-log");
    if (feedback.action === "completed") {
      if (pending) {
        pending.hidden = true;
        pending.classList.remove("error");
      }
      return;
    }
    if (feedback.action !== "rejected") return;
    if (pendingCalculationViewport?.anchorId === feedback.line_id) {
      pendingCalculationViewport = null;
    }
    if (pending) {
      pending.hidden = false;
      pending.classList.add("error");
    }
    if (pendingText) pendingText.textContent = "Error";
    if (cancel) cancel.hidden = true;
    if (log) {
      log.href = "#";
      log.dataset.lineId = String(feedback.line_id);
      log.hidden = false;
    }
    wrapper.classList.remove("calculation-rejected");
    void wrapper.offsetWidth;
    wrapper.classList.add("calculation-rejected");
    if (feedbackTimer !== null) clearTimeout(feedbackTimer);
    feedbackTimer = setTimeout(() => {
      wrapper.classList.remove("calculation-rejected");
      feedbackTimer = null;
    }, 500);
  }

  model.on("change:calculation_feedback", showCalculationFeedback);

  function beginGeneratedBlockViewport(anchorId, anchor) {
    pendingRevealBlockId = null;
    pendingRevealScroller = null;
    pendingRevealScrollTop = null;
    const scroller = scrollingViewport(anchor);
    pendingCalculationViewport = {
      action: "evaluate",
      anchorId,
      knownBlockIds: new Set((model.get("blocks") || []).map((item) => item.id)),
      scroller,
      scrollTop: scroller.scrollTop,
    };
  }

  function revealGeneratedBlock(blockId, scroller) {
    const target = [...list.children]
      .find((item) => item.dataset.blockId === blockId);
    if (target) keepResultInView(target, scroller);
  }

  function renderBlocks() {
    if (locallyUpdatingBlockId !== null) return;
    const currentBlocks = model.get("blocks") || [];
    const cancelledResult = currentBlocks.find((block) => (
      Object.prototype.hasOwnProperty.call(block, "calculation_step")
      && cancelledCalculationGroups.has(connectionGroup(block))
    ));
    if (cancelledResult) {
      const group = connectionGroup(cancelledResult);
      cancelledCalculationGroups.delete(group);
      const source = currentBlocks.find((block) => (
        connectionGroup(block) === group
        && !Object.prototype.hasOwnProperty.call(block, "calculation_step")
      ));
      pendingRestoreBlockId = source?.id || null;
      model.set("blocks", restoreCalculationGroup(currentBlocks, group));
      model.save_changes();
      return;
    }
    const displayBlocks = ensureTrailingBlank(currentBlocks);
    const activeBlock = (model.get('blocks') || []).find(item => item.id === activeEditorId);
    if (activeEditorId !== null && activeBlock && !activeBlock.read_only) {
      for (const editor of list.querySelectorAll(".birdtracks-whiteboard-source")) {
        const current = (model.get("blocks") || [])
          .find((item) => item.id === editor.dataset.blockId);
        if (current) editor.disabled = Boolean(current.read_only);
      }
      return;
    }
    activeEditorId = null;
    const renderScroller = scrollingViewport(list);
    const renderScrollTop = renderScroller.scrollTop;
    const focusedId = document.activeElement?.closest?.('.birdtracks-whiteboard-block')?.dataset.blockId;
    const oldBlock = (model.get('blocks') || []).find(item => item.id === focusedId);
    for (const renderedBlock of list.querySelectorAll(
      ".birdtracks-whiteboard-rendered",
    )) {
      renderedBlock._birdtracksCleanupBlock?.();
    }
    list.replaceChildren();
    for (const [index, block] of displayBlocks.entries()) {
      renderBlock(block, index, displayBlocks);
    }
    let focusTarget = null;
    if (pendingRestoreBlockId !== null) {
      const targetId = pendingRestoreBlockId;
      pendingRestoreBlockId = null;
      focusTarget = [...list.children]
        .find((item) => item.dataset.blockId === targetId) || null;
    }
    const pendingTarget = pendingFocusBlockId === null ? null : [...list.children]
      .find((item) => item.dataset.blockId === pendingFocusBlockId);
    if (pendingTarget) {
      const editor = pendingTarget.querySelector('textarea');
      if (editor && !editor.disabled) {
        editor.focus({preventScroll: true});
        const position = pendingFocusAtEnd ? editor.value.length : 0;
        editor.setSelectionRange(position, position);
      }
      focusTarget = pendingTarget;
    } else if (oldBlock) {
      const related = (model.get('blocks') || []).filter(item => oldBlock.calculation_group
        && item.calculation_group === oldBlock.calculation_group);
      const targetId = related.at(-1)?.id || focusedId;
      const target = [...list.children].find(item => item.dataset.blockId === targetId);
      const editor = target?.querySelector('textarea');
      if (editor && !editor.disabled) editor.focus({preventScroll: true});
      else target?.querySelector('.birdtracks-whiteboard-rendered')?.focus({preventScroll: true});
      focusTarget = target || focusTarget;
    } else if (focusTarget) {
      const editor = focusTarget.querySelector('textarea');
      if (editor && !editor.disabled) editor.focus({preventScroll: true});
      else focusTarget.querySelector('.birdtracks-whiteboard-rendered')?.focus({preventScroll: true});
    }
    renderScroller.scrollTop = renderScrollTop;
    if (pendingCalculationViewport !== null) {
      const viewport = pendingCalculationViewport;
      let completed = viewport.action === "restore";
      if (viewport.action === "evaluate") {
        const targetId = currentBlocks
          .filter((item) => !viewport.knownBlockIds.has(item.id))
          .at(-1)?.id;
        const target = targetId
          ? [...list.children].find((item) => item.dataset.blockId === targetId)
          : null;
        if (target) {
          focusTarget = target;
          completed = true;
        }
      }
      viewport.scroller.scrollTop = viewport.scrollTop;
      if (!completed) {
        return;
      }
      pendingCalculationViewport = null;
      if (viewport.action === "evaluate" && focusTarget) {
        pendingRevealBlockId = focusTarget.dataset.blockId;
        pendingRevealScroller = viewport.scroller;
        revealGeneratedBlock(pendingRevealBlockId, pendingRevealScroller);
        pendingRevealScrollTop = pendingRevealScroller.scrollTop;
        if (!focusTarget.querySelector(".birdtracks-whiteboard-embedded-projector")) {
          pendingRevealBlockId = null;
          pendingRevealScroller = null;
          pendingRevealScrollTop = null;
        }
      }
    }
  }

  function blockLineId(block) {
    return typeof block.line_id === "string" && block.line_id
      ? block.line_id
      : block.id;
  }

  function isContinuationSource(source) {
    return /^\s*&/.test(source);
  }

  function continuationPrefixLength(source) {
    const match = source.match(/^\s*&/);
    return match ? match[0].length : 0;
  }

  function discardRemovedEmbeddedSnapshots(block, previousSource, source) {
    const updated = {...block};
    const markerKinds = [
      ["projector_snapshots", /\\birdtracks\b/g],
      ["pair_snapshots", /\\pair\b(?!\s*\{)/g],
    ];
    for (const [field, pattern] of markerKinds) {
      const previousCount = [...previousSource.matchAll(pattern)].length;
      const count = [...source.matchAll(pattern)].length;
      if (count >= previousCount) continue;
      const snapshots = updated[field];
      if (!snapshots || typeof snapshots !== "object") continue;
      const retained = Object.fromEntries(Object.entries(snapshots)
        .filter(([occurrence]) => Number(occurrence) < count));
      if (Object.keys(retained).length) updated[field] = retained;
      else delete updated[field];
    }
    return updated;
  }

  function nextBlockId(blocks) {
    const ids = new Set(blocks.map((item) => item.id));
    let number = blocks.length + 1;
    while (ids.has(`text-${number}`)) number += 1;
    return `text-${number}`;
  }

  function connectionGroup(block) {
    return String(block.calculation_group || blockLineId(block));
  }

  function restoreCalculationGroup(blocks, group) {
    const restored = [];
    for (const block of blocks) {
      if (connectionGroup(block) !== group) {
        restored.push(block);
        continue;
      }
      if (Object.prototype.hasOwnProperty.call(block, "calculation_step")) continue;
      const copy = {...block};
      delete copy.read_only;
      delete copy.calculation_group;
      restored.push(copy);
    }
    return restored;
  }

  function cancelCalculation(block) {
    const group = connectionGroup(block);
    cancelledCalculationGroups.add(group);
    pendingCalculationViewport = null;
    pendingRevealBlockId = null;
    pendingRevealScroller = null;
    pendingRevealScrollTop = null;
    pendingRestoreBlockId = block.id;
    model.set("blocks", restoreCalculationGroup(model.get("blocks") || [], group));
    model.save_changes();
  }

  function ensureTrailingBlank(blocks) {
    if (blocks.length && blocks.at(-1).source === "" && !blocks.at(-1).read_only) return blocks;
    const id = nextBlockId(blocks);
    return [...blocks, {id, source: "", line_id: id, _trailing_blank: true}];
  }

  function alignmentAnchorIndex(source) {
    const candidates = [source.indexOf("="), source.indexOf("&")]
      .filter((index) => index >= 0);
    return candidates.length ? Math.min(...candidates) : null;
  }

  function sourceElementAt(target, sourceIndex) {
    if (!target) return null;
    return [...target.querySelectorAll("[data-source-start]")]
      .find((element) => Number(element.dataset.sourceStart) === sourceIndex)
      || null;
  }

  function firstSourceElementFrom(target, sourceIndex) {
    if (!target) return null;
    return [...target.querySelectorAll("[data-source-start]")]
      .filter((element) => element.localName !== "mspace")
      .filter((element) => Number(element.dataset.sourceStart) >= sourceIndex)
      .sort((left, right) => (
        Number(left.dataset.sourceStart) - Number(right.dataset.sourceStart)
      ))[0] || null;
  }

  function alignmentAnchorElement(source, rendered) {
    const equalsIndex = source.indexOf("=");
    const ampersandIndex = source.indexOf("&");
    if (equalsIndex >= 0) {
      const afterEquals = firstSourceElementFrom(rendered, equalsIndex + 1);
      if (afterEquals) return afterEquals;
    }
    if (ampersandIndex >= 0
        && (equalsIndex < 0 || ampersandIndex < equalsIndex)
        && ampersandIndex === continuationPrefixLength(source) - 1) {
      return firstSourceElementFrom(rendered, continuationPrefixLength(source));
    }
    const anchorIndex = alignmentAnchorIndex(source);
    return anchorIndex === null ? null : sourceElementAt(rendered, anchorIndex);
  }

  function alignContinuationBlocks() {
    const blocks = model.get("blocks") || [];
    const wrappers = [...list.querySelectorAll(".birdtracks-whiteboard-block")];
    for (let index = 0; index < blocks.length; index += 1) {
      const wrapper = wrappers[index];
      const editor = wrapper?.querySelector(".birdtracks-whiteboard-source");
      const rendered = wrapper?.querySelector(".birdtracks-whiteboard-rendered");
      if (!editor || !rendered) continue;
      editor.style.paddingLeft = "";
      rendered.style.paddingLeft = "";
      if (blocks[index].calculation_step) {
        const previousIndex = blocks.findIndex(item => item.calculation_group
          === blocks[index].calculation_group && item.calculation_step);
        if (previousIndex >= 0 && previousIndex < index) {
          const previous = wrappers[previousIndex].querySelector('.birdtracks-whiteboard-rendered');
          const anchor = previous.querySelector('mo');
          const current = rendered.querySelector('mo');
          if (anchor && current) rendered.style.paddingLeft = `${Math.max(0,
            (parseFloat(getComputedStyle(rendered).paddingLeft) || 0)
            + anchor.getBoundingClientRect().left - current.getBoundingClientRect().left)}px`;
        }
        continue;
      }
      if (index === 0 || !isContinuationSource(blocks[index].source || "")) continue;

      const previousRendered = wrappers[index - 1]?.querySelector(
        ".birdtracks-whiteboard-rendered",
      );
      const previousAnchor = alignmentAnchorElement(
        blocks[index - 1].source || "", previousRendered,
      );
      const currentAnchor = firstSourceElementFrom(
        rendered, continuationPrefixLength(blocks[index].source || ""),
      );
      if (!previousAnchor || !currentAnchor) continue;

      const shift = previousAnchor.getBoundingClientRect().left
        - currentAnchor.getBoundingClientRect().left;
      const basePadding = parseFloat(getComputedStyle(rendered).paddingLeft) || 0;
      const padding = Math.max(0, basePadding + shift);
      editor.style.paddingLeft = `${padding}px`;
      rendered.style.paddingLeft = `${padding}px`;
    }
  }

  let alignmentFrame = null;
  function scheduleContinuationAlignment() {
    if (alignmentFrame !== null) return;
    alignmentFrame = requestAnimationFrame(() => {
      alignmentFrame = null;
      alignContinuationBlocks();
    });
  }

  function scrollingViewport(element) {
    const candidates = [document.scrollingElement];
    let parent = element?.parentElement;
    while (parent) {
      const overflow = getComputedStyle(parent).overflowY;
      if (/^(auto|scroll|overlay)$/.test(overflow)
          && parent.scrollHeight > parent.clientHeight) candidates.push(parent);
      parent = parent.parentElement;
      if (!parent && element?.getRootNode) {
        const root = element.getRootNode();
        parent = root?.host || null;
        element = parent;
      }
    }
    return candidates.reduce((active, candidate) => (
      candidate.scrollTop > active.scrollTop ? candidate : active
    ));
  }

  function scrollViewportBy(scroller, amount) {
    if (scroller === document.scrollingElement) view.scrollBy(0, amount);
    else scroller.scrollTop += amount;
  }

  function keepBlockInView(block, scroller = scrollingViewport(block)) {
    if (!block) return;
    const rect = block.getBoundingClientRect();
    const top = heading.getBoundingClientRect().bottom + 8;
    const viewportBottom = scroller === document.scrollingElement
      ? view.innerHeight
      : scroller.getBoundingClientRect().bottom;
    const bottom = viewportBottom - 8;
    if (rect.top < top) scrollViewportBy(scroller, rect.top - top);
    else if (rect.bottom > bottom) scrollViewportBy(scroller, rect.bottom - bottom);
  }

  function keepResultInView(block, scroller) {
    const rect = block.getBoundingClientRect();
    const viewportBottom = scroller === document.scrollingElement
      ? view.innerHeight
      : scroller.getBoundingClientRect().bottom;
    const bottom = viewportBottom - 8;
    // Following a generated result must never pull the viewport upward.
    if (rect.bottom > bottom) scrollViewportBy(scroller, rect.bottom - bottom);
  }

  function focusBlock(blockId, attempt = 0, placeAtEnd = false, ensureVisible = false) {
    pendingFocusBlockId = blockId;
    pendingFocusAtEnd = placeAtEnd;
    if (pendingFocusTimer !== null) {
      clearTimeout(pendingFocusTimer);
      pendingFocusTimer = null;
    }
    const editor = [...list.querySelectorAll("textarea")]
      .find((item) => item.dataset.blockId === blockId);
    if (editor) {
      editor.focus({preventScroll: true});
      const position = placeAtEnd ? editor.value.length : 0;
      editor.setSelectionRange(position, position);
      if (ensureVisible) keepBlockInView(editor.closest('.birdtracks-whiteboard-block'));
      requestAnimationFrame(() => {
        if (pendingFocusBlockId !== blockId) return;
        if (document.activeElement === editor && editor.isConnected) {
          // Kernel/widget replies can rebuild the rows shortly after Enter.
          // Retain the intended destination briefly so that rebuild restores
          // focus instead of leaving the user typing into nowhere.
          pendingFocusTimer = setTimeout(() => {
            if (pendingFocusBlockId === blockId) pendingFocusBlockId = null;
            pendingFocusTimer = null;
          }, 750);
          return;
        }
        if (attempt >= 5) {
          pendingFocusBlockId = null;
          return;
        }
        focusBlock(blockId, attempt + 1, placeAtEnd, ensureVisible);
      });
      return;
    }
    if (attempt >= 5) {
      pendingFocusBlockId = null;
      return;
    }
    requestAnimationFrame(() => {
      if (pendingFocusBlockId === blockId) {
        focusBlock(blockId, attempt + 1, placeAtEnd, ensureVisible);
      }
    });
  }

  function renderBlock(block, blockIndex, displayBlocks) {
    const wrapper = document.createElement("div");
    wrapper.className = "birdtracks-whiteboard-block";
    wrapper.classList.toggle("trailing-blank", Boolean(block._trailing_blank));
    wrapper.dataset.blockId = block.id;
    const blocks = displayBlocks;
    const group = connectionGroup(block);
    wrapper.dataset.connectionGroup = group;
    wrapper.classList.toggle(
      "connected-line",
      (blockIndex > 0 && connectionGroup(blocks[blockIndex - 1]) === group)
        || (blockIndex + 1 < blocks.length
          && connectionGroup(blocks[blockIndex + 1]) === group),
    );
    wrapper.classList.toggle(
      "connection-break",
      blockIndex > 0
        && connectionGroup(blocks[blockIndex - 1]) !== group
        && !isContinuationSource(block.source || ""),
    );
    wrapper.classList.toggle("calculation-read-only", Boolean(block.read_only));
    wrapper.classList.toggle("calculation-step", Boolean(block.calculation_step));
    wrapper.classList.toggle("continuation", isContinuationSource(block.source || ""));
    const editor = document.createElement("textarea");
    editor.className = "birdtracks-whiteboard-source";
    editor.value = block.source || "";
    editor.disabled = Boolean(block.read_only);
    editor.dataset.blockId = block.id;
    editor.setAttribute("aria-label", "Whiteboard LaTeX source");
    editor.spellcheck = false;
    const rendered = document.createElement("div");
    rendered.className = "birdtracks-whiteboard-rendered";
    rendered.tabIndex = 0;
    const calculationPending = document.createElement("div");
    calculationPending.className = "birdtracks-whiteboard-calculation-pending";
    const pendingText = document.createElement("span");
    pendingText.textContent = "Calculation pending…";
    const cancelCalculationButton = document.createElement("button");
    cancelCalculationButton.type = "button";
    cancelCalculationButton.className = "birdtracks-whiteboard-cancel-calculation";
    cancelCalculationButton.textContent = "Cancel";
    cancelCalculationButton.setAttribute("aria-label", "Cancel calculation");
    const calculationLog = document.createElement("a");
    calculationLog.className = "birdtracks-whiteboard-calculation-log";
    calculationLog.textContent = "Open log";
    calculationLog.target = "_blank";
    calculationLog.rel = "noopener";
    calculationLog.hidden = true;
    calculationLog.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      model.set("open_error_log_request", {
        line_id: calculationLog.dataset.lineId || block.id,
        revision: ++calculationRequestRevision,
      });
      model.save_changes();
    });
    calculationPending.append(
      pendingText, cancelCalculationButton, calculationLog,
    );
    calculationPending.hidden = true;
    let editorBasePaddingTop = 0;
    const caret = document.createElement("span");
    caret.className = "birdtracks-whiteboard-caret";
    caret.hidden = true;
    let caretPoint = null;
    let sourceMarkers = [];
    let lastValidSource = "";
    let activeFraction = null;
    let caretNavigationDirection = 0;
    const embeddedProjectorListeners = new Map();
    let disposed = false;

    rendered._birdtracksCleanupBlock = () => {
      if (disposed) return;
      disposed = true;
      for (const anchor of rendered.querySelectorAll(
        ".birdtracks-whiteboard-embedded-projector, .birdtracks-whiteboard-embedded-pair",
      )) {
        anchor._birdtracksCleanup?.();
        anchor._birdtracksCleanup = null;
        delete anchor._birdtracksProjectorReference;
      }
      for (const [id, listener] of embeddedProjectorListeners) {
        embeddedModels.get(id)?.off(
          "change:port_orders change:graph change:boundary_orders", listener,
        );
      }
      embeddedProjectorListeners.clear();
      for (const id of embeddedModels.keys()) {
        if (!id.startsWith(`${block.id}:`)) continue;
        embeddedModels.delete(id);
        embeddedAnchors.delete(id);
        embeddedProjectorSigns.delete(id);
      }
    };

    function saveEmbeddedState(items) {
      const snapshots = {projectors: {}, pairs: {}};
      for (const item of items) {
        for (const [id, child] of embeddedModels) {
          if (id.startsWith(`${item.id}:projector:`)) {
            child.set("save_command", Number(child.get("save_command") || 0) + 1);
            child.save_changes();
            const snapshot = child.get("save_snapshot");
            if (snapshot) snapshots.projectors[id] = structuredClone(snapshot);
          } else if (id.startsWith(`${item.id}:pair:`)) {
            const expression = child.get("pair_expression");
            if (expression) snapshots.pairs[id] = structuredClone(expression);
          }
        }
      }
      return snapshots;
    }

    function storeEmbeddedSnapshots(blocks, snapshots) {
      return blocks.map((item) => {
        const projectorPrefix = `${item.id}:projector:`;
        const pairPrefix = `${item.id}:pair:`;
        const projectors = Object.entries(snapshots.projectors)
          .filter(([id]) => id.startsWith(projectorPrefix));
        const pairs = Object.entries(snapshots.pairs)
          .filter(([id]) => id.startsWith(pairPrefix));
        if (!projectors.length && !pairs.length) return item;
        const updated = {...item};
        if (projectors.length) {
          const stored = structuredClone(item.projector_snapshots || {});
          for (const [id, snapshot] of projectors) {
            stored[id.slice(projectorPrefix.length)] = snapshot;
          }
          updated.projector_snapshots = stored;
        }
        if (pairs.length) {
          const stored = structuredClone(item.pair_snapshots || {});
          for (const [id, expression] of pairs) {
            stored[id.slice(pairPrefix.length)] = expression;
          }
          updated.pair_snapshots = stored;
        }
        return updated;
      });
    }

    wrapper._birdtracksCommitEmbeddedState = () => {
      const currentBlocks = model.get("blocks") || [];
      const snapshots = saveEmbeddedState(currentBlocks);
      const blocks = storeEmbeddedSnapshots(currentBlocks, snapshots);
      if (blocks.every((item, index) => item === currentBlocks[index])) return;
      locallyUpdatingBlockId = block.id;
      try {
        model.set("blocks", blocks);
        model.save_changes();
      } finally {
        locallyUpdatingBlockId = null;
      }
    };

    function requestCalculation(action) {
      if (action === "evaluate" && !calculationPending.hidden) return;
      if (action === "evaluate") cancelledCalculationGroups.delete(connectionGroup(block));
      if (action === "evaluate") {
        calculationLog.hidden = true;
        delete calculationLog.dataset.lineId;
        calculationLog.removeAttribute("href");
        cancelCalculationButton.hidden = false;
        pendingText.textContent = "Calculation pending…";
        calculationPending.classList.remove("error");
        calculationPending.hidden = false;
      }
      if (action === "evaluate") beginGeneratedBlockViewport(block.id, wrapper);
      else {
        const scroller = scrollingViewport(wrapper);
        pendingCalculationViewport = {
          action,
          anchorId: block.id,
          scroller,
          scrollTop: scroller.scrollTop,
        };
      }
      const snapshots = {};
      if (action === "evaluate") {
        const blocks = model.get("blocks") || [];
        const selected = blocks.find((item) => item.id === block.id) || block;
        for (const item of blocks) {
          for (const [occurrence, snapshot] of Object.entries(
            item.projector_snapshots || {},
          )) {
            if (snapshot) snapshots[`${item.id}:projector:${occurrence}`] = snapshot;
          }
        }
        const saved = saveEmbeddedState(blocks.filter((item) => (
          !item.read_only && blockLineId(item) === blockLineId(selected)
        )));
        // Fresh state on the evaluated line takes precedence. Definitions on
        // earlier lines were committed when Enter created the following row.
        Object.assign(snapshots, saved.projectors);
      } else {
        const blocks = model.get("blocks") || [];
        const group = connectionGroup(block);
        const restored = blocks.find((item) => (
          connectionGroup(item) === group
          && !Object.prototype.hasOwnProperty.call(item, "calculation_step")
        ));
        pendingRestoreBlockId = restored?.id || block.id;
        const restoreAnchor = [...list.children].find(
          (item) => item.dataset.blockId === pendingRestoreBlockId,
        );
        if (restoreAnchor) {
          pendingCalculationViewport.anchorId = pendingRestoreBlockId;
        }
      }
      activeEditorId = null;
      model.set("simplify_request", {
        line_id: block.id,
        action,
        revision: ++calculationRequestRevision,
        snapshots,
      });
      model.save_changes();
    }
    wrapper._requestCalculation = requestCalculation;
    cancelCalculationButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      calculationPending.hidden = true;
      cancelCalculation(block);
    });

    wrapper.addEventListener('keydown', event => {
      if (event.defaultPrevented || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey
          || !['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)
          || event.target.closest('.birdtracks-whiteboard-embedded-projector')) return;
      const horizontal = event.key === 'ArrowLeft' || event.key === 'ArrowRight';
      const backwards = event.key === 'ArrowUp' || event.key === 'ArrowLeft';
      const editing = event.target === editor;
      if (editing && horizontal && (editor.selectionStart !== editor.selectionEnd
          || (backwards ? editor.selectionStart !== 0 : editor.selectionEnd !== editor.value.length))) return;
      const wrappers = [...list.children];
      const next = wrappers[wrappers.indexOf(wrapper) + (backwards ? -1 : 1)];
      if (!next) return;
      event.preventDefault();
      event.stopPropagation();
      const target = next.querySelector('textarea');
      if (target && !target.disabled) {
        const position = horizontal ? (backwards ? target.value.length : 0)
          : Math.min(editing ? editor.selectionStart : 0, target.value.length);
        target.focus();
        target.setSelectionRange(position, position);
        target.dispatchEvent(new Event('select'));
      } else next.querySelector('.birdtracks-whiteboard-rendered')?.focus();
    }, true);

    wrapper.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        requestCalculation("evaluate");
        return;
      }
      if (!block.read_only || event.key !== "Backspace" || !event.shiftKey) return;
      event.preventDefault();
      event.stopPropagation();
      requestCalculation("restore");
    }, true);

    function embeddedKey(index) {
      return `${block.id}:projector:${index}`;
    }

    function pairKey(index) {
      return block.id + ":pair:" + index;
    }

    function projectorMarkers(source) {
      const markers = [];
      // A projector is one atomic source symbol.
      const pattern = /\\birdtracks\b/g;
      let match;
      let occurrence = 0;
      while ((match = pattern.exec(source)) !== null) {
        markers.push({
          start: match.index,
          end: pattern.lastIndex,
          id: embeddedKey(occurrence),
          prefactor: numericPrefactorBefore(source, match.index),
          kind: "explicit",
        });
        occurrence += 1;
      }
      return markers;
    }

    function pairMarkers(source) {
      const markers = [];
      const pattern = /\\pair\b(?!\s*\{)/g;
      let match;
      let occurrence = 0;
      while ((match = pattern.exec(source)) !== null) {
        markers.push({
          start: match.index,
          end: pattern.lastIndex,
          id: pairKey(occurrence),
          prefactor: numericPrefactorBefore(source, match.index),
          kind: "pair",
        });
        occurrence += 1;
      }
      return markers;
    }

    function backendMarkers(source) {
      const currentBlock = (model.get("blocks") || [])
        .find((item) => item.id === block.id) || block;
      const placeholders = [...source.matchAll(/R/g)].map((match) => match.index);
      return (currentBlock.backend_terms || [])
        .filter((term) => term && term.id)
        .map((term, index) => {
          let start = Number(term.start);
          let end = Number(term.end);
          // Older calculated rows could gain a relative minus after these
          // offsets were recorded. Recover their one-character placeholder
          // by term order so the persisted row remains renderable.
          if (source.slice(start, end) !== "R"
              && placeholders[index] !== undefined) {
            start = placeholders[index];
            end = start + 1;
          }
          return {
            start,
            end,
            id: String(term.id),
            kind: "backend",
            prefactor: Boolean(term.prefactor_owned),
          };
        })
        .filter((marker) => Number.isInteger(marker.start)
          && Number.isInteger(marker.end)
          && marker.start >= 0
          && marker.end > marker.start
          && marker.end <= source.length);
    }

    function markerContaining(index) {
      return sourceMarkers.find((marker) => (
        index > marker.start && index < marker.end
      )) || null;
    }

    function activeProjectorMarker(index) {
      return sourceMarkers.find((marker) => (
        index >= marker.start
        && (index < marker.end
          || (index === marker.end && editor.value[marker.end - 1] === "{"))
      )) || null;
    }

    function snapCaretOutOfProjector(direction = 0) {
      if (editor.selectionStart !== editor.selectionEnd) return;
      const marker = markerContaining(editor.selectionStart);
      if (!marker) return;
      const index = direction < 0 || (
        direction === 0 && editor.selectionStart - marker.start
          <= marker.end - editor.selectionStart
      ) ? marker.start : marker.end;
      editor.setSelectionRange(index, index);
    }

    function embeddedMarkerAnchor(marker, index) {
      const projectorId = marker.id || embeddedKey(index);
      const anchor = embeddedAnchors.get(projectorId) || document.createElement("span");
      embeddedAnchors.set(projectorId, anchor);
      anchor.classList.add("birdtracks-whiteboard-embedded-projector");
      anchor.classList.toggle(
        "birdtracks-whiteboard-embedded-pair",
        marker.kind === "pair",
      );
      anchor.tabIndex = 0;
      anchor.dataset.projectorId = projectorId;
      anchor.dataset.sourceStart = String(marker.start);
      anchor.dataset.sourceEnd = String(marker.end);
      anchor.setAttribute(
        "aria-label",
        marker.kind === "pair" ? "Embedded pair editor" : "Embedded projector editor",
      );
      return anchor;
    }

    function markerDisplayStart(marker) {
      return marker.kind === "pair" && marker.prefactor
        ? marker.prefactor.start
        : marker.start;
    }

    function reflowPairCalculation() {
      const svg = rendered.querySelector(
        ":scope > .birdtracks-pair-evaluation-line[data-natural-width]",
      );
      if (!svg) return;
      rendered.classList.add("pair-wrapping");
      const tokens = [...svg.querySelectorAll(":scope > [data-pair-token]")];
      const naturalWidth = Number(svg.dataset.naturalWidth);
      const lineHeight = Number(svg.dataset.lineHeight);
      const available = Math.max(1, rendered.clientWidth);
      if (!tokens.length || !Number.isFinite(naturalWidth)
          || !Number.isFinite(lineHeight)) return;

      for (const token of tokens) token.removeAttribute("transform");
      if (naturalWidth <= available) {
        svg.setAttribute("width", String(naturalWidth));
        svg.setAttribute("height", String(lineHeight));
        svg.setAttribute("viewBox", `0 0 ${naturalWidth} ${lineHeight}`);
        return;
      }

      const equals = tokens.find(token => token.dataset.pairToken === "equals");
      const firstPair = tokens.find(token => token.dataset.pairToken === "pair");
      const indent = equals
        ? Number(equals.dataset.tokenX) + Number(equals.dataset.tokenWidth) + 2
        : Number(firstPair?.dataset.tokenX || 2);
      const rowGap = 8;
      let row = 0;
      let shiftX = 0;
      let pairsOnRow = 0;
      for (let index = 0; index < tokens.length; index += 1) {
        const token = tokens[index];
        const x = Number(token.dataset.tokenX);
        const width = Number(token.dataset.tokenWidth);
        if (token.dataset.pairToken === "pair"
            && pairsOnRow > 0 && x + shiftX + width > available) {
          let breakAt = index;
          if (["sum", "tensor"].includes(tokens[index - 1]?.dataset.pairToken)) {
            breakAt -= 1;
          }
          row += 1;
          shiftX = indent - Number(tokens[breakAt].dataset.tokenX);
          pairsOnRow = 0;
          for (let moved = breakAt; moved < index; moved += 1) {
            tokens[moved].setAttribute(
              "transform", `translate(${shiftX} ${row * (lineHeight + rowGap)})`,
            );
          }
        }
        token.setAttribute(
          "transform", `translate(${shiftX} ${row * (lineHeight + rowGap)})`,
        );
        if (token.dataset.pairToken === "pair") pairsOnRow += 1;
      }
      const wrappedHeight = (row + 1) * lineHeight + row * rowGap;
      svg.setAttribute("width", String(available));
      svg.setAttribute("height", String(wrappedHeight));
      svg.setAttribute("viewBox", `0 0 ${available} ${wrappedHeight}`);
    }

    function renderSource(source, editingIndex = null) {
      // Replacing wide embedded content does not reliably reset an overflow
      // container's scroll position.  A stale scroll offset feeds directly
      // into continuation alignment and can produce enormous left padding.
      rendered.scrollLeft = 0;
      rendered.replaceChildren();
      rendered.classList.remove("pair-wrapping");
      if (block.calculation_svg) {
        rendered.innerHTML = block.calculation_svg;
        const styles = block.calculation_cell_styles || {};
        for (const cell of rendered.querySelectorAll("[data-cell]")) {
          const box = cell.firstElementChild;
          const style = styles[cell.dataset.cell];
          if (!box || !style || typeof style !== "object") continue;
          for (const [property, value] of Object.entries(style)) {
            if (typeof value !== "string") continue;
            if (["fill", "stroke", "strokeWidth", "strokeDasharray",
              "strokeLinecap", "strokeLinejoin"].includes(property)) {
              box.style[property] = value;
            }
          }
        }
        reflowPairCalculation();
        requestAnimationFrame(reflowPairCalculation);
        sourceMarkers = [];
        rendered.classList.remove("error");
        positionCaret();
        return;
      }
      const markers = [
        ...projectorMarkers(source),
        ...pairMarkers(source),
        ...backendMarkers(source),
      ]
        .sort((left, right) => left.start - right.start || left.end - right.end);
      for (const marker of markers) {
        if (marker.kind !== "explicit") continue;
        let groupStart = marker.end;
        while (groupStart < source.length && /\s/.test(source[groupStart])) groupStart += 1;
        if (source[groupStart] === "{" && groupEnd(source, groupStart) === null) {
          throw new Error("unclosed projector group");
        }
      }
      const displayStart = continuationPrefixLength(source);
      let fraction = editingIndex === null
        ? null : fractionRangeAt(source, editingIndex);
      if (!fraction && editingIndex !== null && editingIndex > 0) {
        fraction = fractionRangeAt(source, editingIndex - 1);
      }
      if (!fraction && editingIndex !== null && activeFraction?.source === source
          && editingIndex >= activeFraction.range.start
          && editingIndex < activeFraction.range.end) {
        fraction = activeFraction.range;
      }
      activeFraction = fraction ? {source, range: fraction} : null;
      const effectiveEditingIndex = fraction ? fraction.start : editingIndex;
      sourceMarkers = markers;
      const activeIds = new Set(
        markers.map((marker, index) => marker.id || embeddedKey(index)),
      );
      for (const [id, listener] of embeddedProjectorListeners) {
        if (activeIds.has(id)) continue;
        const anchor = embeddedAnchors.get(id);
        anchor?._birdtracksCleanup?.();
        if (anchor) {
          anchor._birdtracksCleanup = null;
          delete anchor._birdtracksProjectorReference;
        }
        embeddedModels.get(id)?.off(
          "change:port_orders change:graph change:boundary_orders", listener,
        );
        embeddedModels.delete(id);
        embeddedAnchors.delete(id);
        embeddedProjectorListeners.delete(id);
        embeddedProjectorSigns.delete(id);
      }
      wrapper.classList.toggle("has-embedded-projector", markers.length > 0);
      editor.style.pointerEvents = "auto";
      editor.style.zIndex = markers.length ? "0" : "2";
      if (!markers.length) {
        renderLatex(
          source.slice(displayStart), rendered, displayStart, effectiveEditingIndex,
        );
        scheduleContinuationAlignment();
        positionCaret();
        return;
      }
      let position = displayStart;
      let previousMarker = null;
      markers.forEach((marker, index) => {
        const visibleStart = markerDisplayStart(marker);
        const implicitTensor = previousMarker?.kind === "pair"
          && marker.kind === "pair"
          && /^\s*$/.test(source.slice(previousMarker.end, visibleStart));
        if (visibleStart > position) {
          const prefix = document.createElement("span");
          renderLatex(
            source.slice(position, visibleStart),
            prefix,
            position,
            effectiveEditingIndex,
          );
          rendered.appendChild(prefix);
        }
        if (implicitTensor) {
          // Pair juxtaposition is an implicit tensor product in the backend;
          // keep that operation visible even when the source omits \otimes.
          rendered.appendChild(pairOperatorElement(
            "tensor", previousMarker.end, marker.start,
          ));
        }
        const anchor = embeddedMarkerAnchor(marker, index);
        rendered.appendChild(anchor);
        position = marker.end;
        previousMarker = marker;
      });
      if (position < source.length) {
        const suffix = document.createElement("span");
        renderLatex(source.slice(position), suffix, position, effectiveEditingIndex);
        rendered.appendChild(suffix);
      }
      mountEmbeddedProjectors();
      scheduleContinuationAlignment();
      positionCaret();
    }

    function sourceElementEdge(element, end) {
      const textNodes = [];
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) textNodes.push(walker.currentNode);
      const textNode = end ? textNodes[textNodes.length - 1] : textNodes[0];
      if (textNode) {
        const range = document.createRange();
        range.setStart(textNode, end ? textNode.length : 0);
        range.collapse(true);
        const rangeBox = range.getBoundingClientRect();
        if (rangeBox.width || rangeBox.height) return rangeBox.left;
      }
      const box = element.getBoundingClientRect();
      return end ? box.right : box.left;
    }

    function operatorTrailingSpace(element) {
      const value = element.getAttribute("rspace");
      const match = value?.match(/^([0-9.]+)(em|px)$/);
      if (!match) return 0;
      const amount = Number(match[1]);
      if (match[2] === "px") return amount;
      return amount * (parseFloat(getComputedStyle(element).fontSize) || 0);
    }

    function sourceCaretX(sourceIndex) {
      const elements = [...rendered.querySelectorAll("[data-source-start]")]
        .map((element) => ({
          element,
          start: Number(element.dataset.sourceStart),
          end: Number(element.dataset.sourceEnd),
        }))
        .filter(({start, end}) => (
          Number.isInteger(start) && Number.isInteger(end) && end >= start
        ));
      const ending = elements
        .filter(({end}) => end === sourceIndex)
        .sort((left, right) => (
          (left.end - left.start) - (right.end - right.start)
        ));
      const starting = elements
        .filter(({start}) => start === sourceIndex)
        .sort((left, right) => (
          (left.end - left.start) - (right.end - right.start)
        ));
      if (ending.length && starting.length
          && ending[0].element.localName === "mo") {
        return sourceElementEdge(starting[0].element, false);
      }
      if (starting.length) return sourceElementEdge(starting[0].element, false);
      if (ending.length && ending[0].element.localName === "mo") {
        return sourceElementEdge(ending[0].element, true)
          + operatorTrailingSpace(ending[0].element);
      }
      if (ending.length) return sourceElementEdge(ending[0].element, true);
      const containing = elements
        .filter(({start, end}) => start < sourceIndex && sourceIndex < end)
        .sort((left, right) => (
          (left.end - left.start) - (right.end - right.start)
        ))[0];
      if (!containing) return null;
      const text = containing.element.firstChild;
      if (text?.nodeType === Node.TEXT_NODE
          && text.length === containing.end - containing.start) {
        const range = document.createRange();
        range.setStart(text, sourceIndex - containing.start);
        range.collapse(true);
        return range.getBoundingClientRect().left;
      }
      const box = containing.element.getBoundingClientRect();
      const fraction = (sourceIndex - containing.start)
        / (containing.end - containing.start);
      return box.left + box.width * fraction;
    }

    function moveCaretAcrossRenderedSymbol(direction) {
      if (editor.selectionStart !== editor.selectionEnd
          || rendered.querySelector(".birdtracks-whiteboard-fraction-source")) {
        return false;
      }
      const symbols = [...rendered.querySelectorAll("[data-source-start]")]
        .filter((element) => !element.parentElement?.closest(
          "[data-source-start]",
        ))
        .map((element) => ({
          start: Number(element.dataset.sourceStart),
          end: Number(element.dataset.sourceEnd),
        }))
        .filter(({start, end}) => (
          Number.isInteger(start) && Number.isInteger(end) && end > start
        ))
        .sort((left, right) => left.start - right.start);
      const index = editor.selectionStart;
      const continuationLength = continuationPrefixLength(editor.value);
      let symbol;
      if (direction > 0) {
        symbol = continuationLength && index < continuationLength
          ? symbols.find(({start}) => start >= continuationLength)
          : symbols.find(({start, end}) => start <= index && index < end)
          || symbols.find(({start}) => start >= index);
        if (!symbol || symbol.end === index) return false;
        editor.setSelectionRange(symbol.end, symbol.end);
      } else {
        symbol = [...symbols].reverse().find(({start, end}) => (
          start < index && index <= end
        )) || [...symbols].reverse().find(({end}) => end <= index);
        if (!symbol || symbol.start === index) return false;
        editor.setSelectionRange(symbol.start, symbol.start);
      }
      caretNavigationDirection = 0;
      updateSelection();
      return true;
    }

    function positionCaret() {
      const lineHeight = parseFloat(getComputedStyle(editor).lineHeight) || 22;
      const renderedHeight = rendered.getBoundingClientRect().height;
      const hasEmbeddedProjector = wrapper.classList.contains(
        "has-embedded-projector",
      );
      editor.style.paddingTop = `${hasEmbeddedProjector
        ? Math.max(editorBasePaddingTop, (renderedHeight - lineHeight) / 2)
        : editorBasePaddingTop}px`;
      const focused = document.activeElement === editor && !editor.hidden;
      const renderedSource = rendered.querySelector("[data-source-start]");
      const sourceX = sourceCaretX(editor.selectionStart);
      const clickedX = caretPoint?.sourceIndex === editor.selectionStart
        ? caretPoint.x : null;
      const useCustomCaret = focused
        && renderedSource !== null
        && editor.selectionStart === editor.selectionEnd
        && (sourceX !== null || clickedX !== null);
      caret.hidden = !useCustomCaret;
      editor.style.caretColor = useCustomCaret ? "transparent" : "#17202a";
      if (!useCustomCaret) return;
      const renderedBox = rendered.getBoundingClientRect();
      const wrapperBox = wrapper.getBoundingClientRect();
      const visualLineTop = renderedBox.top
        + Math.max(0, (renderedBox.height - lineHeight) / 2);
      caret.style.left = `${(clickedX ?? sourceX) - wrapperBox.left}px`;
      caret.style.top = `${visualLineTop - wrapperBox.top}px`;
      caret.style.height = `${Math.max(lineHeight, 22)}px`;
    }

    function fractionSourceIndexAtPoint(event) {
      if (!activeFraction?.source || activeFraction.source !== editor.value) return null;
      const sourceElement = rendered.querySelector(
        ".birdtracks-whiteboard-fraction-source",
      );
      const textNode = sourceElement?.firstChild;
      if (!sourceElement || !textNode || textNode.nodeType !== Node.TEXT_NODE) return null;
      const box = sourceElement.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right
          || event.clientY < box.top || event.clientY > box.bottom) return null;

      let offset = null;
      const position = document.caretPositionFromPoint?.(
        event.clientX, event.clientY,
      );
      if (position?.offsetNode === textNode) offset = position.offset;
      if (offset === null) {
        const range = document.caretRangeFromPoint?.(
          event.clientX, event.clientY,
        );
        if (range?.startContainer === textNode) offset = range.startOffset;
      }
      if (offset === null) {
        let closestDistance = Infinity;
        for (let index = 0; index <= textNode.length; index += 1) {
          const range = document.createRange();
          range.setStart(textNode, index);
          range.collapse(true);
          const caretBox = range.getBoundingClientRect();
          const distance = Math.abs(event.clientX - caretBox.left);
          if (distance < closestDistance) {
            closestDistance = distance;
            offset = index;
          }
        }
      }
      if (offset === null) return null;
      return Math.max(
        activeFraction.range.start,
        Math.min(activeFraction.range.end, activeFraction.range.start + offset),
      );
    }

    if (typeof ResizeObserver !== "undefined") {
      const caretResizeObserver = new ResizeObserver(() => {
        reflowPairCalculation();
        if (document.activeElement !== editor) return;
        requestAnimationFrame(positionCaret);
      });
      caretResizeObserver.observe(rendered);
    }

    function snapSelectionToRenderedPoint(event) {
      const fractionSourceIndex = fractionSourceIndexAtPoint(event);
      if (fractionSourceIndex !== null) {
        editor.setSelectionRange(fractionSourceIndex, fractionSourceIndex);
        caretPoint = null;
        updateSelection();
        return;
      }
      editor.style.pointerEvents = "none";
      const visualTarget = document.elementFromPoint(event.clientX, event.clientY);
      editor.style.pointerEvents = "auto";
      const atoms = [...rendered.querySelectorAll("[data-source-start]")];
      const fractions = [...rendered.querySelectorAll("mfrac")]
        .map((element) => ({element, box: element.getBoundingClientRect()}))
        .filter(({box}) => (
          event.clientX >= box.left && event.clientX <= box.right
          && event.clientY >= box.top && event.clientY <= box.bottom
        ))
        .sort((left, right) => (
          (left.box.width * left.box.height) - (right.box.width * right.box.height)
        ));
      let scopedAtoms = atoms;
      const fraction = fractions[0];
      if (fraction) {
        const parts = [...fraction.element.children]
          .filter((element) => element.hasAttribute("data-source-start"));
        const part = parts
          .filter((element) => {
            const box = element.getBoundingClientRect();
            return event.clientY >= box.top && event.clientY <= box.bottom;
          })
          .sort((left, right) => {
            const leftBox = left.getBoundingClientRect();
            const rightBox = right.getBoundingClientRect();
            return Math.abs(
              event.clientY - (leftBox.top + leftBox.height / 2),
            ) - Math.abs(
              event.clientY - (rightBox.top + rightBox.height / 2),
            );
          })[0] || parts[
            event.clientY < fraction.box.top + fraction.box.height / 2 ? 0 : 1
          ];
        if (part) scopedAtoms = atoms.filter((element) => part.contains(element));
      }
      const visualSourceElement = visualTarget?.closest?.("[data-source-start]");
      const candidates = scopedAtoms
        .map((element) => ({
          element,
          box: element.getBoundingClientRect(),
          span: Number(element.dataset.sourceEnd)
            - Number(element.dataset.sourceStart),
          isTarget: element === visualSourceElement
            && !element.querySelector("[data-source-start]"),
        }))
        .filter(({box}) => event.clientY >= box.top && event.clientY <= box.bottom)
        .sort((left, right) => {
          if (left.isTarget !== right.isTarget) return left.isTarget ? -1 : 1;
          const leftDistance = Math.max(
            left.box.left - event.clientX,
            0,
            event.clientX - left.box.right,
          );
          const rightDistance = Math.max(
            right.box.left - event.clientX,
            0,
            event.clientX - right.box.right,
          );
          return leftDistance - rightDistance || left.span - right.span;
          });
      const candidate = candidates[0] || (scopedAtoms.includes(visualSourceElement)
        ? {element: visualSourceElement, box: visualSourceElement.getBoundingClientRect()}
        : null);
      const atom = candidate?.element;
      if (!atom || !candidate) return;
      const start = Number(atom.dataset.sourceStart);
      const end = Number(atom.dataset.sourceEnd);
      if (!Number.isInteger(start) || !Number.isInteger(end)) return;
      const box = candidate.box;
      const atEnd = event.clientX >= box.left + box.width / 2;
      const sourceIndex = atEnd ? end : start;
      editor.setSelectionRange(sourceIndex, sourceIndex);
      caretPoint = {
        x: sourceElementEdge(atom, atEnd),
        y: event.clientY,
        sourceIndex,
      };
      updateSelection();
    }

    async function mountEmbeddedProjectors() {
      if (disposed) return;
      const ids = [
        ...(model.get("embedded_projector_ids") || []),
        ...(model.get("embedded_pair_ids") || []),
        ...(model.get("backend_projector_ids") || []),
      ];
      const widgets = [
        ...(model.get("embedded_projectors") || []),
        ...(model.get("embedded_pairs") || []),
        ...(model.get("backend_projectors") || []),
      ];
      const anchors = rendered.querySelectorAll(
        ".birdtracks-whiteboard-embedded-projector, .birdtracks-whiteboard-embedded-pair",
      );
      for (const anchor of anchors) {
        const index = ids.indexOf(anchor.dataset.projectorId);
        const reference = index < 0 ? null : widgets[index];
        if (!reference || !host?.getWidget) {
          anchor._birdtracksMounted = false;
          anchor.replaceChildren();
          continue;
        }
        if (anchor._birdtracksProjectorReference === reference) {
          updateEmbeddedModesForCaret();
          continue;
        }
        anchor._birdtracksCleanup?.();
        anchor.replaceChildren();
        anchor._birdtracksProjectorReference = reference;
        try {
          const childModel = await host.getModel(reference);
          if (disposed) return;
          embeddedModels.set(anchor.dataset.projectorId, childModel);
          const marker = sourceMarkers.find((item, markerIndex) => (
            (item.id || embeddedKey(markerIndex)) === anchor.dataset.projectorId
          ));
          if (marker?.kind === "pair") {
            if (childModel.get("read_only") !== Boolean(block.read_only)) {
              childModel.set("read_only", Boolean(block.read_only));
              childModel.save_changes();
            }
            const child = await host.getWidget(reference);
            anchor._birdtracksCleanup = await child.render({ el: anchor, signal });
            anchor._birdtracksMounted = true;
            positionCaret();
            continue;
          }
          const markerIndex = sourceMarkers.findIndex((marker, markerIndex) => (
            (marker.id || embeddedKey(markerIndex)) === anchor.dataset.projectorId
          ));
          const prefactorOwned = markerIndex >= 0
            && Boolean(sourceMarkers[markerIndex].prefactor);
          if (childModel.get("prefactor_owned") !== prefactorOwned) {
            childModel.set("prefactor_owned", prefactorOwned);
            childModel.save_changes();
          }
          if (!embeddedProjectorListeners.has(anchor.dataset.projectorId)) {
            const projectorId = anchor.dataset.projectorId;
            const onProjectorChange = () => {
              const sign = projectorOrientationSign(
                childModel.get("graph"),
                childModel.get("port_orders"),
              );
              const previous = embeddedProjectorSigns.get(projectorId);
              embeddedProjectorSigns.set(projectorId, sign);
              if (previous === undefined || previous === sign) return;
              const markerIndex = sourceMarkers.findIndex((marker, index) => (
                (marker.id || embeddedKey(index)) === projectorId
              ));
              const marker = markerIndex < 0 ? null : sourceMarkers[markerIndex];
              if (marker?.kind === "pair" || !marker?.prefactor) return;
              const nextSource = flipNumericPrefactor(editor.value, marker.start);
              if (nextSource === null) return;
              editor.value = nextSource;
              updateSource(nextSource);
            };
            if (!embeddedProjectorSigns.has(projectorId)) {
              embeddedProjectorSigns.set(
                projectorId,
                projectorOrientationSign(
                  childModel.get("graph"),
                  childModel.get("port_orders"),
                ),
              );
            }
            embeddedProjectorListeners.set(projectorId, onProjectorChange);
            childModel.on(
              "change:port_orders change:graph change:boundary_orders",
              onProjectorChange,
            );
            onProjectorChange();
          }
          anchor.addEventListener("pointerdown", (event) => {
            event.stopPropagation();
            caretPoint = null;
            caret.hidden = true;
            editor.style.caretColor = "#17202a";
            updateEmbeddedModesForCaret();
          });
          const child = await host.getWidget(reference);
          anchor._birdtracksCleanup = await child.render({ el: anchor, signal });
          anchor._birdtracksMounted = true;
          updateEmbeddedModesForCaret();
          positionCaret();
        } catch (error) {
          anchor._birdtracksMounted = true;
          delete anchor.dataset.projectorReference;
          anchor.textContent = error.message;
          anchor.classList.add("error");
        }
        scheduleContinuationAlignment();
      }
      const projectors = [...anchors].filter((anchor) => (
        anchor.classList.contains("birdtracks-whiteboard-embedded-projector")
      ));
      if (pendingRevealBlockId === block.id
          && projectors.length
          && projectors.every((anchor) => anchor._birdtracksMounted)) {
        pendingRevealScroller.scrollTop = pendingRevealScrollTop;
        revealGeneratedBlock(pendingRevealBlockId, pendingRevealScroller);
        pendingRevealBlockId = null;
        pendingRevealScroller = null;
        pendingRevealScrollTop = null;
      }
    }

    function updateEmbeddedModesForCaret() {
      const current = (model.get("blocks") || []).find((item) => item.id === block.id) || block;
      for (const [id, childModel] of embeddedModels) {
        if (!id.startsWith(`${block.id}:`)) continue;
        const mode = !current.read_only && id.startsWith(`${block.id}:projector:`)
          ? "create" : "evaluate";
        if (childModel.get("mode") !== mode) {
          childModel.set("mode", mode);
          childModel.save_changes();
        }
      }
    }
    rendered._birdtracksMountEmbeddedProjectors = mountEmbeddedProjectors;

    function updateSource(source, editingIndex = null) {
      const currentBlocks = model.get("blocks") || [];
      const blockIndex = currentBlocks.findIndex((item) => item.id === block.id);
      const previous = blockIndex > 0 ? currentBlocks[blockIndex - 1] : null;
      const lineId = isContinuationSource(source) && previous
        ? blockLineId(previous)
        : block.id;
      if (blockIndex < 0) {
        if (source === "") return;
      } else if (currentBlocks[blockIndex].source === source
          && blockLineId(currentBlocks[blockIndex]) === lineId) {
        wrapper.classList.toggle("continuation", isContinuationSource(source));
        rendered.hidden = false;
        if (!rendered.querySelector(".birdtracks-whiteboard-embedded-projector")) {
          renderSource(source, editingIndex);
          scheduleContinuationAlignment();
        }
        return;
      }
      const blocks = blockIndex < 0
        ? [...currentBlocks, (() => {
          const persistedBlock = { ...block };
          delete persistedBlock._trailing_blank;
          return { ...persistedBlock, source, line_id: lineId };
        })()]
        : currentBlocks.map((item) => (
          item.id === block.id
            ? {
              ...discardRemovedEmbeddedSnapshots(
                item, String(item.source || ""), source,
              ),
              source,
              line_id: lineId,
            }
            : item
        ));
      wrapper.classList.toggle("continuation", isContinuationSource(source));
      locallyUpdatingBlockId = block.id;
      try {
        model.set("blocks", blocks);
        model.save_changes();
      } finally {
        locallyUpdatingBlockId = null;
      }
      if (disposed) return;
      rendered.hidden = false;
      try {
        renderSource(source, editingIndex);
        scheduleContinuationAlignment();
        lastValidSource = source;
        rendered.classList.remove("error");
      } catch (error) {
        renderInvalidSource(source, error);
        rendered.classList.add("error");
      }
    }

    function renderInvalidSource(source, error) {
      rendered.scrollLeft = 0;
      rendered.replaceChildren();
      const markers = [
        ...projectorMarkers(source),
        ...pairMarkers(source),
      ].sort((left, right) => left.start - right.start || left.end - right.end);
      wrapper.classList.toggle("has-embedded-projector", markers.length > 0);
      editor.style.pointerEvents = "auto";
      editor.style.zIndex = markers.length ? "0" : "2";
      const invalid = document.createElement("span");
      invalid.className = "birdtracks-whiteboard-invalid-source";
      invalid.dataset.sourceStart = "0";
      invalid.dataset.sourceEnd = String(source.length);
      invalid.title = error.message;
      invalid.setAttribute("aria-label", `${source}: ${error.message}`);
      let position = 0;
      markers.forEach((marker, index) => {
        const visibleStart = markerDisplayStart(marker);
        if (visibleStart > position) {
          invalid.appendChild(document.createTextNode(source.slice(position, visibleStart)));
        }
        invalid.appendChild(embeddedMarkerAnchor(marker, index));
        position = marker.end;
      });
      if (position < source.length) {
        invalid.appendChild(document.createTextNode(source.slice(position)));
      }
      if (!markers.length) invalid.textContent = source;
      rendered.appendChild(invalid);
      sourceMarkers = markers;
      mountEmbeddedProjectors();
      positionCaret();
    }

    function splitAtEnter(event) {
      if (event.key !== "Enter") return;
      event.preventDefault();
      event.stopPropagation();
      const currentBlocks = model.get("blocks") || [];
      const blockIndex = currentBlocks.findIndex((item) => item.id === block.id);
      if (blockIndex < 0) return;
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      const before = editor.value.slice(0, start);
      const after = editor.value.slice(end);
      const previousLineId = blockLineId(currentBlocks[blockIndex]);
      const newId = nextBlockId(currentBlocks);
      const lineId = isContinuationSource(after) && previousLineId
        ? previousLineId
        : newId;
      const updatedBlock = {
        ...currentBlocks[blockIndex],
        source: before,
        line_id: blockLineId(currentBlocks[blockIndex]),
      };
      const newBlock = { id: newId, source: after, line_id: lineId };
      let blocks = [
        ...currentBlocks.slice(0, blockIndex),
        updatedBlock,
        newBlock,
        ...currentBlocks.slice(blockIndex + 1),
      ];
      activeEditorId = null;
      // Enter is the whiteboard's explicit source-edit checkpoint. Save every
      // mounted embedded canvas here, not just the line being split: a user
      // may have drawn a previous definition and then continued elsewhere
      // before pressing Enter.
      const snapshots = saveEmbeddedState(currentBlocks);
      blocks = storeEmbeddedSnapshots(blocks, snapshots);
      model.set("blocks", blocks);
      model.save_changes();
      focusBlock(newId, 0, false, true);
    }

    function handleBackspace(event) {
      if (event.key !== "Backspace") return;
      if (editor.selectionStart !== editor.selectionEnd) return;
      const marker = sourceMarkers.find((item) => (
        editor.selectionStart >= item.start
        && editor.selectionStart <= item.end
      ));
      if (!marker) return;
      event.preventDefault();
      editor.setRangeText("", marker.start, marker.end, "start");
      editor.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function mergeWithPreviousBlock(event) {
      if (event.key !== "Backspace") return;
      if (editor.selectionStart !== 0 || editor.selectionEnd !== 0) return;
      const currentBlocks = model.get("blocks") || [];
      const blockIndex = currentBlocks.findIndex((item) => item.id === block.id);
      if (blockIndex <= 0) return;
      const previous = currentBlocks[blockIndex - 1];
      if (previous.read_only) return;
      const currentSource = editor.value;
      const continuationLength = continuationPrefixLength(currentSource);
      const mergedSource = (previous.source || "")
        + currentSource.slice(continuationLength);
      const merged = currentBlocks.map((item, index) => {
        if (index === blockIndex - 1) {
          return {
            ...item,
            source: mergedSource,
            line_id: blockLineId(item),
          };
        }
        return item;
      }).filter((_item, index) => index !== blockIndex);
      event.preventDefault();
      event.stopPropagation();
      activeEditorId = null;
      model.set("blocks", merged);
      model.save_changes();
      focusBlock(previous.id, 0, true);
    }

    function showRendered() {
      const source = editor.value;
      updateSource(source);
      rendered.hidden = false;
      wrapper.classList.remove("editing");
      activeEditorId = null;
      caret.hidden = true;
      caretPoint = null;
      updateEmbeddedModesForCaret();
    }

    function showEditor() {
      if (block.read_only) return;
      if (pendingFocusBlockId !== null && pendingFocusBlockId !== block.id) {
        pendingFocusBlockId = null;
        if (pendingFocusTimer !== null) {
          clearTimeout(pendingFocusTimer);
          pendingFocusTimer = null;
        }
      }
      activeEditorId = block.id;
      editor.hidden = false;
      rendered.hidden = false;
      rendered.classList.remove("error");
      wrapper.classList.add("editing");
      try {
        // Keep the typeset fraction available until pointerup maps the click
        // to its numerator or denominator. Keyboard/programmatic focus can
        // still reveal the source immediately.
        if (caretPoint === null) renderSource(editor.value, editor.selectionStart);
        lastValidSource = editor.value;
      } catch (error) {
        renderInvalidSource(editor.value, error);
        rendered.classList.add("error");
      }
      updateEmbeddedModesForCaret();
      positionCaret();
    }

    editor.addEventListener("focus", showEditor);
    editor.addEventListener("pointerdown", (event) => {
      caretPoint = { x: event.clientX, y: event.clientY };
      requestAnimationFrame(positionCaret);
    });
    editor.addEventListener("pointerup", snapSelectionToRenderedPoint);
    editor.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        requestCalculation("evaluate");
        return;
      }
      if (event.key === "Backspace" && event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        requestCalculation("restore");
        return;
      }
      if (event.key === "Enter") {
        splitAtEnter(event);
        return;
      }
      caretPoint = null;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        caretNavigationDirection = event.key === "ArrowLeft" ? -1 : 1;
        if (editor.selectionStart === editor.selectionEnd) {
          const marker = markerContaining(editor.selectionStart);
          const enteringRight = event.key === "ArrowRight"
            && marker && editor.selectionStart >= marker.start
            && editor.selectionStart < marker.end;
          const enteringLeft = event.key === "ArrowLeft"
            && marker && editor.selectionStart > marker.start
            && editor.selectionStart <= marker.end;
          if (enteringRight || enteringLeft) {
            event.preventDefault();
            const index = event.key === "ArrowLeft" ? marker.start : marker.end;
            editor.setSelectionRange(index, index);
            updateSelection();
            return;
          }
        }
        if (moveCaretAcrossRenderedSymbol(event.key === "ArrowLeft" ? -1 : 1)) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
      }
      if (event.key === "Backspace") {
        handleBackspace(event);
        if (event.defaultPrevented) return;
        mergeWithPreviousBlock(event);
        if (event.defaultPrevented) return;
      }
      if (event.key !== "Tab" || editor.selectionStart !== editor.selectionEnd) return;
      const before = editor.value.slice(0, editor.selectionStart);
      const suggestion = projectorCommandSuggestion(before);
      if (!suggestion || !suggestion.completion) return;
      event.preventDefault();
      editor.setRangeText(
        suggestion.completion,
        suggestion.start + suggestion.typed.length,
        editor.selectionEnd,
        "end",
      );
      editor.dispatchEvent(new Event("input", { bubbles: true }));
    });
    editor.addEventListener("input", () => {
      caretPoint = null;
      activeFraction = null;
      updateSource(editor.value, editor.selectionStart);
      requestAnimationFrame(() => {
        if (document.activeElement !== editor) return;
        updateEmbeddedModesForCaret();
        positionCaret();
        requestAnimationFrame(() => {
          if (document.activeElement === editor) positionCaret();
        });
      });
    });
    const updateSelection = () => {
      snapCaretOutOfProjector(caretNavigationDirection);
      caretNavigationDirection = 0;
      updateEmbeddedModesForCaret();
      try {
        renderSource(editor.value, editor.selectionStart);
        rendered.classList.remove("error");
      } catch (error) {
        renderInvalidSource(editor.value, error);
        rendered.classList.add("error");
      }
      positionCaret();
    };
    editor.addEventListener("keyup", (event) => {
      if (event.key === "Enter") event.stopPropagation();
      updateSelection();
    });
    editor.addEventListener("mouseup", updateSelection);
    editor.addEventListener("select", updateSelection);
    editor.addEventListener("blur", showRendered);
    function paintPairBox(event) {
      const state = paintbrushState;
      if (!state.active || !/^#[0-9a-f]{6}$/i.test(state.color)) return false;
      const cell = event.target.closest?.("[data-cell]");
      const line = cell?.closest?.(".birdtracks-pair-evaluation-line");
      const box = cell?.firstElementChild;
      if (!line || !rendered.contains(line) || box?.tagName?.toLowerCase() !== "rect") return false;
      const color = state.color.toLowerCase();
      box.style.fill = color;
      const cellKey = cell.dataset.cell;
      if (cellKey) {
        const blocks = (model.get("blocks") || []).map((item) => {
          if (item.id !== block.id) return item;
          const styles = structuredClone(item.calculation_cell_styles || {});
          styles[cellKey] = { ...(styles[cellKey] || {}), fill: color };
          return { ...item, calculation_cell_styles: styles };
        });
        model.set("blocks", blocks);
        model.save_changes();
      }
      state.record?.(color);
      event.preventDefault();
      event.stopPropagation();
      return true;
    }
    rendered.addEventListener("click", (event) => {
      if (paintPairBox(event)) return;
      if (event.target.closest?.(".birdtracks-whiteboard-embedded-projector")) return;
      if (block.read_only) {
        rendered.focus();
        return;
      }
      showEditor();
      editor.focus();
    });
    rendered.addEventListener("keydown", (event) => {
      if (block.pair_calculation && event.key === "Enter" && !event.ctrlKey
          && !event.metaKey && !event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        requestCalculation("evaluate");
        return;
      }
      if (block.read_only && event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        const blocks = [...(model.get('blocks') || [])];
        const related = blocks.map((item, index) => ({item, index}))
          .filter(({item}) => item.calculation_group === block.calculation_group);
        const index = event.ctrlKey ? related[0].index : related.at(-1).index + 1;
        const id = nextBlockId(blocks);
        blocks.splice(index, 0, {id, source: '', line_id: id});
        model.set('blocks', blocks);
        model.save_changes();
        focusBlock(id, 0, false, true);
        return;
      }
      if (event.key === "Backspace" && event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        requestCalculation("restore");
        return;
      }
      if (event.key === "Backspace") handleBackspace(event);
      if (event.defaultPrevented) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        showEditor();
        editor.focus();
      }
    });
    wrapper.append(editor, rendered, calculationPending, caret);
    list.appendChild(wrapper);
    editorBasePaddingTop = parseFloat(getComputedStyle(editor).paddingTop) || 0;
    try {
      renderSource(editor.value);
      lastValidSource = editor.value;
      // Keep the transparent textarea over ordinary rendered text. The
      // browser can then place its native caret exactly where the user clicks,
      // while the MathML below remains the visible representation.
      editor.hidden = false;
    } catch (error) {
      renderInvalidSource(editor.value, error);
      rendered.classList.add("error");
    }
    if (!block._trailing_blank && !editor.value && (model.get("blocks") || []).length === 1) {
      editor.autofocus = true;
      requestAnimationFrame(() => {
        if (!editor.isConnected || editor.value || title.matches(":focus")) return;
        editor.focus();
        editor.setSelectionRange(0, 0);
      });
    }
  }

  model.on("change:blocks", renderBlocks);
  const refreshEmbeddedProjectors = () => {
    if (activeEditorId === null) {
      renderBlocks();
      return;
    }
    for (const renderedBlock of list.querySelectorAll(
      ".birdtracks-whiteboard-rendered",
    )) {
      renderedBlock._birdtracksMountEmbeddedProjectors?.();
    }
  };
  model.on("change:embedded_projector_ids", refreshEmbeddedProjectors);
  model.on("change:embedded_projectors", refreshEmbeddedProjectors);
  model.on("change:backend_projector_ids", refreshEmbeddedProjectors);
  model.on("change:backend_projectors", refreshEmbeddedProjectors);
  model.on("change:embedded_pair_ids", refreshEmbeddedProjectors);
  model.on("change:embedded_pairs", refreshEmbeddedProjectors);

  renderBlocks();
  return () => {
    for (const renderedBlock of list.querySelectorAll(
      ".birdtracks-whiteboard-rendered",
    )) {
      renderedBlock._birdtracksCleanupBlock?.();
    }
    document.removeEventListener("pointerdown", selectProjector, true);
    document.removeEventListener("pointerdown", closeColorPanel, true);
    document.removeEventListener("keydown", calculationShortcut, true);
    root.removeEventListener("birdtracks-operator-expansion", operatorExpansion);
    document.removeEventListener("scroll", queueToolbarPositionUpdate, true);
    view.removeEventListener("resize", queueToolbarPositionUpdate);
    if (toolbarFrame !== null) view.cancelAnimationFrame(toolbarFrame);
    model.off("change:blocks", renderBlocks);
    model.off("change:embedded_projector_ids", refreshEmbeddedProjectors);
    model.off("change:embedded_projectors", refreshEmbeddedProjectors);
    model.off("change:backend_projector_ids", refreshEmbeddedProjectors);
    model.off("change:backend_projectors", refreshEmbeddedProjectors);
    model.off("change:embedded_pair_ids", refreshEmbeddedProjectors);
    model.off("change:embedded_pairs", refreshEmbeddedProjectors);
    model.off("change:title", updateTitle);
    model.off("change:calculation_feedback", showCalculationFeedback);
    model.off("change:export_content", downloadExport);
    if (feedbackTimer !== null) clearTimeout(feedbackTimer);
    if (pendingFocusTimer !== null) clearTimeout(pendingFocusTimer);
  };
}

export default {
  render(context) {
    if (context.model.get("widget_role") === "workspace") return renderWorkspace(context);
    if (context.model.get("widget_role") === "whiteboard") return renderWhiteboard(context);
    return () => {};
  },
};
