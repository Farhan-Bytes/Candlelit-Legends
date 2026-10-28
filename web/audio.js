/* Sound engine: one quiet ambient loop under the tale, one-shots that dip it briefly.
   Real recordings are read from /sounds/<id>.ogg (see sounds/credits.json). Any sound without a
   file is synthesised here, so the experience works before the recordings are downloaded. */

const SoundEngine = (() => {
  const AMBIENT_LEVEL = 0.32;
  const DIP_LEVEL = 0.1;

  let ctx = null, master, ambientBus, fxBus;
  let volume = 0.7, muted = false;
  let ambient = null; // { id, src, gain }
  const buffers = {};
  let available = {}; // id -> true when a recorded file exists

  function unlock() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      ctx = new AC();
      master = ctx.createGain();
      master.connect(ctx.destination);
      ambientBus = ctx.createGain();
      ambientBus.gain.value = AMBIENT_LEVEL;
      ambientBus.connect(master);
      fxBus = ctx.createGain();
      fxBus.connect(master);
      applyVolume();
    }
    if (ctx.state === 'suspended') ctx.resume();
  }

  function applyVolume() {
    if (!ctx) return;
    master.gain.setTargetAtTime(muted ? 0 : volume, ctx.currentTime, 0.05);
  }
  function setVolume(v) { volume = v; applyVolume(); }
  function setMuted(m) { muted = m; applyVolume(); }
  function setAvailable(map) { available = map || {}; }

  async function load(id) {
    if (buffers[id]) return buffers[id];
    if (!ctx) return null;
    if (available[id]) {
      try {
        const res = await fetch(`/sounds/${id}.ogg`);
        if (res.ok) {
          buffers[id] = await ctx.decodeAudioData(await res.arrayBuffer());
          return buffers[id];
        }
      } catch (e) { /* fall through to synthesis (e.g. Safari cannot decode Ogg) */ }
    }
    const make = Synth[id];
    if (!make) return null;
    const sr = ctx.sampleRate;
    const data = make(sr);
    const buf = ctx.createBuffer(1, data.length, sr);
    buf.copyToChannel(data, 0);
    buffers[id] = buf;
    return buf;
  }

  function preload(ids) { return Promise.all([...new Set(ids)].map(load)); }

  async function startAmbient(id) {
    if (!ctx || (ambient && ambient.id === id)) return;
    const buf = await load(id);
    if (!buf) return;
    const now = ctx.currentTime;
    if (ambient) {
      const old = ambient;
      old.gain.gain.setTargetAtTime(0, now, 0.8);
      setTimeout(() => { try { old.src.stop(); } catch (e) {} }, 4000);
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    const gain = ctx.createGain();
    gain.gain.value = 0;
    gain.gain.setTargetAtTime(1, now, 0.8);
    src.connect(gain).connect(ambientBus);
    src.start(now, Math.random() * buf.duration);
    ambient = { id, src, gain };
  }

  function stopAmbient() {
    if (!ambient || !ctx) return;
    const old = ambient;
    ambient = null;
    old.gain.gain.setTargetAtTime(0, ctx.currentTime, 0.6);
    setTimeout(() => { try { old.src.stop(); } catch (e) {} }, 3000);
  }

  // Plays a one-shot at full volume and dips the ambient bed while it sounds.
  async function playOneShot(id) {
    if (!ctx) return 0;
    const buf = await load(id);
    if (!buf) return 0;
    const now = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(fxBus);
    src.start(now);
    const g = ambientBus.gain;
    g.cancelScheduledValues(now);
    g.setTargetAtTime(DIP_LEVEL, now, 0.06);
    g.setTargetAtTime(AMBIENT_LEVEL, now + buf.duration * 0.8, 0.7);
    return buf.duration;
  }

  return { unlock, setVolume, setMuted, setAvailable, preload, startAmbient, stopAmbient, playOneShot,
           get ready() { return !!ctx; } };
})();


/* ---------- Synthesised fallbacks. Each returns a mono Float32Array at the given rate. ---------- */

