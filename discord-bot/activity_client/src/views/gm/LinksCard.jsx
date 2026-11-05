import { Link2 } from "lucide-preact";
import { Block } from "../../ui/Common.jsx";
import { act } from "../../panel/data.js";
import { PRESETS, PRESET_IDS, DEFAULT_BINDING } from "../../fx-model.js";
import { Card } from "./ui.jsx";
import { useLive } from "./hooks.js";

// One place to say what happens at each moment of a fight: a cinematic, the music, an effect and a sound. Each choice is saved at once and is
// the same thing the Cinemáticas, Audio and Efectos tabs edit (they keep all the details: this only picks).
function Row({ link, d, change }) {
  const e = link.event;
  const tracks = d.sounds.filter((s) => s.kind === "music"), effects = d.sounds.filter((s) => s.kind !== "music");
  const music = !link.phase ? "" : link.phase.mode === "stop" ? "__stop" : link.phase.sound;
  return (
    <div class="gm-link" data-testid={`link-${e}`}>
      <strong class="gm-link-title">{link.label}</strong>
      <label class="field"><span class="field-label">🎬 Cinemática</span>
        <select class="select" value={link.cinema ? link.cinema.id : ""} onChange={(ev) => change("gm.cinema_link", { event: e, id: ev.currentTarget.value })} data-testid={`link-cinema-${e}`}>
          <option value="">— ninguna —</option>
          {d.cinemas.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select></label>
      <label class="field"><span class="field-label">🎵 Música</span>
        <select class="select" value={music} onChange={(ev) => { const v = ev.currentTarget.value; change(v === "" ? "gm.phase_clear" : "gm.phase_set", v === "" ? { event: e } : { event: e, mode: v === "__stop" ? "stop" : "music", sound: v === "__stop" ? undefined : v, volume: link.phase ? link.phase.volume : 100 }); }} data-testid={`link-music-${e}`}>
          <option value="">— no cambia —</option><option value="__stop">Parar la música</option>
          {tracks.map((s) => <option key={s.id} value={s.id}>Pone «{s.name}»</option>)}
        </select></label>
      <label class="field"><span class="field-label">✨ Efecto visual</span>
        <select class="select" value={link.effect ? link.effect.preset : ""} onChange={(ev) => { const v = ev.currentTarget.value; change(v === "" ? "gm.fx_clear" : "gm.fx_set", v === "" ? { for: "event", event: e } : { for: "event", event: e, binding: { ...DEFAULT_BINDING, ...(link.effect || {}), preset: v } }); }} data-testid={`link-effect-${e}`}>
          <option value="">— ninguno —</option>
          {PRESET_IDS.filter((p) => p !== "ninguno").map((p) => <option key={p} value={p}>{PRESETS[p].label}</option>)}
        </select></label>
      <label class="field"><span class="field-label">🔊 Sonido</span>
        <select class="select" value={link.cue ? link.cue.sound : ""} onChange={(ev) => { const v = ev.currentTarget.value; change(v === "" ? "gm.cue_clear" : "gm.cue_set", v === "" ? { event: e } : { event: e, sound: v, volume: link.cue ? link.cue.volume : 100, scope: "all" }); }} data-testid={`link-sound-${e}`}>
          <option value="">— ninguno —</option>
          {[...effects, ...tracks].map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select></label>
    </div>
  );
}

export function LinksCard() {
  const q = useLive("gm.quick", {}, 5000);
  const change = async (op, args) => { const out = await act(op, args); if (out) q.refresh(); };
  return (
    <Card title="Qué pasa en cada momento del combate" icon={Link2} testid="gm-links"
      hint="Ata todo lo que quieras a cada momento: al aparecer el jefe puede saltar una cinemática, cambiar la música, verse un efecto y sonar un golpe. Se guarda al elegir, y los detalles se afinan en las pestañas Cinemáticas, Audio y Efectos.">
      <Block q={q}>
        {(d) => <div class="gm-links">{d.links.map((l) => <Row key={l.event} link={l} d={d} change={change} />)}</div>}
      </Block>
    </Card>
  );
}
