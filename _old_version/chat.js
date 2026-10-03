/* Re:Learn chat mode — the whole loop as a conversation with the tutor.
   Student types or speaks; backend NLP (/api/chat/understand) turns messages into answers, questions or commands.
   Tutor messages can be read aloud (voice mode). Diagnosis, personalised fix, animation, probes, recheck and
   report all happen inside the chat. */

window.ReLearnChat = (function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x) => `${Math.round((x || 0) * 100)}%`;
  async function api(path, body) {
    const r = await fetch(path, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) { /* */ } throw new Error(m); }
    return r.json();
  }
  const CONF = { guessing: "guessing", fairly_sure: "fairly sure", certain: "certain" };

  const C = { // chat state
    learner: null, sessionId: null, order: [], idx: 0, questions: {}, taxonomy: {}, starters: [],
    phase: "name", item: null, target: null, probe: null, probeKind: "probe", pending: {}, last: null, sims: [],
    voice: false, listening: false, rec: null, shownAt: 0, fbd: null, speakQueue: [],
  };
  let log, composer, input, micBtn, sendBtn;

  // ---------------- rendering ----------------
  function retireChips() { log.querySelectorAll(".chat-chips button:not([disabled])").forEach((b) => { b.disabled = true; b.classList.add("stale"); }); }
  function msg(role, html, { speak = null, id = null } = {}) {
    if (role === "me") retireChips();
    const el = document.createElement("div"); el.className = `m ${role}`; if (id) el.id = id;
    el.innerHTML = `<div class="avatar" aria-hidden="true">${role === "bot" ? "" : ""}</div><div class="bubble">${html}</div>`;
    log.appendChild(el); log.scrollTo({ top: log.scrollHeight, behavior: "smooth" });
    if (role === "bot") say(speak ?? el.querySelector(".bubble").textContent);
    return el;
  }
  const bot = (html, o) => msg("bot", html, o);
  const me = (text) => msg("me", esc(text));
  function chips(items, onPick, { cls = "" } = {}) {
    const wrap = document.createElement("div"); wrap.className = `chips chat-chips ${cls}`;
    items.forEach((it) => { const b = document.createElement("button"); b.type = "button"; b.className = "chip-btn"; b.innerHTML = it.html || esc(it.label); b.addEventListener("click", () => { wrap.querySelectorAll("button").forEach((x) => { x.disabled = true; }); b.classList.add("on"); onPick(it); }); wrap.appendChild(b); });
    log.lastElementChild.querySelector(".bubble").appendChild(wrap); log.scrollTo({ top: log.scrollHeight, behavior: "smooth" });
    return wrap;
  }
  function typing(on) { let t = $("#typing"); if (on && !t) { t = document.createElement("div"); t.id = "typing"; t.className = "m bot"; t.innerHTML = '<div class="avatar"></div><div class="bubble dots"><i></i><i></i><i></i></div>'; log.appendChild(t); log.scrollTo({ top: log.scrollHeight }); } if (!on && t) t.remove(); }

  // ---------------- voice out (TTS) ----------------
  function say(text) {
    if (!C.voice || !("speechSynthesis" in window) || !text) return;
    const clean = text.replace(/\s+/g, " ").replace(/[→✓✗•]/g, "").trim().slice(0, 600);
    const u = new SpeechSynthesisUtterance(clean); u.lang = "en-IN"; u.rate = 1.02;
    const voices = speechSynthesis.getVoices(); const v = voices.find((x) => /en-IN/.test(x.lang)) || voices.find((x) => /en-GB/.test(x.lang)) || voices.find((x) => /^en/.test(x.lang));
    if (v) u.voice = v;
    u.onend = () => { if (C.voice && C.listening === "auto") startListening(); };
    speechSynthesis.speak(u);
  }
  function setVoice(on) {
    C.voice = on; $("#chatVoice").setAttribute("aria-pressed", String(on)); $("#chatVoice").textContent = on ? "🔊 Voice on" : "🔈 Voice off";
    try { localStorage.setItem("relearn-chat-voice", on ? "1" : "0"); } catch (_) { /* */ }
    if (!on) { speechSynthesis && speechSynthesis.cancel(); stopListening(); }
  }

  // ---------------- voice in (STT) ----------------
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  function startListening() {
    if (!Rec || C.rec) return;
    const rec = new Rec(); rec.lang = "en-IN"; rec.interimResults = true; rec.continuous = false;
    let finalText = "";
    rec.onresult = (e) => { let interim = ""; finalText = ""; for (let i = 0; i < e.results.length; i++) { const t = e.results[i][0].transcript; if (e.results[i].isFinal) finalText += t; else interim += t; } input.value = finalText || interim; input.placeholder = "Listening…"; };
    rec.onstart = () => { micBtn.classList.add("rec"); micBtn.setAttribute("aria-pressed", "true"); input.placeholder = "Listening…"; };
    rec.onend = () => { C.rec = null; micBtn.classList.remove("rec"); micBtn.setAttribute("aria-pressed", "false"); input.placeholder = "Type or speak…"; if (finalText.trim()) { input.value = finalText; send(); } };
    rec.onerror = (e) => { if (e.error === "not-allowed") bot("I can't hear you — the microphone is blocked. Allow it in the browser's address bar and try again."); C.listening = false; };
    C.rec = rec; try { rec.start(); } catch (_) { C.rec = null; }
  }
  function stopListening() { if (C.rec) { try { C.rec.stop(); } catch (_) { /* */ } } }

  // ---------------- helpers for items ----------------
  function itemHtml(item, kind = "question") {
    const tag = kind === "question" ? `Question ${C.idx + 1} of ${C.order.length}` : kind === "recheck" ? "Quick recheck" : `Transfer check · ${esc(item.context || "")}`;
    let body = `<div class="tag">${esc(tag)}</div><p class="q">${esc(item.prompt)}</p>`;
    if (item.kind === "working") body += `<p class="small muted">Tell me the number (in ${esc(item.unit)}) and your working — e.g. “twelve, because a equals F over m…”. ${esc(item.hint)}</p>`;
    else if (item.kind === "fbd") body += `<p class="small muted">Draw the forces below, or say them: “gravity down, normal force up”. Then tell me why.</p><div class="fbd-host"></div>`;
    else body += `<ol class="optlist">${item.options.map((o) => `<li><b>${o.key}</b> ${esc(o.text)}</li>`).join("")}</ol><p class="small muted">Say the letter and <i>why</i> — e.g. “B, because gravity still acts”.</p>`;
    return body;
  }
  function speakItem(item) {
    if (item.kind === "working") return `${item.prompt} Tell me the number in ${item.unit}, and your working.`;
    if (item.kind === "fbd") return `${item.prompt} Draw the forces, or tell me which forces act and which way they point.`;
    return `${item.prompt} ` + item.options.map((o) => `Option ${o.key}: ${o.text}.`).join(" ") + " Tell me the letter and why.";
  }
  function postItem(item, kind) {
    retireChips();
    C.item = item; C.pending = {}; C.shownAt = Date.now(); C.phase = kind === "question" ? "question" : kind;
    const el = bot(itemHtml(item, kind), { speak: speakItem(item) });
    if (item.kind === "fbd") {
      const host = el.querySelector(".fbd-host"); C.fbd = FBD.mount(host, item, () => {});
      const ok = document.createElement("button"); ok.type = "button"; ok.className = "btn small"; ok.textContent = "Done drawing — diagnose"; ok.style.marginTop = ".5rem";
      ok.addEventListener("click", () => submitAnswer({})); host.appendChild(ok);
    }
    if (item.kind === "choice" || !item.kind) chips(item.options.map((o) => ({ label: o.key, key: o.key })), (it) => { C.pending.choice = it.key; me(`Option ${it.key}`); askWhy(); }, { cls: "letters" });
  }
  function askWhy() {
    bot("Got it. <b>Why?</b> One sentence in your own words — or tap “skip reason” and I'll ask a quick follow-up.");
    chips([{ label: "skip reason", skip: true }], () => submitAnswer({}));
  }

  // ---------------- answer submission ----------------
  function struggle() { return { time_ms: Date.now() - C.shownAt, edits: 0, input_method: C.listening ? "voice" : "typed" }; }
  async function submitAnswer(extra) {
    const item = C.item; if (!item) return;
    const p = { ...C.pending, ...extra };
    const base = { learner: C.learner, session_id: C.sessionId, explanation: p.explanation || "", confidence: p.confidence || "fairly_sure", ...struggle() };
    typing(true);
    try {
      let res;
      if (C.phase === "probe" || C.phase === "recheck") {
        if (!p.choice) { typing(false); bot("Which option? Say the letter."); return; }
        res = await api("/api/reassess", { ...base, misconception: C.target, probe_id: item.id, choice: p.choice, phase: C.phase === "recheck" ? "recheck" : "probe" });
        typing(false); return showProbeResult(res);
      }
      if (item.kind === "working") {
        if (p.number == null) { typing(false); bot(`I need the number too (in ${esc(item.unit)}). Say it with your working.`); return; }
        res = await api("/api/diagnose", { ...base, question_id: item.id, numeric_value: p.number });
      } else if (item.kind === "fbd") {
        res = await api("/api/diagnose", { ...base, question_id: item.id, diagram: C.fbd ? C.fbd.get() : [] });
      } else {
        if (!p.choice) { typing(false); bot("Which option? Say the letter, or tap one above."); return; }
        res = await api("/api/diagnose", { ...base, question_id: item.id, choice: p.choice });
      }
      typing(false); C.last = res;
      if (res.status === "needs_reason") return askFollowup(res.followup);
      showVerdict(res);
    } catch (err) { typing(false); bot(`Something went wrong: ${esc(err.message)}`); }
  }
  function askFollowup(fu) {
    C.phase = C.phase === "question" ? "reason" : C.phase;
    bot(`<b>${esc(fu.question)}</b>`, { speak: fu.question + " " + fu.options.filter((o) => o.id !== "OTHER").map((o, i) => `${i + 1}: ${o.text}`).join(" ") });
    chips(fu.options.map((o) => ({ label: o.text, id: o.id, cls: o.id === "OTHER" ? "other" : "" })), (it) => {
      if (it.id === "OTHER") { bot("Go ahead — say it in your own words."); return; }
      me(it.label); C.pending.explanation = it.label; submitAnswer({ explanation: it.label });
    });
  }

  // ---------------- verdict / fix ----------------
  const STATUS = { correct: "✅ Correct — right answer, sound reasoning.", misconception: "The answer is wrong — and I can see why.", flawed_reasoning: "Right answer — but the reasoning hides a misconception.", unknown: "I'd rather ask than guess." };
  function showVerdict(res) {
    const tx = res.misconception;
    let html = `<div class="verdict-line ${res.status}"><b>${STATUS[res.status]}</b> <span class="muted small">confidence ${pct(res.confidence)}${res.hesitant ? " · you hesitated" : ""}</span></div>`;
    if (res.mode === "fbd" && res.diagram_feedback) { const f = res.diagram_feedback; html += `<div class="fbd-fb">${f.ok.map((x) => `<div class="ok">✓ ${esc(x)}</div>`).join("")}${f.missing.map((x) => `<div class="miss">✗ missing: ${esc(x)}</div>`).join("")}${f.extra.map((x) => `<div class="extra">✗ should not be there: ${esc(x)}</div>`).join("")}${f.wrong_size.map((x) => `<div class="extra">✗ ${esc(x)}</div>`).join("")}</div>`; }
    if (res.mode === "working" && res.worked) html += `${res.rule ? `<p><b>In your working:</b> ${esc(res.rule.why)}</p>` : ""}<p><b>Correct answer: ${esc(res.answer_shown)}</b></p><ol class="small">${res.worked.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>`;
    if (res.status === "unknown") { bot(html + `<p>${esc(res.ask)}</p>`, { speak: STATUS.unknown + " " + res.ask }); C.phase = "reason"; return; }
    if (res.status === "correct") { bot(html, { speak: STATUS.correct }); chips([{ label: "Next question →", cmd: "next" }], () => advance()); return; }
    html += `<div class="belief" style="--c:${tx.colour};margin-top:.6rem"><h3>${esc(tx.name)}${res.confidently_held ? ' <span class="badge">held with certainty</span>' : ""}</h3><div class="vs"><div class="you"><b>What your reasoning suggests</b>${esc(tx.believes)}</div><div class="phys"><b>What physics says</b>${esc(tx.physics)}</div></div></div>`;
    bot(html, { speak: `${STATUS[res.status]} The idea behind your answer is ${tx.name}. ${tx.physics}` });
    const p = res.personalised;
    if (p && p.quote) {
      let q = esc(p.quote); if (p.trigger) q = q.replace(esc(p.trigger), `<mark>${esc(p.trigger)}</mark>`);
      bot(`<div class="foryou" style="margin:0"><div class="kicker">Written for you ${p.source === "llm" ? '<span class="badge soft">generated</span>' : ""}</div><blockquote>You said: “${q}”</blockquote><p style="margin:0">${esc(p.bridge)}</p></div>`, { speak: `You said: ${p.quote}. ${p.bridge}` });
    }
    const iv = res.intervention;
    bot(`<p class="fix-head">${esc(iv.headline)}</p>${iv.explanation.map((x) => `<p>${esc(x)}</p>`).join("")}`, { speak: iv.headline + " " + iv.explanation.join(" ") });
    chips([{ label: "▶ Show the animation", cmd: "show_sim" }, { label: "Worked example", cmd: "worked" }, { label: "Test the fix →", cmd: "test_fix" }], (it) => runCommand(it.cmd));
    C.phase = "fix";
  }
  function showSim() {
    const iv = C.last?.intervention; if (!iv) return bot("There's no animation for this step yet.");
    const el = bot(`<div class="simwrap"><canvas width="680" height="330" role="img" aria-label="Physics animation"></canvas><div class="sim-bar"><button class="btn small" type="button" data-play>Pause</button><button class="btn ghost small" type="button" data-replay>Replay</button><label class="small" style="display:flex;align-items:center;gap:.4rem;margin-left:auto"><input type="checkbox" data-belief> Show what the belief predicts</label></div><div class="sim-desc"></div></div>`, { speak: "Here is the animation." });
    const canvas = el.querySelector("canvas"); const sim = Simulations.mount(canvas, iv.simulation); if (!sim) return;
    C.sims.push(sim); el.querySelector(".sim-desc").textContent = sim.describe;
    el.querySelector("[data-play]").addEventListener("click", (e) => { e.target.textContent = sim.toggle() ? "Pause" : "Play"; });
    el.querySelector("[data-replay]").addEventListener("click", () => sim.replay());
    el.querySelector("[data-belief]").addEventListener("change", (e) => sim.setMode(e.target.checked ? "belief" : "physics"));
    chips([{ label: "Show the belief", cmd: "belief" }, { label: "Test the fix →", cmd: "test_fix" }], (it) => runCommand(it.cmd));
  }
  function showWorked() {
    const iv = C.last?.intervention; if (!iv) return bot("Nothing to show yet — answer a question first.");
    bot(`<b>Worked example: ${esc(iv.worked_example.title)}</b><ol class="small">${iv.worked_example.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol><p class="small"><b>Check yourself:</b> ${esc(iv.check_yourself)}</p>`, { speak: `Worked example. ${iv.worked_example.steps.join(". ")}. Check yourself: ${iv.check_yourself}` });
    chips([{ label: "Test the fix →", cmd: "test_fix" }], (it) => runCommand(it.cmd));
  }
  function startProbe(probe, target, kind = "probe") {
    if (!probe) return advance();
    C.probe = probe; C.target = target; C.phase = kind;
    bot(kind === "recheck" ? `Quick recheck on <b>${esc(C.taxonomy[target].name)}</b> — same idea, new context.` : `Let's test the fix in a new situation. Same idea — <b>${esc(C.taxonomy[target].name)}</b> — different context.`);
    postItem(probe, kind);
  }

  // ---------------- probe result ----------------
  function showProbeResult(res) {
    C.last = res;
    if (res.status === "needs_reason") return askFollowup(res.followup);
    if (res.resolved === null) { bot(esc(res.ask)); C.phase = "reason"; return; }
    const tx = C.taxonomy[res.target];
    const state = res.state ? `<span class="state ${res.state}">${res.state}</span>` : "";
    if (res.resolved) {
      bot(`<b>${res.held_across_sessions ? "Held across sessions 🎉" : res.resolved_now ? "Resolved ✅" : "Clear in this context ✓"}</b> ${state}<p>${esc(res.message)}</p>`, { speak: res.message });
      if (res.probe) chips([{ label: `Next context: ${res.probe.context} →` }], () => startProbe(res.probe, res.target));
      else chips([{ label: "Continue →" }], () => advance());
      return;
    }
    bot(`<b>Not yet.</b> ${state}<p>${esc(res.message)}</p>${res.target_present ? `<p class="small muted">Right answer, but “${esc(tx.short.toLowerCase())}” is still in your reasoning.</p>` : ""}`, { speak: res.message });
    const p = res.personalised; if (p && p.quote) { let q = esc(p.quote); if (p.trigger) q = q.replace(esc(p.trigger), `<mark>${esc(p.trigger)}</mark>`); bot(`<div class="foryou" style="margin:0"><blockquote>You said: “${q}”</blockquote><p style="margin:0">${esc(p.bridge)}</p></div>`, { speak: `You said: ${p.quote}. ${p.bridge}` }); }
    if (res.intervention) C.last.intervention = res.intervention;
    if (res.probe) chips([{ label: "▶ Show the animation", cmd: "show_sim" }, { label: `Try another context: ${res.probe.context} →` }], (it) => it.cmd ? runCommand(it.cmd) : startProbe(res.probe, res.target));
    else chips([{ label: "Leave it open and continue →" }], () => advance());
  }

  async function advance() {
    C.sims.forEach((s) => s.destroy()); C.sims = [];
    try {
      const rc = await api(`/api/recheck/${encodeURIComponent(C.learner)}?session_id=${C.sessionId}`);
      if (rc.probe) { bot(rc.cross_session ? `Last session you resolved <b>${esc(C.taxonomy[rc.misconception.id].name)}</b>. Does it still hold today?` : `Earlier you resolved <b>${esc(C.taxonomy[rc.misconception.id].name)}</b>. Still true a few questions later?`); return startProbe(rc.probe, rc.misconception.id, "recheck"); }
    } catch (_) { /* */ }
    C.idx += 1;
    if (C.idx >= C.order.length) return finish();
    postItem(C.questions[C.order[C.idx]], "question");
  }
  async function finish() {
    if (C.sessionId) { try { await api("/api/session/finish", { session_id: C.sessionId }); } catch (_) { /* */ } }
    const r = await api(`/api/report/${encodeURIComponent(C.learner)}`); const s = r.summary;
    const ideas = r.misconceptions.map((m) => `<li><b>${esc(m.name)}</b> — <span class="state ${m.state}">${m.state}</span>${m.held_across_sessions ? " · held across sessions" : ""}</li>`).join("");
    bot(`<b>Session report</b><div class="tiles mini"><div class="tile good"><b>${s.right_first_time}</b><span>right first time</span></div><div class="tile warn"><b>${s.found}</b><span>found</span></div><div class="tile good"><b>${s.fixed}</b><span>fixed</span></div><div class="tile bad"><b>${s.recurring}</b><span>recurring</span></div></div><ul class="small">${ideas || "<li>No misconceptions found — every answer came with sound reasoning.</li>"}</ul><a class="btn ghost small" href="/api/report/${encodeURIComponent(C.learner)}/pdf" download>Download PDF report</a>`,
        { speak: `Session done. ${s.right_first_time} right first time, ${s.found} misconceptions found, ${s.fixed} fixed and verified, ${s.recurring} recurring.` });
    C.phase = "done"; chips([{ label: "Start another session" }], () => { C.sessionId = null; C.idx = 0; startSession(C.learner); });
  }

  // ---------------- commands ----------------
  function runCommand(cmd) {
    switch (cmd) {
      case "skip_reason": if (C.pending.choice || C.pending.number != null || C.item?.kind === "fbd") return submitAnswer({ explanation: "" }); return bot("Tell me your answer first — the letter, the number, or the forces.");
      case "next": if (C.pending.choice && ["question", "probe", "recheck"].includes(C.phase)) return submitAnswer({ explanation: "" }); if (C.phase === "done") return bot("The session is over — say “start again” for a new one."); if (["fix", "probe", "recheck", "reason", "question"].includes(C.phase) && C.last && C.phase !== "question") return bot("Let's finish this idea first — say “test the fix”, or “skip” to leave it open.", { speak: "Let's finish this idea first. Say test the fix, or skip to leave it open." }); return advance();
      case "repeat": if (C.item) return bot(itemHtml(C.item, C.phase === "question" ? "question" : C.phase), { speak: speakItem(C.item) }); return bot("Nothing to repeat yet.");
      case "hint": return hint();
      case "explain_more": if (C.last?.misconception) return bot(`<b>${esc(C.last.misconception.name)}</b>: ${esc(C.last.misconception.physics)} ${esc(C.last.intervention.explanation[2] || "")}`); return bot("Answer the question first and I'll explain exactly the idea behind your answer.");
      case "show_sim": return showSim();
      case "belief": { const s = C.sims[C.sims.length - 1]; if (s) { s.setMode("belief"); return bot("That's what the belief predicts — the red dashed ghost. Compare it with what really happens.", { speak: "That is what the belief predicts, the red dashed ghost. Compare it with what really happens." }); } return showSim(); }
      case "worked": return showWorked();
      case "test_fix": if (C.last?.probe && C.phase === "fix") return startProbe(C.last.probe, C.last.probe.target); return bot("There's no fix to test right now.");
      case "report": return progress();
      case "map": return progress();
      case "theme": return $("#themeToggle").click();
      case "voice": return setVoice(!C.voice);
      case "restart": C.sessionId = null; C.idx = 0; return startSession(C.learner);
      case "clear": C.pending = {}; return bot("Cleared. Say your answer again.");
      case "submit": return submitAnswer({});
      case "sim": { const s = C.sims[C.sims.length - 1]; if (s) s.toggle(); return; }
      default: return bot("I didn't catch that command.");
    }
  }
  function hint() {
    const it = C.item; if (!it) return bot("Ask me once a question is on the screen.");
    const h = it.kind === "working" ? it.hint : it.kind === "fbd" ? "For every arrow you draw, name the object applying that force. If you can't, the arrow doesn't belong." : "Don't start from the answer — start from the forces. Which objects are touching it? Is gravity acting? Then ask what those forces do to the velocity.";
    bot(`<b>Hint:</b> ${esc(h)}<br><span class="small muted">Sentence starters: ${C.starters.map(esc).join(" · ")}</span>`, { speak: `Hint: ${h}` });
  }
  async function progress() {
    const p = await api(`/api/profile/${encodeURIComponent(C.learner)}`);
    const rows = p.misconceptions.map((m) => `<li><b>${esc(C.taxonomy[m.id].name)}</b> — <span class="state ${m.state}">${m.state}</span> (${m.probes_passed}/${m.probes_required} probes)</li>`).join("");
    bot(`<b>Your progress:</b> ${p.answered} answered, ${p.misconceptions.length} idea${p.misconceptions.length === 1 ? "" : "s"} found, ${p.misconceptions.filter((m) => m.state === "resolved").length} fixed.<ul class="small">${rows || "<li>Nothing on the map yet.</li>"}</ul>`);
  }

  // ---------------- incoming message ----------------
  async function handle(text) {
    if (C.phase === "name") {
      let name = text.replace(/^(hi|hello|hey|hii+|namaste|good (morning|afternoon|evening))[,!. ]*/i, "").replace(/^(i am|i'm|im|my name is|it's|its|this is|call me|name is)\s+/i, "").replace(/[.!?]+$/, "").trim();
      name = name.split(/\s+/).slice(0, 3).join(" ").slice(0, 40);
      return startSession(name || "Learner");
    }
    typing(true);
    let u;
    try { u = await api("/api/chat/understand", { text, item_id: C.item?.id || null, phase: C.phase }); } catch (err) { typing(false); return bot(`Hmm — ${esc(err.message)}`); }
    typing(false);
    switch (u.intent) {
      case "greeting": return bot(`Hi ${esc(C.learner)}! ${C.item ? "The question is above — say the letter and why." : "Say “next” to get a question."}`);
      case "thanks": return bot("You're welcome. Keep going!");
      case "who": return bot("I'm Re:Learn, a physics tutor. I don't just mark you right or wrong — I work out the idea behind your answer, fix that idea in your own words, and check that the fix stuck.");
      case "confused": return bot("That's fine — being confused is where learning starts. " + (C.item ? "Tell me what you <i>think</i> happens, even if you're unsure; I'll find the idea behind it. Or say “hint”." : "Say “next” and we'll take it one question at a time."));
      case "question": return bot(`${esc(u.reply)}${u.sources?.length ? `<div class="small muted">from: ${u.sources.map(esc).join(", ")}${u.generated ? " · generated" : ""}</div>` : ""}${C.item ? '<div class="small muted">(The question is still waiting above.)</div>' : ""}`, { speak: u.reply });
      case "command": return runCommand(u.actions[0].command);
      case "answer": return applyActions(u.actions);
      default:
        if (["question", "probe", "recheck", "reason"].includes(C.phase)) { C.pending.explanation = text; return submitAnswer({ explanation: text }); }
        return bot("Tell me your answer, ask a physics question, or say “next”, “hint”, “repeat”, “show the animation”, “report”.");
    }
  }
  function applyActions(actions) {
    const tags = [];
    for (const a of actions) {
      if (a.type === "select") { C.pending.choice = a.key; tags.push(`option ${a.key}${a.how === "fuzzy" ? " (matched by wording)" : ""}`); }
      if (a.type === "number") { C.pending.number = a.value; tags.push(`${a.value}`); }
      if (a.type === "confidence") { C.pending.confidence = a.value; tags.push(CONF[a.value]); }
      if (a.type === "explanation") { C.pending.explanation = a.value; tags.push("reason noted"); }
      if (a.type === "add_force" && C.fbd) { C.fbd.add(a.force, a.direction, a.size); tags.push(`${a.force} ${a.direction}`); }
      if (a.type === "remove_force" && C.fbd) { C.fbd.remove(a.force); tags.push(`removed ${a.force}`); }
    }
    const understood = tags.length ? `<span class="heard-tags">${tags.map((t) => `<span>${esc(t)}</span>`).join("")}</span>` : "";
    const it = C.item;
    const needChoice = (!it.kind || it.kind === "choice") && !C.pending.choice;
    const needNumber = it.kind === "working" && C.pending.number == null;
    if (needChoice) { bot(`${understood} Which option is that? Say the letter.`, { speak: "Which option? Say the letter." }); return; }
    if (needNumber) { bot(`${understood} And the number, in ${esc(it.unit)}?`, { speak: `And the number, in ${it.unit}?` }); return; }
    if ((!it.kind || it.kind === "choice") && !C.pending.explanation && C.phase !== "reason") { bot(`${understood} Why? One sentence — or say “skip reason”.`, { speak: "Why? One sentence, or say skip reason." }); return; }
    submitAnswer({});
  }

  function send() {
    const text = input.value.trim(); if (!text) return;
    input.value = ""; me(text); handle(text);
  }

  // ---------------- session ----------------
  async function startSession(name) {
    C.learner = name;
    try {
      const res = await api("/api/session/start", { learner: name, mode: $("#chatMode").value });
      C.sessionId = res.session_id; C.order = res.question_order; C.idx = 0; C.starters = res.sentence_starters;
      res.questions.forEach((q) => { C.questions[q.id] = q; });
      $("#learnerName").textContent = name; $("#learnerChip").hidden = false;
      if (res.welcome) {
        const w = res.welcome;
        bot(`Welcome back, ${esc(name)}! ${esc(w.message)} ${w.to_verify.length ? `We'll check: ${w.to_verify.map((m) => `<b>${esc(m.name)}</b>`).join(", ")}.` : ""}`);
        return advanceFromStart();
      }
      bot(`Nice to meet you, ${esc(name)}. Here's how this works: I ask, you answer <b>and tell me why</b> — type it or press the mic. I'll find the idea behind your answer, fix exactly that, and test you in a new situation. Ask me physics questions any time. Say “hint”, “repeat”, “next” or “report” whenever you like.`);
      postItem(C.questions[C.order[0]], "question");
    } catch (err) { bot(`Couldn't start a session: ${esc(err.message)}`); }
  }
  async function advanceFromStart() {
    try { const rc = await api(`/api/recheck/${encodeURIComponent(C.learner)}?session_id=${C.sessionId}`); if (rc.probe) return startProbe(rc.probe, rc.misconception.id, "recheck"); } catch (_) { /* */ }
    postItem(C.questions[C.order[0]], "question");
  }

  // ---------------- init ----------------
  async function init(root) {
    root.innerHTML = `<div class="chat">
      <div class="chat-top"><span class="muted small">Chat with the tutor · type or speak</span>
        <select class="input" id="chatMode" aria-label="Session type" style="max-width:220px"><option value="quick">Quick session (9)</option><option value="working">Show your working (5)</option><option value="diagram">Draw the forces (4)</option><option value="full">Full bank (39)</option></select>
        <button class="tool" id="chatVoice" type="button" aria-pressed="false">🔈 Voice off</button></div>
      <div class="chat-log" id="chatLog" aria-live="polite"></div>
      <form class="composer" id="composer"><button type="button" class="mic-big" id="chatMic" aria-pressed="false" ${Rec ? "" : "disabled title='Voice input needs Chrome or Edge'"}>🎙</button><input class="input" id="chatInput" placeholder="Type or speak…" autocomplete="off" maxlength="600"><button class="btn accent" type="submit" id="chatSend">Send</button></form></div>`;
    log = $("#chatLog"); composer = $("#composer"); input = $("#chatInput"); micBtn = $("#chatMic"); sendBtn = $("#chatSend");
    C.taxonomy = await api("/api/misconceptions");
    composer.addEventListener("submit", (e) => { e.preventDefault(); send(); });
    micBtn.addEventListener("click", () => { if (C.rec) { stopListening(); C.listening = false; } else { C.listening = true; startListening(); } });
    $("#chatVoice").addEventListener("click", () => setVoice(!C.voice));
    let pref = "0"; try { pref = localStorage.getItem("relearn-chat-voice") || "0"; } catch (_) { /* */ }
    if (pref === "1") setVoice(true);
    if ("speechSynthesis" in window) speechSynthesis.getVoices();
    bot("Hi! I'm <b>Re:Learn</b>. I don't just tell you that you're wrong — I tell you <i>why</i>, fix that, and check that the fix stuck. <b>What's your name?</b>", { speak: "Hi! I'm Re:Learn. What's your name?" });
    input.focus();
  }

  return { init, say, state: C };
})();
