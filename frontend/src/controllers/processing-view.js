import { plural } from "../domain/demo-data.js";
export class ProcessingViewController {
  constructor(store, ui, ports, timers) {
    this.store = store;
    this.ui = ui;
    this.ports = ports;
    this.timers = timers;
  }
  procVals() {
    const st = this.store.state;
    const cur = st.cur;
    if (!cur) return {};
    const p = st.proc;
    const n = cur.pages.length;
    const plan = this.ports.procPlan(cur);
    const t = p.t || 0;
    const clean = st.up.mode === "clean";
    const PH = [
      ["Изучаем фото", "search"],
      [clean ? "Собираем чистовик" : "Переносим в Word", "move_down"],
      ["Сверяем и доделываем", "compare"],
    ].slice(0, plan.ph.length);
    const ps = cur.pages.map((x, j) => this.ports.pageState(plan, j, t));
    let fj = ps.findIndex((s) => s.k >= 0 && s.k < plan.ph.length);
    if (fj < 0) fj = ps.findIndex((s) => s.k < 0);
    if (fj < 0) fj = n - 1;
    if (p.err) fj = p.err.pi;
    const fs = ps[fj];
    const pg = cur.pages[fj] || {};
    const k = Math.max(0, Math.min(fs.k, plan.ph.length - 1));
    const phase = ["study", "transfer", "check"][k];
    const skey = (pg.id || fj) + "-" + phase + "-" + (p.t0 || 0);
    this.stDelay = this.stDelay || {};
    if (this.stDelay[skey] == null)
      this.stDelay[skey] = -(fs.k === k ? fs.pe : 0);
    const d0 = this.stDelay[skey];
    const ds = (x) => (d0 + x).toFixed(2) + "s";
    const fmt = (s) => {
      s = Math.max(0, Math.ceil(s));
      return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    };
    const pct1 = (v) => v.toFixed(1).replace(".", ",") + "%";
    const fin = cur.pages.map((x, j) => this.ports.matchOf(cur, j));
    const avg = fin.reduce((x, y) => x + y, 0) / n;
    const LP = [
      [80, 70],
      [290, 95],
      [90, 190],
      [285, 230],
      [100, 320],
      [280, 370],
      [130, 450],
      [250, 470],
    ];
    const LT = [0, 0.14, 0.28, 0.42, 0.57, 0.71, 0.85, 1];
    const chips = [
      [1, "Текст", "text_fields"],
      [3, "Таблица", "table"],
      [5, "Поле", "edit_note"],
      [7, "Подпись", "draw"],
    ].map(([i, tt, icon]) => ({
      key: tt,
      t: tt,
      icon,
      x: Math.min(270, LP[i][0] + 40) + "px",
      y: Math.max(8, LP[i][1] - 70) + "px",
      delay: ds(LT[i] * 6),
    }));
    const fly = [
      ["Текст", "text_fields"],
      ["Таблица", "table"],
      ["Галочка", "check_box"],
      ["Поле", "edit_note"],
      ["Абзац", "notes"],
    ].map(([tt, icon], i) => ({
      key: tt,
      t: tt,
      icon,
      y: 8 + i * 36 + "px",
      delay: (-i * 0.64).toFixed(2) + "s",
    }));

    this.markCache = this.markCache || {};
    if (phase === "check" && !this.markCache[skey])
      this.timers.setTimeout(() => this.measureMarks(skey), 60);
    const marks = (this.markCache[skey] || []).map(([l, tp, w, hh], i) => ({
      key: "m" + i,
      l: l * 100 + "%",
      t: tp * 100 + "%",
      w: w * 100 + "%",
      h: hh * 100 + "%",
      inDelay: ds(0.3 + i * 0.25),
      delay: ds(tp * 5 + 0.4),
    }));
    const titles = {
      study: [
        "Изучаем фото",
        "Ищем текст, таблицы, поля для заполнения и подписи",
      ],
      transfer: [
        PH[1][0],
        clean
          ? "Текст встаёт по стандарту: поля, шрифт, отступы"
          : "Текст, таблицы и галочки встают на свои места",
      ],
      check: [
        "Сверяем и доделываем",
        "Сравниваем Word с фото строка за строкой и правим расхождения",
      ],
    };
    const live = !p.err && !p.done;
    const se = this.ui.stageRef && this.ui.stageRef.current;
    const sw = se ? se.clientWidth : 900,
      sh = se ? se.clientHeight : 640;
    const stageZoom = Math.max(
      0.25,
      Math.min(1.25, (sh - 40) / 562, (sw - 40) / 872),
    ).toFixed(3);
    const doneTitle = p.done
      ? ["Word готов", "Всё совпало с оригиналом — можно открывать"]
      : p.err
        ? ["Нужно переснять", "Одна страница не читается — остальные ждут"]
        : null;
    return {
      stageRef: this.ui.stageRef,
      stageZoom,
      procSerialOp: n > 1 ? 1 : 0.35,
      procBar: p.done ? "#16A34A" : "#1F4EF5",
      procKick: p.done
        ? "Готово · " + n + " " + plural(n, "страница", "страницы", "страниц")
        : p.err
          ? "Страница " + (p.err.pi + 1) + " из " + n
          : "Страница " + (fj + 1) + " из " + n,
      procKickIcon: p.done ? "task_alt" : p.err ? "error" : "description",
      procKickFg: p.done ? "#15803D" : p.err ? "#DC2626" : "#1F4EF5",
      procPage: pg,
      procSrc: pg.src || "",
      procNoSrc: !pg.src,
      procRunning: !p.err,
      procLive: live,
      procDone: !!p.done && !p.err,
      procErr: p.err,
      procErrN: p.err ? p.err.pi + 1 : "",
      canSkip: n > 1,
      procN: fj + 1,
      procTotal: n,
      procMulti: n > 1,
      procStreamsLabel:
        n > 1
          ? plan.S +
            " " +
            plural(plan.S, "поток", "потока", "потоков") +
            " сразу"
          : "одна",
      procTitle: doneTitle ? doneTitle[0] : titles[phase][0],
      procSub: doneTitle ? doneTitle[1] : titles[phase][1],
      procElapsed: fmt(t),
      procLeft: p.done ? "0:00" : "≈ " + fmt(plan.total - t),
      procSerial: n > 1 ? fmt(n * plan.D) : "—",
      procPct: Math.min(100, (t / plan.total) * 100).toFixed(1) + "%",
      procRail: [...PH, ["Готово", "task_alt"]].map(([tt, icon], i, arr) => {
        const done =
          fs.k > i || (i === arr.length - 1 && fs.k >= plan.ph.length);
        const on = i === k && fs.k < plan.ph.length;
        const dn = done || !!p.done;
        return {
          key: tt,
          t: tt,
          on: on && live,
          icon: dn ? "check_circle" : icon,
          arrow: i < arr.length - 1,
          bg: on && live ? "#1F4EF5" : dn ? "#E6F6EC" : "transparent",
          fg: on && live ? "#fff" : dn ? "#15803D" : "#8A90A0",
        };
      }),
      stage: [
        {
          key: skey,
          n: fj + 1,
          isStudy: phase === "study",
          isTransfer: phase === "transfer",
          isCheck: phase === "check",
          delay: ds(0),
          chips,
          fly,
          marks,
          flowLabel: clean ? "Оформляем" : "Переносим",
        },
      ],
      procLiveMatch:
        phase === "check"
          ? pct1(84 + (fin[fj] - 84) * Math.min(1, fs.k === 2 ? fs.pf : 1))
          : "",
      procCards: cur.pages.map((x, j) => {
        const q = ps[j];
        const done = q.k >= plan.ph.length;
        const act = q.k >= 0 && !done;
        const failed = !!(p.err && p.err.pi === j);
        return {
          key: x.id || "c" + j,
          failed,
          rowBg: failed
            ? "#FDECEC"
            : j === fj && live
              ? "#F3F6FF"
              : "transparent",
          page: x.page || cur.page,
          blur: x.blur,
          variant: done ? "word" : "photo",
          label: "стр. " + (j + 1),
          done,
          active: act && !p.err,
          status: failed
            ? "не читается"
            : done
              ? pct1(fin[j])
              : act
                ? PH[q.k][0].split(" ")[0]
                : "в очереди",
          fg: done ? "#15803D" : act ? "#1F4EF5" : "#8A90A0",
          w: (q.lp * 100).toFixed(1) + "%",
          bar: done ? "#16A34A" : "#1F4EF5",
          ring: j === fj && live ? "#1F4EF5" : "transparent",
        };
      }),
      sumMatch: pct1(avg),
      sumLine:
        n +
        " " +
        plural(n, "страница", "страницы", "страниц") +
        " · " +
        fmt(plan.total),
      sumRows: cur.pages.map((x, j) => ({
        key: "r" + j,
        label: "стр. " + (j + 1),
        pct: pct1(fin[j]),
        w: Math.max(8, (fin[j] - 90) * 10) + "%",
      })),
      sumStats: [
        ["timer", "Заняло " + fmt(plan.total)],
        ...(n > 1
          ? [
              [
                "bolt",
                "Быстрее на " +
                  fmt(n * plan.D - plan.total) +
                  " — " +
                  plan.S +
                  " " +
                  plural(plan.S, "поток", "потока", "потоков"),
              ],
            ]
          : []),
        ...(plan.check
          ? [["auto_fix_high", "Доделано при сверке: " + n * 3]]
          : []),
      ].map(([icon, tt]) => ({ key: icon, icon, t: tt })),
      procOpen: () => {
        this.timers.clearTimeout(this.doneT);
        this.ports.finishProc();
      },
      reshoot: () => {
        const pi = p.err.pi;
        this.store.update((s) => ({
          up: { ...s.up, pages: s.up.pages.filter((x, j) => j !== pi) },
          docs: s.docs.filter((d) => d.id !== cur.id),
        }));
        this.ports.go("new");
        this.timers.setTimeout(this.ports.pickFile, 100);
      },
      skipPage: () => {
        const pi = p.err.pi;
        const pages = cur.pages.filter((x, j) => j !== pi);
        this.ports.setDoc(cur.id, {
          status: "processing",
          pages: pages.length,
        });
        this.store.update(
          {
            cur: { ...cur, pages, cost: this.ports.costOf(pages, cur) },
            proc: { t0: 0, t: 0, err: null, done: false },
          },
          () => this.ports.runProc(),
        );
      },
    };
  }

