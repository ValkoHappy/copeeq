export class PricingPolicy {
  pageCost(pg, up) {
    return pg.hand && up.hand ? 10 : up.mode === "clean" ? 8 : 5;
  }

  costOf(pages, up) {
    return pages.reduce((a, pg) => a + this.pageCost(pg, up), 0);
  }
}
