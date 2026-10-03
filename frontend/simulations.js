/* Re:Learn physics simulations (canvas).
   Each simulation is a pure draw(ctx, W, H, t, mode) over a looping time t in seconds.
   mode = "physics" (what happens) or "belief" (what the misconception predicts, drawn as a red ghost).
   The controller handles DPR scaling, play/pause/seek, and reduced-motion (no autoplay). */

window.Simulations = (function () {
  const INK = "#141a33", MUTED = "#6b7088", LINE = "#e2dccf", PAPER = "#f7f4ee";
  const V = "#15803d", F = "#f59e0b", GHOST = "#be123c", BLUE = "#0891b2";
  const prefersReduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- drawing helpers ----------
  function arrow(ctx, x1, y1, x2, y2, color, width = 3, dashed = false, label = null) {
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy);
    if (len < 2) return;
    ctx.save();
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = width; ctx.lineCap = "round";
    if (dashed) ctx.setLineDash([6, 5]);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    ctx.setLineDash([]);
    const a = Math.atan2(dy, dx), h = 9 + width;
    ctx.beginPath(); ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - h * Math.cos(a - 0.45), y2 - h * Math.sin(a - 0.45));
    ctx.lineTo(x2 - h * Math.cos(a + 0.45), y2 - h * Math.sin(a + 0.45));
    ctx.closePath(); ctx.fill();
    if (label) {
      ctx.font = "600 13px Roboto, system-ui, sans-serif";
      ctx.textBaseline = "middle";
      if (Math.abs(dx) < Math.abs(dy)) {            // vertical-ish: label beside the tip, to the right
        ctx.textAlign = "left"; ctx.fillText(label, x2 + 14, y2 + (dy > 0 ? 10 : -8));
      } else {                                        // horizontal-ish: label above the midpoint
        ctx.textAlign = "center"; ctx.fillText(label, (x1 + x2) / 2, y2 - 14);
      }
    }
    ctx.restore();
  }
  function text(ctx, s, x, y, { size = 13, color = INK, weight = 500, align = "left", mono = false, base = "alphabetic" } = {}) {
    ctx.save();
    ctx.font = `${weight} ${size}px ${mono ? "'Roboto Mono', monospace" : "Roboto, system-ui, sans-serif"}`;
    ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = base;
    ctx.fillText(s, x, y); ctx.restore();
  }
  function pill(ctx, s, x, y, bg, fg) {
    ctx.save(); ctx.font = "700 11px Roboto, system-ui, sans-serif";
    const w = ctx.measureText(s).width + 16;
    ctx.fillStyle = bg; roundRect(ctx, x, y - 10, w, 20, 10); ctx.fill();
    ctx.fillStyle = fg; ctx.textBaseline = "middle"; ctx.fillText(s, x + 8, y); ctx.restore();
    return w;
  }
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function ball(ctx, x, y, r, color = INK) {
    ctx.save(); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.beginPath(); ctx.arc(x - r * 0.3, y - r * 0.3, r * 0.3, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }
  function ground(ctx, W, y) {
    ctx.save(); ctx.strokeStyle = INK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    ctx.strokeStyle = LINE; ctx.lineWidth = 1;
    for (let x = 0; x < W; x += 18) { ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 8, y + 9); ctx.stroke(); }
    ctx.restore();
  }
  function graph(ctx, x, y, w, h, title, xl, yl) {
    ctx.save(); ctx.fillStyle = "#fff"; roundRect(ctx, x, y, w, h, 10); ctx.fill();
    ctx.strokeStyle = LINE; ctx.stroke();
    ctx.strokeStyle = MUTED; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(x + 28, y + 14); ctx.lineTo(x + 28, y + h - 22); ctx.lineTo(x + w - 10, y + h - 22); ctx.stroke();
    text(ctx, title, x + 10, y + 12, { size: 11, color: MUTED, weight: 700, base: "middle" });
    text(ctx, xl, x + w - 12, y + h - 8, { size: 10, color: MUTED, align: "right" });
    text(ctx, yl, x + 8, y + 26, { size: 10, color: MUTED });
    ctx.restore();
    return { x0: x + 28, y0: y + h - 22, w: w - 40, h: h - 40 };
  }

  // ---------- 1. Ball thrown up: v vs a (VA_CONFUSION) ----------
  const throw_up = {
    duration: 3.0,
    describe: "A ball is thrown straight up. The green arrow is velocity: it shrinks to zero at the top and flips. The amber arrow is acceleration: always 9.8 m/s² downward, even at the top. In belief mode a red ghost shows the acceleration arrow wrongly vanishing at the top.",
    draw(ctx, W, H, t, mode) {
      const g = 9.8, v0 = 12.5, T = 2 * v0 / g; const tt = Math.min(t, T);
      const gy = H - 44, scale = (gy - 70) / (v0 * v0 / (2 * g));
      const y = gy - (v0 * tt - 0.5 * g * tt * tt) * scale, x = W * 0.3;
      const v = v0 - g * tt;
      ground(ctx, W, gy);
      // trajectory guide
      ctx.save(); ctx.strokeStyle = LINE; ctx.setLineDash([3, 5]); ctx.beginPath(); ctx.moveTo(x, gy); ctx.lineTo(x, 70); ctx.stroke(); ctx.restore();
      text(ctx, "top", x + 10, 70, { size: 11, color: MUTED, base: "middle" });
      ball(ctx, x, y, 14);
      // velocity arrow
      if (Math.abs(v) > 0.2) arrow(ctx, x, y, x, y - v * 7, V, 4, false, `v = ${v >= 0 ? "+" : ""}${v.toFixed(1)} m/s`);
      else text(ctx, "v = 0", x + 22, y, { size: 13, color: V, weight: 700, base: "middle" });
      // acceleration arrow
      const belief = mode === "belief";
      const aScale = belief ? Math.min(1, Math.abs(v) / 4) : 1;
      arrow(ctx, x - 40, y, x - 40, y + 60 * aScale, belief ? GHOST : F, 4, belief, belief ? `a → ${(-9.8 * aScale).toFixed(1)}?` : "a = −9.8 m/s²");
      if (belief && aScale < 0.5) pill(ctx, "belief: a = 0 at the top ✗", x - 150, y - 28, "#fde8ee", GHOST);
      if (!belief && Math.abs(v) < 0.6) pill(ctx, "v = 0  but  a ≠ 0", x - 110, y - 28, "#e7f6ea", V);
      // v–t graph
      const G = graph(ctx, W - 250, 16, 234, 150, "velocity vs time", "t", "v");
      ctx.save(); ctx.strokeStyle = V; ctx.lineWidth = 2; ctx.beginPath();
      for (let i = 0; i <= 40; i++) { const s = T * i / 40, vv = v0 - g * s; const px = G.x0 + G.w * s / T, py = G.y0 - G.h / 2 - vv / v0 * G.h / 2; i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }
      ctx.stroke();
      ctx.strokeStyle = LINE; ctx.beginPath(); ctx.moveTo(G.x0, G.y0 - G.h / 2); ctx.lineTo(G.x0 + G.w, G.y0 - G.h / 2); ctx.stroke();
      const px = G.x0 + G.w * tt / T, py = G.y0 - G.h / 2 - v / v0 * G.h / 2;
      ctx.fillStyle = V; ctx.beginPath(); ctx.arc(px, py, 5, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      text(ctx, "slope = a = constant", G.x0 + 40, G.y0 - G.h / 2 + 46, { size: 11, color: MUTED });
      // a–t graph
      const A = graph(ctx, W - 250, 176, 234, 90, "acceleration vs time", "t", "a");
      ctx.save(); ctx.strokeStyle = F; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(A.x0, A.y0 - A.h * 0.8); ctx.lineTo(A.x0 + A.w, A.y0 - A.h * 0.8); ctx.stroke();
      if (belief) { ctx.strokeStyle = GHOST; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(A.x0, A.y0 - A.h * 0.8); ctx.lineTo(A.x0 + A.w * 0.5, A.y0 - 2); ctx.lineTo(A.x0 + A.w, A.y0 - A.h * 0.8); ctx.stroke(); }
      ctx.fillStyle = F; ctx.beginPath(); ctx.arc(A.x0 + A.w * tt / T, A.y0 - A.h * 0.8, 5, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      text(ctx, `t = ${tt.toFixed(2)} s`, 16, 24, { size: 12, color: MUTED, mono: true });
    },
  };

  // ---------- 2. Forces in flight (IMPETUS) ----------
  const forces_in_flight = {
    duration: 3.2,
    describe: "A ball after it leaves the hand. The only force on it is gravity (amber, always down). In belief mode a red dashed 'throw force' is drawn along the motion — no object is applying it, so it does not exist. The ball keeps moving because of inertia, not a stored force.",
    draw(ctx, W, H, t, mode) {
      const g = 9.8, vx = 5.2, vy0 = 11, T = 2 * vy0 / g, tt = Math.min(t, T);
      const gy = H - 44, sx = (W - 120) / (vx * T), sy = (gy - 80) / (vy0 * vy0 / (2 * g));
      const x = 60 + vx * tt * sx, y = gy - (vy0 * tt - 0.5 * g * tt * tt) * sy, vy = vy0 - g * tt;
      ground(ctx, W, gy);
      // hand at launch
      text(ctx, "release", 60, gy + 20, { size: 11, color: MUTED, align: "center" });
      ctx.save(); ctx.strokeStyle = LINE; ctx.setLineDash([3, 5]); ctx.beginPath();
      for (let i = 0; i <= 50; i++) { const s = T * i / 50; const px = 60 + vx * s * sx, py = gy - (vy0 * s - 0.5 * g * s * s) * sy; i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }
      ctx.stroke(); ctx.restore();
      ball(ctx, x, y, 13);
      // velocity (faint)
      arrow(ctx, x, y, x + vx * 5, y - vy * 5, "rgba(21,128,61,.55)", 2, false, "v");
      // gravity
      arrow(ctx, x, y, x, y + 58, F, 4, false, "gravity");
      if (mode === "belief") {
        const sp = Math.hypot(vx, vy); const fade = Math.max(0.15, Math.min(1, 1 - tt / T));
        const L = 70 * fade;
        arrow(ctx, x, y, x + vx / sp * L, y - vy / sp * L, GHOST, 4, true, null);
        text(ctx, "'throw force'? (fading)", x < W / 2 ? x + 20 : x - 20, y - 18, { size: 13, color: GHOST, weight: 600, align: x < W / 2 ? "left" : "right" });
        pill(ctx, "✗ nothing is applying this force", Math.min(x - 60, W - 250), y - 42, "#fde8ee", GHOST);
      } else if (tt > 0.25) {
        pill(ctx, "only gravity acts — inertia keeps it moving", Math.min(x - 110, W - 290), y - 42, "#e7f6ea", V);
      }
      // free-body panel
      const bx = W - 236, by = 16; ctx.save(); ctx.fillStyle = "#fff"; roundRect(ctx, bx, by, 220, 86, 10); ctx.fill(); ctx.strokeStyle = LINE; ctx.stroke(); ctx.restore();
      text(ctx, "forces on the ball", bx + 10, by + 16, { size: 11, color: MUTED, weight: 700 });
      text(ctx, "✓ gravity (Earth pulls it)", bx + 10, by + 40, { size: 12, color: V, weight: 600 });
      text(ctx, mode === "belief" ? "✗ 'throw force' — no object applies it" : "– nothing else is touching it", bx + 10, by + 62, { size: 12, color: mode === "belief" ? GHOST : MUTED, weight: 600 });
      text(ctx, `t = ${tt.toFixed(2)} s`, 16, 24, { size: 12, color: MUTED, mono: true });
    },
  };

  // ---------- 3. Constant force (FORCE_VELOCITY) ----------
  const constant_force = {
    duration: 4.0,
    describe: "A box on a frictionless track is pushed with a constant 4 N force. The velocity keeps increasing (green line rises). In belief mode the red dashed line shows the prediction 'constant force → constant speed', which never happens.",
    draw(ctx, W, H, t, mode) {
      const a = 2, T = 4, tt = Math.min(t, T), v = a * tt, xWorld = 0.5 * a * tt * tt;
      const gy = H - 60; ground(ctx, W, gy);
      const xs = 40 + (xWorld % 14) * ((W - 80) / 14);
      // box
      ctx.save(); ctx.fillStyle = INK; roundRect(ctx, xs - 22, gy - 44, 44, 44, 6); ctx.fill(); ctx.restore();
      arrow(ctx, xs - 70, gy - 22, xs - 26, gy - 22, F, 4, false, null);
      text(ctx, "F = 4 N (constant)", xs - 70, gy - 48, { size: 12, color: F, weight: 700 });
      arrow(ctx, xs + 22, gy - 22, xs + 22 + v * 9, gy - 22, V, 3, false, `v = ${v.toFixed(1)} m/s`);
      // speedometer
      const cx = 96, cy = 96, r = 56;
      ctx.save(); ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(cx, cy, r + 8, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = LINE; ctx.stroke();
      ctx.strokeStyle = LINE; ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(cx, cy, r, Math.PI * 0.75, Math.PI * 2.25); ctx.stroke();
      const frac = v / (a * T), ang = Math.PI * 0.75 + frac * Math.PI * 1.5;
      ctx.strokeStyle = V; ctx.beginPath(); ctx.arc(cx, cy, r, Math.PI * 0.75, ang); ctx.stroke();
      ctx.strokeStyle = INK; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(ang) * (r - 10), cy + Math.sin(ang) * (r - 10)); ctx.stroke(); ctx.restore();
      text(ctx, `${v.toFixed(1)}`, cx, cy + 28, { size: 16, weight: 700, align: "center", mono: true });
      text(ctx, "m/s", cx, cy + 44, { size: 10, color: MUTED, align: "center" });
      // v–t graph
      const G = graph(ctx, W - 250, 16, 234, 170, "velocity vs time", "t", "v");
      ctx.save(); ctx.strokeStyle = V; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(G.x0, G.y0); ctx.lineTo(G.x0 + G.w * tt / T, G.y0 - G.h * tt / T); ctx.stroke();
      if (mode === "belief") { ctx.strokeStyle = GHOST; ctx.setLineDash([5, 4]); ctx.beginPath(); ctx.moveTo(G.x0, G.y0 - G.h * 0.3); ctx.lineTo(G.x0 + G.w, G.y0 - G.h * 0.3); ctx.stroke(); ctx.setLineDash([]); text(ctx, "belief: constant speed ✗", G.x0 + 8, G.y0 - G.h * 0.3 - 8, { size: 11, color: GHOST, weight: 700 }); }
      ctx.fillStyle = V; ctx.beginPath(); ctx.arc(G.x0 + G.w * tt / T, G.y0 - G.h * tt / T, 5, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      text(ctx, "F = m·a  →  a = 2 m/s², fixed", G.x0 + 8, G.y0 + 4, { size: 11, color: MUTED, base: "top" });
      text(ctx, `t = ${tt.toFixed(2)} s`, 16, 24, { size: 12, color: MUTED, mono: true });
    },
  };

  // ---------- 4. Collision (THIRD_LAW) ----------
  const collision = {
    duration: 3.6,
    describe: "A 4000 kg truck hits a 1000 kg car. During contact both force arrows are exactly equal and opposite (40 kN each). The car accelerates four times more because it has a quarter of the mass. In belief mode the red ghost arrows show the unequal forces the misconception predicts.",
    draw(ctx, W, H, t, mode) {
      const gy = H - 60; ground(ctx, W, gy);
      const t1 = 1.3, dt = 0.6, t2 = t1 + dt; const tt = Math.min(t, 3.6);
      const vT = 150, u = 0.6; // px/s truck speed; after collision truck keeps u*vT, car gets 2.2*vT
      let xT, xC; const carStart = 40 + vT * t1 + 160;
      if (tt < t1) { xT = 40 + vT * tt; xC = carStart; }
      else if (tt < t2) { xT = 40 + vT * t1 + vT * u * (tt - t1); xC = carStart + vT * u * (tt - t1); }
      else { xT = 40 + vT * t1 + vT * u * (tt - t1); xC = carStart + vT * u * dt + 1.5 * vT * (tt - t2); }
      // truck
      ctx.save(); ctx.fillStyle = INK; roundRect(ctx, xT, gy - 70, 120, 70, 8); ctx.fill(); ctx.fillStyle = "#3b4160"; roundRect(ctx, xT + 120, gy - 44, 40, 44, 6); ctx.fill();
      ctx.fillStyle = INK; [xT + 24, xT + 96, xT + 146].forEach((wx) => { ctx.beginPath(); ctx.arc(wx, gy, 10, 0, Math.PI * 2); ctx.fill(); });
      // car
      ctx.fillStyle = BLUE; roundRect(ctx, xC, gy - 34, 70, 34, 8); ctx.fill(); ctx.fillStyle = INK; [xC + 16, xC + 54].forEach((wx) => { ctx.beginPath(); ctx.arc(wx, gy, 8, 0, Math.PI * 2); ctx.fill(); }); ctx.restore();
      text(ctx, "truck 4000 kg", xT + 60, gy - 80, { size: 11, color: MUTED, align: "center" });
      text(ctx, "car 1000 kg", xC + 35, gy - 44, { size: 11, color: MUTED, align: "center" });
      const inContact = tt >= t1 && tt < t2;
      if (inContact) {
        const cxp = xT + 160; const belief = mode === "belief";
        const lenC = belief ? 110 : 80, lenT = belief ? 30 : 80;
        const fy = gy - 112;
        ctx.save(); ctx.strokeStyle = LINE; ctx.setLineDash([3, 4]); ctx.beginPath(); ctx.moveTo(cxp, fy + 8); ctx.lineTo(cxp, gy - 70); ctx.stroke(); ctx.restore();
        arrow(ctx, cxp + 4, fy, cxp + 4 + lenC, fy, belief ? GHOST : F, 5, belief, null);
        arrow(ctx, cxp - 4, fy, cxp - 4 - lenT, fy, belief ? GHOST : F, 5, belief, null);
        text(ctx, belief ? "on car: big?" : "on car: 40 kN", cxp + lenC + 14, fy, { size: 13, weight: 600, color: belief ? GHOST : F, base: "middle" });
        text(ctx, belief ? "on truck: small?" : "on truck: 40 kN", cxp - lenT - 14, fy, { size: 13, weight: 600, color: belief ? GHOST : F, base: "middle", align: "right" });
        pill(ctx, belief ? "belief: truck pushes harder ✗" : "equal and opposite ✓", cxp - 90, fy - 44, belief ? "#fde8ee" : "#e7f6ea", belief ? GHOST : V);
      }
      if (tt >= t2) {
        pill(ctx, "same force, a = F/m: car 40 m/s², truck 10 m/s²", W / 2 - 150, 40, "#fff4e0", "#92400e");
      }
      // force meters
      const mx = 16, my = 16; ctx.save(); ctx.fillStyle = "#fff"; roundRect(ctx, mx, my, 210, 70, 10); ctx.fill(); ctx.strokeStyle = LINE; ctx.stroke(); ctx.restore();
      const fOnCar = inContact ? 40 : 0, fOnTruck = inContact ? 40 : 0;
      const belief = mode === "belief";
      text(ctx, "force on car", mx + 10, my + 18, { size: 11, color: MUTED });
      text(ctx, `${belief && inContact ? "60?" : fOnCar} kN`, mx + 200, my + 18, { size: 12, weight: 700, align: "right", mono: true, color: belief && inContact ? GHOST : INK });
      text(ctx, "force on truck", mx + 10, my + 42, { size: 11, color: MUTED });
      text(ctx, `${belief && inContact ? "15?" : fOnTruck} kN`, mx + 200, my + 42, { size: 12, weight: 700, align: "right", mono: true, color: belief && inContact ? GHOST : INK });
      text(ctx, belief ? "belief" : "Newton's third law", mx + 10, my + 62, { size: 10, color: belief ? GHOST : V, weight: 700 });
      text(ctx, `t = ${tt.toFixed(2)} s`, W - 16, 24, { size: 12, color: MUTED, mono: true, align: "right" });
    },
  };

  // ---------- 5. Free fall (HEAVIER_FASTER) ----------
  const free_fall = {
    duration: 2.6,
    describe: "A 7 kg bowling ball and a 0.06 kg tennis ball are dropped together in a vacuum. Both accelerate at 9.8 m/s² and land at the same instant. In belief mode a red ghost shows the heavy ball landing first — which never happens without air.",
    draw(ctx, W, H, t, mode) {
      const g = 9.8, h = 5, T = Math.sqrt(2 * h / g), tt = Math.min(t, T), landed = t >= T - 0.01;
      const top = 58, gy = H - 50, sy = (gy - top - 22) / h; ground(ctx, W, gy);
      const y = top + 0.5 * g * tt * tt * sy;
      const xH = W * 0.3, xL = W * 0.5;
      // ruler
      ctx.save(); ctx.strokeStyle = MUTED; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(xH - 70, top); ctx.lineTo(xH - 70, gy); ctx.stroke();
      for (let m = 0; m <= 5; m++) { const yy = top + m * sy; ctx.beginPath(); ctx.moveTo(xH - 76, yy); ctx.lineTo(xH - 64, yy); ctx.stroke(); text(ctx, `${m} m`, xH - 82, yy, { size: 10, color: MUTED, align: "right", base: "middle" }); }
      ctx.restore();
      const yH = Math.min(y, gy - 22), yL = Math.min(y, gy - 9);
      if (mode === "belief") {
        const yb = Math.min(gy - 22, top + 0.5 * g * 1.9 * tt * tt * sy);
        ctx.save(); ctx.globalAlpha = 0.55; ctx.strokeStyle = GHOST; ctx.setLineDash([4, 4]); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(xH, yb, 22, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
        text(ctx, "belief: heavy lands first ✗ (red ghost)", W - 16, H - 14, { size: 12, color: GHOST, weight: 700, align: "right" });
      }
      ball(ctx, xH, yH, 22);
      ball(ctx, xL, yL, 9, "#c9d64a");
      text(ctx, "7 kg", xH, top - 30, { size: 11, color: MUTED, align: "center" });
      text(ctx, "0.06 kg", xL, top - 30, { size: 11, color: MUTED, align: "center" });
      if (!landed) {
        arrow(ctx, xH, yH, xH, Math.min(yH + 50, gy - 18), F, 4, false, "68.6 N");
        arrow(ctx, xL, yL, xL, Math.min(yL + 50, gy - 18), F, 2.5, false, "0.59 N");
      } else {
        pill(ctx, "both land at t = 1.01 s", xH - 20, gy - 70, "#e7f6ea", V);
      }
      // panel
      const pw = 262, px = W - pw - 16, py = 14; ctx.save(); ctx.fillStyle = "#fff"; roundRect(ctx, px, py, pw, 108, 10); ctx.fill(); ctx.strokeStyle = LINE; ctx.stroke(); ctx.restore();
      text(ctx, "a = F / m", px + 12, py + 20, { size: 12, color: MUTED, weight: 700 });
      text(ctx, "heavy: 68.6 N / 7 kg  = 9.8 m/s²", px + 12, py + 44, { size: 12, mono: true });
      text(ctx, "light: 0.59 N / 0.06 kg = 9.8 m/s²", px + 12, py + 66, { size: 12, mono: true });
      text(ctx, "bigger pull, bigger inertia — it cancels", px + 12, py + 92, { size: 11, color: V, weight: 600 });
      text(ctx, `t = ${tt.toFixed(2)} s   v = ${(g * tt).toFixed(1)} m/s (both)`, 16, H - 14, { size: 12, color: MUTED, mono: true });
    },
  };

  const SIMS = { throw_up, forces_in_flight, constant_force, collision, free_fall };

  // ---------- controller ----------
  function mount(canvas, kind) {
    const sim = SIMS[kind]; if (!sim) return null;
    const ctx = canvas.getContext("2d");
    const Wl = 680, Hl = 330;
    let t = 0, mode = "physics", playing = false, raf = 0, last = 0, listeners = [];
    function resize() {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Wl * dpr; canvas.height = Hl * dpr; canvas.style.aspectRatio = `${Wl} / ${Hl}`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      render();
    }
    function render() {
      ctx.clearRect(0, 0, Wl, Hl); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, Wl, Hl);
      sim.draw(ctx, Wl, Hl, t, mode);
      listeners.forEach((fn) => fn(t));
    }
    function frame(now) {
      if (!playing) return;
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      t += dt * 0.75; // slightly slower than real time for readability
      if (t > sim.duration + 0.6) t = 0;
      render(); raf = requestAnimationFrame(frame);
    }
    const api = {
      duration: sim.duration, describe: sim.describe,
      play() { if (playing) return; playing = true; last = performance.now(); raf = requestAnimationFrame(frame); },
      pause() { playing = false; cancelAnimationFrame(raf); },
      toggle() { playing ? api.pause() : api.play(); return playing; },
      replay() { t = 0; render(); api.play(); },
      seek(v) { t = Math.max(0, Math.min(sim.duration, v)); render(); },
      step(dv = 0.15) { api.pause(); api.seek(t + dv > sim.duration ? 0 : t + dv); },
      setMode(m) { mode = m; render(); },
      get mode() { return mode; }, get t() { return t; }, get playing() { return playing; },
      onTick(fn) { listeners.push(fn); },
      destroy() { api.pause(); window.removeEventListener("resize", resize); listeners = []; },
    };
    window.addEventListener("resize", resize);
    resize();
    if (!prefersReduced) api.play();
    return api;
  }

  return { mount, prefersReduced, kinds: Object.keys(SIMS) };
})();
