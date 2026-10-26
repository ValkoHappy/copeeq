/** Credit arithmetic without UI state, payment providers or timers. */
export class CreditPolicy {
  balance(credits) {
    return credits.free + credits.sub + credits.pack;
  }
  chargeCredits(credits, amount) {
    if (
      !Number.isFinite(amount) ||
      amount < 0 ||
      amount > this.balance(credits)
    ) {
      throw new RangeError("Invalid credit charge");
    }
    const next = { ...credits };
    let remaining = amount;
    for (const bucket of ["sub", "free", "pack"]) {
      const charge = Math.min(next[bucket], remaining);
      next[bucket] -= charge;
      remaining -= charge;
    }
    return next;
  }
}
