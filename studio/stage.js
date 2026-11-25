/* Stage: draws everything that sits on top of the video (captions, hook, looks) for one moment in time.

   The editor preview and the final render both call Stage.html(), so what you see is what you get.
   It is a pure function of (payload, t): every animation is computed from t, never from CSS transitions
   or timers, which is what lets the renderer capture it frame by frame.

   payload = { plan: {style, total, chunks, looks}, hook, media }   (plan as built by reel.timeline)
   Text fields accept *asterisks* for the accent style and \n for a line break. */
(function () {
  const W = 1080, H = 1920;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const font = f => `font-family:'${String(f || 'Inter').replace(/['"\\;]/g, '')}',Inter,Arial,sans-serif;`;
  // overshoots a little, then settles at 1
  const spring = x => x <= 0 ? 0 : 1 - Math.exp(-6.5 * x) * Math.cos(8.5 * x);
  const SOFT = 'text-shadow:0 2px 5px rgba(0,0,0,.55),0 8px 28px rgba(0,0,0,.45);';

  // enter/exit for a block that lives from start to end: returns {o: opacity, tf: transform}
  function motion(kind, t, start, end) {
    const age = t - start, left = end - t;
    let o = clamp(left / 0.14), tf = '';
    if (kind === 'pop') { o *= clamp(age / 0.07); tf = `scale(${(0.72 + 0.28 * spring(age / 0.34)).toFixed(4)})`; }
    else if (kind === 'rise') { o *= clamp(age / 0.16); tf = `translateY(${((1 - spring(age / 0.4)) * 46).toFixed(2)}px)`; }
    else if (kind === 'fade') o *= clamp(age / 0.18);
    return { o: +o.toFixed(3), tf };
  }

  // "*accent* text\nnext line" -> html, accent segments wrapped in the accent style
  function rich(text, accentCss) {
    return String(text ?? '').split('\n').map(line =>
      line.split(/(\*[^*]+\*)/).filter(Boolean).map(seg =>
        seg.length > 2 && seg[0] === '*' && seg.at(-1) === '*'
          ? `<span style="${accentCss}">${esc(seg.slice(1, -1))}</span>` : esc(seg)).join('')).join('<br>');
  }
  const accentOf = b => (b.accent_font ? font(b.accent_font) : '') + (b.accent_italic ? 'font-style:italic;' : '') +
    (b.accent_color ? `color:${b.accent_color};` : '') + (b.accent_weight ? `font-weight:${b.accent_weight};` : '') +
    (b.accent_scale && b.accent_scale !== 1 ? `font-size:${b.accent_scale}em;line-height:1;` : '');
  // a text block that is either boxed (solid pill behind each line) or plain with a soft shadow
  function textBlock(html, b, extra = '') {
    const base = `${font(b.font)}font-weight:${b.weight ?? 800};font-size:${b.size}px;color:${b.color};` +
      `line-height:${b.line_height ?? 1.18};letter-spacing:${b.letter_spacing ?? 0}em;` + (b.uppercase ? 'text-transform:uppercase;' : b.lowercase ? 'text-transform:lowercase;' : '') + extra;
    return b.box
      ? `<span class="st-box" style="${base}background:${b.box};border-radius:${b.radius ?? 0.22}em">${html}</span>`
      : `<span style="${base}${SOFT}display:inline-block">${html}</span>`;
  }
  const block = (y, inner, m, pad = 80) =>
    `<div class="st-ov" style="top:${y}px;padding:0 ${pad}px;opacity:${m.o}"><div style="transform:translateY(-50%) ${m.tf}">${inner}</div></div>`;

  function captionWord(w, c, t, extra = '') {
    let txt = c.uppercase ? w.w.toUpperCase() : c.lowercase ? w.w.toLowerCase() : w.w;
    if (!c.keep_punctuation) txt = txt.replace(/[.,;:]+$/, '');
    const emph = w.emph || (c.auto_numbers && /[\d$%]/.test(w.w));
    const on = t >= w.os && t < w.oe + 0.02;
    const col = emph ? c.emphasis : on && c.highlight ? c.highlight : c.color;
    const peak = emph ? 1.14 : (c.pop ? (c.active_scale ?? 1.08) : 1);
    const sc = on ? 1 + (peak - 1) * spring((t - w.os) / 0.22) : 1;
    const ef = emph && c.emphasis_font ? font(c.emphasis_font) + (c.emphasis_italic ? 'font-style:italic;' : '') +
      `font-weight:${c.emphasis_weight ?? 600};` : '';
    return { emph, html: `<span class="st-w" style="color:${col};transform:scale(${sc.toFixed(4)});${ef}${extra}">${esc(txt)}</span>` };
  }
  function captionCss(c) {
    const stroke = c.outline_width ? `-webkit-text-stroke:${c.outline_width * 2}px ${c.outline};paint-order:stroke fill;` : '';
    const shadow = c.soft_shadow ? SOFT : c.shadow ? `text-shadow:${c.shadow * 2}px ${c.shadow * 2}px 0 rgba(0,0,0,.5);` : '';
    return `${font(c.font)}font-weight:${c.weight ?? 800};font-size:${c.size}px;letter-spacing:${c.letter_spacing ?? 0}em;` +
      `line-height:${c.line_height ?? 1.16};${stroke}${shadow}`;
  }

  function captions(plan, t) {
    const c = plan.style.caption;
    const chunk = plan.chunks.find(ch => t >= ch[0].os && t < ch.at(-1).oe + 0.15);
    if (!chunk) return { html: '', now: null };
    let now = chunk[0]; chunk.forEach(w => { if (w.os <= t) now = w; });
    let inner;
    if (c.mode === 'stack') {
      // lines of mixed sizes that build up as the words are said; key words get their own, bigger line
      const lines = [];
      chunk.forEach(w => {
        const cw = captionWord(w, c, t, t < w.os ? 'opacity:0;' : `opacity:${clamp((t - w.os) / 0.08).toFixed(2)};`);
        const last = lines.at(-1);
        if (last && last.emph === cw.emph && last.words.length < (cw.emph ? 3 : (c.stack_words ?? 3))) last.words.push(cw.html);
        else lines.push({ emph: cw.emph, words: [cw.html] });
      });
      inner = lines.map(l => `<div style="font-size:${l.emph ? (c.stack_scale ?? 1.7) : 1}em;line-height:1.08">${l.words.join(' ')}</div>`).join('');
    } else {
      inner = chunk.map(w => captionWord(w, c, t).html).join(' ');
    }
    const m = c.animation === 'pop' && chunk.length === 1 ? motion('pop', t, chunk[0].os, 1e9) : { o: 1, tf: '' };
    return { html: block(c.position_y * H, `<div style="${captionCss(c)}">${inner}</div>`, m, 60), now: now.i };
  }

  function hook(payload, t) {
    const hk = payload.plan.style.hook, text = payload.hook;
    const until = hk.duration > 0 ? hk.duration : 1e9;
    if (!text || t >= until) return '';
    return block(hk.position_y * H, textBlock(rich(text, accentOf(hk)), hk), motion(hk.animation ?? 'rise', t, 0, until), 90);
  }

  function look(l, payload, t, words) {
    const L = payload.plan.style.looks, m = k => motion(l.animation ?? k, t, l.start, l.end);
    const F = k => Object.assign({ font: L.font }, L[k]);
    if (l.type === 'headline') {
      const h = F('headline'), y = (l.position_y ?? h.position_y) * H;
      const sub = l.sub ? `<div style="margin-top:${Math.round(h.size * 0.22)}px">${textBlock(rich(l.sub, ''), {
        font: h.sub_font ?? h.font, weight: h.sub_weight ?? 500, size: h.sub_size, color: h.sub_color, box: h.sub_box })}</div>` : '';
      return block(y + (l.sub ? h.size * 0.4 : 0), textBlock(rich(l.text, accentOf(h)), h) + sub, m('rise'));
    }
    if (l.type === 'takeover') {
      const k = F('takeover'), mm = m('fade');
      return `<div class="st-take" style="background:${l.bg || k.bg};opacity:${mm.o}"><div style="transform:${motion('pop', t, l.start, l.end).tf}">` +
        `<div style="${font(k.font)}font-weight:${k.weight ?? 800};font-size:${k.size}px;color:${k.color};line-height:1.08;${k.uppercase ? 'text-transform:uppercase;' : ''}">${rich(l.text, accentOf(k))}</div>` +
        (l.sub ? `<div style="margin-top:44px">${textBlock(rich(l.sub, ''), F('label'))}</div>` : '') + '</div></div>';
    }
    if (l.type === 'bigwords') {
      // the spoken words themselves, one giant word at a time (captions step aside meanwhile)
      const k = F('bigwords'), y = (l.position_y ?? k.position_y) * H;
      const said = words.filter(w => w.i >= l.from && w.i <= (l.to ?? l.from) && w.os <= t);
      const w = said.at(-1); if (!w) return '';
      const txt = (l.text ? null : w.w.replace(/[.,;:!?]+$/, ''));
      return block(y, textBlock(txt != null ? esc(txt) : rich(l.text, accentOf(k)), k), motion('pop', t, l.text ? l.start : w.os, l.end), 40);
    }
    if (l.type === 'label') {
      const k = F('label');
      return block((l.position_y ?? k.position_y) * H, textBlock(rich(l.text, accentOf(k)), k), m('pop'));
    }
    if (l.type === 'step') {
      const k = F('step');
      return `<div class="st-step" style="opacity:${m('fade').o};${font(k.font)}font-weight:${k.weight ?? 700};font-size:${k.size}px;color:${k.color};background:${k.box}">${esc(l.text)}</div>`;
    }
    if (l.type === 'counter') {
      const k = F('counter'), y = (l.position_y ?? k.position_y) * H;
      const ramp = Math.min(k.count_seconds, Math.max(l.end - l.start - 0.3, 0.2));
      const p = clamp((t - l.start) / ramp), v = Math.round((+l.value || 0) * (1 - Math.pow(1 - p, 3)));
      const num = `<div class="st-card" style="background:${k.box};padding:${Math.round(k.size * 0.12)}px ${Math.round(k.size * 0.36)}px ${Math.round(k.size * 0.16)}px">` +
        `<div style="${font(k.font)}font-weight:${k.weight ?? 800};font-size:${k.size}px;color:${k.color};line-height:1.05">${esc((l.prefix || '') + v.toLocaleString('en-US') + (l.suffix || ''))}</div>` +
        (l.text ? `<div style="${font(k.sub_font ?? L.body_font ?? k.font)}font-weight:500;font-size:${k.sub_size}px;color:${k.sub_color};margin-top:4px">${esc(l.text)}</div>` : '') + '</div>';
      return block(y, num, m('pop'));
    }
    if (l.type === 'card') {
      const k = F('card'), y = (l.position_y ?? k.position_y) * H;
      const bullets = (l.bullets || []).map((b, n) => {
        const bm = motion('rise', t, l.start + 0.18 + n * (l.stagger ?? 0.16), l.end);
        return `<div class="st-li" style="opacity:${bm.o};transform:${bm.tf}"><i style="background:${k.accent}"></i><span>${rich(b, `color:${k.accent};font-weight:700;`)}</span></div>`;
      }).join('');
      const inner = `<div class="st-card" style="background:${k.bg};color:${k.color};width:${Math.round((l.width ?? k.width) * W)}px;text-align:left;padding:${k.pad ?? 44}px">` +
        (l.kicker ? `<div style="${font(k.body_font ?? L.body_font)}font-weight:600;font-size:${Math.round(k.size * 0.5)}px;letter-spacing:.08em;text-transform:uppercase;color:${k.accent};margin-bottom:10px">${esc(l.kicker)}</div>` : '') +
        (l.text ? `<div style="${font(k.font)}font-weight:${k.weight ?? 700};font-size:${k.size}px;line-height:1.14">${rich(l.text, accentOf(k))}</div>` : '') +
        (l.sub ? `<div style="${font(k.body_font ?? L.body_font)}font-weight:500;font-size:${Math.round(k.size * 0.62)}px;line-height:1.3;margin-top:14px;opacity:.82">${rich(l.sub, '')}</div>` : '') +
        (bullets ? `<div style="${font(k.body_font ?? L.body_font)}font-weight:500;font-size:${Math.round(k.size * 0.66)}px;margin-top:${l.text ? 22 : 0}px">${bullets}</div>` : '') + '</div>';
      return block(y, inner, m('rise'), 0);
    }
    if (l.type === 'image' && l.file) {
      const k = L.image, mm = m('pop');
      return `<img class="st-img" src="${payload.media}/${encodeURIComponent(l.file)}" style="left:${(l.position_x ?? 0.5) * W}px;top:${(l.position_y ?? k.position_y) * H}px;` +
        `width:${(l.width ?? k.width) * W}px;opacity:${mm.o};transform:translate(-50%,-50%) rotate(${l.tilt ?? 0}deg) ${mm.tf};${l.plain ? 'box-shadow:none;border-radius:0;' : ''}">`;
    }
    return '';
  }

  /* opts.only: 'captions' | 'hook' | 'looks' | a look number -> draw just that part (separate layers);
     opts.cover: the hook alone, fully shown (for the cover image). */
  function html(payload, t, opts = {}) {
    const plan = payload.plan, only = opts.only;
    if (opts.cover) return { html: hook(payload, Math.min(1, (plan.style.hook.duration || 2) / 2)), now: null };
    const words = plan.chunks.flat();
    const active = plan.looks.filter(l => t >= l.start && t <= l.end);
    const big = active.some(l => l.type === 'bigwords' || l.type === 'takeover');
    const cap = captions(plan, t);
    let out = '';
    if ((only == null || only === 'looks' || typeof only === 'number'))
      out += active.filter(l => typeof only !== 'number' || l.n === only).map(l => look(l, payload, t, words)).join('');
    if ((only == null || only === 'captions') && !big) out += cap.html;
    if (only == null || only === 'hook') out += hook(payload, t);
    return { html: out, now: cap.now };
  }

  const CSS = `
.st-ov{position:absolute;left:0;width:100%;text-align:center;pointer-events:none;box-sizing:border-box}
.st-w{display:inline-block;margin:0 .1em;transform-origin:50% 60%}
.st-box{display:inline;padding:.14em .4em;-webkit-box-decoration-break:clone;box-decoration-break:clone}
.st-take{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;padding:90px;box-sizing:border-box}
.st-card{display:inline-block;border-radius:34px;box-shadow:0 18px 50px rgba(0,0,0,.28),0 3px 10px rgba(0,0,0,.18);box-sizing:border-box}
.st-li{display:flex;align-items:flex-start;gap:.6em;margin:.5em 0;line-height:1.25}
.st-li i{flex:none;width:.42em;height:.42em;border-radius:50%;margin-top:.42em}
.st-step{position:absolute;top:110px;right:70px;padding:.3em .8em;border-radius:99px;box-shadow:0 6px 18px rgba(0,0,0,.25)}
.st-img{position:absolute;border-radius:22px;box-shadow:0 18px 50px rgba(0,0,0,.35);pointer-events:none}`;
  function install(doc = document) {
    if (doc.getElementById('stage-css')) return;
    const s = doc.createElement('style'); s.id = 'stage-css'; s.textContent = CSS; doc.head.appendChild(s);
  }

  window.Stage = { html, install, W, H };
})();
