import test from "node:test";
import assert from "node:assert/strict";
import { parseTupperExport, describeResult } from "../src/tupper.js";

test("reads the export of Tupperbox, with or without the wrapping object, keeping names and web addresses of pictures only", () => {
  const file = JSON.stringify({ tuppers: [
    { name: "Kuro", avatar_url: "https://cdn.discordapp.com/attachments/1/2/k.png?ex=1", brackets: ["k:", ""] },
    { name: " Shiro ", avatar_url: "ftp://insecure.example/s.png" },
    { name: "Mina", avatar_url: null },
    { name: "Kuro", avatar_url: "https://x/y.png" },
    { name: "", avatar_url: "https://x/z.png" },
    { avatar_url: "https://x/w.png" },
  ], groups: [] });
  const out = parseTupperExport(file);
  assert.deepEqual(out.items, [
    { name: "Kuro", avatar: "https://cdn.discordapp.com/attachments/1/2/k.png?ex=1" }, { name: "Shiro", avatar: null }, { name: "Mina", avatar: null }]);
  assert.equal(out.total, 6);
  assert.equal(out.ignored, 3);
  assert.deepEqual(parseTupperExport(JSON.stringify([{ name: "Solo", avatar_url: "https://a/b.png" }])).items, [{ name: "Solo", avatar: "https://a/b.png" }]);
  assert.equal(parseTupperExport("﻿" + file).items.length, 3);                          // a byte-order mark in front is fine
});

test("says in Spanish what is wrong with a file that is not a Tupperbox export", () => {
  assert.match(parseTupperExport("esto no es json").error, /no es JSON/);
  assert.match(parseTupperExport('{"hello": 1}').error, /No encuentro personajes/);
  assert.match(parseTupperExport('{"tuppers": [{"avatar_url": "x"}]}').error, /ningún personaje/);
  assert.match(parseTupperExport("").error, /no es JSON/);
});

test("each result of an import is worded for the summary", () => {
  assert.deepEqual(describeResult({ status: "new", image: "ok" }), { tone: "ok", text: "Registrado · imagen guardada" });
  assert.equal(describeResult({ status: "mine", image: "none" }).text, "Ya era tuyo · sin imagen");
  assert.equal(describeResult({ status: "new", image: "error", note: "No se pudo descargar la imagen." }).text, "Registrado · sin imagen (No se pudo descargar la imagen)");
  assert.equal(describeResult({ status: "taken" }).tone, "warn");
  assert.equal(describeResult({ status: "skipped", note: "Repetido en el archivo." }).text, "Repetido en el archivo.");
});
