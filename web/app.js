/* Candlelit Legends page controller: screens, the story stream, the typewriter and the end card. */

(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : '');
  const reducedMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const OPTIONS = {
    story_type: [['any', 'Any'], ['ghost', 'Ghost'], ['cryptid', 'Cryptid'], ['cursed place', 'Cursed place'],
                 ['water and shipwreck', 'Water and shipwreck'], ['folklore', 'Folklore'], ['historical mystery', 'Historical mystery']],
    spookiness: [['cozy', 'Cozy'], ['campfire', 'Campfire'], ['unsettling', 'Unsettling']],
    length: [['short', 'Short'], ['long', 'Long']],
    truth_level: [['close', 'Close to sources'], ['dramatic', 'Embellished']],
  };
  const NARRATORS = ['auto', 'old innkeeper', 'lighthouse keeper', 'skeptical historian', 'the ghost itself'];
  const STAGES = [
    'Searching the old records…',
    'Setting aside tales already told…',
    'Reading what the townsfolk wrote…',
    'Choosing a legend and checking its facts…',
    'Dipping the quill…',
  ];
  const CHARS_PER_SECOND = 40;
  const CUE_PAUSE_MS = 650;
  const SPEAKER_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/></svg>';

  const state = {
    lit: false,
    options: { story_type: 'any', spookiness: 'campfire', narrator: 'auto', length: 'short', truth_level: 'close' },
    lastRequest: null,
    story: null,
    meta: null,
    sounds: {},      // id -> {kind, caption, file}
    muted: false,
    volume: 0.7,
    abort: null,
    typewriter: null,
  };

  // Per-viewer conveniences only; the app works without storage.
  const store = {
    get(k, d) { try { const v = localStorage.getItem('cl.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('cl.' + k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
  };

  /* ---------- Screens ---------- */

  const SCREENS = ['light', 'place', 'loading', 'tale', 'truth', 'past'];
  const TITLES = { light: 'Candlelit Legends', place: 'Name a place', loading: 'Searching the records',
                   tale: 'The tale', truth: 'The truth behind it', past: 'Past tales' };

  function show(name) {
    for (const s of SCREENS) $('#screen-' + s).hidden = s !== name;
    document.title = name === 'light' ? 'Candlelit Legends' : `Candlelit Legends · ${TITLES[name]}`;
    window.scrollTo(0, 0);
    if (name !== 'tale' && state.typewriter) { state.typewriter.stop(); state.typewriter = null; }
  }

  function goPlace() {
    if (state.abort) { state.abort.abort(); state.abort = null; }
    show('place');
    if (state.lit) SoundEngine.startAmbient('fire');
  }

  function goHome() { state.lit ? goPlace() : show('light'); }

  /* ---------- Candles, mute and volume ---------- */

  function mountCandles() {
    const tpl = $('#candle-tpl');
    $$('.candle-slot').forEach((slot, i) => {
      const html = tpl.innerHTML.replaceAll('GLOW_ID', 'glow' + i);
      slot.innerHTML = html;
      $('svg', slot).style.width = slot.dataset.size + 'px';
    });
    $$('.mute-slot').forEach((slot) => slot.replaceWith($('#mute-tpl').content.cloneNode(true)));
    $$('.js-mute').forEach((b) => b.addEventListener('click', () => setMuted(!state.muted)));
  }

  function setMuted(m) {
    state.muted = m;
    store.set('muted', m);
    SoundEngine.setMuted(m);
    $$('.js-mute').forEach((b) => {
      b.setAttribute('aria-pressed', String(m));
      b.setAttribute('aria-label', m ? 'Unmute sounds' : 'Mute sounds');
    });
    if (m) setNowPlaying('Sound is muted', true);
    else setNowPlaying(state.nowPlaying || '');
  }

  function setNowPlaying(text, transient) {
    if (!transient) state.nowPlaying = text;
    const shown = state.muted ? 'Sound is muted' : text;
    $$('.js-now-playing').forEach((p) => {
      p.textContent = p.closest('.tale-footer') && shown ? `Now playing: ${shown}` : shown;
    });
  }

  function dipCandle() {
    const c = $('#tale-candle svg');
    if (!c) return;
    c.classList.add('dip');
    setTimeout(() => c.classList.remove('dip'), 320);
  }

  /* ---------- Place form ---------- */

  function renderPills() {
    $$('.pills').forEach((box) => {
      const key = box.dataset.option;
      box.innerHTML = '';
      for (const [value, label] of OPTIONS[key]) {
        const b = el('button', 'pill', label);
        b.type = 'button';
        b.setAttribute('aria-pressed', String(state.options[key] === value));
        b.addEventListener('click', () => { state.options[key] = value; saveOptions(); renderPills(); });
        box.appendChild(b);
      }
    });
    $('#narrator').value = state.options.narrator;
  }

  function saveOptions() { store.set('options', state.options); }

  function roll() {
    const pick = (a) => a[Math.floor(Math.random() * a.length)];
    for (const key of Object.keys(OPTIONS)) state.options[key] = pick(OPTIONS[key])[0];
    state.options.narrator = pick(NARRATORS);
    saveOptions();
    renderPills();
  }

  function submitPlace(e) {
    e.preventDefault();
    const input = $('#place');
    const place = input.value.trim();
    if (!place) {
      input.classList.add('invalid');
      input.setAttribute('aria-invalid', 'true');
      $('#place-hint').textContent = 'Name a place first: a town, a region, or a whole country.';
      input.focus();
      return;
    }
    input.classList.remove('invalid');
    input.removeAttribute('aria-invalid');
    store.set('place', place);
    startStory({ place, ...state.options });
  }

  /* ---------- Loading: stream the pipeline ---------- */

  let stageLabels = STAGES.slice();

  function renderSteps(stage, allDone) {
    const list = $('#steps');
    list.innerHTML = '';
    stageLabels.forEach((label, i) => {
      const done = allDone || i < stage, active = !allDone && i === stage;
      const li = el('li', done ? 'done' : active ? 'active' : '');
      const mark = el('span', 'step-mark');
      if (done) mark.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f5a742" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';
      else mark.appendChild(el('span', active ? 'dot-active' : 'dot-pending'));
      li.append(mark, el('span', null, label));
      if (active) li.setAttribute('aria-current', 'step');
      list.appendChild(li);
    });
  }

  async function startStory(req) {
    SoundEngine.unlock();
    state.lastRequest = req;
    state.story = null;
    state.meta = null;
    stageLabels = STAGES.slice();
    show('loading');
    $('#loading-place').textContent = req.place;
    $('#found-line').hidden = true;
    $('#unroll-btn').hidden = true;
    $('#load-error').hidden = true;
    $('#loading-note').hidden = false;
    $('#steps').hidden = false;
    $('#screen-loading .candle-slot').classList.add('candle-gutter');
    renderSteps(0);

    const ctrl = new AbortController();
    state.abort = ctrl;
    let failed = null;
    try {
      const res = await fetch('/api/story', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`The server answered ${res.status}.`);
      for await (const { event, data } of readSSE(res.body)) {
        if (event === 'status') {
          if (data.text) stageLabels[data.stage] = data.text;
          renderSteps(data.stage);
          if (data.location) {
            const f = $('#found-line');
            f.textContent = `The candle leans toward ${data.location}.`;
            f.hidden = false;
          }
        } else if (event === 'story') {
          state.story = data;
        } else if (event === 'meta') {
          state.meta = data;
        } else if (event === 'error') {
          failed = data.message + (data.detail ? ` (${data.detail})` : '');
        }
      }
      if (!failed && !(state.story && state.meta)) failed = 'The candle went out before the tale was finished. Try again.';
    } catch (err) {
      if (ctrl.signal.aborted) return;
      failed = 'Could not reach the storyteller. Is the local server still running?';
    } finally {
      if (state.abort === ctrl) state.abort = null;
    }

    $('#screen-loading .candle-slot').classList.remove('candle-gutter');
    $('#loading-note').hidden = true;
    if (failed) {
      $('#steps').hidden = true;
      $('#load-error-text').textContent = failed;
      $('#load-error').hidden = false;
      return;
    }
    renderSteps(STAGES.length, true);
    const btn = $('#unroll-btn');
    btn.hidden = false;
    btn.focus();
    // Warm the sound buffers while the reader reaches for the button.
    SoundEngine.preload([state.meta.ambient, ...state.meta.sounds]);
  }

  async function* readSSE(body) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, i);
        buf = buf.slice(i + 2);
        let event = 'message', data = '';
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim();
          else if (line.startsWith('data:')) data += line.slice(5).trim();
        }
        if (data) yield { event, data: JSON.parse(data) };
      }
    }
  }

  /* ---------- The tale ---------- */

  const TOLD_BY = {
    'old innkeeper': 'Told by an old innkeeper',
    'lighthouse keeper': 'Told by a lighthouse keeper',
    'skeptical historian': 'Told by a skeptical historian',
    'the ghost itself': 'Told by the ghost itself',
    "a child's diary": "Told through a child’s diary",
    'a night-shift worker': 'Told by a night-shift worker',
  };
  const toldBy = (n) => TOLD_BY[n] || `Told by ${n}`;
  const caption = (id) => (state.sounds[id] && state.sounds[id].caption) || id;
  const shortPlace = (loc) => (loc || '').split(',')[0].trim();
  // "Fort Henry, Kingston, ON" -> "Kingston": the last part that isn't a province or state code.
  const townOf = (loc) => {
    const parts = (loc || '').split(',').map((s) => s.trim()).filter(Boolean);
    while (parts.length > 1 && parts[parts.length - 1].length <= 3) parts.pop();
    return parts[parts.length - 1] || '';
  };

  function parseStory(text) {
    return text.split(/\n\s*\n/).map((p) => p.replace(/\s*\n\s*/g, ' ').trim()).filter(Boolean).map((p) => {
      const segs = [];
      let last = 0;
      for (const m of p.matchAll(/\[\[sound:([a-z]+)\]\]/g)) {
        const before = p.slice(last, m.index);
        if (before) segs.push({ type: 'text', text: before });
        segs.push({ type: 'cue', id: m[1] });
        last = m.index + m[0].length;
      }
      const rest = p.slice(last);
      if (rest) segs.push({ type: 'text', text: rest });
      return segs;
    });
  }

  function cueNode(id) {
    const s = el('span', 'cue');
    s.innerHTML = SPEAKER_SVG;
    s.appendChild(document.createTextNode(`(${caption(id)})`));
    return s;
  }

  class Typewriter {
    constructor(container, paras, hooks) {
      this.container = container;
      this.hooks = hooks;
      this.tokens = [];
      for (const segs of paras) {
        this.tokens.push({ type: 'para' });
        this.tokens.push(...segs);
      }
      this.total = paras.flat().reduce((n, s) => n + (s.type === 'text' ? s.text.length : 0), 0);
      this.shown = 0;
      this.ti = 0;
      this.ci = 0;
      this.acc = 0;
      this.flickerAt = -1;
      this.caret = el('span', 'caret');
      this.caret.setAttribute('aria-hidden', 'true');
      this.running = false;
    }

    start() {
      this.running = true;
      this.last = performance.now();
      this.pauseUntil = 0;
      const tick = (now) => {
        if (!this.running) return;
        this.step(now);
        if (this.running) this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
    }

    stop() { this.running = false; cancelAnimationFrame(this.raf); }

    step(now) {
      const dt = now - this.last;
      this.last = now;
      if (now < this.pauseUntil) return;
      this.acc += dt * CHARS_PER_SECOND / 1000;
      while (this.running && this.ti < this.tokens.length) {
        const tok = this.tokens[this.ti];
        if (tok.type === 'para') {
          this.p = el('p');
          this.p.appendChild(this.caret);
          this.container.appendChild(this.p);
          this.text = null;
          this.ti++;
        } else if (tok.type === 'cue') {
          this.caret.before(cueNode(tok.id));
          this.text = null;
          this.ti++;
          this.hooks.onCue(tok.id);
          // A tense moment: one letter soon after the sound will flicker.
          this.flickerAt = this.shown + 8 + Math.floor(Math.random() * 40);
          this.pauseUntil = now + CUE_PAUSE_MS;
          this.acc = 0;
          return;
        } else {
          if (this.acc < 1) return;
          const ch = tok.text[this.ci];
          if (this.shown >= this.flickerAt && this.flickerAt >= 0 && /\p{L}/u.test(ch)) {
            this.caret.before(el('span', 'flick', ch));
            this.text = null;
            this.flickerAt = -1;
          } else {
            if (!this.text) { this.text = document.createTextNode(''); this.caret.before(this.text); }
            this.text.appendData(ch);
          }
          this.ci++;
          this.shown++;
          this.acc -= 1;
          if (this.shown % 30 === 0) this.follow();
          if (this.ci >= tok.text.length) { this.ti++; this.ci = 0; }
          this.hooks.onProgress(this.shown / this.total);
        }
      }
      if (this.ti >= this.tokens.length) this.finish();
    }

    // Keep the newest line in view, unless the reader has scrolled away from it.
    follow() {
      const r = this.caret.getBoundingClientRect();
      const limit = window.innerHeight - 140;
      if (r.bottom > limit && r.top < window.innerHeight + 60) {
        window.scrollBy({ top: r.bottom - limit, behavior: reducedMotion() ? 'auto' : 'smooth' });
      }
    }

    finish() {
      this.stop();
      this.caret.remove();
      this.hooks.onDone();
    }
  }

  function renderAll(container, paras) {
    container.innerHTML = '';
    for (const segs of paras) {
      const p = el('p');
      for (const s of segs) p.appendChild(s.type === 'text' ? document.createTextNode(s.text) : cueNode(s.id));
      container.appendChild(p);
    }
  }

  async function showTale(animate) {
    const { story, meta } = state;
    show('tale');
    const screen = $('#screen-tale');
    screen.style.setProperty('--glow-amount', '0.12');
    $('#tale-from').textContent = `From ${meta.place}`;
    $('#tale-title').textContent = story.title;
    $('#tale-where').textContent = meta.location;
    $('#tale-sub').textContent = [toldBy(meta.narrator), cap(meta.tone), meta.length === 'long' ? 'Long tale' : 'Short tale'].join(' · ');
    $('#phone-title').textContent = shortPlace(meta.location) || story.title;
    $('#tale-end').hidden = true;
    $$('.js-skip').forEach((b) => { b.hidden = false; });

    const body = $('#tale-body');
    body.innerHTML = '';
    const paras = parseStory(story.text);

    SoundEngine.startAmbient(meta.ambient);
    setNowPlaying(`Ambient: ${caption(meta.ambient)}`);

    const done = () => {
      state.typewriter = null;
      $$('.js-skip').forEach((b) => { b.hidden = true; });
      $('#tale-end').hidden = false;
      body.setAttribute('aria-live', 'off');
      $('#truth-btn').focus({ preventScroll: true });
    };

    if (!animate || reducedMotion()) {
      renderAll(body, paras);
      screen.style.setProperty('--glow-amount', '0.06');
      done();
      return;
    }

    // Load every sound before typing so cues land exactly on their words.
    await Promise.race([SoundEngine.preload([meta.ambient, ...meta.sounds]), new Promise((r) => setTimeout(r, 2500))]);
    if ($('#screen-tale').hidden) return;

    state.typewriter = new Typewriter(body, paras, {
      onCue(id) {
        const info = state.sounds[id];
        if (info && info.kind === 'ambient') SoundEngine.startAmbient(id);
        else { SoundEngine.playOneShot(id); dipCandle(); }
        setNowPlaying(caption(id));
      },
      onProgress(p) {
        // The room darkens as the tale goes on.
        screen.style.setProperty('--glow-amount', (0.12 - 0.07 * p).toFixed(3));
      },
      onDone: done,
    });
    state.typewriter.start();
  }

  function skipToEnd() {
    if (!state.typewriter) return;
    state.typewriter.stop();
    state.typewriter = null;
    renderAll($('#tale-body'), parseStory(state.story.text));
    $('#screen-tale').style.setProperty('--glow-amount', '0.06');
    $$('.js-skip').forEach((b) => { b.hidden = true; });
    $('#tale-end').hidden = false;
    $('#truth-btn').focus({ preventScroll: true });
  }

  /* ---------- The truth behind it ---------- */

  const SEALS = {
    'documented history': ['Documented', 'history', 'seal-documented'],
    'local legend': ['Local', 'legend', ''],
    'internet lore': ['Internet', 'lore', 'seal-lore'],
  };

  function showTruth() {
    const m = state.meta;
    show('truth');
    SoundEngine.startAmbient('fire');
    $('#truth-from').textContent = `From ${m.place}`;
    $('#truth-title').textContent = m.title;
    $('#truth-location').textContent = m.location;

    const [a, b, cls] = SEALS[m.label] || SEALS['local legend'];
    const seal = $('#truth-seal');
    seal.innerHTML = '';
    seal.append(a, document.createElement('br'), b);
    seal.parentElement.className = 'seal ' + cls;
    seal.parentElement.setAttribute('aria-label', `Label: ${m.label}`);

    const notes = [];
    if (m.embellished) notes.push('Embellished: some scenes and details in this tale were invented for drama.');
    if (m.widened) notes.push('The records were thin, so the search widened to nearby towns and the region.');
    $('#truth-notes').textContent = notes.join(' ');
    $('#truth-notes').hidden = !notes.length;

    for (const kind of ['documented', 'legend']) {
      const ul = $('#facts-' + kind);
      ul.innerHTML = '';
      const facts = m.facts.filter((f) => f.kind === kind);
      for (const f of facts) {
        const li = el('li', null, f.text);
        const sup = el('sup', null, `[${f.source}]`);
        li.appendChild(sup);
        ul.appendChild(li);
      }
      $('#col-' + kind).hidden = !facts.length;
    }

    const ol = $('#truth-sources');
    ol.innerHTML = '';
    for (const s of m.sources) {
      const li = el('li');
      const a2 = el('a', null, s.title || s.url);
      a2.href = s.url;
      a2.target = '_blank';
      a2.rel = 'noopener noreferrer';
      let host = '';
      try { host = new URL(s.url).hostname.replace(/^www\./, ''); } catch (e) { /* keep empty */ }
      li.appendChild(a2);
      if (host) li.appendChild(el('span', 'src-host', `, ${host}`));
      ol.appendChild(li);
    }

    const chips = $('#truth-chips');
    chips.innerHTML = '';
    [`Narrator: ${m.narrator}`, `Tone: ${m.tone}`,
     `Sounds: ${m.sounds.length ? [...new Set(m.sounds)].join(', ') : 'none'}`, `Model: ${m.model}`]
      .forEach((t) => chips.appendChild(el('span', 'chip', t)));

    $('#again-btn').textContent = `Another tale from ${shortPlace(m.place)}`;
    renderHistory($('#truth-history'));
  }

  /* ---------- History ---------- */

  async function renderHistory(root) {
    root.innerHTML = '';
    root.appendChild($('#history-tpl').content.cloneNode(true));
    const list = $('.history-list', root), empty = $('.history-empty', root), foot = $('.history-foot', root);
    const clearBtn = $('.js-clear', root);
    let items = [];
    try { items = await (await fetch('/api/history')).json(); } catch (e) { /* show as empty */ }

    const setEmpty = (msg) => {
      list.innerHTML = '';
      empty.textContent = msg;
      empty.hidden = false;
      foot.hidden = true;
      clearBtn.hidden = true;
    };
    if (!items.length) setEmpty('No tales told yet. Name a place and the first one will be written here.');

    for (const it of items) {
      const li = el('li');
      const b = el('button', 'history-item');
      b.type = 'button';
      const town = townOf(it.location) || it.place;
      b.append(el('span', 't', it.title || it.location),
               el('span', 'm', [town, cap(it.narrator), cap(it.tone)].filter(Boolean).join(' · ')));
      b.addEventListener('click', () => openPast(it.id));
      li.appendChild(b);
      list.appendChild(li);
    }

    let armed = null;
    clearBtn.addEventListener('click', async () => {
      if (!armed) {
        clearBtn.textContent = 'Click again to forget every tale';
        clearBtn.classList.add('confirming');
        armed = setTimeout(() => {
          armed = null;
          clearBtn.textContent = 'Clear history';
          clearBtn.classList.remove('confirming');
        }, 4000);
        return;
      }
      clearTimeout(armed);
      try {
        await fetch('/api/history', { method: 'DELETE' });
        setEmpty('History cleared. Every legend is new again.');
      } catch (e) {
        clearBtn.textContent = 'Could not clear. Try again';
      }
    });
  }

  async function openPast(id) {
    try {
      const data = await (await fetch(`/api/history/${id}`)).json();
      state.story = data.story;
      state.meta = data.meta;
      showTale(true);
    } catch (e) { /* stay on the list */ }
  }

  /* ---------- Status of the local model ---------- */

  async function checkStatus() {
    let s;
    try { s = await (await fetch('/api/status')).json(); } catch (e) { return; }
    state.sounds = s.sounds || {};
    const files = {};
    for (const [id, info] of Object.entries(state.sounds)) files[id] = info.file;
    SoundEngine.setAvailable(files);

    const warn = $('#model-warning');
    const code = (t) => `<code>${t.replace(/[<>&]/g, '')}</code>`;
    if (!s.ollama) {
      warn.innerHTML = `The local model isn’t awake. Start Ollama, then run ${code('ollama pull ' + s.model)}.`;
      warn.hidden = false;
    } else if (!s.model_ready) {
      warn.innerHTML = `Ollama is running, but the story model isn’t pulled yet. Run ${code('ollama pull ' + s.model)}.`;
      warn.hidden = false;
    } else if (!s.embed_ready) {
      warn.innerHTML = `Optional: run ${code('ollama pull nomic-embed-text')} to turn on the check that keeps tales from repeating.`;
      warn.hidden = false;
    } else {
      warn.hidden = true;
    }
    $('#model-note').textContent = `Told by ${s.model}, an open-weight model on your laptop. Only the search leaves your machine.`;
  }

  /* ---------- Wiring ---------- */

  function init() {
    mountCandles();
    state.options = { ...state.options, ...store.get('options', {}) };
    state.volume = store.get('volume', 0.7);
    $('#vol').value = Math.round(state.volume * 100);
    SoundEngine.setVolume(state.volume);
    setMuted(store.get('muted', false));
    $('#place').value = store.get('place', '');
    renderPills();
    checkStatus();

    $('#light-btn').addEventListener('click', () => {
      SoundEngine.unlock();
      state.lit = true;
      $('#screen-light').classList.add('lighting');
      setTimeout(() => { goPlace(); $('#place').focus(); }, reducedMotion() ? 0 : 450);
    });
    $$('.js-home').forEach((b) => b.addEventListener('click', goHome));
    $$('.js-new-place').forEach((b) => b.addEventListener('click', goPlace));
    $$('.js-past').forEach((b) => b.addEventListener('click', () => { show('past'); renderHistory($('#past-history')); }));
    $$('.js-skip').forEach((b) => b.addEventListener('click', skipToEnd));

    $('#narrator').addEventListener('change', (e) => { state.options.narrator = e.target.value; saveOptions(); });
    $('#roll-btn').addEventListener('click', roll);
    $('#place-form').addEventListener('submit', submitPlace);
    $('#place').addEventListener('input', (e) => {
      if (e.target.value.trim()) { e.target.classList.remove('invalid'); e.target.removeAttribute('aria-invalid'); }
    });
    $('#cancel-btn').addEventListener('click', goPlace);
    $('#unroll-btn').addEventListener('click', () => showTale(true));
    $('#truth-btn').addEventListener('click', showTruth);
    $('#again-btn').addEventListener('click', () => {
      const m = state.meta;
      const last = state.lastRequest;
      startStory(last && last.place === m.place ? last : { ...state.options, place: m.place });
    });
    $('#vol').addEventListener('input', (e) => {
      state.volume = Number(e.target.value) / 100;
      store.set('volume', state.volume);
      SoundEngine.setVolume(state.volume);
      if (state.muted && state.volume > 0) setMuted(false);
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && state.typewriter) skipToEnd();
    });

    show('light');
  }

  init();
})();
