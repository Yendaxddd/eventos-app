// The part of the screen the page really has on a phone: the on-screen keyboard and Discord's own buttons must not cover the game.
//
// Some phones shrink the page when the keyboard opens, others (Discord on iPhone) draw the keyboard over it and only the "visual
// viewport" gets smaller. Either way the page is made exactly as tall as what is visible (--app-h), and while the keyboard is up
// <html data-kb="open"> lets the CSS fold away what is not needed to write (the bottom bar, the action bar).

const EDITABLE = /^(TEXTAREA|SELECT)$/;

export function isEditable(el) {
  if (!el) return false;
  if (EDITABLE.test(el.tagName)) return true;
  if (el.tagName === "INPUT") return !/^(button|checkbox|radio|range|color|file|submit|reset|image)$/i.test(el.type || "text");
  return !!el.isContentEditable;
}

// Is the keyboard up? Something to write in has the focus and the visible height is clearly smaller than the tallest seen at this width.
export function keyboardOpen({ focused, height, tallest }) {
  return !!focused && tallest > 0 && height < tallest * 0.8;
}

const coarse = () => typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;

// The keyboard is closed when a QTE of this player starts on a phone: the button needs the room, and what was written stays in the box.
export function closeKeyboard() {
  if (typeof document === "undefined") return;
  const el = document.activeElement;
  if (coarse() && isEditable(el)) el.blur();
}

export function installViewport() {
  const vv = window.visualViewport;
  const root = document.documentElement;
  let tallest = 0, width = 0;
  const update = () => {
    const height = vv ? vv.height : window.innerHeight;
    const w = Math.round(vv ? vv.width : window.innerWidth);
    if (w !== width) { width = w; tallest = 0; }                     // turned: start again
    tallest = Math.max(tallest, height);
    root.style.setProperty("--app-h", `${Math.round(height)}px`);
    const open = keyboardOpen({ focused: isEditable(document.activeElement), height, tallest });
    if (open) root.dataset.kb = "open"; else delete root.dataset.kb;
    // a phone that slid the whole page up to show the box: put it back, the page is already as tall as what is visible
    if (document.scrollingElement && document.scrollingElement.scrollTop) document.scrollingElement.scrollTop = 0;
  };
  update();
  window.addEventListener("resize", update);
  if (vv) { vv.addEventListener("resize", update); vv.addEventListener("scroll", update); }
  document.addEventListener("focusin", (e) => {
    update();
    if (coarse() && isEditable(e.target)) setTimeout(() => { update(); e.target.scrollIntoView({ block: "nearest" }); }, 350);
  });
  document.addEventListener("focusout", () => setTimeout(update, 50));
}
