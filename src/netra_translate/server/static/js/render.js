// Page rebuild: the translated page is a clean sheet with the same geometry as
// the scan. Each OCR line keeps its box; the block's translation is split over
// those boxes, sized from the line height and coloured from the scan's ink.
// The block structure only drives this layout and is never shown.

const TEXT_TYPES = new Set(["heading", "paragraph", "caption", "page_header", "page_footer"]);
const INK = "#1c1917";
const FONT = '"Kantumruy Pro", "Noto Sans Khmer", system-ui, sans-serif';
const KHMER = /[ក-៿᧠-᧿]/;

// ── pixels ────────────────────────────────────────────────────────────
// The page render, decoded once so line colours can be read from it.
export function loadPixels(src) {
  return new Promise((resolve) => {
    if (!src) return resolve(null);
    const img = new Image();
    img.decoding = "async";
    img.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        resolve({ data: ctx.getImageData(0, 0, c.width, c.height).data, w: c.width, h: c.height });
      } catch {
        resolve(null);
      }
    };
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

const lum = ([r, g, b]) => (0.299 * r + 0.587 * g + 0.114 * b) / 255;
const dist = (a, b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]);

// Text colour of a box: paper = median of a thin ring around it, ink = mean of
// the pixels inside that differ most from the paper. Light ink (white text on a
// dark band) would vanish on a white sheet, so it falls back to INK.
function inkColor(px, bbox, sx, sy) {
  if (!px) return INK;
  const x1 = Math.max(0, Math.floor(bbox[0] * sx)), y1 = Math.max(0, Math.floor(bbox[1] * sy));
  const x2 = Math.min(px.w - 1, Math.ceil(bbox[2] * sx)), y2 = Math.min(px.h - 1, Math.ceil(bbox[3] * sy));
  if (x2 <= x1 || y2 <= y1) return INK;
  const at = (x, y) => { const i = (y * px.w + x) * 4; return [px.data[i], px.data[i + 1], px.data[i + 2]]; };

  const ring = [];
  const step = Math.max(1, Math.floor((x2 - x1) / 60));
  for (let x = x1; x <= x2; x += step) {
    if (y1 >= 2) ring.push(at(x, y1 - 2));
    if (y2 + 2 < px.h) ring.push(at(x, y2 + 2));
  }
  for (let y = y1; y <= y2; y += Math.max(1, Math.floor((y2 - y1) / 10))) {
    if (x1 >= 2) ring.push(at(x1 - 2, y));
    if (x2 + 2 < px.w) ring.push(at(x2 + 2, y));
  }
  if (!ring.length) return INK;
  ring.sort((a, b) => lum(a) - lum(b));
  const paper = ring[Math.floor(ring.length / 2)];

  const inside = [];
  const total = (x2 - x1) * (y2 - y1);
  const stride = Math.max(1, Math.floor(Math.sqrt(total / 4000)));
  for (let y = y1; y < y2; y += stride) {
    for (let x = x1; x < x2; x += stride) {
      const c = at(x, y);
      inside.push([dist(c, paper), c]);
    }
  }
  inside.sort((a, b) => b[0] - a[0]);
  const top = inside.slice(0, Math.max(1, Math.floor(inside.length * 0.08)));
  if (top[0][0] < 90) return INK;
  const mean = [0, 1, 2].map((k) => Math.round(top.reduce((s, [, c]) => s + c[k], 0) / top.length));
  if (lum(mean) > 0.62) return INK;
  return `rgb(${mean[0]}, ${mean[1]}, ${mean[2]})`;
}

// ── splitting a translation over the source lines ─────────────────────
function segments(text) {
  const lang = KHMER.test(text) ? "km" : "en";
  if (typeof Intl !== "undefined" && Intl.Segmenter) {
    return [...new Intl.Segmenter(lang, { granularity: "word" }).segment(text)].map((s) => s.segment);
  }
  return text.split(/(\s+)/).filter(Boolean);
}

// Split ``text`` into ``widths.length`` pieces, each sized to its line's share
// of the total width, breaking only between words.
export function splitAcross(text, widths) {
  const n = widths.length;
  text = text.replace(/\s+/g, " ").trim();
  if (n <= 1) return [text];
  const segs = segments(text);
  const totalW = widths.reduce((a, b) => a + b, 0) || n;
  const total = text.length;
  const out = Array.from({ length: n }, () => "");
  let line = 0, used = 0, target = (widths[0] / totalW) * total;
  for (const s of segs) {
    // Move on once the midpoint of this word falls past the line's share.
    while (line < n - 1 && used + s.length / 2 > target && out[line].trim()) {
      line += 1;
      target += (widths[line] / totalW) * total;
    }
    out[line] += s;
    used += s.length;
  }
  return out.map((s) => s.trim());
}

