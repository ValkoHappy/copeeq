(function () {
  const S = '#1F4EF5', L = '#A9BEFF', F = '#F6F8FF', B = '#EAF0FF', W = '#FFFFFF';
  const G = { S: '#8F95A6', L: '#CDD1DB', F: '#F5F5F7', B: '#EEEFF2' };
  const BADGE = { blue: '#1F4EF5', green: '#16A34A', red: '#E5484D', orange: '#E8742E', excel: '#16824A', pdf: '#E5484D', ppt: '#E8742E', word: '#1F4EF5' };

  const blob = c => `<circle cx="32" cy="32" r="27" fill="${c}"/>`;
  const sparks = c => `<g data-sp="1" stroke="${c}" stroke-width="2.4" stroke-linecap="round"><path d="M52.5 5l-2 4"/><path d="M59 11.5l-4 1.8"/></g>`;
  const doc = (c, l, f, lines) => `<path d="M17 9h19l11 11v31a3 3 0 0 1-3 3H17a3 3 0 0 1-3-3V12a3 3 0 0 1 3-3z" fill="${f}" stroke="${c}" stroke-width="3.2" stroke-linejoin="round"/><path d="M36 9v11h11" fill="none" stroke="${c}" stroke-width="3.2" stroke-linejoin="round"/>` + (lines === false ? '' : `<g stroke="${l}" stroke-width="3" stroke-linecap="round"><path d="M20 27h13"/><path d="M20 33h17"/><path d="M20 39h10"/></g>`);
  const docBack = c => `<path d="M11 15V8a3 3 0 0 1 3-3h17" fill="none" stroke="${c}" stroke-width="3" stroke-linecap="round"/>`;
  const badge = (col, inner) => `<circle cx="46" cy="46" r="12" fill="${col}" stroke="#fff" stroke-width="3"/>` + inner;
  const bPlus = `<path d="M40.5 46h11M46 40.5v11" stroke="#fff" stroke-width="3.2" stroke-linecap="round"/>`;
  const bCheck = `<path d="M40.5 46.5l3.8 3.8 7.4-7.6" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>`;
  const bBolt = `<path d="M47.6 38.5l-6.4 9h4.6l-1.4 7 6.4-9.2h-4.7z" fill="#fff"/>`;
  const bBang = `<path d="M46 40v7.5" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/><circle cx="46" cy="52" r="2" fill="#fff"/>`;
  const bStar = `<path d="M46 39.5l2 4.3 4.6.5-3.4 3.1 1 4.6-4.2-2.4-4.2 2.4 1-4.6-3.4-3.1 4.6-.5z" fill="#fff"/>`;
  const bText = (t, size) => `<text x="46" y="${46 + size * 0.36}" text-anchor="middle" font-family="Manrope,Arial,Helvetica,sans-serif" font-weight="800" font-size="${size}" fill="#fff">${t}</text>`;
  const sq = (col, inner) => `<rect x="34" y="34" width="24" height="24" rx="6" fill="${col}" stroke="#fff" stroke-width="3"/>` + inner;
  const st = (c, w) => `fill="none" stroke="${c}" stroke-width="${((w || 3.2) * 1.12).toFixed(2)}" stroke-linecap="round" stroke-linejoin="round"`;

  const coinFace = (cx, cy, r, face, edge, ring, bolt) => `<circle cx="${cx + r * 0.16}" cy="${cy + r * 0.2}" r="${r}" fill="${edge}"/><circle cx="${cx}" cy="${cy}" r="${r}" fill="${face}"/><circle cx="${cx}" cy="${cy}" r="${r * 0.72}" fill="none" stroke="${ring}" stroke-width="${Math.max(1.6, r * 0.09)}"/>` + (bolt ? `<path transform="translate(${cx} ${cy}) scale(${r / 18})" d="M2.6-10.5L-7 2.2h6.2L-2.6 10.5 7-2.4H.8z" fill="#fff"/>` : '');
  const coinPal = { face: S, edge: '#0A2BC4', ring: '#7C9BFF', back: '#B9CBFF', backEdge: '#8DA8FF' };
  const coinGray = { face: '#A7ACBA', edge: '#7D8395', ring: '#C9CDD7', back: '#DADDE4', backEdge: '#C4C8D2' };

  const LIB = {
    credits: c => blob(c.B) + doc(c.S, c.L, c.F) + badge(c.badge || BADGE.blue, bBolt) + sparks(c.S),
    newdoc: c => blob(c.B) + doc(c.S, c.L, c.F) + badge(c.badge || BADGE.blue, bPlus) + sparks(c.S),
    docs: c => blob(c.B) + `<path d="M8 19a4 4 0 0 1 4-4h11l5 5h24a4 4 0 0 1 4 4v24a4 4 0 0 1-4 4H12a4 4 0 0 1-4-4z" fill="${c.F}" stroke="${c.S}" stroke-width="3.2" stroke-linejoin="round"/><path d="M8 28a3 3 0 0 1 3-3h42a3 3 0 0 1 3 3v20a4 4 0 0 1-4 4H12a4 4 0 0 1-4-4z" fill="${c.S}"/><path d="M15 33h14" stroke="#fff" stroke-opacity=".55" stroke-width="3" stroke-linecap="round"/>` + sparks(c.S),
    templates: c => blob(c.B) + doc(c.S, c.L, c.F) + sq(c.badge || BADGE.blue, bStar.replace(/46/g, '46')) + sparks(c.S),
    history: c => blob(c.B) + `<circle cx="33" cy="32" r="18" fill="${c.F}"/><path d="M15.5 27A18 18 0 1 1 19 43" ${st(c.S, 3.4)}/><path d="M13 19l2.5 8.5 8.4-2.6" ${st(c.S, 3.4)}/><path d="M33 22v11l7 4" ${st(c.S, 3.4)}/>`,
    trash: c => blob(c.B) + `<path d="M19 21h26l-2.6 30a3 3 0 0 1-3 2.8H24.6a3 3 0 0 1-3-2.8z" fill="${c.F}" stroke="${c.S}" stroke-width="3.2" stroke-linejoin="round"/><path d="M14 21h36M26 21v-6h12v6" ${st(c.S)}/><path d="M28 29v17M36 29v17" ${st(c.L, 3)}/>` + sparks(c.S),
    search: c => blob(c.B) + `<circle cx="28" cy="28" r="14" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><path d="M21 25a8 8 0 0 1 6-5" ${st(c.L, 3)}/><path d="M39 39l11 11" ${st(c.S, 6)}/>` + sparks(c.S),
    settings: c => blob(c.B) + `<g ${st(c.S, 5.2)}><path d="M32 11v4"/><path d="M32 49v4"/><path d="M11 32h4"/><path d="M49 32h4"/><path d="M17.2 17.2l2.8 2.8"/><path d="M44 44l2.8 2.8"/><path d="M46.8 17.2L44 20"/><path d="M20 44l-2.8 2.8"/></g><circle cx="32" cy="32" r="15" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><circle cx="32" cy="32" r="6" fill="none" stroke="${c.S}" stroke-width="3.4"/>` + sparks(c.S),
    profile: c => blob(c.B) + `<circle cx="32" cy="23" r="10" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><path d="M14 53c1.5-10 8.5-15.5 18-15.5S48.5 43 50 53z" fill="${c.F}" stroke="${c.S}" stroke-width="3.4" stroke-linejoin="round"/>` + sparks(c.S),
    security: c => blob(c.B) + `<path d="M32 8l18 7v13c0 13-7.5 22-18 27-10.5-5-18-14-18-27V15z" fill="${c.F}" stroke="${c.S}" stroke-width="3.4" stroke-linejoin="round"/><path d="M24.5 31.5l5.5 5.5 10-10.5" ${st(c.S, 3.6)}/>` + sparks(c.S),
    word: c => blob(c.B) + doc(c.S, c.L, c.F) + sq(BADGE.word, bText('W', 15)),
    excel: c => blob(c.B) + doc(c.S, c.L, c.F) + sq(BADGE.excel, bText('X', 15)),
    ppt: c => blob(c.B) + doc(c.S, c.L, c.F) + sq(BADGE.ppt, bText('P', 15)),
    pdf: c => blob(c.B) + doc(c.S, c.L, c.F) + `<rect x="30" y="37" width="28" height="18" rx="5" fill="${BADGE.pdf}" stroke="#fff" stroke-width="3"/>` + `<text x="44" y="49.5" text-anchor="middle" font-family="Manrope,Arial,Helvetica,sans-serif" font-weight="800" font-size="10.5" fill="#fff">PDF</text>`,
    image: c => blob(c.B) + `<rect x="9" y="14" width="46" height="36" rx="5" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><path d="M14 45l11-11 8 8 6-6 11 9z" fill="${c.S}"/><circle cx="40" cy="25" r="4.5" fill="${c.L}"/>`,
    forms: c => blob(c.B) + `<rect x="15" y="9" width="34" height="46" rx="4" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><g stroke="${c.L}" stroke-width="3" stroke-linecap="round"><path d="M21 19h18"/><path d="M21 26h22"/><path d="M21 33h14"/></g><path d="M21 44h10M35 44h8" ${st(c.S, 3)}/>`,
    process: c => blob(c.B) + `<path d="M32 10v25" ${st(c.S, 3.6)}/><path d="M22.5 26l9.5 9.5 9.5-9.5" ${st(c.S, 3.6)}/><path d="M13 37v9a5 5 0 0 0 5 5h28a5 5 0 0 0 5-5v-9" ${st(c.S, 3.6)}/>` + sparks(c.S),
    upload: c => blob(c.B) + `<path d="M32 36V11" ${st(c.S, 3.6)}/><path d="M22.5 20.5L32 11l9.5 9.5" ${st(c.S, 3.6)}/><path d="M13 37v9a5 5 0 0 0 5 5h28a5 5 0 0 0 5-5v-9" ${st(c.S, 3.6)}/>` + sparks(c.S),
    convert: c => blob(c.B) + `<path d="M17.9 26.9A15 15 0 0 1 43.5 22.4" ${st(c.S, 3.6)}/><path d="M36.2 20.7L43.5 22.4L43 14.9" ${st(c.S, 3.6)}/><path d="M46.1 37.1A15 15 0 0 1 20.5 41.6" ${st(c.S, 3.6)}/><path d="M27.8 43.3L20.5 41.6L21 49.1" ${st(c.S, 3.6)}/>`,
    star: c => blob(c.B) + `<path d="M32 10l6.6 13.6 15 2-11 10.4 2.8 14.8L32 43.6l-13.4 7.2 2.8-14.8-11-10.4 15-2z" fill="${c.S}" stroke="${c.S}" stroke-width="2" stroke-linejoin="round"/>` + sparks(c.S),
    bell: c => blob(c.B) + `<path d="M19 42V29a13 13 0 0 1 26 0v13l4 4.5H15z" fill="${c.F}" stroke="${c.S}" stroke-width="3.4" stroke-linejoin="round"/><path d="M27.5 50.5a4.6 4.6 0 0 0 9 0" ${st(c.S, 3.4)}/><path d="M32 12.5v3" ${st(c.S, 3.4)}/>` + sparks(c.S),
    support: c => blob(c.B) + `<path d="M32 12c12.2 0 21 7.4 21 17s-8.8 17-21 17c-2.6 0-5-.3-7.3-1L15 51l2.6-9.2C13.5 38.8 11 34.2 11 29c0-9.6 8.8-17 21-17z" fill="${c.F}" stroke="${c.S}" stroke-width="3.4" stroke-linejoin="round"/><path d="M27 25a5 5 0 1 1 7.4 4.4c-1.6.9-2.4 1.9-2.4 3.6" ${st(c.S, 3.4)}/><circle cx="32" cy="39" r="2.2" fill="${c.S}"/>`,
    logout: c => blob(c.B) + `<path d="M31 13H17a3 3 0 0 0-3 3v32a3 3 0 0 0 3 3h14" ${st(c.S, 3.6)}/><path d="M26 32h25" ${st(c.S, 3.6)}/><path d="M43 24l8 8-8 8" ${st(c.S, 3.6)}/>` + sparks(c.S),
    pages: c => blob(c.B) + doc(c.S, c.L, c.F) + sq(c.badge || BADGE.blue, bText('3', 15)),
    tariff: c => blob(c.B) + `<path d="M35 9h15a3 3 0 0 1 3 3v15L29.5 50.5a4 4 0 0 1-5.6 0L12.5 39a4 4 0 0 1 0-5.6z" fill="${c.F}" stroke="${c.S}" stroke-width="3.4" stroke-linejoin="round"/><circle cx="43" cy="19" r="3.4" fill="${c.S}"/><path d="M24 36l7-7" ${st(c.L, 3)}/>`,
    loading: c => blob(c.B) + doc(c.S, c.L, c.F) + `<circle cx="46" cy="46" r="12" fill="#fff"/><path d="M46 36a10 10 0 1 1-10 10" ${st(c.S, 3.4)}/><path d="M36 46a10 10 0 0 1 10-10" ${st(c.L, 3.4)}/>`,
    done: c => blob(c.B) + `<circle cx="32" cy="32" r="19" fill="${c.badge || BADGE.blue}"/><path d="M23.5 32.5l6 6 11-11.5" ${st('#fff', 4)}/>` + sparks(c.S),
    editor: c => blob(c.B) + `<rect x="9" y="12" width="42" height="36" rx="5" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><path d="M9 21h42" ${st(c.S, 3)}/><circle cx="15" cy="16.5" r="1.6" fill="${c.S}"/><circle cx="20" cy="16.5" r="1.6" fill="${c.S}"/><path d="M15 29h14M15 35h9" ${st(c.L, 3)}/><path d="M52 27l5 5-17 17-7 2 2-7z" fill="${c.S}" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/>`,
    compare: c => blob(c.B) + `<rect x="7" y="14" width="22" height="30" rx="3" fill="${c.F}" stroke="${c.S}" stroke-width="3"/><rect x="35" y="14" width="22" height="30" rx="3" fill="${c.F}" stroke="${c.S}" stroke-width="3"/><g stroke="${c.L}" stroke-width="2.6" stroke-linecap="round"><path d="M11 22h12M11 28h14M11 34h9M39 22h12M39 28h14M39 34h9"/></g><path d="M27 50h10M33 46l4 4-4 4" ${st(c.S, 3)}/>`,
    download: c => blob(c.B) + `<path d="M32 9v26" ${st(c.S, 3.6)}/><path d="M22.5 25.5L32 35l9.5-9.5" ${st(c.S, 3.6)}/><path d="M12 38v8a5 5 0 0 0 5 5h30a5 5 0 0 0 5-5v-8" ${st(c.S, 3.6)}/>` + sparks(c.S),
    success: c => blob(c.B) + doc(c.S, c.L, c.F) + badge(BADGE.green, bCheck),
    error: c => blob(c.B) + doc(c.S, c.L, c.F) + badge(BADGE.red, bBang),
    pending: c => blob(c.B) + `<circle cx="32" cy="32" r="18" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><path d="M32 22v10l7 4" ${st(c.S, 3.4)}/>`,
    recent: c => blob(c.B) + `<path d="M8 19a4 4 0 0 1 4-4h11l5 5h22a4 4 0 0 1 4 4v20a4 4 0 0 1-4 4H12a4 4 0 0 1-4-4z" fill="${c.S}"/><circle cx="44" cy="44" r="12" fill="#fff" stroke="${c.S}" stroke-width="3.2"/><path d="M44 38v6.5l4 2.3" ${st(c.S, 3)}/>` + sparks(c.S),
    topup: c => blob(c.B) + `<rect x="8" y="16" width="42" height="30" rx="5" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><path d="M8 25h42" stroke="${c.S}" stroke-width="5"/><path d="M14 36h12" ${st(c.L, 3)}/>` + badge(c.badge || BADGE.blue, bPlus),
    dashboard: c => blob(c.B) + `<rect x="12" y="12" width="17" height="17" rx="4" fill="${c.S}"/><rect x="35" y="12" width="17" height="17" rx="4" fill="${c.F}" stroke="${c.S}" stroke-width="3"/><rect x="12" y="35" width="17" height="17" rx="4" fill="${c.F}" stroke="${c.S}" stroke-width="3"/><rect x="35" y="35" width="17" height="17" rx="4" fill="${c.F}" stroke="${c.S}" stroke-width="3"/>` + sparks(c.S),
    business: c => blob(c.B) + `<rect x="10" y="20" width="44" height="30" rx="5" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><path d="M24 20v-5a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v5" ${st(c.S, 3.4)}/><path d="M10 32h44" ${st(c.S, 3)}/><rect x="28" y="28" width="8" height="8" rx="2" fill="${c.S}"/>` + sparks(c.S),
    clean: c => blob(c.B) + doc(c.S, c.L, c.F) + `<path d="M46 34l2.6 6.4L55 43l-6.4 2.6L46 52l-2.6-6.4L37 43l6.4-2.6z" fill="${c.badge || BADGE.blue}" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/>`,
    camera: c => blob(c.B) + `<path d="M10 23a4 4 0 0 1 4-4h7l4-5h14l4 5h7a4 4 0 0 1 4 4v22a4 4 0 0 1-4 4H14a4 4 0 0 1-4-4z" fill="${c.F}" stroke="${c.S}" stroke-width="3.4" stroke-linejoin="round"/><circle cx="32" cy="33" r="8.5" fill="none" stroke="${c.S}" stroke-width="3.4"/>` + sparks(c.S),
    scan: c => blob(c.B) + doc(c.S, c.L, c.F) + `<path d="M8 33h48" stroke="${c.badge || BADGE.blue}" stroke-width="3.4" stroke-linecap="round"/>`,
    coin: (c, o) => { const p = o.gray ? coinGray : coinPal; return (o.bare ? '' : blob(o.gray ? G.B : B)) + coinFace(36, 34, 15, p.back, p.backEdge, p.back, false) + coinFace(28, 28, 18, p.face, p.edge, p.ring, true) + (o.low ? `<circle cx="47" cy="47" r="9" fill="${BADGE.orange}" stroke="#fff" stroke-width="3"/><path d="M47 42.5v5" stroke="#fff" stroke-width="3" stroke-linecap="round"/><circle cx="47" cy="51.2" r="1.6" fill="#fff"/>` : ''); },
    coin1: (c, o) => { const p = o.gray ? coinGray : o.white ? { face: '#fff', edge: '#C9D6FF', ring: '#D4DFFF', back: '', backEdge: '' } : coinPal; const s = coinFace(30, 30, 22, p.face, p.edge, p.ring, true); return o.white ? s.replace('fill="#fff"/>', 'fill="#1F4EF5"/>') : s; },
  };

  const CSS = `<style>.fb{transform-box:fill-box;transform-origin:center}
@keyframes bobD{0%,100%{transform:translateY(-2px)}50%{transform:translateY(3px)}}
@keyframes bobU{0%,100%{transform:translateY(2px)}50%{transform:translateY(-3px)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes draw{from{stroke-dashoffset:30}to{stroke-dashoffset:0}}
@keyframes pop{0%{transform:scale(.4);opacity:0}60%{transform:scale(1.12);opacity:1}100%{transform:scale(1)}}
@keyframes shake{0%,100%{transform:translateX(0)}20%,60%{transform:translateX(-2.5px)}40%,80%{transform:translateX(2.5px)}}
@keyframes swing{0%,100%{transform:rotate(0)}20%{transform:rotate(14deg)}40%{transform:rotate(-10deg)}60%{transform:rotate(6deg)}80%{transform:rotate(-3deg)}}
@keyframes flip{0%,100%{transform:scaleX(1)}50%{transform:scaleX(.08)}}
@keyframes bounce{0%,100%{transform:translateY(0)}35%{transform:translateY(-6px)}65%{transform:translateY(1px)}}
@keyframes tw{0%,100%{opacity:1}50%{opacity:.15}}
@keyframes floatC{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
@keyframes floatB{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.5px)}}
@keyframes coinDrop{0%{transform:translateY(-18px);opacity:0}30%{opacity:1}55%{transform:translateY(0)}66%{transform:translateY(-3px)}76%,100%{transform:translateY(0);opacity:1}}
@keyframes dropIn{0%{transform:translateY(-14px);opacity:0}70%{transform:translateY(2px);opacity:1}100%{transform:translateY(0)}}
</style>`;
  const once = o => (o.loop ? 'infinite' : '1 both');
  const ANIM = {
    upload: (c, o) => blob(c.B) + `<g style="animation:bobU 1.3s ease-in-out infinite"><path d="M32 36V11" ${st(c.S, 3.6)}/><path d="M22.5 20.5L32 11l9.5 9.5" ${st(c.S, 3.6)}/></g><path d="M13 37v9a5 5 0 0 0 5 5h28a5 5 0 0 0 5-5v-9" ${st(c.S, 3.6)}/>` + sparksA(c.S),
    download: (c, o) => blob(c.B) + `<g style="animation:bobD 1.3s ease-in-out ${o.loop === false ? '2' : 'infinite'}"><path d="M32 9v26" ${st(c.S, 3.6)}/><path d="M22.5 25.5L32 35l9.5-9.5" ${st(c.S, 3.6)}/></g><path d="M12 38v8a5 5 0 0 0 5 5h30a5 5 0 0 0 5-5v-8" ${st(c.S, 3.6)}/>` + sparksA(c.S),
    process: (c, o) => ANIM.download(c, o),
    loading: c => blob(c.B) + doc(c.S, c.L, c.F) + `<circle cx="46" cy="46" r="12" fill="#fff"/><circle cx="46" cy="46" r="10" ${st(c.L, 3.4)}/><g class="fb" style="animation:spin .9s linear infinite"><path d="M46 36a10 10 0 0 1 10 10" ${st(c.S, 3.4)}/><circle cx="46" cy="46" r="11.7" fill="none"/></g>`,
    pending: c => blob(c.B) + `<circle cx="32" cy="32" r="18" fill="${c.F}" stroke="${c.S}" stroke-width="3.4"/><g style="transform-origin:32px 32px;animation:spin 3s linear infinite"><path d="M32 32V21" ${st(c.S, 3.4)}/></g><path d="M32 32l6 3.5" ${st(c.S, 3.4)}/><circle cx="32" cy="32" r="2.4" fill="${c.S}"/>`,
    convert: c => blob(c.B) + `<g style="transform-origin:32px 32px;animation:spin 2.4s linear infinite"><path d="M17.9 26.9A15 15 0 0 1 43.5 22.4" ${st(c.S, 3.6)}/><path d="M36.2 20.7L43.5 22.4L43 14.9" ${st(c.S, 3.6)}/><path d="M46.1 37.1A15 15 0 0 1 20.5 41.6" ${st(c.S, 3.6)}/><path d="M27.8 43.3L20.5 41.6L21 49.1" ${st(c.S, 3.6)}/></g>`,
    done: (c, o) => blob(c.B) + `<circle class="fb" cx="32" cy="32" r="19" fill="${BADGE.blue}" style="animation:pop .5s cubic-bezier(.3,1.4,.5,1) ${once(o)}"/><path d="M23.5 32.5l6 6 11-11.5" ${st('#fff', 4)} stroke-dasharray="30" style="animation:draw .45s .35s ease-out ${once(o)};stroke-dashoffset:30"/>` + sparksA(c.S),
    success: (c, o) => blob(c.B) + doc(c.S, c.L, c.F) + `<g class="fb" style="animation:pop .5s .1s cubic-bezier(.3,1.4,.5,1) ${once(o)}"><circle cx="46" cy="46" r="12" fill="${BADGE.green}" stroke="#fff" stroke-width="3"/></g><path d="M40.5 46.5l3.8 3.8 7.4-7.6" ${st('#fff', 3.2)} stroke-dasharray="30" style="animation:draw .4s .45s ease-out ${once(o)};stroke-dashoffset:30"/>`,
    error: (c, o) => blob(c.B) + `<g style="animation:shake .5s .15s ease-in-out ${o.loop ? 'infinite' : '2'}">` + doc(c.S, c.L, c.F) + badge(BADGE.red, bBang) + `</g>`,
    bell: (c, o) => blob(c.B) + `<g style="transform-origin:32px 12px;animation:swing 1.1s ease-in-out ${o.loop ? 'infinite' : '2'}"><path d="M19 42V29a13 13 0 0 1 26 0v13l4 4.5H15z" fill="${c.F}" stroke="${c.S}" stroke-width="3.4" stroke-linejoin="round"/><path d="M27.5 50.5a4.6 4.6 0 0 0 9 0" ${st(c.S, 3.4)}/></g><path d="M32 12.5v3" ${st(c.S, 3.4)}/>` + sparksA(c.S),
    credits: (c, o) => blob(c.B) + doc(c.S, c.L, c.F) + `<g class="fb" style="animation:pop .5s cubic-bezier(.3,1.4,.5,1) ${once(o)}">` + badge(BADGE.blue, bBolt) + `</g>` + sparksA(c.S),
    newdoc: (c, o) => blob(c.B) + `<g style="animation:dropIn .55s ease-out ${once(o)}">` + doc(c.S, c.L, c.F) + `</g><g class="fb" style="animation:pop .45s .4s cubic-bezier(.3,1.4,.5,1) ${once(o)}">` + badge(BADGE.blue, bPlus) + `</g>` + sparksA(c.S),
    coin: (c, o) => { const p = o.gray ? coinGray : coinPal; const sp = o.anim === 'spin'; const mode = sp ? 'floatC 1.8s ease-in-out infinite' : 'bounce .6s ease-out 1'; return (o.bare ? '' : blob(B)) + (sp ? `<g style="animation:floatB 1.8s .15s ease-in-out infinite">` : '<g>') + coinFace(36, 34, 15, p.back, p.backEdge, p.back, false) + '</g>' + `<g class="fb" style="animation:${mode}">` + coinFace(28, 28, 18, p.face, p.edge, p.ring, true) + `</g>` + (o.low ? `<g class="fb" style="animation:pop .5s cubic-bezier(.3,1.4,.5,1) 1 both"><circle cx="47" cy="47" r="9" fill="${BADGE.orange}" stroke="#fff" stroke-width="3"/><path d="M47 42.5v5" stroke="#fff" stroke-width="3" stroke-linecap="round"/><circle cx="47" cy="51.2" r="1.6" fill="#fff"/></g>` : ''); },
    coin1: (c, o) => { const p = o.white ? { face: '#fff', edge: '#C9D6FF', ring: '#D4DFFF' } : coinPal; let s = coinFace(31, 31, o.anim === 'spin' ? 18 : 22, p.face, p.edge, p.ring, true); if (o.white) s = s.replace('fill="#fff"/>', 'fill="#1F4EF5"/>');
      if (o.anim === 'spin') { const tr = o.white ? 'rgba(255,255,255,.28)' : '#DCE5FF', arc = o.white ? '#fff' : S; return `<circle cx="32" cy="32" r="28" fill="none" stroke="${tr}" stroke-width="4"/><g style="transform-origin:32px 32px;animation:spin 1s linear infinite"><path d="M32 4a28 28 0 0 1 28 28" fill="none" stroke="${arc}" stroke-width="4" stroke-linecap="round"/></g>` + s; }
      return `<g class="fb" style="animation:bounce .6s ease-out 1">` + s + `</g>`; },
  };
  const sparksA = c => `<g data-sp="1" stroke="${c}" stroke-width="2.4" stroke-linecap="round"><path d="M52.5 5l-2 4" style="animation:tw 1.6s ease-in-out infinite"/><path d="M59 11.5l-4 1.8" style="animation:tw 1.6s .5s ease-in-out infinite"/></g>`;

  const DOCSET = ['credits', 'newdoc', 'templates', 'word', 'excel', 'ppt', 'pdf', 'pages', 'loading', 'success', 'error', 'clean', 'scan'];
  function get(name, opt) {
    const o = opt || {}; const g = !!o.gray;
    let c = { S: g ? G.S : S, L: g ? G.L : L, F: g ? G.F : F, B: o.noBlob ? 'none' : (g ? G.B : B), badge: o.badge ? (BADGE[o.badge] || o.badge) : (g ? G.S : null) };
    if (o.onDark && !/^coin/.test(name)) c = { S: '#FFFFFF', L: '#B9CBFF', F: 'rgba(255,255,255,.16)', B: o.noBlob ? 'none' : 'rgba(255,255,255,.14)', badge: '#0B1024' };
    const animated = !!o.anim && ANIM[name];
    const fn = animated ? ANIM[name] : (LIB[name] || LIB.newdoc);
    let inner = fn(c, o); const bl = blob(c.B);
    if (inner.startsWith(bl) && c.B !== 'none' || (o.noBlob && !/^coin/.test(name))) {
      let rest = inner.startsWith(bl) ? inner.slice(bl.length) : inner; const sp = [];
      rest = rest.replace(/<g data-sp="1"[\s\S]*?<\/g><\/g>|<g data-sp="1"[^>]*>(?:<path[^>]*\/>)+<\/g>/g, m => { sp.push(m); return ''; });
      const dx = DOCSET.includes(name) ? -4 : 0; const k = c.B === 'none' ? 0.92 : 0.8;
      inner = (inner.startsWith(bl) ? bl : '') + `<g transform="translate(32 32) scale(${k}) translate(${-32 + dx} -32)">` + rest + '</g>' + sp.join('');
    }
    const body = (animated ? CSS : '') + inner + (o.nonce ? `<!--${o.nonce}-->` : '');
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">${body}</svg>`;
    return o.raw ? svg : 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }
  window.CQI = { get, names: Object.keys(LIB), animated: Object.keys(ANIM) };
})();