  measureMarks(key) {
    const box = document.querySelector('[data-wordsheet="' + key + '"]');
    if (!box || (this.markCache && this.markCache[key])) return;
    const br = box.getBoundingClientRect();
    if (!br.width) return;
    const leaves = [...box.querySelectorAll("*")]
      .filter(
        (e) => !e.children.length && (e.textContent || "").trim().length > 1,
      )
      .map((e) => e.getBoundingClientRect())
      .filter((r) => r.width > 6 && r.height > 3);
    if (leaves.length < 3) {
      this.timers.setTimeout(() => this.measureMarks(key), 150);
      return;
    }
    const rows = [];
    leaves
      .sort((a, b) => a.top - b.top)
      .forEach((r) => {
        const row = rows.find((x) => Math.abs(x.top - r.top) < 4);
        if (row) {
          row.left = Math.min(row.left, r.left);
          row.right = Math.max(row.right, r.right);
          row.bottom = Math.max(row.bottom, r.bottom);
        } else
          rows.push({
            top: r.top,
            bottom: r.bottom,
            left: r.left,
            right: r.right,
          });
      });
    const pick = [0.22, 0.5, 0.8]
      .map((f) => rows[Math.min(rows.length - 1, Math.floor(f * rows.length))])
      .filter((r, i, a) => a.indexOf(r) === i);
    const pad = (4 * br.width) / 372;
    this.markCache[key] = pick.map((r) => [
      (r.left - pad - br.left) / br.width,
      (r.top - pad - br.top) / br.height,
      (r.right - r.left + 2 * pad) / br.width,
      (r.bottom - r.top + 2 * pad) / br.height,
    ]);
    this.ui.invalidate();
  }
}
