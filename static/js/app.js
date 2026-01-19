// Equine Vet Synapse - client side helpers
// - file preview (image/video)
// - coat "other" toggle

function $(sel) {
  return document.querySelector(sel);
}

function safeClear(el) {
  if (!el) return;
  while (el.firstChild) el.removeChild(el.firstChild);
}

function humanBytes(bytes) {
  if (!bytes && bytes !== 0) return "";
  const units = ["B", "KB", "MB", "GB"]; 
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n = n / 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function mountFileMeta(container, file) {
  const meta = document.createElement("div");
  meta.className = "small muted";
  meta.textContent = `選択: ${file.name} (${humanBytes(file.size)})`;
  container.appendChild(meta);
}

function previewImage(input, containerId) {
  const container = document.getElementById(containerId);
  if (!input || !container) return;
  input.addEventListener("change", () => {
    safeClear(container);
    const file = input.files && input.files[0];
    if (!file) return;
    mountFileMeta(container, file);
    const img = document.createElement("img");
    img.style.maxWidth = "100%";
    img.style.borderRadius = "12px";
    img.style.marginTop = "8px";
    img.alt = "preview";
    const url = URL.createObjectURL(file);
    img.onload = () => URL.revokeObjectURL(url);
    img.src = url;
    container.appendChild(img);
  });
}

function previewVideo(input, containerId) {
  const container = document.getElementById(containerId);
  if (!input || !container) return;
  input.addEventListener("change", () => {
    safeClear(container);
    const file = input.files && input.files[0];
    if (!file) return;
    mountFileMeta(container, file);

    const video = document.createElement("video");
    video.controls = true;
    video.muted = true;
    video.playsInline = true;
    video.style.maxWidth = "100%";
    video.style.borderRadius = "12px";
    video.style.marginTop = "8px";
    const url = URL.createObjectURL(file);
    video.onloadeddata = () => {
      // iPhoneのHEVCなどでブラウザ再生できない場合でも、ファイル選択情報は残る
      // (サーバー側で解析できる形式へ変換/フォールバックします)
    };
    video.onerror = () => {
      const note = document.createElement("div");
      note.className = "small";
      note.style.marginTop = "8px";
      note.textContent = "この端末ではプレビュー再生できない形式の可能性があります（アップロードは可能です）。";
      container.appendChild(note);
    };
    video.src = url;
    container.appendChild(video);
  });
}

function coatOtherToggle() {
  const sel = document.querySelector('select[name="coat"]');
  const other = document.querySelector('input[name="coat_other"]');
  if (!sel || !other) return;
  const update = () => {
    const isOther = (sel.value || "").includes("その他");
    other.style.display = isOther ? "block" : "none";
    if (!isOther) other.value = "";
  };
  sel.addEventListener("change", update);
  update();
}

document.addEventListener("DOMContentLoaded", () => {
  previewImage(document.querySelector('input[name="side_photo"]'), "pv_side");
  previewImage(document.querySelector('input[name="front_photo"]'), "pv_front");
  previewImage(document.querySelector('input[name="rear_photo"]'), "pv_rear");
  previewVideo(document.querySelector('input[name="video"]'), "pv_video");
  coatOtherToggle();
});
