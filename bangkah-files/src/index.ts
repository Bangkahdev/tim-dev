interface R2Object {
  key: string;
  size: number;
  uploaded: Date;
  httpMetadata?: { contentType?: string };
  customMetadata?: Record<string, string>;
}

interface R2Bucket {
  put(
    key: string,
    value: ArrayBuffer | ReadableStream,
    options?: {
      httpMetadata?: { contentType?: string; contentDisposition?: string };
      customMetadata?: Record<string, string>;
    },
  ): Promise<unknown>;
  get(key: string): Promise<{
    body: ReadableStream;
    size: number;
    httpMetadata?: { contentType?: string };
    customMetadata?: Record<string, string>;
  } | null>;
  delete(key: string): Promise<void>;
  list(options?: {
    prefix?: string;
    limit?: number;
    cursor?: string;
    include?: string[];
  }): Promise<{ objects: R2Object[]; truncated: boolean; cursor?: string }>;
  head(key: string): Promise<R2Object | null>;
}

interface Env {
  FILES_BUCKET: R2Bucket;
  FILES_TOKEN: string;
  MAX_UPLOAD_BYTES?: string;
}

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function safeName(name: string): string {
  const cleaned = name
    .normalize("NFKD")
    .replace(/[^\w.\- ]+/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[.-]+/, "")
    .slice(0, 120);
  // Biarkan "" apa adanya; fallback ditentukan oleh pemanggil.
  return cleaned;
}

function safeFolder(folder: string): string {
  return folder
    .split("/")
    .map((part) => safeName(part).replace(/\./g, ""))
    .filter(Boolean)
    .slice(0, 4)
    .join("/");
}

async function safeEqual(left: string, right: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const a = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(left)));
  const b = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(right)));
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.min(a.length, b.length); i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

function basicCredentials(request: Request): { user: string; password: string } | null {
  const header = request.headers.get("authorization") || "";
  if (!header.startsWith("Basic ")) return null;
  try {
    const decoded = atob(header.slice(6));
    const separator = decoded.indexOf(":");
    if (separator < 0) return null;
    return { user: decoded.slice(0, separator), password: decoded.slice(separator + 1) };
  } catch {
    return null;
  }
}

