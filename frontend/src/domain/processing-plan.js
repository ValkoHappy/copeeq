export class ProcessingPlan {
  procPlan(cur, options = cur) {
    const n = cur.pages.length;
    const check = options.check !== false;
    const ph = check ? [6, 6.5, 5] : [6, 6.5];
    const D = ph.reduce((x, y) => x + y, 0);
    const S = Math.min(3, n);
    const starts = cur.pages.map(
      (x, j) => Math.floor(j / S) * D + (j % S) * 2.2,
    );
    return { ph, D, S, starts, total: Math.max(...starts) + D, check };
  }

  pageState(plan, j, t) {
    const lt = t - plan.starts[j];
    if (lt < 0) return { k: -1, lp: 0, pe: 0, pf: 0 };
    if (lt >= plan.D) return { k: plan.ph.length, lp: 1, pe: 0, pf: 1 };
    let acc = 0;
    for (let k = 0; k < plan.ph.length; k++) {
      if (lt < acc + plan.ph[k])
        return {
          k,
          lp: lt / plan.D,
          pe: lt - acc,
          pf: (lt - acc) / plan.ph[k],
        };
      acc += plan.ph[k];
    }
    return { k: plan.ph.length, lp: 1, pe: 0, pf: 1 };
  }

  matchOf(cur, j) {
    const s = String(cur.id)
      .split("")
      .reduce((x, c) => x + c.charCodeAt(0), 0);
    return 97 + ((s + j * 37) % 24) / 10;
  }
}
