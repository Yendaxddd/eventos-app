import { useState } from "preact/hooks";
import { cdn, cx, hueOf, initial } from "../util.js";

// A picture, or the person's initial on a coloured disc when there is none (or it does not load).
export function Avatar({ url, name, size = "", class: className }) {
  const [shown, setShown] = useState(false);
  const [broken, setBroken] = useState(false);
  return (
    <span class={cx("avatar", size, className)} style={{ background: `hsl(${hueOf(name)} 45% 38%)`, position: "relative", overflow: "hidden" }} aria-hidden="true">
      {initial(name)}
      {url && !broken && (
        <img src={cdn(url)} alt="" onLoad={() => setShown(true)} onError={() => setBroken(true)}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: shown ? 1 : 0, transition: "opacity .2s" }} />
      )}
    </span>
  );
}