async function authorize(request: Request, env: Env): Promise<string | null> {
  if (!env.FILES_TOKEN) return null;
  const header = request.headers.get("authorization") || "";
  if (header.startsWith("Bearer ") && (await safeEqual(header.slice(7), env.FILES_TOKEN))) {
    return "api";
  }
  const basic = basicCredentials(request);
  if (basic && (await safeEqual(basic.password, env.FILES_TOKEN))) {
    return basic.user || "owner";
  }
  return null;
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

async function listFiles(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const prefix = safeFolder(url.searchParams.get("prefix") || "");
  const options: {
    prefix?: string;
    limit?: number;
    include?: string[];
  } = { limit: 500, include: ["httpMetadata", "customMetadata"] };
  if (prefix) options.prefix = `${prefix}/`;
  let result = await env.FILES_BUCKET.list(options);

  // Beberapa runtime menyimpan bucket list berbeda saat tanpa prefix.
  if (!prefix && result.objects.length === 0) {
    const retryPlain = await env.FILES_BUCKET.list({ limit: 500 });
    console.log("[DEBUG retryPlain] count=", retryPlain.objects.length);
    if (retryPlain.objects.length > 0) result = retryPlain;
    else {
      const retryUploads = await env.FILES_BUCKET.list({
        prefix: "uploads/",
        limit: 500,
        include: ["httpMetadata", "customMetadata"],
      });
      console.log("[DEBUG retryUploads] count=", retryUploads.objects.length);
      if (retryUploads.objects.length > 0) result = retryUploads;
    }
  }
  const files = result.objects
    .filter((object) => !object.key.endsWith("/"))
    .map((object) => ({
      key: object.key,
      name: object.customMetadata?.["original-name"] || object.key.split("/").pop() || object.key,
      size: object.size,
      uploaded: object.uploaded,
      contentType: object.httpMetadata?.contentType || "application/octet-stream",
    }))
    .sort((a, b) => new Date(b.uploaded).getTime() - new Date(a.uploaded).getTime());

  return json({ files, truncated: result.truncated });
}

async function uploadFile(request: Request, env: Env, user: string): Promise<Response> {
  const url = new URL(request.url);
  const originalName = (url.searchParams.get("name") || "file").slice(0, 200);
  const folder = safeFolder(url.searchParams.get("folder") || "uploads");
  const maxBytes = Number(env.MAX_UPLOAD_BYTES || 104857600);
  const declared = Number(request.headers.get("content-length") || 0);

  if (!request.body) return json({ error: "Body kosong." }, 400);
  if (declared > maxBytes) {
    return json({ error: `Ukuran file melebihi batas ${formatBytes(maxBytes)}.` }, 413);
  }

  const now = new Date();
  const datePath = `${now.getUTCFullYear()}/${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
  const key = `${folder || "uploads"}/${datePath}/${crypto.randomUUID()}-${safeName(originalName) || "file"}`;

  await env.FILES_BUCKET.put(key, request.body, {
    httpMetadata: {
      contentType: request.headers.get("content-type") || "application/octet-stream",
      contentDisposition: `attachment; filename="${safeName(originalName)}"`,
    },
    customMetadata: {
      "original-name": originalName,
      "uploaded-by": user,
      "uploaded-at": now.toISOString(),
    },
  });

  return json({ ok: true, key, name: originalName, size: declared });
}

async function downloadFile(request: Request, env: Env): Promise<Response> {
  const key = new URL(request.url).searchParams.get("key") || "";
  if (!key) return json({ error: "Parameter key wajib." }, 400);

  const object = await env.FILES_BUCKET.get(key);
  if (!object) return json({ error: "File tidak ditemukan." }, 404);

  const name = object.customMetadata?.["original-name"] || key.split("/").pop() || "download";
  return new Response(object.body, {
    headers: {
      "content-type": object.httpMetadata?.contentType || "application/octet-stream",
      "content-disposition": `attachment; filename="${safeName(name) || "download"}"`,
      "content-length": String(object.size),
      "cache-control": "private, no-store",
    },
  });
}

async function deleteFile(request: Request, env: Env): Promise<Response> {
  const key = new URL(request.url).searchParams.get("key") || "";
  if (!key) return json({ error: "Parameter key wajib." }, 400);
  const object = await env.FILES_BUCKET.head(key);
  if (!object) return json({ error: "File tidak ditemukan." }, 404);
  await env.FILES_BUCKET.delete(key);
  return json({ ok: true });
}

function appHtml(): string {
  return `<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Files · Bangkah</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%2346c08a'/%3E%3Ctext x='32' y='45' text-anchor='middle' font-size='40' font-family='sans-serif' font-weight='bold' fill='%2308130d'%3EB%3C/text%3E%3C/svg%3E" />
<style>
  :root { color-scheme: dark; --bg:#0f1418; --panel:#131b21; --border:#26333d; --text:#dfe7ec; --muted:#8fa2ae; --primary:#46c08a; --danger:#e5726f; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }
  header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 22px; border-bottom:1px solid var(--border); position:sticky; top:0; background:rgba(15,20,24,.94); backdrop-filter:blur(8px); z-index:5; }
  .brand { display:flex; align-items:center; gap:10px; font-weight:600; }
  .logo { width:34px; height:34px; border-radius:9px; background:var(--primary); color:#08130d; display:grid; place-items:center; font-weight:800; }
  .brand small { display:block; color:var(--muted); font-weight:400; font-size:11px; letter-spacing:.14em; text-transform:uppercase; }
  main { max-width:1100px; margin:0 auto; padding:22px; }
  .login { max-width:420px; margin:10vh auto; background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:26px; }
  .login h1 { margin:0 0 6px; font-size:22px; }
  .login p { margin:0 0 18px; color:var(--muted); font-size:14px; line-height:1.5; }
  .field { display:flex; flex-direction:column; gap:6px; margin-bottom:14px; }
  label { font-size:13px; color:var(--muted); }
  input { width:100%; border:1px solid var(--border); background:#0b1115; color:var(--text); border-radius:8px; padding:10px 12px; font-size:14px; }
  input:focus { outline:2px solid rgba(70,192,138,.35); border-color:var(--primary); }
  .btn { border:1px solid var(--border); background:#18222a; color:var(--text); border-radius:8px; padding:8px 13px; font-size:13px; cursor:pointer; text-decoration:none; display:inline-flex; align-items:center; gap:6px; }
  .btn:hover { border-color:#3a4b58; }
  .btn.primary { background:var(--primary); color:#08130d; border-color:transparent; font-weight:600; }
  .btn.danger { color:var(--danger); }
  .drop { border:1.5px dashed var(--border); border-radius:14px; padding:26px; text-align:center; color:var(--muted); background:var(--panel); transition:.15s; cursor:pointer; }
  .drop.over { border-color:var(--primary); background:rgba(70,192,138,.06); color:var(--text); }
  .drop strong { color:var(--text); }
  .toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:10px; justify-content:space-between; margin:18px 0 10px; }
  .toolbar input { max-width:280px; }
  table { width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
  th, td { text-align:left; padding:11px 14px; border-bottom:1px solid var(--border); font-size:13px; }
  th { color:var(--muted); font-weight:500; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
  tr:last-child td { border-bottom:0; }
  td.name { font-weight:500; overflow-wrap:anywhere; }
  td.size, td.time { color:var(--muted); white-space:nowrap; }
  .actions { display:flex; gap:6px; justify-content:flex-end; }
  .status { font-size:12px; color:var(--muted); margin:8px 0; min-height:18px; }
  .empty { color:var(--muted); text-align:center; padding:34px; font-size:14px; }
  .progress { height:6px; background:#0b1115; border-radius:99px; overflow:hidden; margin-top:12px; display:none; }
  .progress > div { height:100%; width:0; background:var(--primary); transition:width .2s; }
  .error { color:var(--danger); font-size:13px; min-height:18px; }
  .note { color:var(--muted); font-size:12px; line-height:1.5; margin-top:10px; }
</style>
</head>
<body>
<header>
  <div class="brand"><div class="logo">B</div><div>Bangkah Files<small>files.bangkah.my.id</small></div></div>
  <div style="display:flex;gap:8px;align-items:center">
    <span id="who" class="status" style="margin:0"></span>
    <button class="btn" id="logout" hidden>Keluar</button>
  </div>
</header>
<main>
  <section id="loginView" class="login">
    <h1>Portal file perusahaan</h1>
    <p>Tempat berbagi file internal Bangkah. Akses dilindungi token perusahaan.</p>
    <div class="field"><label for="token">Access token</label><input id="token" type="password" autocomplete="current-password" placeholder="Tempel token perusahaan" /></div>
    <div id="loginError" class="error"></div>
    <button id="loginBtn" class="btn primary" style="width:100%">Masuk</button>
  </section>

  <section id="filesView" hidden>
    <div class="drop" id="drop">
      <strong>Letakkan file di sini</strong> atau klik untuk memilih.
      <div class="note">Maksimal 100 MB per file. File disimpan di Cloudflare R2.</div>
      <div class="progress" id="progress"><div id="progressBar"></div></div>
      <input id="fileInput" type="file" multiple hidden />
    </div>
    <div class="toolbar">
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <input id="search" placeholder="Cari nama file..." />
        <button class="btn" id="refresh">Muat ulang</button>
      </div>
      <span id="count" class="status" style="margin:0"></span>
    </div>
    <div class="status" id="status"></div>
    <table>
      <thead><tr><th>Nama</th><th>Ukuran</th><th>Diunggah</th><th style="text-align:right">Aksi</th></tr></thead>
      <tbody id="rows"><tr><td colspan="4" class="empty">Belum ada file.</td></tr></tbody>
    </table>
  </section>
</main>
<script>
  const state = { token: localStorage.getItem("bangkah_files_token") || "", files: [] };
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtSize = (bytes) => { if (!bytes) return "0 B"; const u = ["B", "KB", "MB", "GB", "TB"]; const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), u.length - 1); return (bytes / 1024 ** i).toFixed(i ? 1 : 0) + " " + u[i]; };
  const fmtTime = (value) => { try { return new Date(value).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); } catch { return value; } };
  const auth = () => ({ authorization: "Bearer " + state.token });

  async function api(path, options) {
    const response = await fetch(path, Object.assign({}, options, { headers: Object.assign({}, (options || {}).headers || {}, auth()) }));
    if (response.status === 401) { showLogin("Sesi berakhir."); throw new Error("Unauthorized"); }
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.error || "Permintaan gagal"); }
    return response;
  }

  function showLogin(message) {
    if (message === undefined) message = "";
    $("loginView").hidden = false;
    $("filesView").hidden = true;
    $("logout").hidden = true;
    $("who").textContent = "";
    $("loginError").textContent = message;
  }

  function showFiles() {
    $("loginView").hidden = true;
    $("filesView").hidden = false;
    $("logout").hidden = false;
    $("who").textContent = "Terhubung";
  }

  async function loadFiles() {
    $("status").textContent = "Memuat...";
    try {
      const response = await api("/api/files");
      const data = await response.json();
      state.files = data.files || [];
      render();
      $("status").textContent = "";
    } catch (error) { $("status").textContent = error.message; }
  }

  function render() {
    const term = $("search").value.trim().toLowerCase();
    const files = state.files.filter((file) => !term || file.name.toLowerCase().includes(term));
    $("count").textContent = files.length + " file · " + fmtSize(files.reduce((total, file) => total + file.size, 0));
    if (!files.length) {
      $("rows").innerHTML = '<tr><td colspan="4" class="empty">Tidak ada file.</td></tr>';
      return;
    }
    $("rows").innerHTML = files.map((file) => (
      "<tr>"
      + '<td class="name">' + esc(file.name) + "</td>"
      + '<td class="size">' + esc(fmtSize(file.size)) + "</td>"
      + '<td class="time">' + esc(fmtTime(file.uploaded)) + "</td>"
      + '<td><div class="actions">'
      + '<a class="btn" href="/api/download?key=' + encodeURIComponent(file.key) + '&token=' + encodeURIComponent(state.token) + '">Unduh</a>'
      + '<button class="btn danger" data-delete="' + esc(file.key) + '">Hapus</button>'
      + "</div></td>"
      + "</tr>"
    )).join("");
    document.querySelectorAll("[data-delete]").forEach(function (button) {
      button.addEventListener("click", function () { remove(button.getAttribute("data-delete")); });
    });
  }

  async function upload(fileList) {
    const files = [...fileList];
    if (!files.length) return;
    $("status").textContent = "Mengunggah " + files.length + " file...";
    $("progress").style.display = "block";
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      try {
        await new Promise(function (resolve, reject) {
          const xhr = new XMLHttpRequest();
          xhr.open("PUT", "/api/files?name=" + encodeURIComponent(file.name));
          xhr.setRequestHeader("authorization", "Bearer " + state.token);
          xhr.setRequestHeader("content-type", file.type || "application/octet-stream");
          xhr.upload.onprogress = function (event) {
            if (!event.lengthComputable) return;
            const overall = ((index + event.loaded / event.total) / files.length) * 100;
            $("progressBar").style.width = overall + "%";
          };
          xhr.onload = function () {
            if (xhr.status >= 200 && xhr.status < 300) resolve();
            else reject(new Error("Gagal mengunggah " + file.name));
          };
          xhr.onerror = function () { reject(new Error("Koneksi terputus saat mengunggah " + file.name)); };
          xhr.send(file);
        });
      } catch (error) {
        $("status").textContent = error.message;
      }
    }
    $("progress").style.display = "none";
    $("progressBar").style.width = "0%";
    $("status").textContent = "Selesai.";
    await loadFiles();
  }

  async function remove(key) {
    if (!confirm("Hapus file ini secara permanen?")) return;
    try {
      await api("/api/files?key=" + encodeURIComponent(key), { method: "DELETE" });
      await loadFiles();
    } catch (error) { $("status").textContent = error.message; }
  }

  async function login() {
    const token = $("token").value.trim();
    if (!token) return showLogin("Token wajib diisi.");
    state.token = token;
    try {
      const response = await fetch("/api/files", { headers: { authorization: "Bearer " + token } });
      if (!response.ok) throw new Error("Token tidak valid.");
      localStorage.setItem("bangkah_files_token", token);
      showFiles();
      await loadFiles();
    } catch (error) {
      state.token = "";
      showLogin(error.message);
    }
  }

  $("loginBtn").addEventListener("click", login);
  $("token").addEventListener("keydown", function (event) { if (event.key === "Enter") login(); });
  $("logout").addEventListener("click", function () { localStorage.removeItem("bangkah_files_token"); state.token = ""; showLogin(); });
  $("refresh").addEventListener("click", loadFiles);
  $("search").addEventListener("input", render);
  $("drop").addEventListener("click", function () { $("fileInput").click(); });
  $("fileInput").addEventListener("change", function (event) { upload(event.target.files); });
  ["dragenter", "dragover"].forEach(function (name) {
    $("drop").addEventListener(name, function (event) { event.preventDefault(); $("drop").classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (name) {
    $("drop").addEventListener(name, function (event) { event.preventDefault(); $("drop").classList.remove("over"); });
  });
  $("drop").addEventListener("drop", function (event) { upload(event.dataTransfer.files); });

  if (state.token) { showFiles(); loadFiles(); } else { showLogin(); }
</script>
</body>
</html>`;
}

async function handleRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === "/api/health") {
    return json({ status: "ok", service: "bangkah-files" });
  }

  if (url.pathname === "/" && request.method === "GET") {
    return new Response(appHtml(), { headers: { "content-type": "text/html; charset=utf-8" } });
  }

  // Unduhan mendukung ?token= agar tautan dari UI bisa langsung dipakai.
  if (url.pathname === "/api/download" && request.method === "GET") {
    const token = url.searchParams.get("token") || "";
    if (token && env.FILES_TOKEN && (await safeEqual(token, env.FILES_TOKEN))) {
      return downloadFile(request, env);
    }
  }

  const user = await authorize(request, env);
  if (!user) {
    return new Response("Unauthorized", {
      status: 401,
      headers: { "www-authenticate": 'Basic realm="Bangkah Files", charset="UTF-8"' },
    });
  }

  if (url.pathname === "/api/files" && request.method === "GET") return listFiles(request, env);
  if (url.pathname === "/api/files" && request.method === "PUT") return uploadFile(request, env, user);
  if (url.pathname === "/api/files" && request.method === "DELETE") return deleteFile(request, env);
  if (url.pathname === "/api/download" && request.method === "GET") return downloadFile(request, env);

  return json({ error: "Not found" }, 404);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },
};