const Synth = (() => {
  const TAU = Math.PI * 2;
  const rnd = (a, b) => a + Math.random() * (b - a);

  function noise(n) { const x = new Float32Array(n); for (let i = 0; i < n; i++) x[i] = Math.random() * 2 - 1; return x; }
  function brown(n) {
    const x = new Float32Array(n); let y = 0;
    for (let i = 0; i < n; i++) { y = (y + 0.02 * (Math.random() * 2 - 1)) / 1.02; x[i] = y * 3.5; }
    return x;
  }
  function lowpass(x, sr, fc) {
    const a = Math.exp(-TAU * fc / sr); let y = 0;
    for (let i = 0; i < x.length; i++) { y = (1 - a) * x[i] + a * y; x[i] = y; }
    return x;
  }
  function highpass(x, sr, fc) {
    const a = Math.exp(-TAU * fc / sr); let lp = 0;
    for (let i = 0; i < x.length; i++) { lp = (1 - a) * x[i] + a * lp; x[i] = x[i] - lp; }
    return x;
  }
  // RBJ band-pass; `f0` may be a function of the sample index for sweeping filters.
  function bandpass(x, sr, f0, q) {
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0, b0, b2, a0, a1, a2;
    const coef = (f) => {
      const w = TAU * f / sr, al = Math.sin(w) / (2 * q);
      b0 = al; b2 = -al; a0 = 1 + al; a1 = -2 * Math.cos(w); a2 = 1 - al;
    };
    const sweep = typeof f0 === 'function';
    if (!sweep) coef(f0);
    for (let i = 0; i < x.length; i++) {
      if (sweep && i % 64 === 0) coef(f0(i));
      const y = (b0 * x[i] + b2 * x2 - a1 * y1 - a2 * y2) / a0;
      x2 = x1; x1 = x[i]; y2 = y1; y1 = y; x[i] = y;
    }
    return x;
  }
  function normalize(x, peak) {
    let m = 0; for (let i = 0; i < x.length; i++) m = Math.max(m, Math.abs(x[i]));
    if (m > 0) for (let i = 0; i < x.length; i++) x[i] *= peak / m;
    return x;
  }
  function fade(x, sr, inS, outS) {
    const a = Math.floor(inS * sr), b = Math.floor(outS * sr), n = x.length;
    for (let i = 0; i < a && i < n; i++) x[i] *= i / a;
    for (let i = 0; i < b && i < n; i++) x[n - 1 - i] *= i / b;
    return x;
  }
  // Crossfades the tail into the head so the buffer loops without a click.
  function loopable(x, sr, seconds) {
    const f = Math.floor(seconds * sr), n = x.length - f, out = x.slice(0, n);
    for (let i = 0; i < f; i++) { const t = i / f; out[i] = x[i] * t + x[n + i] * (1 - t); }
    return out;
  }
  function addAt(dst, src, start, gain = 1) {
    for (let i = 0; i < src.length && start + i < dst.length; i++) dst[start + i] += src[i] * gain;
  }
  function decay(n, sr, tau) { const e = new Float32Array(n); for (let i = 0; i < n; i++) e[i] = Math.exp(-i / (tau * sr)); return e; }
  function mul(x, e) { for (let i = 0; i < x.length; i++) x[i] *= e[i]; return x; }

  // Simple feedback-comb room, so dry clicks sound like they happen in a space.
  function room(x, sr, mix = 0.3, time = 0.9) {
    const out = new Float32Array(x.length + Math.floor(time * sr));
    out.set(x);
    const delays = [0.0297, 0.0371, 0.0411, 0.0437].map((d) => Math.floor(d * sr));
    const fb = Math.pow(0.001, 0.035 / time);
    for (const d of delays) {
      const buf = new Float32Array(out.length);
      for (let i = 0; i < out.length; i++) buf[i] = (i < x.length ? x[i] : 0) + (i >= d ? buf[i - d] * fb : 0);
      for (let i = 0; i < out.length; i++) out[i] += buf[i] * mix / delays.length;
    }
    return lowpass(out, sr, 5000);
  }

  return {
    fire(sr) {
      const n = Math.floor(7 * sr);
      const x = lowpass(brown(n), sr, 500);
      for (let i = 0; i < x.length; i++) x[i] *= 0.5;
      const pops = Math.floor(7 * rnd(9, 13));
      for (let p = 0; p < pops; p++) {
        const len = Math.floor(rnd(0.002, 0.012) * sr);
        const burst = highpass(mul(noise(len), decay(len, sr, rnd(0.001, 0.004))), sr, 1500);
        addAt(x, burst, Math.floor(Math.random() * (n - len)), rnd(0.2, 1.2));
      }
      return normalize(loopable(x, sr, 0.4), 0.6);
    },
    wind(sr) {
      const n = Math.floor(10 * sr), ph = Math.random() * TAU;
      const x = bandpass(noise(n), sr, (i) => 420 + 260 * Math.sin(TAU * 0.11 * i / sr + ph) + 90 * Math.sin(TAU * 0.37 * i / sr), 2.2);
      for (let i = 0; i < n; i++) {
        const t = i / sr;
        x[i] *= 0.45 + 0.35 * Math.sin(TAU * 0.07 * t + ph) + 0.2 * Math.sin(TAU * 0.23 * t);
      }
      return normalize(loopable(x, sr, 1.5), 0.6);
    },
    water(sr) {
      const n = Math.floor(10 * sr);
      const body = lowpass(brown(n), sr, 700);
      const hiss = bandpass(noise(n), sr, 1800, 0.7);
      const x = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const t = i / sr;
        const w = Math.pow(Math.max(0, Math.sin(TAU * t / 3.4)), 2) * 0.7 + Math.pow(Math.max(0, Math.sin(TAU * t / 5.1 + 1)), 3) * 0.5;
        x[i] = body[i] * (0.35 + w) + hiss[i] * w * 0.25;
      }
      return normalize(loopable(x, sr, 1.5), 0.6);
    },
    creak(sr) {
      const dur = 1.5, n = Math.floor(dur * sr), x = new Float32Array(n);
      let phase = 0;
      for (let i = 0; i < n; i++) {
        const t = i / sr, f = 55 + 70 * Math.sin(Math.PI * t / dur) + rnd(-6, 6);
        phase += f / sr;
        if (phase >= 1) { phase -= 1; x[i] = rnd(0.6, 1); }
      }
      const a = bandpass(x.slice(), sr, 520, 9), b = bandpass(x.slice(), sr, 1250, 7), c = bandpass(x, sr, 2600, 6);
      for (let i = 0; i < n; i++) {
        const env = Math.sin(Math.PI * i / n) ** 0.7;
        a[i] = (a[i] + 0.6 * b[i] + 0.3 * c[i]) * env;
      }
      return normalize(room(a, sr, 0.25, 0.6), 0.85);
    },
    door(sr) {
      const n = Math.floor(0.9 * sr), x = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const t = i / sr;
        x[i] = Math.sin(TAU * (48 + 30 * Math.exp(-t * 20)) * t) * Math.exp(-t * 7) * 0.9;
      }
      addAt(x, mul(lowpass(noise(Math.floor(0.3 * sr)), sr, 400), decay(Math.floor(0.3 * sr), sr, 0.06)), 0, 0.8);
      const latch = highpass(mul(noise(Math.floor(0.03 * sr)), decay(Math.floor(0.03 * sr), sr, 0.004)), sr, 2500);
      addAt(x, latch, Math.floor(0.12 * sr), 0.5);
      return normalize(room(x, sr, 0.5, 1.4), 0.9);
    },
    footsteps(sr) {
      const n = Math.floor(3 * sr), x = new Float32Array(n);
      [0.05, 0.75, 1.45, 2.15].forEach((s, k) => {
        const len = Math.floor(0.25 * sr);
        const thud = mul(lowpass(noise(len), sr, rnd(220, 320)), decay(len, sr, 0.045));
        for (let i = 0; i < len; i++) thud[i] += Math.sin(TAU * 75 * i / sr) * Math.exp(-i / (0.03 * sr)) * 0.5;
        addAt(x, thud, Math.floor(s * sr), (k % 2 ? 0.8 : 1) * rnd(0.85, 1));
        const scuff = mul(bandpass(noise(len), sr, 900, 1), decay(len, sr, 0.02));
        addAt(x, scuff, Math.floor((s + 0.03) * sr), 0.15);
      });
      return normalize(room(x, sr, 0.35, 0.9), 0.85);
    },
    bell(sr) {
      const dur = 6.5, n = Math.floor(dur * sr), x = new Float32Array(n), base = 196;
      const partials = [[0.5, 0.6, 4.5], [1, 1, 3.2], [1.183, 0.7, 2.6], [1.506, 0.5, 2], [2, 0.45, 1.6], [2.514, 0.3, 1.2], [2.662, 0.25, 1], [3.011, 0.2, 0.8], [4.166, 0.12, 0.5]];
      for (const [r, a, tau] of partials) {
        const f = base * r * rnd(0.998, 1.002);
        for (let i = 0; i < n; i++) x[i] += a * Math.sin(TAU * f * i / sr) * Math.exp(-i / (tau * sr));
      }
      for (let i = 0; i < Math.floor(0.004 * sr); i++) x[i] *= i / (0.004 * sr);
      return normalize(room(lowpass(x, sr, 2200), sr, 0.4, 2), 0.75);
    },
    whisper(sr) {
      const dur = 2.6, n = Math.floor(dur * sr);
      const src = highpass(noise(n), sr, 500);
      const f1 = bandpass(src.slice(), sr, (i) => 700 + 300 * Math.sin(TAU * 3.1 * i / sr), 5);
      const f2 = bandpass(src.slice(), sr, (i) => 1900 + 500 * Math.sin(TAU * 4.3 * i / sr + 1), 6);
      const f3 = bandpass(src, sr, 3800, 3);
      const x = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const t = i / sr;
        const syll = Math.max(0, Math.sin(TAU * 2.6 * t + Math.sin(TAU * 0.9 * t))) ** 1.5;
        const env = Math.sin(Math.PI * t / dur) * syll;
        x[i] = (f1[i] + 0.8 * f2[i] + 0.5 * f3[i]) * env;
      }
      return normalize(room(x, sr, 0.3, 1), 0.5);
    },
    knock(sr) {
      const n = Math.floor(1.4 * sr), x = new Float32Array(n);
      [0.02, 0.36, 0.7].forEach((s) => {
        const len = Math.floor(0.2 * sr);
        const imp = new Float32Array(len); imp[0] = 1; imp[1] = -0.6;
        const a = bandpass(imp.slice(), sr, 190, 12), b = bandpass(imp.slice(), sr, 430, 14), c = bandpass(imp, sr, 1100, 8);
        for (let i = 0; i < len; i++) a[i] = (a[i] + 0.7 * b[i] + 0.3 * c[i]) * Math.exp(-i / (0.05 * sr));
        addAt(x, a, Math.floor(s * sr), rnd(0.9, 1));
      });
      return normalize(room(x, sr, 0.45, 1.1), 0.9);
    },
    crow(sr) {
      const n = Math.floor(2.2 * sr), x = new Float32Array(n);
      [0.05, 0.6, 1.2].forEach((s, k) => {
        const len = Math.floor(rnd(0.3, 0.4) * sr), caw = new Float32Array(len);
        let ph = 0; const f0 = rnd(560, 640) - k * 25;
        for (let i = 0; i < len; i++) {
          const t = i / len, f = f0 * (1.1 - 0.35 * t) + rnd(-25, 25);
          ph += f / sr; ph -= Math.floor(ph);
          caw[i] = (2 * ph - 1) * 0.7 + (Math.random() * 2 - 1) * 0.35;
          caw[i] *= Math.min(1, t * 12) * Math.pow(1 - t, 0.6);
        }
        const shaped = bandpass(caw.slice(), sr, 1400, 2.2);
        const nasal = bandpass(caw, sr, 2600, 4);
        for (let i = 0; i < len; i++) shaped[i] += nasal[i] * 0.5;
        addAt(x, shaped, Math.floor(s * sr), k === 2 ? 0.8 : 1);
      });
      return normalize(room(x, sr, 0.35, 1.6), 0.7);
    },
    chains(sr) {
      const n = Math.floor(1.8 * sr), x = new Float32Array(n);
      for (let k = 0; k < 34; k++) {
        const s = Math.pow(Math.random(), 1.3) * 1.4, len = Math.floor(0.08 * sr), clink = new Float32Array(len);
        const fs = [rnd(2200, 3200), rnd(3800, 5200), rnd(6000, 7800)];
        for (let i = 0; i < len; i++) {
          const e = Math.exp(-i / (rnd(0.012, 0.03) * sr));
          clink[i] = (Math.sin(TAU * fs[0] * i / sr) + 0.6 * Math.sin(TAU * fs[1] * i / sr) + 0.3 * Math.sin(TAU * fs[2] * i / sr)) * e;
        }
        addAt(x, clink, Math.floor(s * sr), rnd(0.2, 1));
      }
      const rattle = mul(bandpass(noise(n), sr, 3500, 1.5), decay(n, sr, 0.5));
      for (let i = 0; i < n; i++) x[i] += rattle[i] * 0.15;
      return normalize(room(x, sr, 0.3, 1), 0.6);
    },
    heartbeat(sr) {
      const n = Math.floor(3.4 * sr), x = new Float32Array(n);
      const beat = (amp, f) => {
        const len = Math.floor(0.22 * sr), b = new Float32Array(len);
        for (let i = 0; i < len; i++) {
          const t = i / sr;
          b[i] = Math.sin(TAU * (f + 25 * Math.exp(-t * 30)) * t) * Math.exp(-t * 22) * Math.min(1, t * 300) * amp;
        }
        return b;
      };
      [0.05, 1.1, 2.15].forEach((s) => {
        addAt(x, beat(1, 48), Math.floor(s * sr));
        addAt(x, beat(0.7, 42), Math.floor((s + 0.3) * sr));
      });
      return normalize(lowpass(x, sr, 300), 0.95);
    },
  };
})();