// ── layout model ──────────────────────────────────────────────────────
// Font size from the box height. A Khmer line's box includes stacked vowels
// and subscripts, so the same visual size needs a smaller fraction of it.
function fontPx(lineH, sourceText) {
  return lineH * (KHMER.test(sourceText || "") ? 0.58 : 0.74);
}

function blockLines(b) {
  const lines = (b.lines || []).filter((l) => l.bbox);
  return lines.length ? lines : [{ bbox: b.bbox, text: b.source_text || "" }];
}

// Everything to draw on one page, in page coordinates:
//   {kind: "line", key, bbox, text, size, color, weight, align}
//   {kind: "table", key, bbox, rows, size}   rows: [{key, bbox, cells}]
//   {kind: "figure", bbox, image}
// ``hits`` are the source boxes on the scan, keyed like the lines they link to.
export function layoutPage(page, blocks, px) {
  const sx = px ? px.w / page.width : 1;
  const sy = px ? px.h / page.height : 1;
  const items = [];
  const hits = [];
  for (const b of blocks) {
    if (!b.bbox) continue;
    if (TEXT_TYPES.has(b.type)) {
      const lines = blockLines(b);
      const pieces = splitAcross(b.text || "", lines.map((l) => l.bbox[2] - l.bbox[0]));
      // One size per block, from its median line height, as in the original.
      const heights = lines.map((l) => l.bbox[3] - l.bbox[1]).sort((a, c) => a - c);
      const size = fontPx(heights[Math.floor(heights.length / 2)], b.source_text || lines[0].text);
      const align = b.align === "center" || b.align === "right" ? b.align : "left";
      lines.forEach((l, i) => {
        const key = `${b.id}:${i}`;
        hits.push({ key, bbox: l.bbox });
        if (!pieces[i]) return;
        // Left-aligned text may run on to the paragraph's right edge, as wrapped text would.
        const bbox = align === "left" ? [l.bbox[0], l.bbox[1], Math.max(l.bbox[2], b.bbox[2]), l.bbox[3]] : l.bbox;
        items.push({
          kind: "line", key, block: b.id, bbox, text: pieces[i], size,
          color: inkColor(px, l.bbox, sx, sy),
          weight: b.type === "heading" ? 700 : 400,
          align,
        });
      });
    } else if (b.type === "table") {
      const rows = b.rows || [];
      const [x1, y1, x2, y2] = b.bbox;
      const rh = (y2 - y1) / Math.max(1, rows.length);
      const tableRows = rows.map((cells, i) => {
        const bbox = [x1, y1 + i * rh, x2, y1 + (i + 1) * rh];
        const key = `${b.id}:r${i}`;
        hits.push({ key, bbox });
        return { key, bbox, cells };
      });
      items.push({ kind: "table", key: b.id, bbox: b.bbox, rows: tableRows, size: rh * 0.42 });
    } else if (b.image) {
      items.push({ kind: "figure", bbox: b.bbox, image: b.image });
    }
  }
  return { items, hits };
}

// ── DOM ───────────────────────────────────────────────────────────────
// Sizes are in cqw (percent of the sheet's width), so a sheet scales with
// zoom without being laid out again.
function place(el, bbox, page) {
  const [x1, y1, x2, y2] = bbox;
  el.style.left = `${(x1 / page.width) * 100}%`;
  el.style.top = `${(y1 / page.height) * 100}%`;
  el.style.width = `${((x2 - x1) / page.width) * 100}%`;
  el.style.height = `${((y2 - y1) / page.height) * 100}%`;
  return el;
}

const cqw = (px, page) => `${(px / page.width) * 100}cqw`;

export function buildTranslated(sheet, page, layout, assetUrl) {
  const els = [];
  for (const it of layout.items) {
    if (it.kind === "line") {
      const text = document.createElement("span");
      text.className = "ln-t";
      text.textContent = it.text;
      const el = place(document.createElement("span"), it.bbox, page);
      el.className = `ln ln-${it.align}`;
      el.dataset.line = it.key;
      el.dataset.block = it.block;
      el.style.fontSize = cqw(it.size, page);
      el.style.color = it.color;
      if (it.weight !== 400) el.style.fontWeight = it.weight;
      el.append(text);
      els.push(el);
    } else if (it.kind === "table") {
      const table = document.createElement("table");
      const body = document.createElement("tbody");
      for (const row of it.rows) {
        const tr = document.createElement("tr");
        tr.dataset.line = row.key;
        for (const cell of row.cells) {
          const td = document.createElement("td");
          td.textContent = cell;
          tr.append(td);
        }
        body.append(tr);
      }
      table.append(body);
      const el = place(document.createElement("div"), it.bbox, page);
      el.className = "tb";
      el.style.fontSize = cqw(it.size, page);
      el.append(table);
      els.push(el);
    } else {
      const img = document.createElement("img");
      img.src = assetUrl(it.image);
      img.alt = "";
      img.className = "fig";
      img.draggable = false;
      els.push(place(img, it.bbox, page));
    }
  }
  sheet.replaceChildren(...els);
}

