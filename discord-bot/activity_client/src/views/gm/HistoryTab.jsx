import { History } from "lucide-preact";
import { Block, Empty } from "../../ui/Common.jsx";
import { ago } from "../../util.js";
import { useLive } from "./hooks.js";

const dayOf = (ts) => new Date(ts).toLocaleDateString("es", { weekday: "long", day: "numeric", month: "long" });
const clock = (ts) => new Date(ts).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

// Everything the game masters changed from this panel, newest first: who did what.
export function HistoryTab() {
  const q = useLive("gm.history", null, 5000);
  return (
    <div class="dash-col" data-testid="gm-history">
      <Block q={q}>
        {({ entries }) => {
          if (!entries.length) return <Empty icon={History} title="Todavía no se ha cambiado nada">Aquí quedará anotado quién hace qué desde este panel.</Empty>;
          const days = [];
          for (const entry of entries) {
            const day = dayOf(entry.ts);
            if (!days.length || days[days.length - 1].day !== day) days.push({ day, items: [] });
            days[days.length - 1].items.push(entry);
          }
          return (
            <>
              <p class="faint gm-hint">Se guardan los últimos cambios, también cuando el bot se reinicia.</p>
              {days.map(({ day, items }) => (
                <section key={day}>
                  <h3 class="gm-sub" style={{ textTransform: "capitalize" }}>{day}</h3>
                  <ul class="gm-log">
                    {items.map((e) => (
                      <li key={`${e.ts}-${e.who}-${e.action}`} class="gm-log-item" data-testid="gm-log-item">
                        <time class="num faint" dateTime={new Date(e.ts).toISOString()} title={ago(e.ts)}>{clock(e.ts)}</time>
                        <b>{e.who}</b>
                        <span class="grow">{e.action}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </>
          );
        }}
      </Block>
    </div>
  );
}
