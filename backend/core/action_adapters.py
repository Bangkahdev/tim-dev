"""Explicit, post-approval adapters for company actions.

No action is executed when an approval is merely created. The Owner must first
approve it and then explicitly call the outbox execute endpoint. All secrets are
read from backend environment variables and never stored in approval payloads.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import make_msgid
from urllib.parse import urlparse

from .company_operations import OPS


class AdapterError(RuntimeError):
    pass


class DeliveryUncertain(AdapterError):
    """Provider accepted a connection but the final delivery result is unknown."""


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def execute_outbox(outbox_id: str):
    item = OPS.get_outbox_item(outbox_id)
    if item["status"] == "succeeded":
        return {"success": True, "already_completed": True, "outbox": OPS.list_outbox()}
    if item["status"] in ("unknown", "executing"):
        raise AdapterError("Status eksekusi belum dapat dipastikan. Jangan kirim ulang sebelum rekonsiliasi provider.")
    if item["approval_status"] != "approved":
        raise AdapterError("Outbox hanya dapat dieksekusi setelah approval Owner berstatus approved.")
    if item["status"] not in ("queued", "failed", "awaiting_executor"):
        raise AdapterError("Outbox item belum siap dieksekusi.")
    OPS.claim_outbox(outbox_id)
    action = item["action_type"]
    payload = item["payload"]
    try:
        if action == "email.send":
            result = _send_email(outbox_id, payload)
        elif action == "website.deploy":
            result = _trigger_deploy(outbox_id, item["approval_id"], item["payload_sha256"], payload)
        else:
            OPS.update_outbox(outbox_id, "awaiting_executor", error="Tidak ada adapter pengeluaran otomatis. Proses manual diperlukan.")
            return {"success": False, "status": "awaiting_executor", "message": "Aksi pengeluaran memerlukan proses manual."}
        OPS.update_outbox(outbox_id, "succeeded", external_id=str(result.get("external_id", "")), result=result)
        return {"success": True, "status": "succeeded", "result": result}
    except DeliveryUncertain as exc:
        OPS.update_outbox(outbox_id, "unknown", error=str(exc))
        raise AdapterError("Provider tidak memberi hasil final. Outbox ditandai UNKNOWN untuk mencegah duplikasi.") from exc
    except AdapterError as exc:
        OPS.update_outbox(outbox_id, "failed", error=str(exc))
        raise
    except Exception as exc:
        OPS.update_outbox(outbox_id, "failed", error=f"{type(exc).__name__}: {exc}")
        raise AdapterError("Eksekusi gagal. Periksa konfigurasi provider dan audit log.") from exc


def _send_email(outbox_id: str, payload: dict):
    host = _env("SMTP_HOST")
    username = _env("SMTP_USERNAME")
    password = _env("SMTP_PASSWORD")
    sender = _env("SMTP_FROM")
    if not all((host, username, password, sender)):
        raise AdapterError("SMTP belum dikonfigurasi. Isi SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, dan SMTP_FROM.")
    try:
        port = int(_env("SMTP_PORT", "587"))
    except ValueError as exc:
        raise AdapterError("SMTP_PORT harus berupa angka.") from exc
    recipients = payload["to"] if isinstance(payload["to"], list) else [payload["to"]]
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = str(payload["subject"])[:250]
    domain = sender.rsplit("@", 1)[-1].strip(">")
    msg["Message-ID"] = make_msgid(idstring=outbox_id.lower(), domain=domain)
    msg["X-Bangkah-Outbox-ID"] = outbox_id
    msg.set_content(str(payload["body"])[:50000])
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as server:
                server.login(username, password)
                try:
                    refused = server.send_message(msg)
                except Exception as exc:
                    raise DeliveryUncertain(f"Koneksi SMTP terputus saat pengiriman: {type(exc).__name__}") from exc
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(username, password)
                try:
                    refused = server.send_message(msg)
                except Exception as exc:
                    raise DeliveryUncertain(f"Koneksi SMTP terputus saat pengiriman: {type(exc).__name__}") from exc
    except DeliveryUncertain:
        raise
    except (OSError, smtplib.SMTPException) as exc:
        raise AdapterError(f"SMTP tidak dapat dihubungi: {type(exc).__name__}") from exc
    if refused:
        raise DeliveryUncertain("SMTP menerima sebagian penerima dan menolak sebagian lainnya; periksa provider sebelum mengulang.")
    return {"external_id": msg["Message-ID"], "provider": "smtp", "recipient_count": len(recipients)}


def _trigger_deploy(outbox_id: str, approval_id: str, payload_hash: str, payload: dict):
    url = _env("DEPLOY_WEBHOOK_URL")
    token = _env("DEPLOY_WEBHOOK_TOKEN")
    if not url or not token:
        raise AdapterError("Webhook deployment belum dikonfigurasi.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AdapterError("DEPLOY_WEBHOOK_URL wajib menggunakan HTTPS.")
    request_body = {
        "outbox_id": outbox_id,
        "approval_id": approval_id,
        "payload_sha256": payload_hash,
        "repository": payload["repository"],
        "ref": payload["ref"],
        "target": payload.get("target", "production"),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                 "Idempotency-Key": outbox_id},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            # Keep provider response bodies out of the database and API response.
            # They may contain internal deployment details or echoed request data.
            return {"external_id": response.headers.get("X-Deployment-ID", ""),
                    "provider": "deployment_webhook", "http_status": response.status}
    except urllib.error.HTTPError as exc:
        # Do not echo remote provider response bodies into logs or the owner UI.
        exc.read(4000)
        if exc.code >= 500:
            raise DeliveryUncertain(f"Webhook deployment mengembalikan HTTP {exc.code}; status remote perlu diperiksa.") from exc
        raise AdapterError(f"Webhook deployment menolak permintaan (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DeliveryUncertain("Koneksi webhook deployment terputus; periksa status deployment sebelum mengulang.") from exc
