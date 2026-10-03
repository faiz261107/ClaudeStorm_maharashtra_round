/* Free-body diagram editor. The learner picks a force from the palette, a direction and a size;
   arrows are drawn on the object. Produces [{force, direction, size}] for /api/diagnose.
   Also renders a read-only "ideal" diagram next to the learner's for the result screen. */

window.FBD = (function () {
  const INK = "#141a33", LINE = "#e2dccf", MUTED = "#6b7088";
  const COLOURS = { "gravity": "#f59e0b", "normal force": "#0891b2", "throw force": "#be123c", "forward push": "#be123c",
                    "friction": "#7c3aed", "air resistance": "#7c3aed", "engine force": "#15803d", "drag + friction": "#7c3aed" };
  const W = 520, H = 320;

  function drawScene(ctx, item) {
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W, H);
    ctx.font = "12px Roboto, system-ui, sans-serif"; ctx.fillStyle = MUTED;
    const cx = W / 2, cy = H / 2 + 10;
    if (item.scene === "sliding" || item.scene === "cruising") {
      ctx.strokeStyle = INK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(30, cy + 36); ctx.lineTo(W - 30, cy + 36); ctx.stroke();
      ctx.strokeStyle = LINE; for (let x = 30; x < W - 30; x += 18) { ctx.beginPath(); ctx.moveTo(x, cy + 36); ctx.lineTo(x - 8, cy + 45); ctx.stroke(); }
      ctx.fillText(item.scene === "sliding" ? "frictionless ice" : "road", 34, cy + 60);
    } else {
      ctx.strokeStyle = LINE; ctx.setLineDash([3, 5]); ctx.beginPath(); ctx.moveTo(cx, 30); ctx.lineTo(cx, H - 20); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillText(item.scene === "top" ? "top of flight" : "rising", cx + 10, 40);
    }
    // object
    ctx.fillStyle = INK;
    if (item.object === "car") { roundRect(ctx, cx - 50, cy - 6, 100, 42, 8); ctx.fill(); ctx.beginPath(); ctx.arc(cx - 30, cy + 36, 9, 0, 7); ctx.arc(cx + 30, cy + 36, 9, 0, 7); ctx.fill(); }
    else if (item.object === "puck") { roundRect(ctx, cx - 34, cy + 12, 68, 24, 6); ctx.fill(); }
    else { ctx.beginPath(); ctx.arc(cx, cy, 24, 0, Math.PI * 2); ctx.fill(); }
    // motion hint
    if (item.motion && item.motion !== "none") {
      ctx.strokeStyle = "#15803d"; ctx.fillStyle = "#15803d"; ctx.lineWidth = 2; ctx.setLineDash([4, 4]);
      const d = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] }[item.motion];
      const sx = cx + d[0] * 70, sy = cy + d[1] * 70 - (item.object === "car" ? 40 : 0);
      ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(sx + d[0] * 50, sy + d[1] * 50); ctx.stroke(); ctx.setLineDash([]);
      ctx.font = "11px Roboto, system-ui, sans-serif"; ctx.fillText("motion", sx + d[0] * 55 + (d[0] ? 0 : 8), sy + d[1] * 55 + (d[1] ? 0 : -8));
    }
    return { cx, cy };
  }

  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }

  function drawArrow(ctx, x, y, dir, size, colour, label, dashed) {
    const len = 40 + size * 28; const d = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] }[dir] || [0, 1];
    const x2 = x + d[0] * len, y2 = y + d[1] * len;
    ctx.save(); ctx.strokeStyle = colour; ctx.fillStyle = colour; ctx.lineWidth = 2 + size; ctx.lineCap = "round";
    if (dashed) ctx.setLineDash([6, 5]);
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
    const a = Math.atan2(y2 - y, x2 - x), h = 10 + size * 2;
    ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - h * Math.cos(a - 0.45), y2 - h * Math.sin(a - 0.45)); ctx.lineTo(x2 - h * Math.cos(a + 0.45), y2 - h * Math.sin(a + 0.45)); ctx.closePath(); ctx.fill();
    ctx.font = "600 12px Roboto, system-ui, sans-serif"; ctx.textBaseline = "middle";
    if (d[0]) { ctx.textAlign = "center"; ctx.fillText(label, (x + x2) / 2, y - 14); }
    else { ctx.textAlign = "left"; ctx.fillText(label, x2 + 12, y2 + (d[1] > 0 ? -6 : 6)); }
    ctx.restore();
  }

  function render(canvas, item, diagram, { dashed = false } = {}) {
    const dpr = window.devicePixelRatio || 1; canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.aspectRatio = `${W} / ${H}`;
    const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const { cx, cy } = drawScene(ctx, item);
    const oy = item.object === "car" ? cy + 15 : (item.object === "puck" ? cy + 24 : cy);
    // offset arrows that share a direction so they don't overlap
    const seen = {};
    const half = item.object === "car" ? 52 : (item.object === "puck" ? 36 : 26);
    diagram.forEach((a) => {
      const k = a.direction; seen[k] = (seen[k] || 0) + 1; const off = (seen[k] - 1) * 18;
      const horiz = a.direction === "left" || a.direction === "right";
      const ox = horiz ? (a.direction === "right" ? half : -half) : off, oyy = horiz ? off - 10 : 0;
      drawArrow(ctx, cx + ox, oy + oyy, a.direction, Number(a.size) || 2, COLOURS[a.force] || INK, `${a.force}${a.size == 3 ? " (large)" : a.size == 1 ? " (small)" : ""}`, dashed);
    });
    if (!diagram.length) { ctx.fillStyle = MUTED; ctx.font = "13px Roboto, system-ui, sans-serif"; ctx.textAlign = "center"; ctx.fillText("No forces drawn yet — pick one from the palette", cx, H - 24); }
  }

  /* Mount an editor into `root`, optionally pre-filled with `initial` arrows. Returns { get(), destroy() }. onChange called on every edit. */
  function mount(root, item, onChange, initial) {
    const diagram = (initial || []).filter((a) => a && item.palette.includes(a.force)).map((a) => ({ ...a }));
    let force = item.palette[0], dir = "down", size = 2;
    root.innerHTML = `<div class="fbd">
      <canvas id="fbdCanvas" role="img" aria-label="Free-body diagram editor"></canvas>
      <div class="fbd-side">
        <h3>1 · Force</h3><div class="chips" id="fbdForces">${item.palette.map((f) => `<button type="button" class="chip-btn ${f === force ? "on" : ""}" data-f="${f}">${f}</button>`).join("")}</div>
        <h3>2 · Direction</h3><div class="chips" id="fbdDirs">${["up", "down", "left", "right"].map((d) => `<button type="button" class="chip-btn ${d === dir ? "on" : ""}" data-d="${d}">${{ up: "↑ up", down: "↓ down", left: "← left", right: "→ right" }[d]}</button>`).join("")}</div>
        <h3>3 · Size</h3><div class="chips" id="fbdSizes">${[1, 2, 3].map((s) => `<button type="button" class="chip-btn ${s === size ? "on" : ""}" data-s="${s}">${["small", "medium", "large"][s - 1]}</button>`).join("")}</div>
        <button type="button" class="btn small" id="fbdAdd">Add arrow</button>
        <div class="arrows" id="fbdList" aria-live="polite"></div>
      </div></div>`;
    const canvas = root.querySelector("#fbdCanvas");
    const sync = () => {
      render(canvas, item, diagram);
      root.querySelector("#fbdList").innerHTML = diagram.map((a, i) => `<div><span>${a.force} · ${a.direction} · ${["small", "medium", "large"][a.size - 1]}</span><button type="button" data-rm="${i}" aria-label="remove ${a.force}">✕</button></div>`).join("");
      root.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { diagram.splice(Number(b.dataset.rm), 1); sync(); onChange && onChange(diagram); }));
    };
    const pick = (sel, attr, set) => root.querySelectorAll(sel).forEach((b) => b.addEventListener("click", () => { set(b.dataset[attr]); root.querySelectorAll(sel).forEach((x) => x.classList.toggle("on", x === b)); }));
    pick("#fbdForces .chip-btn", "f", (v) => { force = v; });
    pick("#fbdDirs .chip-btn", "d", (v) => { dir = v; });
    pick("#fbdSizes .chip-btn", "s", (v) => { size = Number(v); });
    root.querySelector("#fbdAdd").addEventListener("click", () => {
      const existing = diagram.findIndex((a) => a.force === force);
      if (existing >= 0) diagram.splice(existing, 1);
      diagram.push({ force, direction: dir, size }); sync(); onChange && onChange(diagram);
    });
    sync();
    return { get: () => diagram.slice(), destroy: () => { root.innerHTML = ""; } };
  }

  return { mount, render };
})();
