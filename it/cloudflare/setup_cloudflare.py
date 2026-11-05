#!/usr/bin/env python3
"""Provisioning Cloudflare untuk perusahaan Bangkah.

Sekali jalan, script ini menyiapkan seluruh infrastruktur online:

1. Verifikasi API token dan akun Cloudflare
2. Cari zone bangkah.web.id
3. Buat database D1  : bangkah-contacts, bangkah-mail
4. Buat bucket R2    : bangkah-files, bangkah-mail
5. Tulis ID ke file wrangler.jsonc (bangkah-web, bangkah-mail, bangkah-files)
6. Deploy Workers    : bangkah-web, bangkah-mail, bangkah-files
7. Aktifkan Email Routing + record MX/SPF/DKIM + DMARC
8. Buat aturan catch-all -> Worker mail (arsip semua @bangkah.web.id)
9. Buat kredensial (MAIL_API_TOKEN, FILES_TOKEN, ADMIN_TOKEN) -> credentials/

Pemakaian:
    export CLOUDFLARE_API_TOKEN=...   # token dengan izin (lihat README)
    export CLOUDFLARE_ACCOUNT_ID=...  # opsional jika token punya akses ke >1 akun
    export OWNER_EMAIL=...            # alamat tujuan penerusan email (mis. Gmail pribadi)
    python3 setup_cloudflare.py
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IT_DIR = Path(__file__).resolve().parents[1]
CREDENTIALS_DIR = IT_DIR / "credentials"
WRANGLER_BIN = ROOT / "bangkah-web" / "node_modules" / "wrangler" / "bin" / "wrangler.js"
BASE_DIR = ROOT / "bangkah-web"

API = "https://api.cloudflare.com/client/v4"
DOMAIN = "bangkah.web.id"

ZONE = {}
ACCOUNT = {}
TOKEN = ""
OWNER_EMAIL = "mdhyaulatha@gmail.com"


def api_call(method: str, endpoint: str, payload: dict | None = None, allow_fail: bool = False) -> dict:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API}{endpoint}",
        data=data,
        method=method,
        headers={
            "authorization": f"Bearer {TOKEN}",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:400]
        if allow_fail:
            return {"success": False, "http": error.code, "error": detail}
        raise SystemExit(f"[x] API {method} {endpoint} -> HTTP {error.code}: {detail}") from error
    if not body.get("success") and not allow_fail:
        raise SystemExit(f"[x] API gagal: {method} {endpoint} -> {body.get('errors')}")
    return body


def first_result(body: dict) -> dict | None:
    results = body.get("result")
    return results[0] if isinstance(results, list) and results else results


def run_wrangler(args: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    command = ["node", str(WRANGLER_BIN), *args]
    env = dict(os.environ, CLOUDFLARE_API_TOKEN=TOKEN)
    if os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        env["CLOUDFLARE_ACCOUNT_ID"] = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    return subprocess.run(
        command,
        cwd=str(BASE_DIR),
        env=env,
        capture_output=capture,
        text=True,
    )


def wrangler_json(args: list[str]) -> dict:
    result = run_wrangler(args, capture=True)
    if result.returncode != 0:
        raise SystemExit(f"[x] wrangler {' '.join(args)} gagal:\n{result.stderr or result.stdout}")
    return json.loads(result.stdout)


def verify_token() -> None:
    body = api_call("GET", "/user/tokens/verify")
    status = body["result"].get("status")
    print(f"[+] Token valid ({status}).")


def find_account() -> None:
    global ACCOUNT
    explicit = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if explicit:
        body = api_call("GET", f"/accounts/{explicit}")
        ACCOUNT = body["result"]
        return
    body = api_call("GET", "/accounts")
    accounts = body["result"]
    if not accounts:
        raise SystemExit("[x] Tidak punya akses ke akun Cloudflare mana pun dengan token ini.")
    prefer = "155d49116414c2ec2461da423cc17ba2"
    match = next((account for account in accounts if account["id"] == prefer), accounts[0])
    ACCOUNT = match
    print(f"[+] Akun: {ACCOUNT['name']} ({ACCOUNT['id']})")


def find_zone() -> None:
    global ZONE
    body = api_call("GET", f"/zones?name={DOMAIN}")
    zones = body["result"]
    if not zones:
        raise SystemExit(f"[x] Zone {DOMAIN} tidak ditemukan pada account {ACCOUNT['id']}.")
    ZONE = zones[0]
    print(f"[+] Zone: {ZONE['name']} ({ZONE['id']})")


def ensure_d1() -> None:
    listing = api_call("GET", f"/accounts/{ACCOUNT['id']}/d1/database")["result"]
    existing = {database["name"] for database in listing}
    for name in ("bangkah-contacts", "bangkah-mail"):
        if name in existing:
            print(f"[=] D1 '{name}' sudah ada.")
        else:
            info = api_call("POST", f"/accounts/{ACCOUNT['id']}/d1/database", {"name": name})["result"]
            print(f"[+] D1 '{name}' dibuat ({info['uuid']}).")


def d1_uuid(name: str) -> str:
    listing = api_call("GET", f"/accounts/{ACCOUNT['id']}/d1/database")["result"]
    for database in listing:
        if database["name"] == name:
            return database["uuid"]
    raise SystemExit(f"[x] D1 {name} tidak ditemukan.")


def patch_wrangler_configs() -> None:
    contacts_id = d1_uuid("bangkah-contacts")
    mail_id = d1_uuid("bangkah-mail")

    for path, mapping in (
        (BASE_DIR / "wrangler.jsonc", {"DB": contacts_id}),
        (ROOT / "bangkah-mail" / "wrangler.jsonc", {"MAIL_DB": mail_id}),
    ):
        text = path.read_text(encoding="utf-8")
        updated = text
        for binding, uuid in mapping.items():
            pattern = re.compile(
                '("binding"\\s*:\\s*"%s"[^\\n]*?"database_id"\\s*:\\s*)"[^"]*"' % binding
            )
            updated = pattern.sub('\\1"%s"' % uuid, updated)
        if updated != text:
            if not updated.endswith("\n"):
                updated += "\n"
            path.write_text(updated, encoding="utf-8")
            print(f"[+] database_id ditulis ke {path.relative_to(ROOT)}")


def ensure_r2() -> None:
    listing = api_call("GET", f"/accounts/{ACCOUNT['id']}/r2/buckets")["result"]
    existing = {bucket["name"] for bucket in listing["buckets"]}
    for name in ("bangkah-files", "bangkah-mail"):
        if name in existing:
            print(f"[=] R2 '{name}' sudah ada.")
        else:
            api_call("POST", f"/accounts/{ACCOUNT['id']}/r2/buckets", {"name": name})
            print(f"[+] R2 '{name}' dibuat.")


def migrate_d1() -> None:
    env = dict(os.environ, CLOUDFLARE_API_TOKEN=TOKEN)
    if os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        env["CLOUDFLARE_ACCOUNT_ID"] = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    jobs = [
        (BASE_DIR, ["d1", "execute", "bangkah-contacts", "--remote", "--file=worker/migrations/0001_contacts.sql", "-y"]),
        (ROOT / "bangkah-mail", ["d1", "execute", "bangkah-mail", "--remote", "--file=schema.sql", "-y"]),
    ]
    for cwd, args in jobs:
        result = subprocess.run(
            ["node", str(WRANGLER_BIN), *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"[x] Migrasi D1 gagal ({args[3]}):\n{result.stderr or result.stdout}")
        print(f"[+] Skema mulai dijalankan: {args[2]}")


def deploy_website() -> None:
    print("[+] Build website...")
    build = subprocess.run(
        ["node", str(BASE_DIR / "node_modules/next/dist/bin/next"), "build"],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        print(build.stdout or build.stderr)
        raise SystemExit("[x] Build Next.js gagal.")
    print("[+] Deploy bangkah-web...")
    result = run_wrangler(["deploy", "--config", str(BASE_DIR / "wrangler.jsonc")], capture=False)
    if result.returncode != 0:
        raise SystemExit("[x] Deploy bangkah-web gagal.")


def deploy_worker(folder: str) -> None:
    print(f"[+] Deploy {folder}...")
    config = ROOT / folder / "wrangler.jsonc"
    result = run_wrangler(["deploy", "--config", str(config)], capture=False)
    if result.returncode != 0:
        raise SystemExit(f"[x] Deploy {folder} gagal.")


def enable_email_routing() -> None:
    settings = api_call("GET", f"/zones/{ZONE['id']}/email/routing")["result"]
    if settings.get("enabled"):
        print("[=] Email Routing sudah aktif.")
    else:
        api_call("POST", f"/zones/{ZONE['id']}/email/routing/enable")
        print("[+] Email Routing diaktifkan.")

    dns = api_call("POST", f"/zones/{ZONE['id']}/email/routing/dns")
    if dns["result"]:
        print("[+] Record DNS email (MX/SPF/DKIM) dibuat / diverifikasi.")

    dmarc_name = "_dmarc." + DOMAIN
    existing = api_call("GET", f"/zones/{ZONE['id']}/dns_records?type=TXT&name={dmarc_name}")
    records = existing["result"]
    dmarc_value = f"v=DMARC1; p=quarantine; rua=mailto:{OWNER_EMAIL}"
    if records:
        api_call(
            "PUT",
            f"/zones/{ZONE['id']}/dns_records/{records[0]['id']}",
            {
                "type": "TXT",
                "name": dmarc_name,
                "content": dmarc_value,
                "ttl": 3600,
            },
        )
        print("[=] Record DMARC diperbarui.")
    else:
        api_call(
            "POST",
            f"/zones/{ZONE['id']}/dns_records",
            {"type": "TXT", "name": dmarc_name, "content": dmarc_value, "ttl": 3600},
        )
        print("[+] Record DMARC dibuat.")


def ensure_destination() -> None:
    body = api_call("GET", f"/zones/{ZONE['id']}/email/routing/destination_addresses", allow_fail=True)
    destinations = (body.get("result") or []) if body.get("success") else []
    owner_record = next(
        (item for item in destinations if item.get("email", "").lower() == OWNER_EMAIL.lower()),
        None,
    )
    if owner_record is None:
        created = api_call(
            "POST",
            f"/zones/{ZONE['id']}/email/routing/destination_addresses",
            {"email": OWNER_EMAIL},
            allow_fail=True,
        )
        if created.get("success"):
            print(f"[+] Alamat tujuan {OWNER_EMAIL} ditambahkan — periksa email verifikasi dari Cloudflare.")
        else:
            print(f"[!] Tidak bisa menambah tujuan otomatis (HTTP {created.get('http')}). Tambahkan manual di dasbor Cloudflare, Email Routing.")
        return

    status = owner_record.get("verified") or owner_record.get("status")
    if status in (True, "verified", "active"):
        print(f"[=] Alamat tujuan {OWNER_EMAIL} terverifikasi.")
    else:
        print(f"[!] Alamat tujuan {OWNER_EMAIL} belum terverifikasi ({status}). Buka tautan di email verifikasi Cloudflare.")


def set_catch_all() -> None:
    payload = {
        "actions": [{"type": "worker", "value": ["bangkah-mail"]}],
        "enabled": True,
        "name": "Bangkah mail archive",
        "matchers": [{"type": "all"}],
    }
    api_call("PUT", f"/zones/{ZONE['id']}/email/routing/rules/catch_all", payload)
    print("[+] Catch-all email -> Worker bangkah-mail (semua alamat @bangkah.web.id diarsipkan).")


def ensure_forward_config() -> None:
    config_path = ROOT / "bangkah-mail" / "wrangler.jsonc"
    text = config_path.read_text(encoding="utf-8")
    updated = re.sub(r'("FORWARD_TO"\s*:\s*)"[^"]*"', rf'\1"{OWNER_EMAIL}"', text)
    if updated != text:
        config_path.write_text(updated, encoding="utf-8")
        print(f"[+] FORWARD_TO di set ke {OWNER_EMAIL} pada bangkah-mail/wrangler.jsonc")


def write_credentials() -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    env_path = CREDENTIALS_DIR / "company-secrets.env"

    for path in (BASE_DIR / ".dev.vars", ROOT / "bangkah-mail" / ".dev.vars", ROOT / "bangkah-files" / ".dev.vars"):
        path.write_text("", encoding="utf-8")

    mail_token = secrets.token_urlsafe(24)
    files_token = secrets.token_urlsafe(24)
    admin_token = secrets.token_urlsafe(24)

    def put_secret(project: str, name: str, value: str) -> None:
        config = ROOT / project / "wrangler.jsonc"
        result = subprocess.run(
            ["node", str(WRANGLER_BIN), "secret", "put", name, "--config", str(config)],
            input=value + "\n",
            env=dict(os.environ, CLOUDFLARE_API_TOKEN=TOKEN),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"[x] secret put {project}/{name} gagal:\n{result.stderr or result.stdout}")

    put_secret("bangkah-mail", "MAIL_API_TOKEN", mail_token)
    put_secret("bangkah-files", "FILES_TOKEN", files_token)
    put_secret("bangkah-web", "ADMIN_TOKEN", admin_token)

    content = (
        "# Kredensial layanan online Bangkah — JANGAN dibagikan / di-commit.\n"
        f"MAIL_API_TOKEN={mail_token}\n"
        f"FILES_TOKEN={files_token}\n"
        f"ADMIN_TOKEN={admin_token}\n"
        f"OWNER_EMAIL={OWNER_EMAIL}\n"
    )
    env_path.write_text(content, encoding="utf-8")
    env_path.chmod(0o600)
    print(f"[+] Kredensial disimpan di {env_path}")
    print(f"    Mail   : https://mail.bangkah.web.id  (token MAIL_API_TOKEN)")
    print(f"    Files  : https://files.bangkah.web.id (token FILES_TOKEN)")
    print(f"    Admin  : GET https://bangkah.web.id/api/contacts (Bearer ADMIN_TOKEN)")


def main() -> None:
    global TOKEN, OWNER_EMAIL

    TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not TOKEN:
        sys.exit("Set CLOUDFLARE_API_TOKEN terlebih dahulu. Lihat it/cloudflare/README.md.")
    OWNER_EMAIL = os.environ.get("OWNER_EMAIL", OWNER_EMAIL).strip()

    print("=== Bangkah Cloudflare Provisioning ===\n")
    verify_token()
    find_account()
    find_zone()

    ensure_d1()
    ensure_r2()
    patch_wrangler_configs()

    print()
    deploy_worker("bangkah-mail")
    deploy_worker("bangkah-files")
    deploy_website()

    print()
    migrate_d1()

    print()
    enable_email_routing()
    ensure_destination()
    ensure_forward_config()
    deploy_worker("bangkah-mail")  # deploy ulang agar FORWARD_TO ikut
    set_catch_all()

    print()
    write_credentials()

    print()
    print("=== Selesai ===")
    print(f"Website : https://{DOMAIN}")
    print(f"Mail    : https://mail.{DOMAIN}")
    print(f"Files   : https://files.{DOMAIN}")
    print(f"Kredensial: {CREDENTIALS_DIR / 'company-secrets.env'}")


if __name__ == "__main__":
    main()
