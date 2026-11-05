import { useState } from "preact/hooks";
import { Copy, LifeBuoy } from "lucide-preact";
import { comp, link, version, you, toast, rules } from "../state.js";
import { DIFFICULTY } from "../terms.js";
import { Page, Section } from "../ui/Controls.jsx";
import { inDiscord } from "../util.js";

const SHORTCUTS = [
  ["Espacio", "Responder al QTE más urgente (esquivar o parry, según toque)"],
  ["E", "Esquivar"], ["P", "Parry"], ["S", "Rescatar a un compañero"],
  ["↑ ↓ ← →", "Direcciones del QTE de flechas (recuerda: la opuesta)"],
  ["A", "Adaptar"], ["Q", "Contraataque"], ["1 · 2", "Poder 1 · Poder 2"], ["3", "Dominio"],
  ["Esc", "Salir del campo de texto / volver"],
];

const RULES = [
  ["Esquivar", "Vale desde el principio hasta el final de su ventana. Si llegas tarde, recibes el golpe."],
  ["Parry", "Solo vale dentro de su ventana (la barra de arriba la muestra). Antes de tiempo o tarde falla. La banda violeta es la zona de Black Flash."],
  ["QTE grupal", "Todo el grupo debe esquivar; el parry no cuenta."],
  ["Combo", "Una secuencia de esquivar/parry en orden. Un error o ir lento la rompe."],
  ["Flechas", "Aparece una flecha y hay que pulsar la contraria."],
  ["Rescatar", "Si el QTE es de otro jugador puedes salvarlo (máximo 2 por minuto). Si llegas tarde, el golpe es para ti."],
  ["Contraataque", "Tras esquivar a tiempo tienes unos segundos para contraatacar."],
];

export function HelpPage() {
  const [copied, setCopied] = useState(false);
  const diagnostic = () => {
    const l = link.value, c = comp.value;
    return [
      `Eventos App ${version.value || "?"}`, `Dentro de Discord: ${inDiscord ? "sí" : "no"}`, `Jugador: ${you.value ? you.value.name : "?"}`,
      `Ping: mediana ${l.median === null ? "—" : Math.round(l.median)} ms, mínimo ${l.min === null ? "—" : Math.round(l.min)} ms, vibración ${l.jitter === null ? "—" : Math.round(l.jitter)} ms (${l.samples} muestras)`,
      `Ajuste del servidor: red ${c.net === null || c.net === undefined ? "—" : Math.round(c.net)} ms, dispositivo ${c.device ?? 0} ms`,
      `Pantalla: ${window.innerWidth}x${window.innerHeight} @${window.devicePixelRatio}`, `Navegador: ${navigator.userAgent}`,
    ].join("\n");
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(diagnostic()); setCopied(true); setTimeout(() => setCopied(false), 1800); toast("Datos copiados.", "ok"); }
    catch { toast("No se pudo copiar. Haz una captura de esta pantalla.", "warn"); }
  };
  return (
    <Page title="Ayuda y atajos" icon={LifeBuoy}>
      <Section title="Reglas de los QTE">
        <div class="col">
          {RULES.map(([name, text]) => <div class="setting stack" key={name}><div class="info"><strong>{name}</strong><span>{text}</span></div></div>)}
        </div>
      </Section>
      <Section title="Teclado">
        <div class="col">
          {SHORTCUTS.map(([keys, text]) => (
            <div class="setting" key={keys}><span class="kbd" style={{ minWidth: "64px", height: "26px" }}>{keys}</span><div class="info"><span style={{ marginTop: 0 }}>{text}</span></div></div>
          ))}
        </div>
        <p class="faint" style={{ fontSize: ".8125rem" }}>Mientras escribes en el chat, usa Alt + la letra.</p>
      </Section>
      <Section title="Para soporte">
        <div class="setting"><div class="info"><strong>Datos de tu conexión</strong><span>Si algo falla, copia esto y envíaselo a quien organiza el evento.</span></div>
          <button class="btn btn-sm" type="button" onClick={copy}><Copy size={14} /> {copied ? "Copiado" : "Copiar"}</button></div>
        {rules.value && <p class="faint" style={{ fontSize: ".75rem" }}>Ventanas de esta partida: {Object.entries(rules.value.times || {}).map(([k, t]) => `${DIFFICULTY[k] || k} (esquivar ${t.evade} s, parry ${t.parry[0]}–${t.parry[1]} s)`).join(" · ")}</p>}
      </Section>
    </Page>
  );
}