export function buildHits(layer, page, layout) {
  layer.replaceChildren(...layout.hits.map((hit) => {
    const el = place(document.createElement("span"), hit.bbox, page);
    el.className = "hit";
    el.dataset.line = hit.key;
    return el;
  }));
}

// Shrink lines that overflow their box: the font size of the whole block first
// (down to 70%, so a paragraph keeps one size), then a horizontal squeeze for
// any line still too long. Needs the sheet on screen; the ratios hold at any
// zoom because everything is in cqw.
export function fitSheet(sheet) {
  if (!sheet.clientWidth || sheet.dataset.fitted) return;
  sheet.dataset.fitted = "1";
  const groups = new Map();
  for (const el of sheet.querySelectorAll(".ln")) {
    if (!groups.has(el.dataset.block)) groups.set(el.dataset.block, []);
    groups.get(el.dataset.block).push(el);
  }
  for (const els of groups.values()) {
    const ratio = Math.min(...els.map((el) => el.clientWidth / Math.max(1, el.firstChild.scrollWidth)));
    if (ratio >= 1) continue;
    const shrink = Math.max(0.7, ratio).toFixed(3);
    for (const el of els) el.style.fontSize = `calc(${el.style.fontSize} * ${shrink})`;
    for (const el of els) {
      const rest = el.clientWidth / Math.max(1, el.firstChild.scrollWidth);
      if (rest < 1) el.firstChild.style.transform = `scaleX(${rest.toFixed(3)})`;
    }
  }
  for (const el of sheet.querySelectorAll(".tb")) {
    const table = el.firstChild;
    const ratio = Math.min(el.clientHeight / Math.max(1, table.scrollHeight),
      el.clientWidth / Math.max(1, table.scrollWidth));
    if (ratio < 1) el.style.fontSize = `calc(${el.style.fontSize} * ${Math.max(0.5, ratio).toFixed(3)})`;
  }
}

// ── image export ──────────────────────────────────────────────────────
function loadImage(src) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

// The translated sheet as a PNG blob, drawn from the same layout model.
export async function pagePng(page, layout, assetUrl) {
  const scale = Math.min(2, 2400 / page.width);
  const c = document.createElement("canvas");
  c.width = Math.round(page.width * scale);
  c.height = Math.round(page.height * scale);
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.scale(scale, scale);
  ctx.textBaseline = "middle";
  await document.fonts?.ready;

  const measure = (text, size, weight) => {
    ctx.font = `${weight} ${size}px ${FONT}`;
    return ctx.measureText(text).width;
  };
  // Same rule as fitSheet: one shrink per block, then squeeze long lines.
  const shrink = new Map();
  for (const it of layout.items) {
    if (it.kind !== "line") continue;
    const r = (it.bbox[2] - it.bbox[0]) / Math.max(1, measure(it.text, it.size, it.weight));
    shrink.set(it.block, Math.min(shrink.get(it.block) ?? 1, r));
  }
  const fitText = (text, x1, x2, yMid, size, weight, color, align) => {
    ctx.font = `${weight} ${size}px ${FONT}`;
    ctx.fillStyle = color;
    const boxW = x2 - x1;
    const w = ctx.measureText(text).width;
    const squeeze = Math.min(1, boxW / Math.max(1, w));
    const drawn = w * squeeze;
    const x = align === "center" ? x1 + (boxW - drawn) / 2 : align === "right" ? x2 - drawn : x1;
    ctx.save();
    ctx.translate(x, yMid);
    ctx.scale(squeeze, 1);
    ctx.fillText(text, 0, 0);
    ctx.restore();
  };

  for (const it of layout.items) {
    const [x1, y1, x2, y2] = it.bbox;
    if (it.kind === "figure") {
      const img = await loadImage(assetUrl(it.image));
      if (img) ctx.drawImage(img, x1, y1, x2 - x1, y2 - y1);
    } else if (it.kind === "line") {
      const size = it.size * Math.max(0.7, Math.min(1, shrink.get(it.block)));
      fitText(it.text, x1, x2, (y1 + y2) / 2, size, it.weight, it.color, it.align);
    } else {
      ctx.strokeStyle = "#999";
      ctx.lineWidth = 1 / scale;
      for (const row of it.rows) {
        const [, ry1, , ry2] = row.bbox;
        const cw = (x2 - x1) / Math.max(1, row.cells.length);
        row.cells.forEach((cell, i) => {
          ctx.strokeRect(x1 + i * cw, ry1, cw, ry2 - ry1);
          const room = cw - 8;
          const size = it.size * Math.max(0.6, Math.min(1, room / Math.max(1, measure(cell, it.size, 400))));
          fitText(cell, x1 + i * cw + 4, x1 + (i + 1) * cw - 4, (ry1 + ry2) / 2, size, 400, INK, "left");
        });
      }
    }
  }
  return new Promise((resolve) => c.toBlob(resolve, "image/png"));
}
