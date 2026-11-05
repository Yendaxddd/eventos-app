import test from "node:test";
import assert from "node:assert/strict";
import { hpChanges } from "../src/hits.js";

test("every change of HP between two looks at the game becomes a number, damage and healing alike", () => {
  const before = { boss: { name: "Rey", hp: 900 }, players: [{ id: "1", hp: 50 }, { id: "2", hp: 80 }] };
  const after = { boss: { name: "Rey", hp: 820 }, players: [{ id: "1", hp: 70 }, { id: "2", hp: 80 }, { id: "3", hp: 100 }] };
  assert.deepEqual(hpChanges(before, after), [{ target: "boss", amount: -80 }, { target: "1", amount: 20 }]);
  assert.deepEqual(hpChanges(null, after), []);
  assert.deepEqual(hpChanges({ boss: { name: "Rey", hp: 10 } }, { boss: { name: "Otro", hp: 500 } }), []);    // a new boss is not "healed"
});
