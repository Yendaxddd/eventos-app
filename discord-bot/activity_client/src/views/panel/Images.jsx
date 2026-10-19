import { useRef, useState } from "preact/hooks";
import { Image as ImageIcon, Link as LinkIcon, Trash2, Upload } from "lucide-preact";
import { toast } from "../../state.js";
import { uploadImage } from "../../net.js";
import { Block, ConfirmButton, Empty } from "../../ui/Common.jsx";
import { act, usePanel } from "../../panel/data.js";
import { cdn } from "../../util.js";

function Images({ d, replace }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(null);
  const picker = useRef(null);

  const add = async (address) => {
    const out = await act("panel.image_add", { url: address }, "Imagen añadida.");
    if (out) { replace(out); return true; }
    return false;
  };
  const upload = async (e) => {
    const picked = e.currentTarget.files && e.currentTarget.files[0];
    e.currentTarget.value = "";
    if (!picked) return;
    setBusy("upload");
    try { await add(await uploadImage(picked)); } catch (error) { toast(error.message, "bad", 4500); }
    setBusy(null);
  };
  const addUrl = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy("url");
    if (await add(url.trim())) setUrl("");
    setBusy(null);
  };
  const remove = async (index) => {
    const out = await act("panel.image_remove", { index }, "Imagen quitada.");
    if (out) replace(out);
  };
  const clear = async () => {
    const out = await act("panel.images_clear", {}, "Imágenes quitadas. Se usará la imagen por defecto.");
    if (out) replace(out);
  };

  return (
    <div class="dash-col" data-testid="images">
      <section class="card-2">
        <div class="card-title"><ImageIcon size={16} /><strong class="display">Imágenes de contraataque</strong><span class="faint num" style={{ fontSize: ".75rem" }}>{d.images.length} / {d.max}</span></div>
        <p class="faint" style={{ fontSize: ".875rem", marginBottom: "var(--sp-3)" }}>Cuando contraatacas, el bot muestra una de estas imágenes o GIF <b>al azar</b>. Sin ninguna, usa la de por defecto.</p>
        <div class="col" style={{ gap: "var(--sp-2)" }}>
          <div class="row" style={{ gap: "8px" }}>
            <button class="btn btn-primary" type="button" onClick={() => picker.current && picker.current.click()} disabled={busy !== null || d.images.length >= d.max} data-testid="image-upload">
              <Upload size={16} />{busy === "upload" ? "Subiendo…" : "Subir una imagen"}
            </button>
            <input ref={picker} type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden onChange={upload} data-testid="image-file" />
            <span class="faint" style={{ fontSize: ".75rem" }}>PNG, JPG, GIF o WebP · máx. 8 MB</span>
          </div>
          <form class="row" style={{ gap: "8px" }} onSubmit={addUrl}>
            <input class="input" type="url" placeholder="…o pega el enlace de una imagen (https)" value={url} onInput={(e) => setUrl(e.currentTarget.value)} data-testid="image-url" aria-label="Enlace de la imagen" />
            <button class="btn" type="submit" disabled={busy !== null || !url.trim()} data-testid="image-add"><LinkIcon size={16} /> Añadir</button>
          </form>
        </div>
      </section>

      {d.images.length === 0
        ? <Empty icon={ImageIcon} title="No tienes imágenes propias">Sube la tuya y se usará cada vez que contraataques.</Empty>
        : (
          <>
            <div class="gallery">
              {d.images.map((address, index) => (
                <figure key={`${address}-${index}`} class="shot" data-testid={`image-${index}`}>
                  <img src={cdn(address)} alt={`Imagen de contraataque ${index + 1}`} loading="lazy" />
                  <figcaption>
                    <span class="num">{index + 1}</span>
                    <button class="icon-btn" type="button" onClick={() => remove(index)} aria-label={`Quitar la imagen ${index + 1}`} data-testid={`image-remove-${index}`}><Trash2 size={16} /></button>
                  </figcaption>
                </figure>
              ))}
            </div>
            <div class="row" style={{ justifyContent: "flex-end" }}><ConfirmButton icon={Trash2} confirm="Sí, quitar todas" class="btn-ghost" onConfirm={clear} testid="images-clear">Quitar todas</ConfirmButton></div>
          </>
        )}
    </div>
  );
}

export function ImagesTab() {
  const q = usePanel("panel.images");
  return <Block q={q}>{(d) => <Images d={d} replace={q.replace} />}</Block>;
}
