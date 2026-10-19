import test from "node:test";
import assert from "node:assert/strict";
import { matchTaps, summarizeNet } from "../src/latency-model.js";

test("each tap answers one flash only and practice flashes do not count", () => {
  const flashes = [0, 1000, 2000, 3000, 4000];
  const taps = [20, 1030, 1990, 3010, 4040];
  assert.deepEqual(matchTaps(flashes, taps, { skip: 1 }), [30, -10, 10, 40]);
  // one tap between two flashes cannot be counted for both
  assert.deepEqual(matchTaps([1000, 1300], [1150], { window: 450 }), [150]);
});

test("a tap before the first counted flash is not counted for it, and a missed beat leaves no error", () => {
  assert.deepEqual(matchTaps([0, 1000, 2000], [1010], { skip: 1 }), [10]);
  assert.deepEqual(matchTaps([0, 1000, 2000], [], { skip: 0 }), []);
  assert.deepEqual(matchTaps([1000], [2000], { skip: 0 }), []);          // too far to be an answer
});

test("pings slower than the limit count as lost", () => {
  const net = summarizeNet([50, 60, 70, 2000, null, undefined], 1500);
  assert.equal(net.loss, 0.5);
  assert.equal(net.median, 60);
  assert.equal(net.min, 50);
  assert.deepEqual(net.samples, [50, 60, 70, null, null, null]);
});

test("nothing answered: no numbers and total loss", () => {
  const net = summarizeNet([undefined, null]);
  assert.equal(net.median, null);
  assert.equal(net.loss, 1);
  assert.equal(net.p90, null);
});
