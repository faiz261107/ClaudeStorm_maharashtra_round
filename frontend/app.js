/* Re:Learn single-page app. Vanilla JS, no build step.
   Flow: start → (welcome back + cross-session recheck) → question [choice | working | diagram]
         → diagnose → (personalised fix + intervention → transfer probe(s)) → delayed recheck → … → report
   Input tools: typed, voice dictation (Web Speech API), photo of handwritten working (OCR). */

(function () {
  "use strict";

  // ---------------- state ----------------
  const S = {
    learner: null, sessionId: null, order: [], idx: 0, questions: {}, starters: [],
    taxonomy: {}, profile: null, current: null, phase: "question", target: null, probe: null,
    lastAttempt: null, lastInput: null, sim: null, finished: false, welcome: null,
    shownAt: 0, edits: 0, inputMethod: "typed", imageId: null, fbd: null, teacherToken: null, liveTimer: null,
  };
  try { S.teacherToken = sessionStorage.getItem("relearn-teacher"); } catch (_) { /* ignore */ }
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
  const MODE_LABEL = { quick: "Quick", topic: "One topic", full: "Full bank", working: "Show your working", diagram: "Draw the forces" };

  // ---------------- api / utils ----------------
  async function api(path, body, method) {
    const opts = { method: method || (body ? "POST" : "GET"), headers: { "Content-Type": "application/json" } };
    if (S.teacherToken) opts.headers["X-Teacher-Token"] = S.teacherToken;
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    if (r.status === 401 && S.teacherToken && path !== "/api/teacher/login") setTeacherToken(null);  // PIN needed again
    if (!r.ok) { let msg = r.statusText; try { msg = (await r.json()).detail || msg; } catch (_) { /* ignore */ } throw new Error(msg); }
    return r.json();
  }
  function toast(msg, ms = 2600) { const el = $("#toast"); el.textContent = msg; el.hidden = false; clearTimeout(toast._t); toast._t = setTimeout(() => { el.hidden = true; }, ms); }
  function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function pct(x) { return `${Math.round((x || 0) * 100)}%`; }
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  function toTop() { window.scrollTo({ top: 0, left: 0, behavior: "auto" }); }
  function rail(step) { const steps = ["answer", "diagnose", "fix", "verify", "track"]; const i = steps.indexOf(step); $$("#rail li").forEach((li, k) => { li.classList.toggle("done", k < i); li.classList.toggle("now", k === i); }); }

  // ---------------- theme ----------------
  $("#themeToggle").addEventListener("click", () => {
    const root = document.documentElement;
    const sysDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const cur = root.getAttribute("data-theme") || (sysDark ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("relearn-theme", next); } catch (_) { /* ignore */ }
  });

  // ---------------- tabs ----------------
  $$(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  function showTab(name) {
    $$(".tab").forEach((b) => { const on = b.dataset.tab === name; b.classList.toggle("is-active", on); on ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"); });
    ["learn", "map", "teacher", "eval", "about"].forEach((n) => { $(`#tab-${n}`).hidden = n !== name; });
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    if (name === "map") renderMapFull();
    if (name !== "teacher") stopLive();
    if (name === "teacher") renderTeacher($(".subtab.is-active")?.dataset.sub || "overview");
    if (name === "eval") renderEval();
  }
  $$(".subtab").forEach((b) => b.addEventListener("click", () => { $$(".subtab").forEach((x) => x.classList.toggle("is-active", x === b)); renderTeacher(b.dataset.sub); }));

  // ---------------- side panel ----------------
  function stateBadge(st) { return `<span class="state ${st}">${st}</span>`; }
  function pips(m) { let s = '<span class="pips" aria-label="transfer probes passed">'; for (let i = 0; i < m.probes_required; i++) s += `<i class="${i < m.probes_passed || m.state === "resolved" ? "on" : ""}"></i>`; return s + "</span>"; }
  function renderSide() {
    const p = S.profile; if (!p) return;
    const fixed = p.misconceptions.filter((m) => m.state === "resolved").length;
    $("#sideStats").innerHTML = `<div><b>${p.answered}</b><span>answered</span></div><div><b>${p.misconceptions.length}</b><span>found</span></div><div><b>${fixed}</b><span>fixed</span></div>`;
    $("#sideProgress").textContent = S.order.length ? `Q ${Math.min(S.idx + 1, S.order.length)} / ${S.order.length}` : "";
    const mini = $("#mapMini");
    if (!p.misconceptions.length) { mini.innerHTML = '<p class="muted small">Nothing found yet. Explain your reasoning and I\'ll look for the idea behind it.</p>'; }
    else mini.innerHTML = p.misconceptions.map((m) => { const tx = S.taxonomy[m.id] || { name: m.id, colour: "#141a33" }; return `<div class="mchip" style="--c:${tx.colour}"><div><b>${esc(tx.name)}</b><span class="muted tiny">seen ${m.detected}×${m.confidently_held ? " · held with certainty" : ""}${m.held_across_sessions ? " · held across sessions" : ""}</span><br>${pips(m)}</div><span class="st">${stateBadge(m.state)}</span></div>`; }).join("");
    $("#btnReport").hidden = !S.sessionId || S.finished;
  }
  $("#btnReport").addEventListener("click", () => finishSession());

  // ---------------- Ask the tutor: small voice chatbot ----------------
  (function askTutor() {
    const log = $("#askLog"), input = $("#askInput"), mic = $("#askMic"), form = $("#askForm"), speakT = $("#askSpeak");
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Rec) { mic.disabled = true; mic.title = "Voice needs Chrome or Edge"; }
    let speakOn = true; try { speakOn = localStorage.getItem("relearn-ask-speak") !== "0"; } catch (_) { /* */ }
    speakT.setAttribute("aria-pressed", String(speakOn)); speakT.textContent = speakOn ? "🔊" : "🔈";
    speakT.addEventListener("click", () => { speakOn = !speakOn; speakT.setAttribute("aria-pressed", String(speakOn)); speakT.textContent = speakOn ? "🔊" : "🔈"; try { localStorage.setItem("relearn-ask-speak", speakOn ? "1" : "0"); } catch (_) { /* */ } if (!speakOn && "speechSynthesis" in window) speechSynthesis.cancel(); });
    function say(text) {
      if (!speakOn || !("speechSynthesis" in window)) return;
      speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text.replace(/[→✓✗]/g, "")); u.lang = "en-IN"; u.rate = 1.02;
      const v = speechSynthesis.getVoices().find((x) => /en-IN/.test(x.lang)) || speechSynthesis.getVoices().find((x) => /^en/.test(x.lang)); if (v) u.voice = v;
      speechSynthesis.speak(u);
    }
    const history = [];  // earlier turns, so follow-ups like "why?" or "explain simpler" make sense to the AI tutor
    function add(role, text, meta) {
      const d = document.createElement("div"); d.className = `ask-m ${role}`; d.innerHTML = `<div>${esc(text)}</div>${meta ? `<div class="tiny muted">${esc(meta)}</div>` : ""}`;
      log.appendChild(d); while (log.children.length > 12) log.removeChild(log.firstChild); log.scrollTop = log.scrollHeight;
      return d;
    }
    let busy = false;
    async function ask(text) {
      text = text.trim(); if (!text || busy) return;
      busy = true; add("me", text); input.value = ""; input.disabled = true;
      const typing = add("bot thinking", "Thinking…");
      try {
        const r = await api("/api/ask", { text, item_id: S.current?.id || null, history: history.slice(-8) });
        typing.remove();
        add("bot", r.reply, r.generated ? "AI tutor" : r.sources?.length ? `from: ${r.sources.join(", ")}` : "");
        history.push({ role: "user", content: text }, { role: "assistant", content: r.reply });
        say(r.reply);
      } catch (err) { typing.remove(); add("bot", `Sorry — ${err.message}`); }
      finally { busy = false; input.disabled = false; input.focus(); }
    }
    form.addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
    mic.addEventListener("click", () => {
      if (mic.classList.contains("rec")) return;
      const rec = new Rec(); rec.lang = "en-IN"; rec.interimResults = true; let finalText = "";
      rec.onresult = (e) => { let interim = ""; finalText = ""; for (let i = 0; i < e.results.length; i++) { const t = e.results[i][0].transcript; if (e.results[i].isFinal) finalText += t; else interim += t; } input.value = finalText || interim; };
      rec.onstart = () => { mic.classList.add("rec"); input.placeholder = "Listening…"; };
      rec.onend = () => { mic.classList.remove("rec"); input.placeholder = "Ask a physics question…"; if (finalText.trim()) ask(finalText); };
      rec.onerror = () => { mic.classList.remove("rec"); };
      try { rec.start(); } catch (_) { /* */ }
    });
    if ("speechSynthesis" in window) speechSynthesis.getVoices();
  })();

  // ---------------- start ----------------
  function showStart() {
    rail(null); $("#learnerChip").hidden = true; toTop();
    stage.innerHTML = `
      <div class="hero fade-in">
        <h1 class="h-display">Re:Learn doesn't tell you that you're wrong. It tells you <em>why</em> — and checks that the fix stuck.</h1>
        <p class="lede">Answer a mechanics question and explain your thinking — type it, say it, photograph your handwriting, or draw the forces. The model names the misconception behind your reasoning, fixes exactly that in your own words, and tests you in a new situation.</p>
        <form class="form" id="startForm">
          <div class="field"><label for="name">Your name</label><input class="input" id="name" name="name" placeholder="e.g. Aiman" autocomplete="off" required maxlength="40"></div>
          <div class="field"><span style="display:block;font-weight:500;margin-bottom:.35rem">Session</span>
            <div class="seg" role="radiogroup" aria-label="Session type">
              ${Object.entries(MODE_LABEL).map(([k, v], i) => `<label><input type="radio" name="mode" value="${k}" ${i === 0 ? "checked" : ""}><span>${v}${k === "quick" ? " (9)" : k === "full" ? " (39)" : k === "working" ? " (5)" : k === "diagram" ? " (4)" : ""}</span></label>`).join("")}
            </div>
            <select class="input" id="topic" style="margin-top:.6rem;max-width:280px" hidden aria-label="Topic">
              <option value="kinematics">Kinematics: velocity vs acceleration</option><option value="newton1">Newton's first law</option>
              <option value="newton2">Newton's second law</option><option value="newton3">Newton's third law</option><option value="freefall">Free fall</option>
            </select>
          </div>
          <div class="btn-row" style="margin-top:.2rem"><button class="btn accent" type="submit">Start learning →</button></div>
        </form>
        <div class="howitworks" aria-label="How it works">
          <div><b>1 · Answer</b>Choose, calculate or draw. Explain why — typed, spoken or photographed.</div>
          <div><b>2 · Diagnose</b>The model names the idea behind your reasoning — or asks for more.</div>
          <div><b>3 · Fix</b>A fix that starts from your own words, with a worked example and animation.</div>
          <div><b>4 · Verify</b>Transfer questions in new contexts. Clean reasoning required.</div>
          <div><b>5 · Track</b>Active → improving → resolved. Re-checked later — and next session.</div>
        </div>
      </div>`;
    $$('#startForm input[name=mode]').forEach((r) => r.addEventListener("change", () => { $("#topic").hidden = r.value !== "topic" || !r.checked; }));
    $("#startForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = $("#name").value.trim(); if (!name) return;
      const mode = $('#startForm input[name=mode]:checked').value;
      try {
        const res = await api("/api/session/start", { learner: name, mode, topic: mode === "topic" ? $("#topic").value : null });
        S.learner = res.learner; S.sessionId = res.session_id; S.order = res.question_order; S.idx = 0; S.finished = false; S.welcome = res.welcome;
        res.questions.forEach((q) => { S.questions[q.id] = q; });
        S.profile = res.profile;
        $("#learnerName").textContent = S.learner; $("#learnerChip").hidden = false; toTop();
        renderSide();
        if (res.welcome) showWelcome(res.welcome); else showQuestion();
      } catch (err) { toast(`Could not start: ${err.message}`); }
    });
    $("#name").focus();
  }

  function showWelcome(w) {
    rail(null); toTop();
    const open = w.open_ideas.map((m) => `<span class="chip" style="--c:${S.taxonomy[m.id].colour}">${esc(m.name)} · ${m.state}</span>`).join(" ");
    const verify = w.to_verify.map((m) => `<span class="chip" style="--c:${S.taxonomy[m.id].colour}">${esc(m.name)}</span>`).join(" ");
    stage.innerHTML = `<div class="fade-in"><div class="welcome"><div class="kicker" style="font-size:.75rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--green)">Welcome back · session ${w.sessions_before + 1}</div>
      <h2 style="margin:.3rem 0">${esc(w.message)}</h2>
      <p class="small muted">Last session: ${w.last_session.questions_answered} question${w.last_session.questions_answered === 1 ? "" : "s"} answered, ${timeAgo(w.last_session.started)}.</p>
      ${verify ? `<p><b>Resolved last time, to verify now:</b> ${verify}</p>` : ""}
      ${open ? `<p><b>Still open:</b> ${open}</p>` : ""}
      ${!verify && !open ? "<p>Nothing carried over — a clean start.</p>" : ""}</div>
      <div class="btn-row"><button class="btn accent" id="go">${verify ? "Start with the recheck →" : "Continue →"}</button></div></div>`;
    $("#go").addEventListener("click", () => checkRecheckThen(() => showQuestion()));
  }
  function timeAgo(ts) { const m = Math.round((Date.now() / 1000 - ts) / 60); if (m < 60) return `${m} min ago`; const h = Math.round(m / 60); if (h < 48) return `${h} h ago`; return `${Math.round(h / 24)} days ago`; }

  // ---------------- input tools: voice + photo ----------------
  function inputTools(textarea) {
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const wrap = document.createElement("div"); wrap.className = "tools";
    wrap.innerHTML = `<label class="tool">📷 Photo of handwriting<input type="file" id="photoIn" accept="image/*" capture="environment"></label>
      <span class="muted tiny">or type / edit the transcript above</span>`;
    const status = () => $("#toolStatus");
    if (Rec) {
      let rec = null, listening = false;
      const btn = $("#micBtn");
      btn.addEventListener("click", () => {
        if (listening) { rec && rec.stop(); return; }
        rec = new Rec(); rec.lang = "en-IN"; rec.interimResults = true; rec.continuous = true;
        let base = textarea.value.trim(); let finalText = "";
        rec.onresult = (e) => { let interim = ""; finalText = ""; for (let i = 0; i < e.results.length; i++) { const t = e.results[i][0].transcript; if (e.results[i].isFinal) finalText += t + " "; else interim += t; } textarea.value = (base ? base + " " : "") + finalText + interim; textarea.dispatchEvent(new Event("input")); };
        rec.onstart = () => { listening = true; btn.classList.add("rec"); btn.textContent = "■ Stop"; btn.setAttribute("aria-pressed", "true"); status().textContent = "Listening… speak your reasoning, then tap Stop."; S.inputMethod = "voice"; };
        rec.onend = () => { listening = false; btn.classList.remove("rec"); btn.textContent = "🎙 Tap and speak"; btn.setAttribute("aria-pressed", "false"); status().textContent = "Transcribed. Edit if anything is wrong, then submit."; };
        rec.onerror = (e) => { status().textContent = e.error === "not-allowed" ? "Microphone blocked — allow it in the browser." : `Voice error: ${e.error}`; };
        try { rec.start(); } catch (_) { /* ignore */ }
      });
    }
    $("#photoIn", wrap).addEventListener("change", async (e) => {
      const file = e.target.files[0]; if (!file) return;
      status().textContent = "Uploading…";
      const fd = new FormData(); fd.append("file", file);
      try {
        const r = await fetch("/api/upload", { method: "POST", body: fd }); if (!r.ok) { let msg = r.statusText; try { msg = (await r.json()).detail || msg; } catch (_) { /* ignore */ } throw new Error(msg); }
        const up = await r.json(); S.imageId = up.image_id; S.inputMethod = "photo";
        let prev = $("#photoPrev"); if (!prev) { prev = document.createElement("div"); prev.id = "photoPrev"; prev.className = "photo-preview"; textarea.parentNode.insertBefore(prev, textarea.nextSibling); }
        prev.innerHTML = `<img src="${up.url}" alt="your handwritten working"><span id="ocrNote">Reading your handwriting…</span>`;
        let text = up.transcript;
        if (!text) {
          if (!window.Tesseract) { $("#ocrNote").textContent = "OCR library not loaded (offline?). Type the text from your photo."; status().textContent = ""; return; }
          const res = await window.Tesseract.recognize(file, "eng");
          text = (res.data.text || "").replace(/\s+\n/g, "\n").trim();
        }
        if (text) { textarea.value = (textarea.value.trim() ? textarea.value.trim() + "\n" : "") + text; textarea.dispatchEvent(new Event("input")); $("#ocrNote").textContent = up.transcript ? "Transcribed. Check it and edit if needed." : "Read by OCR — handwriting is hard, so correct anything wrong before you submit."; }
        else $("#ocrNote").textContent = "Couldn't read any text. Type it in instead.";
        status().textContent = "";
      } catch (err) { status().textContent = `Photo failed: ${err.message}`; }
    });
    return wrap;
  }

  function struggleStart() { S.shownAt = Date.now(); S.edits = 0; S.inputMethod = "typed"; S.imageId = null; }
  function struggleTrack(textarea, opts) {
    let lastLen = textarea.value.length;
    textarea.addEventListener("input", () => { const n = textarea.value.length; if (n < lastLen - 5) S.edits += 1; lastLen = n; });
    if (opts) opts.addEventListener("change", () => { S.edits += 1; });
  }
  const struggle = () => ({ time_ms: Date.now() - S.shownAt, edits: S.edits, input_method: S.inputMethod, image_id: S.imageId });

  // ---------------- question / probe forms ----------------
  function headHtml(item, kind, context, target) {
    const tagHtml = kind === "question"
      ? `<span class="tag">${esc(item.topic)}${item.kind === "working" ? " · show your working" : item.kind === "fbd" ? " · draw the forces" : ""}</span><span class="muted small">Question ${S.idx + 1} of ${S.order.length}</span>`
      : kind === "recheck" ? `<span class="tag recheck">${context && context.startsWith("cross") ? "New-session recheck" : "Delayed recheck"}</span>`
      : `<span class="tag probe">Transfer check · ${esc(context || "new context")}</span>`;
    const targetChip = target ? `<span class="chip" style="--c:${S.taxonomy[target].colour}">testing: ${esc(S.taxonomy[target].name)}</span>` : "";
    return `<div class="q-head">${tagHtml}${targetChip}</div><p class="q-prompt" id="prompt">${esc(item.prompt)}</p>`;
  }
  function explainHtml(label, placeholder, prefill, rows = 3) {
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    return `<div class="explain voicebox">
      <div class="voice-head"><label for="expl"><b>${label}</b> <span class="muted">${placeholder}</span></label></div>
      <div class="voice-row">
        <button type="button" class="mic-big" id="micBtn" aria-pressed="false" ${Rec ? "" : 'disabled title="Voice input needs Chrome or Edge"'}>🎙 Tap and speak</button>
        <span class="voice-status muted small" id="toolStatus">${Rec ? "Say it in your own words — I'll transcribe it here." : "Voice needs Chrome or Edge — type instead."}</span>
      </div>
      <textarea class="input transcript" id="expl" rows="${rows}" maxlength="900" placeholder="Your spoken explanation appears here… (you can also type or edit)">${esc(prefill || "")}</textarea>
      <div class="nlp-live" id="nlpLive" aria-live="polite"></div>
      <div id="tools"></div></div>`;
  }
  let nlpTimer = null;
  function liveNlp(textarea) {
    const box = $("#nlpLive"); if (!box) return;
    const t = textarea.value.trim();
    clearTimeout(nlpTimer);
    if (!t) { box.innerHTML = ""; return; }
    nlpTimer = setTimeout(async () => {
      try {
        const r = await api("/api/nlp/analyse", { text: t, item_id: S.current?.id || null });
        const chips = r.concepts.map((c) => `<span>${esc(c.replace("_", " "))}</span>`).join("");
        box.innerHTML = `<span class="nlp-label">${r.ready ? "✓ I heard" : "I heard"}:</span> ${chips || '<span class="muted">no physics words yet</span>'}
          ${r.has_reason ? '<span class="ok">reason ✓</span>' : ""}${r.hedged ? '<span class="soft">unsure tone</span>' : ""}${r.certain ? '<span class="soft">confident tone</span>' : ""}
          <em class="nudge">${esc(r.nudge).replace(/\*([^*]+)\*/g, "<b>$1</b>")}</em>`;
      } catch (_) { /* ignore */ }
    }, 350);
  }
  function confHtml(prefill) {
    return `<div class="conf-row"><span style="font-weight:500">How sure are you?</span><div class="seg" role="radiogroup" aria-label="Confidence">
      ${["guessing", "fairly_sure", "certain"].map((c) => `<label><input type="radio" name="conf" value="${c}" ${(prefill?.confidence || "fairly_sure") === c ? "checked" : ""}><span>${CONF_LABEL[c]}</span></label>`).join("")}</div>
      <span class="wordcount" id="wc">0 words</span></div>`;
  }
  function wireCommon(btnLabel, onSubmit, canSubmit, intro) {
    const expl = $("#expl"), wc = $("#wc"), btn = $("#submitBtn");
    $("#tools").appendChild(inputTools(expl));
    const update = () => { const words = expl.value.trim().split(/\s+/).filter(Boolean).length; wc.textContent = `${words} word${words === 1 ? "" : "s"}`; btn.disabled = !canSubmit(); liveNlp(expl); };
    expl.addEventListener("input", update); update();
    expl.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !btn.disabled) $("#answerForm").requestSubmit(); });
    $("#answerForm").addEventListener("submit", (e) => { e.preventDefault(); btn.disabled = true; btn.textContent = "Thinking…"; onSubmit().catch((err) => { toast(err.message); btn.disabled = false; btn.textContent = "Try again"; }); });
    return update;
  }

  function answerForm(item, { kind = "question", context = null, target = null, prefill = null, intro = null } = {}) {
    struggleStart();
    const introHtml = intro ? `<div class="verdict ${intro.cls}"><div class="kicker">${esc(intro.kicker)}</div><div class="title">${esc(intro.title)}</div>${intro.body ? `<p style="margin:.3rem 0 0">${esc(intro.body)}</p>` : ""}</div>` : "";
    const btnText = kind === "question" ? "Diagnose my thinking" : "Check my thinking";

    if (item.kind === "working") {
      stage.innerHTML = `<div class="fade-in">${introHtml}${headHtml(item, kind)}
        <form id="answerForm">
          <div class="numrow"><label for="num"><b>Your answer</b></label><input class="input" id="num" type="number" step="any" inputmode="decimal" placeholder="number"><span class="unit">${esc(item.unit)}</span></div>
          ${explainHtml("Explain your working out loud.", item.hint, prefill?.explanation, 5)}${confHtml(prefill)}
          <div class="btn-row"><button class="btn accent" type="submit" id="submitBtn" disabled>${btnText} →</button><span class="muted small"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> to submit</span></div>
        </form></div>`;
      if (prefill?.numeric_value != null) $("#num").value = prefill.numeric_value;
      const update = wireCommon(btnText, async () => {
        const payload = { numeric_value: Number($("#num").value), explanation: $("#expl").value.trim(), confidence: $('input[name=conf]:checked').value };
        await submitDiagnose(payload);
      }, () => $("#num").value !== "", intro);
      $("#num").addEventListener("input", update); struggleTrack($("#expl"), $("#num"));
      (prefill ? $("#expl") : $("#num")).focus({ preventScroll: true });
    } else if (item.kind === "fbd") {
      stage.innerHTML = `<div class="fade-in">${introHtml}${headHtml(item, kind)}
        <form id="answerForm"><div id="fbdRoot"></div>
          ${explainHtml("Explain your diagram out loud.", "Optional, but it helps me tell similar ideas apart.", prefill?.explanation, 2)}${confHtml(prefill)}
          <div class="btn-row"><button class="btn accent" type="submit" id="submitBtn" disabled>${btnText} →</button></div>
        </form></div>`;
      let diagram = [];
      S.fbd = FBD.mount($("#fbdRoot"), item, (d) => { diagram = d; S.edits += 1; update(); }, prefill?.diagram);
      const update = wireCommon(btnText, async () => {
        const payload = { diagram: S.fbd.get(), explanation: $("#expl").value.trim(), confidence: $('input[name=conf]:checked').value };
        await submitDiagnose(payload);
      }, () => true, intro);
      $("#submitBtn").disabled = false;
      struggleTrack($("#expl"), null);
    } else {
      stage.innerHTML = `<div class="fade-in">${introHtml}${headHtml(item, kind, context, target)}
        <form id="answerForm"><div class="opts" role="radiogroup" aria-labelledby="prompt" id="opts"></div>
          ${explainHtml("Explain your answer in your own words.", "Speak it — the words matter more than the option.", prefill?.explanation)}${confHtml(prefill)}
          <div class="btn-row"><button class="btn accent" type="submit" id="submitBtn" disabled>${btnText} →</button><span class="muted small"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> to submit</span></div>
        </form></div>`;
      const opts = $("#opts"), tpl = $("#tpl-option");
      item.options.forEach((o) => { const n = tpl.content.firstElementChild.cloneNode(true); const inp = n.querySelector("input"); inp.value = o.key; inp.id = `opt-${o.key}`; if (prefill?.choice === o.key) inp.checked = true; n.querySelector(".opt-key").textContent = o.key; n.querySelector(".opt-text").textContent = o.text; opts.appendChild(n); });
      const update = wireCommon(btnText, async () => {
        const payload = { choice: $('input[name=opt]:checked').value, explanation: $("#expl").value.trim(), confidence: $('input[name=conf]:checked').value };
        if (kind === "question") await submitDiagnose(payload); else await submitReassess(payload, kind);
      }, () => !!$('input[name=opt]:checked'), intro);
      opts.addEventListener("change", update); struggleTrack($("#expl"), opts);
      (prefill ? $("#expl") : $("#opt-A")).focus({ preventScroll: true });
    }
    toTop();
  }

  function showQuestion(prefill = null) {
    if (S.idx >= S.order.length) return finishSession();
    S.phase = "question"; S.target = null; S.probe = null; rail("answer");
    S.current = S.questions[S.order[S.idx]]; renderSide();
    answerForm(S.current, { kind: "question", prefill });
  }
  async function submitDiagnose(payload) {
    S.lastInput = payload;
    const res = await api("/api/diagnose", { learner: S.learner, session_id: S.sessionId, question_id: S.current.id, ...payload, ...struggle() });
    S.lastAttempt = res; S.profile = res.profile; renderSide(); showVerdict(res);
  }

  // ---------------- verdict + intervention ----------------
  function probBars(probs, top) {
    const entries = Object.entries(probs).slice(0, 4);
    return `<div class="probs" aria-label="Model probabilities">${entries.map(([k, v]) => `<div><span>${esc(S.taxonomy[k]?.name || (k === "NONE" ? "No misconception" : k))}</span><span class="bar"><i class="${k === top ? "top" : ""}" style="width:${pct(v)}"></i></span><span class="mono">${pct(v)}</span></div>`).join("")}</div>`;
  }
  function feedbackBox(attemptId, currentLabel) {
    const opts = [["NONE", "No misconception — my reasoning was fine"], ...Object.values(S.taxonomy).map((m) => [m.id, m.name])].filter(([k]) => k !== currentLabel).map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join("");
    return `<div class="feedback"><details><summary>That's not what I meant</summary><div class="row"><label for="fb-${attemptId}" class="small">What were you actually thinking?</label><select id="fb-${attemptId}">${opts}</select><button class="btn ghost small" type="button" data-fb="${attemptId}">Send</button></div><p class="muted tiny" style="margin:.4rem 0 0">Stored as a candidate training example — this is how the model gets better.</p></details></div>`;
  }
  function tutorBlock(t) {
    if (!t || !t.text) return "";
    const paras = t.text.split(/\n\n+/).map((p) => `<p>${esc(p).replace(/\*([^*]+)\*/g, "<em>$1</em>")}</p>`).join("");
    const sig = t.signals || {};
    const tags = (sig.concepts || []).map((c) => `<span>${esc(c.replace("_", " "))}</span>`).join("");
    return `<div class="tutor"><div class="tutor-avatar" aria-hidden="true"></div><div class="tutor-bubble"><div class="tutor-kicker">Tutor ${t.source === "llm" ? '<span class="badge soft">generated</span>' : '<span class="badge soft">NLP</span>'}</div>${paras}${tags ? `<div class="tutor-tags" title="concepts found in your explanation">${tags}</div>` : ""}</div></div>`;
  }
  function verdictBlock(res) {
    const c = STATUS_COPY[res.status];
    const self = res.self_confidence ? ` · you said: ${CONF_LABEL[res.self_confidence]}` : "";
    const src = { embedding: "matched by description (unseen-misconception fallback)", "working-rules": "from your working", "diagram-rules": "from your diagram", "diagram+text": "from your diagram + your sentence" }[res.source];
    return `<div class="verdict ${res.status}"><div class="kicker">${c.kicker}${res.correct ? " · answer ✓" : res.status !== "unknown" ? " · answer ✗" : ""}</div><div class="title">${c.title}</div>
      <div class="muted small">${res.status === "unknown" ? "no diagnosis yet" : `model confidence ${pct(res.confidence)}`} · ${res.latency_ms} ms${self}${src ? " · " + src : ""}${res.hesitant ? " · you hesitated on this one" : ""}</div></div>`;
  }
  function forYou(p) {
    if (!p || !p.quote) return "";
    let q = esc(p.quote);
    if (p.trigger) q = q.replace(esc(p.trigger), `<mark>${esc(p.trigger)}</mark>`);
    return `<div class="foryou"><div class="kicker">Written for you ${p.source === "llm" ? '<span class="badge soft">generated</span>' : '<span class="badge soft">from your words</span>'}</div>
      <blockquote>You said: “${q}”</blockquote><p style="margin:0">${esc(p.bridge).replace(/\n\n/g, "</p><p>")}</p></div>`;
  }
  function simBlock(checked) {
    return `<div class="simwrap" id="simwrap"><canvas id="sim" width="680" height="330" role="img" aria-label="Physics animation"></canvas>
      <div class="sim-bar"><button class="btn small" type="button" id="simPlay">${Simulations.prefersReduced ? "Play" : "Pause"}</button><button class="btn ghost small" type="button" id="simReplay">Replay</button><button class="btn ghost small" type="button" id="simStep">Step</button>
      <label class="small" style="display:flex;align-items:center;gap:.4rem;flex:1;min-width:140px"><span class="sr-only">Time</span><input type="range" id="simSeek" min="0" max="100" value="0" style="width:100%" aria-label="Scrub animation time"></label>
      <label class="small" style="display:flex;align-items:center;gap:.4rem"><input type="checkbox" id="simBelief" ${checked ? "checked" : ""}> Show what the belief predicts</label></div>
      <div class="sim-desc" id="simDesc"></div></div>`;
  }
  function workingBlock(res) {
    if (res.mode !== "working" || !res.worked) return "";
    return `${res.rule ? `<div class="rulebox"><b>In your working:</b> ${esc(res.rule.why)}</div>` : ""}<div class="worked" style="margin-bottom:1rem"><h3>Correct answer: ${esc(res.answer_shown)}</h3><ol>${res.worked.map((s) => `<li>${esc(s)}</li>`).join("")}</ol></div>`;
  }
  function fbdBlock(res) {
    if (res.mode !== "fbd" || !res.diagram_feedback) return "";
    const f = res.diagram_feedback;
    const lines = [...f.ok.map((x) => `<div class="ok">✓ ${esc(x)}</div>`), ...f.missing.map((x) => `<div class="miss">✗ missing: ${esc(x)}</div>`), ...f.extra.map((x) => `<div class="extra">✗ should not be there: ${esc(x)}</div>`), ...f.wrong_direction.map((x) => `<div class="miss">✗ ${esc(x)}</div>`), ...f.wrong_size.map((x) => `<div class="extra">✗ ${esc(x)}</div>`)];
    return `<div class="fbd-fb">${lines.join("")}</div>${res.ideal_diagram ? `<h3>The correct free-body diagram</h3><div class="fbd" style="grid-template-columns:1fr"><canvas id="fbdIdeal" role="img" aria-label="Correct free-body diagram"></canvas></div>` : ""}`;
  }
  function drawIdeal(res) { const c = $("#fbdIdeal"); if (c && res.ideal_diagram) FBD.render(c, S.current, res.ideal_diagram); }

  function showVerdict(res) {
    rail("diagnose"); toTop();
    if (res.status === "unknown") {
      const mismatch = !res.correct && (res.notes || []).some((n) => n.startsWith("answer is wrong but the reasoning"));
      const mismatchHtml = mismatch ? `<div class="callout"><b>Your explanation sounds like correct physics — but it doesn't match the option you picked.</b> Re-read the options: did you mean a different one? If you really meant that option, say why in your explanation.</div>` : "";
      const fbdHtml = res.mode === "fbd" ? `<div class="callout"><b>Your diagram isn't complete yet.</b> Fix the arrows listed below — I keep everything you've already drawn.</div>` : "";
      stage.innerHTML = `<div class="fade-in">${verdictBlock(res)}${mismatchHtml}${fbdHtml}${mismatch || res.mode === "fbd" ? "" : tutorBlock(res.tutor)}${fbdBlock(res)}${Object.keys(res.probabilities).length ? `<p class="muted small">Top candidates right now:</p>${probBars(res.probabilities, null)}` : ""}
        <div class="btn-row"><button class="btn accent" id="elab">${res.mode === "fbd" ? "Fix my diagram" : "Add to my explanation"}</button></div></div>`;
      $("#elab").addEventListener("click", () => showQuestion(S.lastInput));
      return;
    }
    if (res.status === "correct") {
      stage.innerHTML = `<div class="fade-in">${verdictBlock(res)}${tutorBlock(res.tutor)}${fbdBlock(res)}${workingBlock(res)}${res.mode === "choice" ? probBars(res.probabilities, "NONE") : ""}
        <div class="btn-row"><button class="btn accent" id="next">Next question →</button></div></div>`;
      drawIdeal(res);
      $("#next").addEventListener("click", () => advance());
      return;
    }
    const m = res.misconception, iv = res.intervention;
    const held = res.confidently_held ? `<span class="badge">held with certainty</span>` : "";
    const recur = res.state === "recurring" ? `<span class="badge">came back after being resolved</span>` : "";
    stage.innerHTML = `<div class="fade-in">${verdictBlock(res)}${tutorBlock(res.tutor)}${fbdBlock(res)}${workingBlock(res)}
      <div class="diag">
        <div class="belief" style="--c:${m.colour}"><h3>${esc(m.name)} ${held}${recur}</h3><p class="muted small" style="margin:0">${esc(m.short)}</p>
          <div class="vs"><div class="you"><b>What your reasoning suggests</b>${esc(m.believes)}</div><div class="phys"><b>What physics says</b>${esc(m.physics)}</div></div></div>
        <div class="confbox"><b>How sure is the model?</b>
          <div class="meter" role="meter" aria-valuenow="${Math.round(res.confidence * 100)}" aria-valuemin="0" aria-valuemax="100" aria-label="model confidence"><i style="width:${pct(res.confidence)}"></i></div>
          <div class="small"><span class="mono">${pct(res.confidence)}</span> that this is the idea behind your ${res.mode === "fbd" ? "diagram" : res.mode === "working" ? "working" : "words"}</div>
          ${Object.keys(res.probabilities).length > 1 ? probBars(res.probabilities, res.label) : ""}
          ${res.notes?.length ? `<p class="muted tiny" style="margin:.6rem 0 0">${esc(res.notes.join(" · "))}</p>` : ""}
          ${feedbackBox(res.attempt_id, res.label)}</div>
      </div>
      <div class="fix" id="fix"><div class="fix-head">${esc(iv.headline)}</div>${iv.explanation.map((p) => `<p>${esc(p)}</p>`).join("")}
        ${simBlock(false)}
        <div class="worked"><h3>Worked example: ${esc(iv.worked_example.title)}</h3><ol>${iv.worked_example.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol></div>
        <div class="check"><b>Check yourself:</b> ${esc(iv.check_yourself)}</div></div>
      <div class="btn-row"><button class="btn accent" id="toProbe">Test the fix in a new situation →</button><span class="muted small">A transfer question — same idea, different context.</span></div></div>`;
    rail("fix"); drawIdeal(res); mountSim(iv.simulation);
    $("#toProbe").addEventListener("click", () => { if (res.probe) showProbe(res.probe, res.probe.target); else advance(); });
    wireFeedback();
  }

  function mountSim(kind) {
    if (S.sim) { S.sim.destroy(); S.sim = null; }
    const canvas = $("#sim"); if (!canvas) return;
    const sim = Simulations.mount(canvas, kind); if (!sim) return;
    S.sim = sim; $("#simDesc").textContent = sim.describe;
    const play = $("#simPlay"), seek = $("#simSeek");
    play.addEventListener("click", () => { const p = sim.toggle(); play.textContent = p ? "Pause" : "Play"; });
    $("#simReplay").addEventListener("click", () => { sim.replay(); play.textContent = "Pause"; });
    $("#simStep").addEventListener("click", () => { sim.step(); play.textContent = "Play"; });
    seek.addEventListener("input", () => { sim.pause(); play.textContent = "Play"; sim.seek(seek.value / 100 * sim.duration); });
    sim.onTick((t) => { if (sim.playing) seek.value = Math.round(t / sim.duration * 100); });
    const belief = $("#simBelief"); belief.addEventListener("change", (e) => sim.setMode(e.target.checked ? "belief" : "physics")); if (belief.checked) sim.setMode("belief");
  }
  function wireFeedback() {
    $$("[data-fb]").forEach((b) => b.addEventListener("click", async () => { const id = b.dataset.fb, sel = $(`#fb-${id}`); try { const r = await api("/api/feedback", { learner: S.learner, attempt_id: Number(id), suggested_label: sel.value, note: "" }); toast(r.message); b.disabled = true; b.textContent = "Sent"; } catch (err) { toast(err.message); } }));
  }

  // ---------------- probes ----------------
  function showProbe(probe, target, intro = null, kind = "probe", context = null) {
    S.phase = kind; S.probe = probe; S.target = target; rail("verify");
    answerForm(probe, { kind, context: context || probe.context, target, intro });
  }
  async function submitReassess(payload, kind) {
    S.lastInput = payload;
    const res = await api("/api/reassess", { learner: S.learner, session_id: S.sessionId, misconception: S.target, probe_id: S.probe.id, phase: kind === "recheck" ? "recheck" : "probe", ...payload, ...struggle() });
    S.lastAttempt = res; S.profile = res.profile; renderSide(); showProbeResult(res, kind);
  }
  function showProbeResult(res, kind) {
    toTop();
    const tx = S.taxonomy[res.target];
    if (res.resolved === null) {
      stage.innerHTML = `<div class="fade-in"><div class="verdict unknown"><div class="kicker">Almost</div><div class="title">${esc(res.ask)}</div></div>${tutorBlock(res.tutor)}<div class="btn-row"><button class="btn accent" id="elab">Add my reasoning</button></div></div>`;
      $("#elab").addEventListener("click", () => showProbe(S.probe, S.target, null, kind)); return;
    }
    const cls = res.resolved ? "resolved" : "notyet";
    const kicker = res.resolved ? (res.held_across_sessions ? "Held across sessions" : (res.resolved_now || kind === "recheck" ? "Resolved" : "Clear in this context")) : (kind === "recheck" ? "It came back" : "Not yet");
    const detail = res.correct ? (res.target_present ? `Answer ✓ — but the reasoning still reads as “${esc(tx.short.toLowerCase())}”.` : `Answer ✓ and no trace of “${esc(tx.short.toLowerCase())}” in your words.`) : `Answer ✗${res.label && res.label !== "UNKNOWN" && res.label !== "NONE" ? ` — reasoning reads as ${esc(S.taxonomy[res.label]?.name || res.label)}` : ""}.`;
    const newM = res.new_misconception ? `<div class="callout"><b>Something else surfaced:</b> ${esc(res.new_misconception.name)} (${pct(res.new_misconception.confidence)}). Added to your map — we'll come back to it.</div>` : "";
    let html = `<div class="fade-in"><div class="verdict ${cls}"><div class="kicker">${kicker} · <span class="chip" style="--c:${tx.colour}">${esc(tx.name)}</span></div><div class="title">${esc(res.message)}</div><div class="small">${detail} <span class="muted">· model ${pct(res.confidence)}</span></div>
      ${res.state ? `<div style="margin-top:.4rem">${stateBadge(res.state)} ${res.probes_required ? pips({ probes_required: res.probes_required, probes_passed: res.probes_passed, state: res.state }) : ""}</div>` : ""}</div>${tutorBlock(res.tutor)}${newM}`;
    if (res.resolved) {
      html += res.probe ? `<div class="btn-row"><button class="btn accent" id="nextProbe">Next context: ${esc(res.probe.context)} →</button></div></div>` : `<div class="btn-row"><button class="btn accent" id="cont">Continue →</button></div></div>`;
      stage.innerHTML = html; rail("track");
      if (res.probe) $("#nextProbe").addEventListener("click", () => showProbe(res.probe, res.target)); else $("#cont").addEventListener("click", () => advance());
      return;
    }
    const iv = res.intervention;
    html += `<details class="collapsible" open><summary>Look at the idea again</summary><div class="fix" style="margin-top:.8rem"><div class="fix-head">${esc(iv.headline)}</div>${iv.explanation.map((p) => `<p>${esc(p)}</p>`).join("")}${simBlock(true)}<div class="check"><b>Check yourself:</b> ${esc(iv.check_yourself)}</div></div></details>`;
    html += res.probe ? `<div class="btn-row"><button class="btn accent" id="nextProbe">Try another context: ${esc(res.probe.context)} →</button></div></div>` : `<div class="btn-row"><button class="btn accent" id="cont">Leave it open and continue →</button></div></div>`;
    stage.innerHTML = html; mountSim(iv.simulation);
    if (res.probe) $("#nextProbe").addEventListener("click", () => showProbe(res.probe, res.target)); else $("#cont").addEventListener("click", () => advance());
    rail("fix");
  }

  // ---------------- advancing, delayed + cross-session recheck ----------------
  async function checkRecheckThen(next) {
    try {
      const rc = await api(`/api/recheck/${encodeURIComponent(S.learner)}?session_id=${S.sessionId}`);
      if (rc.probe) {
        const tx = S.taxonomy[rc.misconception.id];
        const intro = rc.cross_session
          ? { cls: "unknown", kicker: "New session · quick recheck", title: `Last session you resolved “${tx.name}”. Does it still hold today?`, body: "Same idea, new context. Passing this after a break is the strongest evidence of learning we can collect." }
          : { cls: "unknown", kicker: "Quick recheck", title: `Earlier you resolved “${tx.name}”. Still true a few questions later?`, body: "Same idea, new context. This is how Re:Learn tells learning apart from a lucky streak." };
        showProbe(rc.probe, rc.misconception.id, intro, "recheck", rc.cross_session ? "cross-session" : null);
        return;
      }
    } catch (_) { /* ignore */ }
    next();
  }
  async function advance() {
    if (S.sim) { S.sim.destroy(); S.sim = null; }
    checkRecheckThen(() => { S.idx += 1; if (S.idx >= S.order.length) return finishSession(); showQuestion(); });
  }

  // ---------------- report ----------------
  async function finishSession() {
    if (S.sim) { S.sim.destroy(); S.sim = null; }
    if (!S.finished && S.sessionId) { try { await api("/api/session/finish", { session_id: S.sessionId }); } catch (_) { /* ignore */ } }
    S.finished = true; renderSide(); rail("track"); toTop();
    const r = await api(`/api/report/${encodeURIComponent(S.learner)}`); const s = r.summary;
    const tiles = [["good", s.right_first_time, "right first time"], ["warn", s.found, "misconceptions found"], ["good", s.fixed, "fixed & verified"], ["", s.improving, "improving"], ["warn", s.still_open, "still open"], ["bad", s.recurring, "recurring"], ["", s.flawed_reasoning, "right answer, wrong idea"], ["good", s.held_across_sessions, "held across sessions"]];
    const rows = r.misconceptions.map((m) => { const probes = r.timeline.filter((t) => (t.phase === "probe" || t.phase === "recheck") && t.target === m.id); const ribbon = probes.map((t) => `<i class="${t.resolved ? "probe-pass" : "probe-fail"}" title="${t.phase} ${t.resolved ? "passed" : "failed"}"></i>`).join("");
      return `<div class="mrow" style="--c:${m.colour}"><div><b>${esc(m.name)}</b> ${stateBadge(m.state)} ${m.confidently_held ? '<span class="badge">held with certainty</span>' : ""} ${m.held_across_sessions ? '<span class="badge soft">verified in a later session</span>' : ""}
        <div class="meta">seen ${m.detected}× · probes passed ${Math.min(m.probes_passed, m.probes_required)}/${m.probes_required} · ${m.recheck_pending ? "recheck pending" : m.state === "resolved" ? "recheck passed" : ""}</div>
        <div class="small" style="margin-top:.3rem">${esc(m.physics)}</div><div class="ribbon">${ribbon}</div></div></div>`; }).join("") || '<div class="empty">No misconceptions were found — every answer came with sound reasoning.</div>';
    const timeline = r.timeline.map((t) => `<i class="${t.phase === "question" ? t.status : (t.resolved ? "probe-pass" : "probe-fail")}" title="${t.phase} ${t.item_id}: ${t.status}${t.mode && t.mode !== "choice" ? " (" + t.mode + ")" : ""}${t.input_method && t.input_method !== "typed" ? " via " + t.input_method : ""}"></i>`).join("");
    stage.innerHTML = `<div class="fade-in"><h1 class="h-display">Session report for ${esc(r.learner)}</h1>
      <p class="lede">${s.answered} question${s.answered === 1 ? "" : "s"} answered · ${pct(s.explained_share)} came with an explanation · session ${s.sessions}${s.avg_time_s ? ` · ${Math.round(s.avg_time_s)} s per question on average` : ""}${s.hesitant ? ` · hesitated on ${s.hesitant}` : ""}</p>
      <div class="tiles">${tiles.map(([c, v, l]) => `<div class="tile ${c}"><b>${v}</b><span>${l}</span></div>`).join("")}</div>
      <h2>What happened to each idea</h2>${rows}
      <h2 style="margin-top:1.4rem">Timeline</h2><div class="ribbon">${timeline}</div>
      <div class="legend"><span><i style="background:var(--green)"></i>correct</span><span><i style="background:var(--amber)"></i>misconception</span><span><i style="background:var(--purple)"></i>right answer, wrong idea</span><span><i style="background:var(--blue)"></i>asked for more</span><span><i style="background:var(--green);border-radius:50%"></i>probe passed</span><span><i style="background:var(--red);border-radius:50%"></i>probe failed</span></div>
      <div class="btn-row"><button class="btn accent" id="again">Start another session</button><a class="btn ghost" href="/api/report/${encodeURIComponent(S.learner)}/pdf" download>Download PDF report</a><button class="btn ghost" id="dl">JSON</button><button class="btn ghost" id="teacherBtn">Teacher view</button></div></div>`;
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
    el.innerHTML = p.misconceptions.map((m) => { const tx = S.taxonomy[m.id]; const hist = p.timeline.filter((t) => t.label === m.id || t.target === m.id).map((t) => `<i class="${t.phase === "question" ? t.status : (t.resolved ? "probe-pass" : "probe-fail")}" title="${t.phase} ${t.item_id}"></i>`).join("");
      return `<div class="mrow" style="--c:${tx.colour}"><div><b>${esc(tx.name)}</b> ${stateBadge(m.state)} ${m.confidently_held ? '<span class="badge">held with certainty</span>' : ""} ${m.held_across_sessions ? '<span class="badge soft">verified in a later session</span>' : ""}
        <div class="meta">${esc(tx.short)} · detected ${m.detected}× · probes ${m.probes_passed}/${m.probes_required} passed, ${m.probes_failed} failed</div>
        <div class="small" style="margin-top:.4rem"><b style="color:var(--red)">Belief:</b> ${esc(tx.believes)}</div><div class="small"><b style="color:var(--green)">Physics:</b> ${esc(tx.physics)}</div><div class="ribbon">${hist}</div></div></div>`; }).join("");
  }

  // ---------------- teacher ----------------
  function setTeacherToken(tok) {
    S.teacherToken = tok;
    try { if (tok) sessionStorage.setItem("relearn-teacher", tok); else sessionStorage.removeItem("relearn-teacher"); } catch (_) { /* ignore */ }
    if (!tok) stopLive();
  }
  function stopLive() { clearInterval(S.liveTimer); S.liveTimer = null; $("#livePill").hidden = true; }
  function startLive(sub) {
    stopLive();
    if (sub !== "overview" && sub !== "heatmap") return;  // labelling / discover: don't redraw under the teacher's cursor
    $("#livePill").hidden = false;
    S.liveTimer = setInterval(() => { if (!$("#tab-teacher").hidden && !document.hidden) renderTeacher(sub, true); }, 5000);
  }
  function renderTeacherLogin(el, msg = "") {
    $("#teacherNav").hidden = true; stopLive();
    el.innerHTML = `<form class="pin-card" id="pinForm"><h2>Teacher access</h2>
      <p class="muted small">Class data (names, explanations, labels) is for the teacher only. Enter the teacher PIN.</p>
      <div class="pin-row"><input class="input" id="pin" type="password" inputmode="numeric" autocomplete="off" placeholder="PIN" aria-label="Teacher PIN" maxlength="40"><button class="btn accent" type="submit">Unlock</button></div>
      <p class="pin-err small" id="pinErr" role="alert">${esc(msg)}</p></form>`;
    $("#pinForm").addEventListener("submit", async (e) => {
      e.preventDefault(); const pin = $("#pin").value.trim(); if (!pin) return;
      try { const r = await api("/api/teacher/login", { pin }); setTeacherToken(r.token); renderTeacher($(".subtab.is-active")?.dataset.sub || "overview"); }
      catch (err) { $("#pinErr").textContent = err.message === "wrong PIN" ? "Wrong PIN, try again." : err.message; $("#pin").select(); }
    });
    $("#pin").focus();
  }
  $("#teacherLock").addEventListener("click", async () => {
    try { await api("/api/teacher/logout", {}); } catch (_) { /* already locked */ }
    setTeacherToken(null); renderTeacherLogin($("#teacherView"));
  });
  async function renderTeacher(sub, quiet = false) {
    const el = $("#teacherView");
    if (!S.teacherToken) return renderTeacherLogin(el);
    $("#teacherNav").hidden = false;
    if (!quiet) { el.innerHTML = '<p class="muted">Loading…</p>'; startLive(sub); }
    try {
      if (sub === "overview") return await renderTeacherOverview(el);
      if (sub === "heatmap") return await renderHeatmap(el);
      if (sub === "label") return await renderLabelling(el);
      if (sub === "discover") return await renderDiscover(el);
    } catch (err) {
      if (!S.teacherToken) return renderTeacherLogin(el, "Session expired. Enter the PIN again.");
      if (!quiet) el.innerHTML = `<div class="empty">Couldn't load: ${esc(err.message)}</div>`;
    }
  }
  function feedHtml(a) {
    if (!a.rows.length) return '<div class="empty">Waiting for the first answer…</div>';
    const ago = (ts) => { const s = Math.max(0, Math.round(a.now - ts)); return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`; };
    const what = (r) => {
      const chip = r.name ? `<span class="chip" style="--c:${r.colour}">${esc(r.name)}</span>` : "";
      if (r.phase === "question") return { correct: "answered correctly", misconception: `misconception ${chip}`, flawed_reasoning: `right answer, wrong idea ${chip}`, unknown: "was asked to explain more" }[r.status] || esc(r.status);
      return `${r.phase === "recheck" ? "recheck" : "transfer check"} ${r.resolved === 1 ? "passed ✓" : r.resolved === 0 ? "failed ✗" : "needs reasoning"} ${chip}`;
    };
    const cls = (r) => (r.phase === "question" ? r.status : r.resolved === 1 ? "pass" : "fail");
    return `<ul class="feed">${a.rows.map((r) => `<li class="${cls(r)}"><b>${esc(r.learner)}</b> ${what(r)} <span class="muted tiny">· ${esc(r.item_id)} · ${ago(r.ts)}</span></li>`).join("")}</ul>`;
  }
  async function renderTeacherOverview(el) {
    const [c, act] = await Promise.all([api("/api/class"), api("/api/activity?limit=12")]);
    if (!c.learners) { el.innerHTML = '<div class="empty">No learners yet. Run a session or two (try different names) and come back.</div>'; return; }
    const ids = Object.keys(c.taxonomy); const max = Math.max(1, ...ids.map((m) => (c.misconceptions[m]?.total || 0)));
    const bars = ids.map((m) => { const d = c.misconceptions[m] || { active: 0, improving: 0, resolved: 0, recurring: 0, total: 0, confidently_held: 0 }; const seg = (k) => d[k] ? `<i class="${k}" style="width:${d[k] / max * 100}%" title="${k}: ${d[k]}"></i>` : "";
      return `<div class="barrow"><div><b class="tx" style="--c:${c.taxonomy[m].colour}">${esc(c.taxonomy[m].name)}</b><div class="muted tiny">${d.confidently_held ? `${d.confidently_held} held with certainty` : ""}</div></div><div class="track">${seg("recurring")}${seg("active")}${seg("improving")}${seg("resolved")}</div><div class="mono small">${d.total} / ${c.learners}</div></div>`; }).join("");
    const st = c.question_status_counts;
    const expo = c.exposure.map((e) => `<tr><td class="mono">${esc(e.item_id)}</td><td>${esc(c.taxonomy[e.label]?.name || e.label)}</td><td>${e.n}</td></tr>`).join("");
    const certain = c.confidently_held.map((x) => `<tr><td>${esc(x.learner)}</td><td>${esc(c.taxonomy[x.misconception]?.name)}</td><td>${stateBadge(x.state)}</td></tr>`).join("");
    el.innerHTML = `<div class="tiles"><div class="tile"><b>${c.learners}</b><span>learners</span></div><div class="tile"><b>${c.attempts}</b><span>attempts</span></div><div class="tile good"><b>${st.correct || 0}</b><span>correct</span></div><div class="tile warn"><b>${st.misconception || 0}</b><span>misconception</span></div><div class="tile"><b>${st.flawed_reasoning || 0}</b><span>right answer, wrong idea</span></div><div class="tile"><b>${st.unknown || 0}</b><span>asked for more</span></div><div class="tile"><b>${c.labelled}</b><span>real rows labelled</span></div></div>
      <h2>Live activity</h2><p class="muted small">Refreshes every 5 seconds while this tab is open. Have students answer on their phones and watch it fill in.</p>${feedHtml(act)}
      <h2>Misconceptions across the class</h2><p class="muted small">Learners holding each idea, by state.</p><div class="bars">${bars}</div>
      <div class="legend"><span><i style="background:var(--red)"></i>recurring</span><span><i style="background:var(--amber)"></i>active</span><span><i style="background:var(--blue)"></i>improving</span><span><i style="background:var(--green)"></i>resolved</span></div>
      <div class="diag" style="margin-top:1.4rem"><div><h2>Which questions expose which ideas</h2><table class="t"><thead><tr><th>Item</th><th>Misconception</th><th>Times</th></tr></thead><tbody>${expo || '<tr><td colspan="3" class="muted">none yet</td></tr>'}</tbody></table></div>
      <div><h2>Confidently held wrong ideas</h2><p class="muted small">Learner said “certain” when the misconception was detected — these need the most attention.</p><table class="t"><thead><tr><th>Learner</th><th>Misconception</th><th>State</th></tr></thead><tbody>${certain || '<tr><td colspan="3" class="muted">none</td></tr>'}</tbody></table></div></div>
      <p class="muted small">Learners: ${c.learner_names.map(esc).join(", ")}</p>`;
  }
  async function renderHeatmap(el) {
    const c = await api("/api/class"); const ids = Object.keys(c.taxonomy); const learners = Object.keys(c.heatmap);
    if (!learners.length) { el.innerHTML = '<div class="empty">No data yet.</div>'; return; }
    const short = (m) => c.taxonomy[m].name.split(":")[0].split(" ").slice(0, 2).join(" ");
    el.innerHTML = `<h2>Misconception × learner</h2><p class="muted small">Each cell is the current state; the number is how many times it was detected. Blank = never seen in that learner's reasoning.</p>
      <div class="heat" style="grid-template-columns:120px repeat(${ids.length}, minmax(80px,1fr))"><div class="cell hd"></div>${ids.map((m) => `<div class="cell hd" title="${esc(c.taxonomy[m].name)}">${esc(short(m))}</div>`).join("")}
      ${learners.map((l) => `<div class="cell hd rh">${esc(l)}</div>` + ids.map((m) => { const x = c.heatmap[l][m]; return x ? `<div class="cell ${x.state}" title="${x.state}, detected ${x.detected}×${x.confidently_held ? ", held with certainty" : ""}">${x.detected}${x.confidently_held ? "!" : ""}</div>` : '<div class="cell"></div>'; }).join("")).join("")}</div>
      <div class="legend" style="margin-top:.8rem"><span><i style="background:var(--amber-bg)"></i>active</span><span><i style="background:var(--blue-bg)"></i>improving</span><span><i style="background:var(--green-bg)"></i>resolved</span><span><i style="background:var(--red-bg)"></i>recurring</span><span>! = held with certainty</span></div>`;
  }
  async function renderLabelling(el) {
    const d = await api("/api/labels/pending");
    const name = (l) => l === "NONE" ? "NONE (sound reasoning)" : l === "OTHER" ? "OTHER (fits none of these / unclear)" : (S.taxonomy[l]?.name || l);
    // Blind labelling: the model's guess stays hidden until the label is saved, so it can't anchor the labeller.
    const sel = (id) => `<select class="input" data-lab="${id}"><option value="" selected disabled>Choose a label…</option>${d.labels.map((l) => `<option value="${l}">${esc(name(l))}</option>`).join("")}</select>`;
    const rowsById = Object.fromEntries(d.rows.map((r) => [String(r.id), r]));
    el.innerHTML = `<div class="callout"><b>Blind labelling.</b> Read each real explanation and pick the misconception <i>you</i> see. The model's guess is hidden until you save, so it can't influence you. Use <b>OTHER</b> when it fits none of the known ideas. Then <b>Export</b> writes <code>ml/data/real_responses.csv</code>; <code>python ml/evaluate.py</code> reports accuracy on these rows using a model never trained on them.</div>
      <div class="btn-row" style="margin:0 0 1rem"><button class="btn small" id="exportLabels">Export labelled rows</button><span class="muted small" id="labelCount">${d.rows.length} unlabelled</span><span class="muted small" id="agreeCount"></span></div>
      ${d.rows.length ? d.rows.map((r) => `<div class="lab"><div><div class="q">${esc(r.item_id)} · chose “${esc(r.option_text)}”${r.input_method && r.input_method !== "typed" ? " · via " + r.input_method : ""}</div><div class="e">“${esc(r.explanation)}”</div>${r.image_id ? `<img src="/uploads/${r.image_id}" alt="handwritten working">` : ""}<div class="muted small" data-reveal="${r.id}"></div></div>
        <div style="display:grid;gap:.4rem">${sel(r.id)}<button class="btn small" data-save="${r.id}">Save label</button></div></div>`).join("") : '<div class="empty">Nothing to label — every response so far has a label.</div>'}`;
    let agree = 0, done = 0;
    $$("[data-save]", el).forEach((b) => b.addEventListener("click", async () => {
      const id = b.dataset.save; const label = $(`[data-lab="${id}"]`, el).value;
      if (!label) { toast("Pick a label first."); return; }
      try {
        const res = await api("/api/labels", { attempt_id: Number(id), label });
        b.textContent = "Saved ✓"; b.disabled = true; $(`[data-lab="${id}"]`, el).disabled = true;
        $("#labelCount").textContent = `${res.labelled} labelled so far`;
        const r = rowsById[id], model = r.model_label === "UNKNOWN" ? "unknown (model abstained)" : name(r.model_label);
        const same = r.model_label === label; done++; if (same) agree++;
        $(`[data-reveal="${id}"]`, el).textContent = `Model said: ${model} (${pct(r.model_confidence)}) ${same ? "✓ agrees" : "✗ disagrees"}`;
        $("#agreeCount").textContent = `· model agreed on ${agree}/${done} this sitting`;
      } catch (err) { toast(err.message); }
    }));
    $("#exportLabels").addEventListener("click", async () => { try { const r = await api("/api/labels/export", {}); toast(`Exported ${r.rows} rows to ${r.path}`); } catch (err) { toast(err.message); } });
  }
  async function renderDiscover(el) {
    const d = await api("/api/discover");
    el.innerHTML = `<div class="callout"><b>Misconception discovery.</b> When the model abstains, the explanation goes here. Similar unplaceable explanations are clustered; a cluster that matches no known description is a candidate <em>new</em> misconception. Name it, add a description in <code>backend/data.py</code>, and the embedding fallback diagnoses it immediately — no retraining.</div>
      <p class="muted small">${esc(d.message)}</p>
      ${d.clusters.map((c) => `<div class="cluster"><h3>Pattern ${c.id + 1} · ${c.size} explanation${c.size === 1 ? "" : "s"}</h3><div class="terms">${c.top_terms.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
        <p class="small" style="margin:.5rem 0 0"><b>Nearest known idea:</b> ${esc(c.nearest_known.name)} (similarity ${c.nearest_known.similarity}) — ${esc(c.verdict)}</p>
        <ul>${c.examples.map((e) => `<li>“${esc(e.explanation)}” <span class="muted tiny">(${esc(e.learner)}, ${esc(e.item_id)})</span></li>`).join("")}</ul></div>`).join("")}`;
  }

  // ---------------- evaluation ----------------
  async function renderEval() {
    const el = $("#evalView"); const m = await api("/api/metrics");
    if (!m.available) { el.innerHTML = `<div class="empty">No evaluation yet. Run <code>python ml/evaluate.py</code> and refresh.</div>`; return; }
    const T = m.targets, ok = (b) => (b ? '<span class="ok">✓ met</span>' : '<span class="no">✗ missed</span>');
    const rows = [["Diagnosis macro-F1 (held-out questions)", m.heldout_questions_only.macro_f1, `≥ ${T.macro_f1_heldout_questions}`, m.targets_met.macro_f1_heldout_questions],
      [`Confusable-pair accuracy (n=${m.confusable_pair_n})`, m.confusable_pair_accuracy, `≥ ${T.confusable_pair_accuracy}`, m.targets_met.confusable_pair_accuracy],
      [`Flawed-reasoning recall (n=${m.flawed_reasoning_n})`, m.flawed_reasoning_recall, `≥ ${T.flawed_reasoning_recall}`, m.targets_met.flawed_reasoning_recall],
      ["Unseen-misconception top-1 (leave-one-out)", m.unseen_misconception_top1, `≥ ${T.unseen_misconception_top1}`, m.targets_met.unseen_misconception_top1],
      ["Calibration (ECE)", m.ece, `≤ ${T.ece}`, m.targets_met.ece], ["Latency per diagnosis", `${m.latency_ms_per_diagnosis.toFixed(1)} ms`, "< 1000 ms", true]];
    const labels = m.confusion_matrix.labels, cm = m.confusion_matrix.matrix, mx = Math.max(...cm.flat());
    const short = (l) => (l === "NONE" ? "none" : l.replace("_", " ").toLowerCase().replace("va confusion", "v–a").replace("force velocity", "force→v").replace("heavier faster", "heavier").replace("third law", "3rd law"));
    const grid = `<div class="cm" style="grid-template-columns: 90px repeat(${labels.length}, minmax(52px, 1fr))"><div class="cell hd">true ↓ / pred →</div>${labels.map((l) => `<div class="cell hd">${short(l)}</div>`).join("")}${cm.map((row, i) => `<div class="cell hd rh">${short(labels[i])}</div>` + row.map((v) => `<div class="cell" style="background:${v ? `rgba(124,58,237,${0.12 + 0.75 * v / mx})` : "var(--paper-2)"};color:${v / mx > 0.75 ? "#fff" : "var(--ink)"}">${v}</div>`).join("")).join("")}</div>`;
    const calib = `<div class="calib" aria-label="Reliability diagram">${m.reliability.map((b) => `<div class="bin" title="${b.bin}: n=${b.n}${b.n ? `, confidence ${pct(b.confidence)}, accuracy ${pct(b.accuracy)}` : ""}"><div class="bar"><i class="c" style="height:${pct(b.confidence || 0)}"></i><i class="a" style="height:${pct(b.accuracy || 0)}"></i></div><small>${b.bin.split("-")[0]}</small></div>`).join("")}</div><div class="legend"><span><i style="background:var(--line)"></i>mean confidence</span><span><i style="background:var(--purple)"></i>accuracy</span><span>per confidence bin — bars of equal height = perfectly calibrated</span></div>`;
    const unseen = Object.entries(m.unseen_misconception).map(([k, v]) => `<tr><td>${esc(S.taxonomy[k]?.name || k)}</td><td>${v.n}</td><td>${v.top1.toFixed(2)}</td><td>${v.top1_when_answered.toFixed(2)}</td><td>${pct(v.abstained)}</td><td>${(v.false_positive_rate * 100).toFixed(1)}%</td></tr>`).join("");
    const perLabel = Object.entries(m.per_label).map(([k, v]) => `<tr><td>${esc(S.taxonomy[k]?.name || "No misconception")}</td><td>${v.precision.toFixed(2)}</td><td>${v.recall.toFixed(2)}</td><td>${v.f1.toFixed(2)}</td><td>${v.support}</td></tr>`).join("");
    const hand = m.hand_rows_template_only_model; const real = m.real_rows;
    el.innerHTML = `<div class="callout">Dataset: <b>${m.dataset.rows}</b> labelled rows over <b>${m.dataset.items}</b> items (${m.dataset.hand_rows} hand-written). Split by item: <b>${m.split.train_items.length}</b> train / <b>${m.split.test_items.length}</b> held-out.</div>
      <table class="t"><thead><tr><th>Metric</th><th>Value</th><th>Target</th><th></th></tr></thead><tbody>${rows.map(([n, v, t, b]) => `<tr><td>${n}</td><td class="mono">${typeof v === "number" ? v.toFixed(3) : v}</td><td class="mono">${t}</td><td>${ok(b)}</td></tr>`).join("")}</tbody></table>
      <h2>Real learner rows</h2>${real ? `<p class="small">Teacher-labelled responses typed into this app (never in training): accuracy <b class="mono">${(real.accuracy || 0).toFixed(3)}</b>, macro-F1 <b class="mono">${(real.macro_f1 || 0).toFixed(3)}</b>, n=${real.total}, abstained ${pct(real.abstained)}.</p>` : `<p class="small muted">None yet — label responses on the Teacher tab, export, then run <code>python ml/evaluate.py</code>.</p>`}
      <h2>Calibration</h2>${calib}
      <h2>Confusion matrix (held-out)</h2>${grid}
      <h2>Does synthetic training data transfer to natural writing?</h2>
      <p class="small">A model trained on <em>template rows only</em>, tested on all ${m.dataset.hand_rows} hand-written rows: accuracy <b class="mono">${(hand.accuracy || 0).toFixed(3)}</b>, macro-F1 <b class="mono">${(hand.macro_f1 || 0).toFixed(3)}</b>, abstained ${pct(hand.abstained)}. Vague explanations routed to <em>unknown</em>: <b class="mono">${pct(m.vague_abstain_rate)}</b> (n=${m.vague_n}). Flawed-reasoning false alarms: <b class="mono">${(m.flawed_reasoning_false_alarm_rate * 100).toFixed(1)}%</b>.</p>
      <h2>Unseen misconceptions (leave one out of training; recover it from its description)</h2>
      <table class="t"><thead><tr><th>Held out</th><th>n</th><th>top-1</th><th>top-1 when answered</th><th>abstained</th><th>false positives</th></tr></thead><tbody>${unseen}</tbody></table>
      <h2>Per label</h2><table class="t"><thead><tr><th>Label</th><th>P</th><th>R</th><th>F1</th><th>n</th></tr></thead><tbody>${perLabel}</tbody></table>
      <p class="muted small">Decision rule: answer prior ×${m.decision_config.prior_boost} on mapped labels · abstain below ${m.decision_config.abstain_threshold} · unseen fallback when description similarity ≥ ${m.decision_config.unseen_sim_threshold}. Machine: ${esc(m.machine)}.</p>`;
  }

  // ---------------- boot ----------------
  async function boot() {
    try { const [tax, health] = await Promise.all([api("/api/misconceptions"), api("/api/health")]); S.taxonomy = tax; $("#modelName").textContent = `${health.model.backend} · ${health.probes_required} probes to resolve${health.llm?.provider ? ` · AI tutor: ${health.llm.model}` : ""}`; }
    catch (err) { toast(`API not reachable: ${err.message}`, 6000); }
    showStart();
  }
  boot();
})();
