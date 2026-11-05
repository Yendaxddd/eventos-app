// Reading what Tupperbox exports (`tul!export` -> tuppers.json), in the page: only the names and picture addresses go to the server.
export const MAX_IMPORT = 40;        // per import (the server's limit too)

// -> { items: [{ name, avatar }], total, ignored } or { error }.
export function parseTupperExport(text) {
  let data;
  try { data = JSON.parse(String(text || "").replace(/^﻿/, "")); } catch { return { error: "Ese archivo no es JSON. Es el que te manda Tupperbox con «tul!export» (se llama tuppers.json)." }; }
  const list = Array.isArray(data) ? data : data && Array.isArray(data.tuppers) ? data.tuppers : null;
  if (!list) return { error: "No encuentro personajes en ese archivo. ¿Es el de «tul!export» de Tupperbox?" };
  const items = [];
  const seen = new Set();
  let ignored = 0;
  for (const raw of list) {
    const name = raw && typeof raw.name === "string" ? raw.name.trim().slice(0, 80) : "";
    if (!name || seen.has(name)) { ignored++; continue; }
    seen.add(name);
    const url = raw && typeof raw.avatar_url === "string" ? raw.avatar_url.trim() : "";
    items.push({ name, avatar: /^https?:\/\//i.test(url) ? url : null });
  }
  if (!items.length) return { error: "El archivo no tiene ningún personaje con nombre." };
  return { items, total: list.length, ignored };
}

// What each result of an import says (the server's statuses), for the summary.
export function describeResult(r) {
  if (r.status === "taken") return { tone: "warn", text: "Ya lo tiene otra persona" };
  if (r.status === "skipped") return { tone: "warn", text: r.note || "Omitido" };
  const what = r.status === "new" ? "Registrado" : "Ya era tuyo";
  if (r.image === "ok") return { tone: "ok", text: `${what} · imagen guardada` };
  if (r.image === "error") return { tone: "warn", text: `${what} · sin imagen (${(r.note || "no se pudo descargar").replace(/\.$/, "")})` };
  return { tone: "ok", text: `${what} · sin imagen` };
}
