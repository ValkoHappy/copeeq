import { test } from "node:test";
import assert from "node:assert/strict";
import { CreditPolicy } from "../src/domain/credit-policy.js";
import { PricingPolicy } from "../src/domain/pricing-policy.js";

test("credits spend subscription, free then purchased balances without mutating the source", () => {
  const policy = new CreditPolicy();
  const credits = { sub: 3, free: 5, pack: 10 };
  assert.deepEqual(policy.chargeCredits(credits, 10), {
    sub: 0,
    free: 0,
    pack: 8,
  });
  assert.deepEqual(credits, { sub: 3, free: 5, pack: 10 });
  for (const charge of [-1, 19, NaN])
    assert.throws(() => policy.chargeCredits(credits, charge), RangeError);
});

test("page pricing respects mode and whether handwriting recognition is enabled", () => {
  const policy = new PricingPolicy();
  const pages = [{ hand: false }, { hand: true }];
  assert.equal(policy.costOf(pages, { mode: "copy", hand: true }), 15);
  assert.equal(policy.costOf(pages, { mode: "clean", hand: true }), 18);
  assert.equal(policy.costOf(pages, { mode: "clean", hand: false }), 16);
});
