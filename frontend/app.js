/* Re:Learn single-page app. Vanilla JS, no build step.
   Flow: start → question → diagnose → (intervention → transfer probe(s)) → delayed recheck → … → report */

(function () {
  "use strict";

  // ---------------- state ----------------
  const S = {
    learner: null, sessionId: null, order: [], idx: 0, questions: {}, starters: [],
    taxonomy: {}, profile: null, current: null, phase: "question", target: null, probe: null,
    lastAttempt: null, lastInput: null, sim: null, pendingRecheck: null, finished: false,
  };
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const stage = $("#stage");
  const STATUS_COPY = {
    correct: { kicker: "Correct", title: "Right answer, sound reasoning." },
    misconception: { kicker: "Misconception found", title: "The answer is wrong — and I can see why." },
    flawed_reasoning: { kicker: "Right answer, wrong idea", title: "You got it right, but the reasoning hides a misconception." },
    unknown: { kicker: "Tell me more", title: "I'd rather ask than guess." },
  };
  const CONF_LABEL = { guessing: "guessing", fairly_sure: "fairly sure", certain: "certain" };

  // ---------------- api ----------------
  async function api(path, body, method) {
    const opts = { method: method || (body ? "POST" : "GET"), headers: { "Content-Type": "application/json" } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch (_) { /* ignore */ }
      throw new Error(msg);
    }
    return r.json();
  }
  function toast(msg, ms = 2600) {
    const el = $("#toast"); el.textContent = msg; el.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => { el.hidden = true; }, ms);
  }
  function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function pct(x) { return `${Math.round((x || 0) * 100)}%`; }

  // ---------------- rail ----------------
  function rail(step) {
    const steps = ["answer", "diagnose", "fix", "verify", "track"];
    const i = steps.indexOf(step);
    $$("#rail li").forEach((li, k) => { li.classList.toggle("done", k < i); li.classList.toggle("now", k === i); });
  }

  // ---------------- tabs ----------------
  $$(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  function showTab(name) {
    $$(".tab").forEach((b) => { const on = b.dataset.tab === name; b.classList.toggle("is-active", on); on ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"); });
    ["learn", "map", "teacher", "eval", "about"].forEach((n) => { $(`#tab-${n}`).hidden = n !== name; });
    if (name === "map") renderMapFull();
    if (name === "teacher") renderTeacher();
    if (name === "eval") renderEval();
  }

  // ---------------- side panel ----------------
  function stateBadge(st) { return `<span class="state ${st}">${st}</span>`; }
  function pips(m) { let s = '<span class="pips" aria-label="transfer probes passed">'; for (let i = 0; i < m.probes_required; i++) s += `<i class="${i < m.probes_passed || m.state === "resolved" ? "on" : ""}"></i>`; return s + "</span>"; }
  function renderSide() {
    const p = S.profile;
    const stats = $("#sideStats");
    const mini = $("#mapMini");
    if (!p) return;
    const fixed = p.misconceptions.filter((m) => m.state === "resolved").length;
    stats.innerHTML = `<div><b>${p.answered}</b><span>answered</span></div><div><b>${p.misconceptions.length}</b><span>found</span></div><div><b>${fixed}</b><span>fixed</span></div>`;
    $("#sideProgress").textContent = S.order.length ? `Q ${Math.min(S.idx + 1, S.order.length)} / ${S.order.length}` : "";
    if (!p.misconceptions.length) { mini.innerHTML = '<p class="muted small">Nothing found yet. Explain your reasoning and I\'ll look for the idea behind it.</p>'; return; }
    mini.innerHTML = p.misconceptions.map((m) => {
      const tx = S.taxonomy[m.id] || { name: m.id, colour: "#141a33" };
      return `<div class="mchip" style="--c:${tx.colour}"><div><b>${esc(tx.name)}</b><span class="muted tiny">seen ${m.detected}× ${m.confidently_held ? "· held with certainty" : ""}</span><br>${pips(m)}</div><span class="st">${stateBadge(m.state)}</span></div>`;
    }).join("");
    $("#btnReport").hidden = !S.sessionId || S.finished;
  }
  $("#btnReport").addEventListener("click", () => finishSession());

  // ---------------- start ----------------
  function showStart() {
    rail(null); $("#learnerChip").hidden = true;
    stage.innerHTML = `
      <div class="hero fade-in">
        <h1 class="h-display">Re:Learn doesn't tell you that you're wrong. It tells you <em>why</em> — and checks that the fix stuck.</h1>
        <p class="lede">Answer a mechanics question, explain your thinking in a sentence. The model names the misconception behind your reasoning, fixes exactly that, and then tests you in a new situation.</p>
        <form class="form" id="startForm">
          <div class="field"><label for="name">Your name</label><input class="input" id="name" name="name" placeholder="e.g. Aiman" autocomplete="off" required maxlength="40"></div>
          <div class="field"><span class="lbl" style="display:block;font-weight:500;margin-bottom:.35rem">Session</span>
            <div class="seg" role="radiogroup" aria-label="Session type">
              <label><input type="radio" name="mode" value="quick" checked><span>Quick (8 questions)</span></label>
              <label><input type="radio" name="mode" value="topic"><span>One topic</span></label>
              <label><input type="radio" name="mode" value="full"><span>Full bank (30)</span></label>
            </div>
            <select class="input" id="topic" style="margin-top:.6rem;max-width:280px" hidden aria-label="Topic">
              <option value="kinematics">Kinematics: velocity vs acceleration</option>
              <option value="newton1">Newton's first law</option>
              <option value="newton2">Newton's second law</option>
              <option value="newton3">Newton's third law</option>
              <option value="freefall">Free fall</option>
            </select>
          </div>
          <div class="btn-row" style="margin-top:.2rem"><button class="btn accent" type="submit">Start learning →</button></div>
        </form>
        <div class="howitworks" aria-label="How it works">
          <div><b>1 · Answer</b>Pick an option, rate your confidence, explain why.</div>
          <div><b>2 · Diagnose</b>The model names the idea behind your reasoning — or asks for more.</div>
          <div><b>3 · Fix</b>An explanation, worked example and animation for that idea.</div>
          <div><b>4 · Verify</b>Transfer questions in new contexts. Clean reasoning required.</div>
          <div><b>5 · Track</b>Active → improving → resolved. Re-checked later. Recurring if it comes back.</div>
        </div>
      </div>`;
    $$('#startForm input[name=mode]').forEach((r) => r.addEventListener("change", () => { $("#topic").hidden = r.value !== "topic" || !r.checked; }));
    $("#startForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = $("#name").value.trim(); if (!name) return;
      const mode = $('#startForm input[name=mode]:checked').value;
      try {
        const res = await api("/api/session/start", { learner: name, mode, topic: mode === "topic" ? $("#topic").value : null });
        S.learner = res.learner; S.sessionId = res.session_id; S.order = res.question_order; S.idx = 0; S.finished = false;
        res.questions.forEach((q) => { S.questions[q.id] = q; });
        S.starters = res.sentence_starters; S.profile = res.profile;
        $("#learnerName").textContent = S.learner; $("#learnerChip").hidden = false;
        renderSide(); showQuestion();
      } catch (err) { toast(`Could not start: ${err.message}`); }
    });
    $("#name").focus();
  }

  // ---------------- question / probe form ----------------
  function answerForm(item, { kind = "question", context = null, target = null, prefill = null, intro = null } = {}) {
    const tagHtml = kind === "question"
      ? `<span class="tag">${esc(item.topic)}</span><span class="muted small">Question ${S.idx + 1} of ${S.order.length}</span>`
      : kind === "recheck"
        ? `<span class="tag recheck">Delayed recheck</span><span class="muted small">${esc(context || "")}</span>`
        : `<span class="tag probe">Transfer check · ${esc(context || "new context")}</span>`;
    const targetChip = target ? `<span class="chip" style="--c:${S.taxonomy[target].colour}">testing: ${esc(S.taxonomy[target].name)}</span>` : "";
    stage.innerHTML = `
      <div class="fade-in">
        ${intro ? `<div class="verdict ${intro.cls}"><div class="kicker">${esc(intro.kicker)}</div><div class="title">${esc(intro.title)}</div>${intro.body ? `<p style="margin:.3rem 0 0">${esc(intro.body)}</p>` : ""}</div>` : ""}
        <div class="q-head">${tagHtml}${targetChip}</div>
        <p class="q-prompt" id="prompt">${esc(item.prompt)}</p>
        <form id="answerForm">
          <div class="opts" role="radiogroup" aria-labelledby="prompt" id="opts"></div>
          <div class="explain">
            <label for="expl"><b>Why?</b> <span class="muted">One or two sentences. The words matter more than the option.</span></label>
            <textarea class="input" id="expl" rows="3" placeholder="Explain your reasoning…" maxlength="600">${esc(prefill?.explanation || "")}</textarea>
            <div class="starters" aria-label="Sentence starters">${S.starters.map((s) => `<button type="button" class="starter">${esc(s)}</button>`).join("")}</div>
            <div class="conf-row">
              <span class="lbl" style="font-weight:500">How sure are you?</span>
              <div class="seg" role="radiogroup" aria-label="Confidence">
                ${["guessing", "fairly_sure", "certain"].map((c) => `<label><input type="radio" name="conf" value="${c}" ${(prefill?.confidence || "fairly_sure") === c ? "checked" : ""}><span>${CONF_LABEL[c]}</span></label>`).join("")}
              </div>
              <span class="wordcount" id="wc">0 words</span>
            </div>
          </div>
          <div class="btn-row">
            <button class="btn accent" type="submit" id="submitBtn" disabled>${kind === "question" ? "Diagnose my thinking" : "Check my thinking"} →</button>
            <span class="muted small">Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to submit</span>
          </div>
        </form>
      </div>`;
    const opts = $("#opts"), tpl = $("#tpl-option");
    item.options.forEach((o) => {
      const n = tpl.content.firstElementChild.cloneNode(true);
      const inp = n.querySelector("input"); inp.value = o.key; inp.id = `opt-${o.key}`;
      if (prefill?.choice === o.key) inp.checked = true;
      n.querySelector(".opt-key").textContent = o.key; n.querySelector(".opt-text").textContent = o.text;
      opts.appendChild(n);
    });
    const expl = $("#expl"), wc = $("#wc"), btn = $("#submitBtn");
    const update = () => {
      const words = expl.value.trim().split(/\s+/).filter(Boolean).length;
      wc.textContent = `${words} word${words === 1 ? "" : "s"}`;
      btn.disabled = !$('input[name=opt]:checked');
    };
    expl.addEventListener("input", update); opts.addEventListener("change", update); update();
    $$(".starter").forEach((b) => b.addEventListener("click", () => { expl.value = (expl.value.trim() ? expl.value.trim() + " " : "") + b.textContent + " "; expl.focus(); update(); }));
    expl.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !btn.disabled) $("#answerForm").requestSubmit(); });
    $("#answerForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const payload = { choice: $('input[name=opt]:checked').value, explanation: expl.value.trim(), confidence: $('input[name=conf]:checked').value };
      btn.disabled = true; btn.textContent = "Thinking…";
      (kind === "question" ? submitDiagnose(payload) : submitReassess(payload, kind)).catch((err) => { toast(err.message); btn.disabled = false; btn.textContent = "Try again"; });
    });
    (prefill ? expl : $("#opt-A")).focus({ preventScroll: true });
    stage.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function showQuestion(prefill = null) {
    if (S.idx >= S.order.length) return finishSession();
    S.phase = "question"; S.target = null; S.probe = null; rail("answer");
    S.current = S.questions[S.order[S.idx]];
    renderSide();
    answerForm(S.current, { kind: "question", prefill });
  }

  async function submitDiagnose(payload) {
    S.lastInput = payload;
    const res = await api("/api/diagnose", { learner: S.learner, session_id: S.sessionId, question_id: S.current.id, ...payload });
    S.lastAttempt = res; S.profile = res.profile; renderSide();
    showVerdict(res);
  }

  // ---------------- verdict + intervention ----------------
  function probBars(probs, top) {
    const entries = Object.entries(probs).slice(0, 4);
    return `<div class="probs" aria-label="Model probabilities">${entries.map(([k, v]) => `<div><span>${esc(S.taxonomy[k]?.name || (k === "NONE" ? "No misconception" : k))}</span><span class="bar"><i class="${k === top ? "top" : ""}" style="width:${pct(v)}"></i></span><span class="mono">${pct(v)}</span></div>`).join("")}</div>`;
  }
  function feedbackBox(attemptId, currentLabel) {
    const opts = [["NONE", "No misconception — my reasoning was fine"], ...Object.values(S.taxonomy).map((m) => [m.id, m.name])]
      .filter(([k]) => k !== currentLabel).map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join("");
    return `<div class="feedback"><details><summary>That's not what I meant</summary>
      <div class="row"><label for="fb-${attemptId}" class="small">What were you actually thinking?</label><select id="fb-${attemptId}">${opts}</select>
      <button class="btn ghost small" type="button" data-fb="${attemptId}">Send</button></div>
      <p class="muted tiny" style="margin:.4rem 0 0">Stored as a candidate training example — this is how the model gets better.</p></details></div>`;
  }
  function verdictBlock(res) {
    const c = STATUS_COPY[res.status];
    const self = res.self_confidence ? ` · you said: ${CONF_LABEL[res.self_confidence]}` : "";
    return `<div class="verdict ${res.status}"><div class="kicker">${c.kicker}${res.correct ? " · answer ✓" : res.status !== "unknown" ? " · answer ✗" : ""}</div><div class="title">${c.title}</div>
      <div class="muted small">model confidence ${pct(res.confidence)} · ${res.latency_ms} ms${self}${res.source === "embedding" ? " · matched by description (unseen-misconception fallback)" : ""}</div></div>`;
  }

  function showVerdict(res) {
    rail("diagnose");
    if (res.status === "unknown") {
      stage.innerHTML = `<div class="fade-in">${verdictBlock(res)}
        <p class="lede" style="margin-bottom:.8rem">${esc(res.ask)}</p>
        <p class="muted small">Top candidates right now:</p>${probBars(res.probabilities, null)}
        <div class="btn-row"><button class="btn accent" id="elab">Add to my explanation</button></div></div>`;
      $("#elab").addEventListener("click", () => showQuestion(S.lastInput));
      return;
    }
    if (res.status === "correct") {
      stage.innerHTML = `<div class="fade-in">${verdictBlock(res)}
        <p class="lede">${esc(res.message)}</p>${probBars(res.probabilities, "NONE")}
        <div class="btn-row"><button class="btn accent" id="next">Next question →</button></div></div>`;
      $("#next").addEventListener("click", () => advance());
      return;
    }
    // misconception or flawed reasoning
    const m = res.misconception, iv = res.intervention;
    const held = res.confidently_held ? `<span class="badge">held with certainty</span>` : "";
    const recur = res.state === "recurring" ? `<span class="badge">came back after being resolved</span>` : "";
    stage.innerHTML = `<div class="fade-in">${verdictBlock(res)}
      <div class="diag">
        <div class="belief" style="--c:${m.colour}">
          <h3>${esc(m.name)} ${held}${recur}</h3>
          <p class="muted small" style="margin:0">${esc(m.short)}</p>
          <div class="vs">
            <div class="you"><b>What your reasoning suggests</b>${esc(m.believes)}</div>
            <div class="phys"><b>What physics says</b>${esc(m.physics)}</div>
          </div>
        </div>
        <div class="confbox">
          <b>How sure is the model?</b>
          <div class="meter" role="meter" aria-valuenow="${Math.round(res.confidence * 100)}" aria-valuemin="0" aria-valuemax="100" aria-label="model confidence"><i style="width:${pct(res.confidence)}"></i></div>
          <div class="small"><span class="mono">${pct(res.confidence)}</span> that this is the idea behind your words</div>
          ${probBars(res.probabilities, res.label)}
          ${res.notes?.length ? `<p class="muted tiny" style="margin:.6rem 0 0">${esc(res.notes.join(" · "))}</p>` : ""}
          ${feedbackBox(res.attempt_id, res.label)}
        </div>
      </div>
      <div class="fix" id="fix">
        <div class="fix-head">${esc(iv.headline)}</div>
        ${iv.explanation.map((p) => `<p>${esc(p)}</p>`).join("")}
        <div class="simwrap" id="simwrap"><canvas id="sim" width="680" height="330" role="img" aria-label="Physics animation"></canvas>
          <div class="sim-bar">
            <button class="btn small" type="button" id="simPlay">${Simulations.prefersReduced ? "Play" : "Pause"}</button>
            <button class="btn ghost small" type="button" id="simReplay">Replay</button>
            <button class="btn ghost small" type="button" id="simStep">Step</button>
            <label class="small" style="display:flex;align-items:center;gap:.4rem;flex:1;min-width:140px"><span class="sr-only">Time</span><input type="range" id="simSeek" min="0" max="100" value="0" style="width:100%" aria-label="Scrub animation time"></label>
            <label class="small" style="display:flex;align-items:center;gap:.4rem"><input type="checkbox" id="simBelief"> Show what the belief predicts</label>
          </div>
          <div class="sim-desc" id="simDesc"></div>
        </div>
        <div class="worked"><h3>Worked example: ${esc(iv.worked_example.title)}</h3><ol>${iv.worked_example.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol></div>
        <div class="check"><b>Check yourself:</b> ${esc(iv.check_yourself)}</div>
      </div>
      <div class="btn-row"><button class="btn accent" id="toProbe">Test the fix in a new situation →</button><span class="muted small">A transfer question — same idea, different context.</span></div>
    </div>`;
    rail("fix");
    mountSim(iv.simulation);
    $("#toProbe").addEventListener("click", () => { if (res.probe) showProbe(res.probe, res.probe.target); else advance(); });
    wireFeedback();
  }

  function mountSim(kind) {
    if (S.sim) { S.sim.destroy(); S.sim = null; }
    const canvas = $("#sim"); if (!canvas) return;
    const sim = Simulations.mount(canvas, kind); if (!sim) return;
    S.sim = sim;
    $("#simDesc").textContent = sim.describe;
    const play = $("#simPlay"), seek = $("#simSeek");
    play.addEventListener("click", () => { const p = sim.toggle(); play.textContent = p ? "Pause" : "Play"; });
    $("#simReplay").addEventListener("click", () => { sim.replay(); play.textContent = "Pause"; });
    $("#simStep").addEventListener("click", () => { sim.step(); play.textContent = "Play"; });
    seek.addEventListener("input", () => { sim.pause(); play.textContent = "Play"; sim.seek(seek.value / 100 * sim.duration); });
    sim.onTick((t) => { if (sim.playing) seek.value = Math.round(t / sim.duration * 100); });
    $("#simBelief").addEventListener("change", (e) => sim.setMode(e.target.checked ? "belief" : "physics"));
  }

  function wireFeedback() {
    $$("[data-fb]").forEach((b) => b.addEventListener("click", async () => {
      const id = b.dataset.fb, sel = $(`#fb-${id}`);
      try { const r = await api("/api/feedback", { learner: S.learner, attempt_id: Number(id), suggested_label: sel.value, note: "" }); toast(r.message); b.disabled = true; b.textContent = "Sent"; }
      catch (err) { toast(err.message); }
    }));
  }

  // ---------------- probes ----------------
  function showProbe(probe, target, intro = null, kind = "probe") {
    S.phase = kind; S.probe = probe; S.target = target; rail("verify");
    answerForm(probe, { kind, context: probe.context, target, intro });
  }

  async function submitReassess(payload, kind) {
    S.lastInput = payload;
    const res = await api("/api/reassess", { learner: S.learner, session_id: S.sessionId, misconception: S.target, probe_id: S.probe.id, phase: kind === "recheck" ? "recheck" : "probe", ...payload });
    S.lastAttempt = res; S.profile = res.profile; renderSide();
    showProbeResult(res, kind);
  }

  function showProbeResult(res, kind) {
    const tx = S.taxonomy[res.target];
    if (res.resolved === null) {
      stage.innerHTML = `<div class="fade-in"><div class="verdict unknown"><div class="kicker">Almost</div><div class="title">${esc(res.ask)}</div></div>
        <div class="btn-row"><button class="btn accent" id="elab">Add my reasoning</button></div></div>`;
      $("#elab").addEventListener("click", () => showProbe(S.probe, S.target, null, kind));
      return;
    }
    const cls = res.resolved ? "resolved" : "notyet";
    const kicker = res.resolved ? (res.resolved_now || kind === "recheck" ? "Resolved" : "Clear in this context") : (kind === "recheck" ? "It came back" : "Not yet");
    const title = res.message;
    const detail = res.correct
      ? (res.target_present ? `Answer ✓ — but the reasoning still reads as “${esc(tx.short.toLowerCase())}”.` : `Answer ✓ and no trace of “${esc(tx.short.toLowerCase())}” in your words.`)
      : `Answer ✗${res.label && res.label !== "UNKNOWN" && res.label !== "NONE" ? ` — reasoning reads as ${esc(S.taxonomy[res.label]?.name || res.label)}` : ""}.`;
    const newM = res.new_misconception ? `<div class="callout"><b>Something else surfaced:</b> ${esc(res.new_misconception.name)} (${pct(res.new_misconception.confidence)}). Added to your map — we'll come back to it.</div>` : "";
    let html = `<div class="fade-in"><div class="verdict ${cls}"><div class="kicker">${kicker} · <span class="chip" style="--c:${tx.colour}">${esc(tx.name)}</span></div><div class="title">${esc(title)}</div>
      <div class="small">${detail} <span class="muted">· model ${pct(res.confidence)}</span></div>
      ${res.state ? `<div style="margin-top:.4rem">${stateBadge(res.state)} ${res.probes_required ? pips({ probes_required: res.probes_required, probes_passed: res.probes_passed, state: res.state }) : ""}</div>` : ""}</div>${newM}`;
    if (res.resolved) {
      if (res.probe) {
        html += `<div class="btn-row"><button class="btn accent" id="nextProbe">Next context: ${esc(res.probe.context)} →</button></div></div>`;
        stage.innerHTML = html; $("#nextProbe").addEventListener("click", () => showProbe(res.probe, res.target));
      } else {
        html += `<div class="btn-row"><button class="btn accent" id="cont">Continue →</button></div></div>`;
        stage.innerHTML = html; $("#cont").addEventListener("click", () => advance());
      }
      rail("track");
      return;
    }
    // not resolved: show the intervention again (collapsed) + next probe
    const iv = res.intervention;
    html += `<details class="collapsible" open><summary>Look at the idea again</summary><div class="fix" style="margin-top:.8rem">
        <div class="fix-head">${esc(iv.headline)}</div>${iv.explanation.map((p) => `<p>${esc(p)}</p>`).join("")}
        <div class="simwrap"><canvas id="sim" width="680" height="330" role="img" aria-label="Physics animation"></canvas>
          <div class="sim-bar"><button class="btn small" type="button" id="simPlay">${Simulations.prefersReduced ? "Play" : "Pause"}</button><button class="btn ghost small" type="button" id="simReplay">Replay</button><button class="btn ghost small" type="button" id="simStep">Step</button>
          <label class="small" style="display:flex;align-items:center;gap:.4rem;flex:1;min-width:140px"><input type="range" id="simSeek" min="0" max="100" value="0" style="width:100%" aria-label="Scrub animation time"></label>
          <label class="small" style="display:flex;align-items:center;gap:.4rem"><input type="checkbox" id="simBelief" checked> Show what the belief predicts</label></div>
          <div class="sim-desc" id="simDesc"></div></div>
        <div class="check"><b>Check yourself:</b> ${esc(iv.check_yourself)}</div></div></details>`;
    html += res.probe
      ? `<div class="btn-row"><button class="btn accent" id="nextProbe">Try another context: ${esc(res.probe.context)} →</button></div></div>`
      : `<div class="btn-row"><button class="btn accent" id="cont">Leave it open and continue →</button></div></div>`;
    stage.innerHTML = html;
    mountSim(iv.simulation); if (S.sim) S.sim.setMode("belief");
    if (res.probe) $("#nextProbe").addEventListener("click", () => showProbe(res.probe, res.target));
    else $("#cont").addEventListener("click", () => advance());
    rail("fix");
  }

  // ---------------- advancing, delayed recheck ----------------
  async function advance() {
    if (S.sim) { S.sim.destroy(); S.sim = null; }
    // Delayed recheck due? (FR-7)
    try {
      const rc = await api(`/api/recheck/${encodeURIComponent(S.learner)}`);
      if (rc.probe) {
        const tx = S.taxonomy[rc.misconception.id];
        showProbe(rc.probe, rc.misconception.id, { cls: "unknown", kicker: "Quick recheck", title: `Earlier you resolved “${tx.name}”. Still true a few questions later?`, body: "Same idea, new context. This is how Re:Learn tells learning apart from a lucky streak." }, "recheck");
        return;
      }
    } catch (_) { /* ignore */ }
    S.idx += 1;
    if (S.idx >= S.order.length) return finishSession();
    showQuestion();
  }

  // ---------------- report ----------------
  async function finishSession() {
    if (S.sim) { S.sim.destroy(); S.sim = null; }
    if (!S.finished && S.sessionId) { try { await api("/api/session/finish", { session_id: S.sessionId }); } catch (_) { /* ignore */ } }
    S.finished = true; renderSide(); rail("track");
    const r = await api(`/api/report/${encodeURIComponent(S.learner)}`);
    const s = r.summary;
    const tiles = [
      ["good", s.right_first_time, "right first time"], ["warn", s.found, "misconceptions found"], ["good", s.fixed, "fixed & verified"],
      ["", s.improving, "improving"], ["warn", s.still_open, "still open"], ["bad", s.recurring, "recurring"], ["", s.flawed_reasoning, "right answer, wrong idea"],
    ];
    const rows = r.misconceptions.map((m) => {
      const probes = r.timeline.filter((t) => (t.phase === "probe" || t.phase === "recheck") && t.target === m.id);
      const ribbon = probes.map((t) => `<i class="${t.resolved ? "probe-pass" : "probe-fail"}" title="${t.phase} ${t.resolved ? "passed" : "failed"}"></i>`).join("");
      return `<div class="mrow" style="--c:${m.colour}"><div><b>${esc(m.name)}</b> ${stateBadge(m.state)} ${m.confidently_held ? '<span class="badge">held with certainty</span>' : ""}
        <div class="meta">seen ${m.detected}× · probes passed ${m.probes_passed}/${m.probes_required} · ${m.recheck_pending ? "recheck pending" : m.state === "resolved" ? "recheck passed" : ""}</div>
        <div class="small" style="margin-top:.3rem">${esc(m.physics)}</div><div class="ribbon">${ribbon}</div></div></div>`;
    }).join("") || '<div class="empty">No misconceptions were found — every answer came with sound reasoning.</div>';
    const timeline = r.timeline.map((t) => `<i class="${t.phase === "question" ? t.status : (t.resolved ? "probe-pass" : "probe-fail")}" title="${t.phase} ${t.item_id}: ${t.status}"></i>`).join("");
    stage.innerHTML = `<div class="fade-in"><h1 class="h-display">Session report for ${esc(r.learner)}</h1>
      <p class="lede">${s.answered} question${s.answered === 1 ? "" : "s"} answered · ${pct(s.explained_share)} came with an explanation</p>
      <div class="tiles">${tiles.map(([c, v, l]) => `<div class="tile ${c}"><b>${v}</b><span>${l}</span></div>`).join("")}</div>
      <h2>What happened to each idea</h2>${rows}
      <h2 style="margin-top:1.4rem">Timeline</h2><div class="ribbon">${timeline}</div>
      <div class="legend"><span><i style="background:var(--green)"></i>correct</span><span><i style="background:var(--amber)"></i>misconception</span><span><i style="background:var(--purple)"></i>right answer, wrong idea</span><span><i style="background:var(--blue)"></i>asked for more</span><span><i style="background:var(--green);border-radius:50%"></i>probe passed</span><span><i style="background:var(--red);border-radius:50%"></i>probe failed</span></div>
      <div class="btn-row"><button class="btn accent" id="again">Start another session</button><button class="btn ghost" id="dl">Download report (JSON)</button><button class="btn ghost" id="teacherBtn">Teacher view</button></div></div>`;
    $("#again").addEventListener("click", () => { S.sessionId = null; S.order = []; S.idx = 0; showStart(); });
    $("#dl").addEventListener("click", () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(r, null, 2)], { type: "application/json" })); a.download = `relearn-report-${S.learner}.json`; a.click(); });
    $("#teacherBtn").addEventListener("click", () => showTab("teacher"));
  }

  // ---------------- full map ----------------
  async function renderMapFull() {
    const el = $("#mapFull");
    if (!S.learner) { el.innerHTML = '<div class="empty">Start a session on the Learn tab first.</div>'; return; }
    const p = await api(`/api/profile/${encodeURIComponent(S.learner)}`); S.profile = p; renderSide();
    if (!p.misconceptions.length) { el.innerHTML = '<div class="empty">Nothing on the map yet.</div>'; return; }
    el.innerHTML = p.misconceptions.map((m) => {
      const tx = S.taxonomy[m.id];
      const hist = p.timeline.filter((t) => t.label === m.id || t.target === m.id).map((t) => `<i class="${t.phase === "question" ? t.status : (t.resolved ? "probe-pass" : "probe-fail")}" title="${t.phase} ${t.item_id}"></i>`).join("");
      return `<div class="mrow" style="--c:${tx.colour}"><div><b>${esc(tx.name)}</b> ${stateBadge(m.state)} ${m.confidently_held ? '<span class="badge">held with certainty</span>' : ""}
        <div class="meta">${esc(tx.short)} · detected ${m.detected}× · probes ${m.probes_passed}/${m.probes_required} passed, ${m.probes_failed} failed</div>
        <div class="small" style="margin-top:.4rem"><b style="color:var(--red)">Belief:</b> ${esc(tx.believes)}</div>
        <div class="small"><b style="color:var(--green)">Physics:</b> ${esc(tx.physics)}</div>
        <div class="ribbon">${hist}</div></div></div>`;
    }).join("");
  }

  // ---------------- teacher ----------------
  async function renderTeacher() {
    const el = $("#teacherView");
    const c = await api("/api/class");
    if (!c.learners) { el.innerHTML = '<div class="empty">No learners yet. Run a session or two (try different names) and come back.</div>'; return; }
    const ids = Object.keys(c.taxonomy);
    const max = Math.max(1, ...ids.map((m) => (c.misconceptions[m]?.total || 0)));
    const bars = ids.map((m) => {
      const d = c.misconceptions[m] || { active: 0, improving: 0, resolved: 0, recurring: 0, total: 0, confidently_held: 0 };
      const seg = (k) => d[k] ? `<i class="${k}" style="width:${d[k] / max * 100}%" title="${k}: ${d[k]}"></i>` : "";
      return `<div class="barrow"><div><b style="color:${c.taxonomy[m].colour}">${esc(c.taxonomy[m].name)}</b><div class="muted tiny">${d.confidently_held ? `${d.confidently_held} held with certainty` : ""}</div></div><div class="track">${seg("recurring")}${seg("active")}${seg("improving")}${seg("resolved")}</div><div class="mono small">${d.total} / ${c.learners}</div></div>`;
    }).join("");
    const st = c.question_status_counts;
    el.innerHTML = `<div class="tiles"><div class="tile"><b>${c.learners}</b><span>learners</span></div><div class="tile"><b>${c.attempts}</b><span>attempts</span></div><div class="tile good"><b>${st.correct || 0}</b><span>correct</span></div><div class="tile warn"><b>${st.misconception || 0}</b><span>misconception</span></div><div class="tile"><b>${st.flawed_reasoning || 0}</b><span>right answer, wrong idea</span></div><div class="tile"><b>${st.unknown || 0}</b><span>asked for more</span></div></div>
      <h2>Misconceptions across the class</h2><p class="muted small">Learners holding each idea, by state. Bars are scaled to the most common misconception.</p>
      <div class="bars">${bars}</div>
      <div class="legend"><span><i style="background:var(--red)"></i>recurring</span><span><i style="background:var(--amber)"></i>active</span><span><i style="background:var(--blue)"></i>improving</span><span><i style="background:var(--green)"></i>resolved</span></div>
      <p class="muted small" style="margin-top:1rem">Learners: ${c.learner_names.map(esc).join(", ")}</p>`;
  }

  // ---------------- evaluation ----------------
  async function renderEval() {
    const el = $("#evalView");
    const m = await api("/api/metrics");
    if (!m.available) { el.innerHTML = `<div class="empty">No evaluation yet. Run <code>python ml/evaluate.py</code> and refresh.</div>`; return; }
    const T = m.targets, ok = (b) => (b ? '<span class="ok">✓ met</span>' : '<span class="no">✗ missed</span>');
    const rows = [
      ["Diagnosis macro-F1 (held-out questions)", m.heldout_questions_only.macro_f1, `≥ ${T.macro_f1_heldout_questions}`, m.targets_met.macro_f1_heldout_questions],
      [`Confusable-pair accuracy (n=${m.confusable_pair_n})`, m.confusable_pair_accuracy, `≥ ${T.confusable_pair_accuracy}`, m.targets_met.confusable_pair_accuracy],
      [`Flawed-reasoning recall (n=${m.flawed_reasoning_n})`, m.flawed_reasoning_recall, `≥ ${T.flawed_reasoning_recall}`, m.targets_met.flawed_reasoning_recall],
      ["Unseen-misconception top-1 (leave-one-out)", m.unseen_misconception_top1, `≥ ${T.unseen_misconception_top1}`, m.targets_met.unseen_misconception_top1],
      ["Calibration (ECE)", m.ece, `≤ ${T.ece}`, m.targets_met.ece],
      ["Latency per diagnosis", `${m.latency_ms_per_diagnosis.toFixed(1)} ms`, "< 1000 ms", true],
    ];
    const labels = m.confusion_matrix.labels, cm = m.confusion_matrix.matrix, mx = Math.max(...cm.flat());
    const short = (l) => (l === "NONE" ? "none" : l.replace("_", " ").toLowerCase().replace("va confusion", "v–a").replace("force velocity", "force→v").replace("heavier faster", "heavier").replace("third law", "3rd law"));
    const grid = `<div class="cm" style="grid-template-columns: 90px repeat(${labels.length}, minmax(52px, 1fr))">
      <div class="cell hd">true ↓ / pred →</div>${labels.map((l) => `<div class="cell hd">${short(l)}</div>`).join("")}
      ${cm.map((row, i) => `<div class="cell hd rh">${short(labels[i])}</div>` + row.map((v, j) => `<div class="cell" style="background:${v ? `rgba(124,58,237,${0.12 + 0.75 * v / mx})` : "var(--paper-2)"};color:${v / mx > 0.5 ? "#fff" : "var(--ink)"}">${v}</div>`).join("")).join("")}</div>`;
    const unseen = Object.entries(m.unseen_misconception).map(([k, v]) => `<tr><td>${esc(S.taxonomy[k]?.name || k)}</td><td>${v.n}</td><td>${v.top1.toFixed(2)}</td><td>${v.top1_when_answered.toFixed(2)}</td><td>${pct(v.abstained)}</td><td>${(v.false_positive_rate * 100).toFixed(1)}%</td></tr>`).join("");
    const perLabel = Object.entries(m.per_label).map(([k, v]) => `<tr><td>${esc(S.taxonomy[k]?.name || "No misconception")}</td><td>${v.precision.toFixed(2)}</td><td>${v.recall.toFixed(2)}</td><td>${v.f1.toFixed(2)}</td><td>${v.support}</td></tr>`).join("");
    const hand = m.hand_rows_template_only_model;
    el.innerHTML = `
      <div class="callout">Dataset: <b>${m.dataset.rows}</b> labelled rows over <b>${m.dataset.items}</b> items (${m.dataset.hand_rows} hand-written). Split by item: <b>${m.split.train_items.length}</b> train / <b>${m.split.test_items.length}</b> held-out. Held-out items: <span class="mono">${m.split.test_items.join(", ")}</span>.</div>
      <table class="t"><thead><tr><th>Metric</th><th>Value</th><th>Target</th><th></th></tr></thead><tbody>${rows.map(([n, v, t, b]) => `<tr><td>${n}</td><td class="mono">${typeof v === "number" ? v.toFixed(3) : v}</td><td class="mono">${t}</td><td>${ok(b)}</td></tr>`).join("")}</tbody></table>
      <h2>Confusion matrix (held-out)</h2>${grid}
      <h2>Does synthetic training data transfer to natural writing?</h2>
      <p class="small">A model trained on <em>template rows only</em>, tested on all ${m.dataset.hand_rows} hand-written rows: accuracy <b class="mono">${(hand.accuracy || 0).toFixed(3)}</b>, macro-F1 <b class="mono">${(hand.macro_f1 || 0).toFixed(3)}</b>, abstained on ${pct(hand.abstained)}. Vague explanations routed to <em>unknown</em>: <b class="mono">${pct(m.vague_abstain_rate)}</b> (n=${m.vague_n}); valid rows abstained: <b class="mono">${pct(m.abstain_rate_on_valid_rows)}</b>. Flawed-reasoning false alarms: <b class="mono">${(m.flawed_reasoning_false_alarm_rate * 100).toFixed(1)}%</b>.</p>
      <h2>Unseen misconceptions (leave one out of training; recover it from its description)</h2>
      <table class="t"><thead><tr><th>Held out</th><th>n</th><th>top-1</th><th>top-1 when answered</th><th>abstained</th><th>false positives</th></tr></thead><tbody>${unseen}</tbody></table>
      <h2>Per label</h2>
      <table class="t"><thead><tr><th>Label</th><th>P</th><th>R</th><th>F1</th><th>n</th></tr></thead><tbody>${perLabel}</tbody></table>
      <p class="muted small">Decision rule: answer prior ×${m.decision_config.prior_boost} on mapped labels · abstain below ${m.decision_config.abstain_threshold} · unseen fallback when description similarity ≥ ${m.decision_config.unseen_sim_threshold} with margin ${m.decision_config.unseen_margin}. Machine: ${esc(m.machine)}.</p>`;
  }

  // ---------------- boot ----------------
  async function boot() {
    try {
      const [tax, health] = await Promise.all([api("/api/misconceptions"), api("/api/health")]);
      S.taxonomy = tax; $("#modelName").textContent = `${health.model.backend} · ${health.probes_required} probes to resolve`;
    } catch (err) { toast(`API not reachable: ${err.message}`, 6000); }
    showStart();
  }
  boot();
})();
