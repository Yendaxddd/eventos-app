import test from "node:test";
import assert from "node:assert/strict";
import { groupedWithPrevious } from "../src/feed-model.js";

const msg = (id, ts, author, extra = {}) => ({ id, ts, author: { id: "1", name: "Ana", avatar: "a.png", webhook: false, ...author }, ...extra });

test("messages of one person within five minutes share a header", () => {
  const list = [msg("1", 0, {}), msg("2", 60_000, {}), msg("3", 400_000, {})];
  assert.deepEqual(list.map((_, i) => groupedWithPrevious(list, i)), [false, true, false]);
});

test("a character that speaks through different webhooks is still one speaker while name and picture match", () => {
  const hook = (id, ts, hookId, avatar = "kuro.png") => msg(id, ts, { id: hookId, name: "Kuro", avatar, webhook: true });
  const list = [hook("1", 0, "w1"), hook("2", 1000, "w2"), hook("3", 2000, "w3"), hook("4", 3000, "w1", "other.png")];
  assert.deepEqual(list.map((_, i) => groupedWithPrevious(list, i)), [false, true, true, false]);
});

test("a webhook and a person with the same name, and replies, never share", () => {
  const list = [msg("1", 0, {}), msg("2", 1000, { webhook: true }), msg("3", 2000, { webhook: true }, { reply: { author: "x", text: "y" } })];
  assert.deepEqual(list.map((_, i) => groupedWithPrevious(list, i)), [false, false, false]);
});

import { cdn } from "../src/util.js";

test("the Activity's own address for a character's picture is read from the Activity itself, other hosts are left alone", () => {
  assert.equal(cdn("https://equipo.example.net/files/images/0123456789abcdef01234567.png"), "/files/images/0123456789abcdef01234567.png");
  assert.equal(cdn("files/images/0123456789abcdef01234567.png"), "/files/images/0123456789abcdef01234567.png");
  assert.equal(cdn("https://example.net/files/audio/0123456789abcdef01234567.mp3"), "https://example.net/files/audio/0123456789abcdef01234567.mp3");
  assert.match(cdn("https://cdn.discordapp.com/a.png"), /^\/media\?u=/);
});
