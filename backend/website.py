"""Website perusahaan: paket perubahan, publikasi dengan persetujuan, rollback.

Publikasi nyata dilakukan dengan menyusun ulang folder deploy dari
WEBSITE_SOURCE_DIR, setelah membuat backup folder aktif (WEB-06). Setiap
publikasi memiliki release id yang ditulis ke folder aktif sehingga
rekonsiliasi dapat memeriksa versi yang benar-benar berjalan (WEB-07).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from . import audit, events, papers, settings
from .db import fetch_all, fetch_one, json_dump, json_load, now

RELEASE_MARKER = ".bangkah-release"


class WebsiteError(Exception):
    status_code = 400


def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    row["check_result"] = json_load(row.get("check_result"), {})
    return row


def get_deployment(conn, release_id: str) -> dict[str, Any]:
    row = _decode(fetch_one(conn, "SELECT * FROM website_deployments WHERE id = ?", (release_id,)))
    if not row:
        raise WebsiteError(f"Rilis website {release_id} tidak ditemukan.")
    return row


def list_deployments(conn, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = fetch_all(
        conn,
        "SELECT * FROM website_deployments ORDER BY created_at DESC LIMIT ?",
        (max(1, min(limit, 200)),),
    )
    return [_decode(row) for row in rows]


def create_deployment(
    conn,
    *,
    summary: str,
    diff: str,
    requester: str = "owner",
    task_id: str | None = None,
    auto_deliver: bool = True,
) -> dict[str, Any]:
    summary = (summary or "").strip() or "Perubahan website"
    diff = (diff or "").strip()
    if not diff:
        raise WebsiteError("Paket perubahan website wajib berisi diff atau pratinjau.")
    release_id = f"rel_{uuid.uuid4().hex[:10]}"
    payload = {
        "release_id": release_id,
        "url": settings.WEBSITE_URL,
        "summary": summary,
        "diff": diff,
    }
    bundle = papers.create_approval_bundle(
        conn,
        approval_type="website",
        payload=payload,
        requester=requester,
        summary=f"Publikasi website: {summary}",
        task_id=task_id,
    )
    stamp = now()
    conn.execute(
        """
        INSERT INTO website_deployments
            (id, approval_id, status, summary, diff, url, created_at, updated_at)
        VALUES (?, ?, 'PENDING', ?, ?, ?, ?, ?)
        """,
        (release_id, bundle["approval"]["id"], summary, diff, settings.WEBSITE_URL, stamp, stamp),
    )
    if auto_deliver:
        papers.print_paper(conn, bundle["paper"]["id"], actor=requester)
        bundle["paper"] = papers.deliver_paper(conn, bundle["paper"]["id"], actor=requester)
    audit.log(
        conn, actor=requester, actor_kind="employee", action="website.package_created",
        detail=json_dump({"release_id": release_id, "summary": summary}),
        ref_type="website", ref_id=release_id,
    )
    events.publish(conn, "website.package_created", requester, {"release_id": release_id})
    return {"status": "PENDING_APPROVAL", "deployment": get_deployment(conn, release_id), **bundle}


def _active_version(target: Path) -> str:
    marker = target / RELEASE_MARKER
    try:
        return marker.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _backup(target: Path, release_id: str) -> Path | None:
    if not target.is_dir():
        return None
    destination = settings.WEBSITE_BACKUP_DIR / f"{release_id}-{uuid.uuid4().hex[:6]}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(target, destination)
    return destination


def _publish_files(source: Path, target: Path, release_id: str) -> None:
    if not source.is_dir():
        raise WebsiteError("Folder sumber website tidak ditemukan.")
    source = source.resolve()
    target = target.resolve()
    if source == target or target in source.parents or source in target.parents:
        raise WebsiteError("Folder sumber dan folder deploy tidak boleh sama atau bersarang.")
    target.mkdir(parents=True, exist_ok=True)
    for item in target.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()
    shutil.copytree(source, target, dirs_exist_ok=True)
    (target / RELEASE_MARKER).write_text(release_id, encoding="utf-8")


def _post_check(target: Path, release_id: str) -> dict[str, Any]:
    return {
        "release_marker": _active_version(target) == release_id,
        "index_present": (target / "index.html").is_file(),
        "checked_at": now(),
    }


def set_status_by_approval(conn, approval_id: str, status: str) -> None:
    """Cerminkan keputusan Owner pada paket rilis (ditolak / minta revisi)."""
    conn.execute(
        "UPDATE website_deployments SET status = ?, updated_at = ? WHERE approval_id = ? AND status = 'PENDING'",
        (status, now(), approval_id),
    )


def reattach_revision(
    conn,
    old_approval_id: str,
    new_approval_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Hubungkan paket rilis lama ke persetujuan versi baru (PAP-10)."""
    row = fetch_one(conn, "SELECT * FROM website_deployments WHERE approval_id = ?", (old_approval_id,))
    if not row:
        return None
    conn.execute(
        """
        UPDATE website_deployments
        SET approval_id = ?, summary = ?, diff = ?, status = 'PENDING', updated_at = ?
        WHERE id = ?
        """,
        (
            new_approval_id,
            str(payload.get("summary") or row["summary"]),
            str(payload.get("diff") or row["diff"]),
            now(),
            row["id"],
        ),
    )
    return get_deployment(conn, row["id"])


def reconcile(conn, release_id: str) -> dict[str, Any]:
    """WEB-07: periksa versi yang aktif di server sebelum publikasi diulang."""
    row = get_deployment(conn, release_id)
    active = _active_version(settings.WEBSITE_DEPLOY_DIR)
    return {
        "release_id": release_id,
        "expected": row["version"] or release_id,
        "active": active,
        "in_sync": active == release_id,
    }


def publish(conn, release_id: str, *, actor: str = "owner") -> dict[str, Any]:
    row = get_deployment(conn, release_id)
    if row["status"] == "PUBLISHED":
        return row
    approval = papers.get_approval(conn, row["approval_id"])
    if approval["status"] != "APPROVED":
        raise WebsiteError("Website hanya dapat dipublikasikan setelah disetujui Owner.")
    if papers.payload_hash(approval["payload"]) != approval["payload_hash"]:
        raise WebsiteError("Payload publikasi berubah; publikasi dibatalkan.")
    if _active_version(settings.WEBSITE_DEPLOY_DIR) == release_id:
        return _finish_publish(conn, row, actor, approval, previous="", backup=None, check={"reconciled": True})

    claimed = papers.claim_execution(conn, row["approval_id"], "website")
    if not claimed:
        return get_deployment(conn, release_id)

    target = settings.WEBSITE_DEPLOY_DIR
    previous = _active_version(target)
    backup = _backup(target, release_id)
    try:
        _publish_files(settings.WEBSITE_SOURCE_DIR, target, release_id)
        check = _post_check(target, release_id)
        if not check["release_marker"]:
            raise WebsiteError("Pemeriksaan pasca-publikasi gagal: penanda rilis tidak cocok.")
    except Exception as error:
        conn.execute(
            "UPDATE website_deployments SET status = 'FAILED', updated_at = ? WHERE id = ?",
            (now(), release_id),
        )
        papers.finish_execution(conn, row["approval_id"], status="FAILED", result=str(error)[:500])
        audit.log(
            conn, actor="executor", actor_kind="backend", action="website.publish_failed",
            detail=json_dump({"release_id": release_id, "error": str(error)[:300]}),
            ref_type="website", ref_id=release_id,
        )
        raise
    return _finish_publish(conn, row, actor, approval, previous=previous, backup=backup, check=check)


def _finish_publish(
    conn,
    row: dict[str, Any],
    actor: str,
    approval: dict[str, Any],
    *,
    previous: str,
    backup: Path | None,
    check: dict[str, Any],
) -> dict[str, Any]:
    stamp = now()
    conn.execute(
        """
        UPDATE website_deployments
        SET status = 'PUBLISHED', version = ?, previous_version = ?, backup_path = ?,
            approved_by = ?, published_at = ?, check_result = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            row["id"], previous or None, str(backup) if backup else None,
            approval.get("decided_by") or actor, stamp, json_dump(check), stamp, row["id"],
        ),
    )
    papers.finish_execution(conn, row["approval_id"], status="SUCCEEDED", result="published")
    audit.log(
        conn, actor=actor, actor_kind="owner", action="website.published",
        detail=json_dump(
            {
                "release_id": row["id"],
                "version": row["id"],
                "previous_version": previous,
                "approved_by": approval.get("decided_by"),
                "backup": str(backup) if backup else None,
            }
        ),
        ref_type="website", ref_id=row["id"],
    )
    events.publish(conn, "website.published", actor, {"release_id": row["id"]})
    return get_deployment(conn, row["id"])


def publish_approved(conn, approval_id: str, *, actor: str = "owner") -> dict[str, Any]:
    row = fetch_one(conn, "SELECT id FROM website_deployments WHERE approval_id = ?", (approval_id,))
    if not row:
        raise WebsiteError("Paket rilis untuk persetujuan ini tidak ditemukan.")
    return publish(conn, row["id"], actor=actor)


def rollback(conn, release_id: str, *, actor: str = "owner") -> dict[str, Any]:
    """Kembalikan folder deploy ke backup sebelum rilis ini (WEB-04)."""
    row = get_deployment(conn, release_id)
    if row["status"] not in ("PUBLISHED", "ROLLED_BACK"):
        raise WebsiteError("Hanya rilis yang sudah dipublikasikan yang dapat di-rollback.")
    backup = Path(row["backup_path"]) if row.get("backup_path") else None
    if not backup or not backup.is_dir():
        raise WebsiteError("Backup untuk rilis ini tidak tersedia.")
    target = settings.WEBSITE_DEPLOY_DIR
    target.mkdir(parents=True, exist_ok=True)
    for item in target.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()
    shutil.copytree(backup, target, dirs_exist_ok=True)
    if row.get("previous_version"):
        (target / RELEASE_MARKER).write_text(row["previous_version"], encoding="utf-8")
    stamp = now()
    conn.execute(
        "UPDATE website_deployments SET status = 'ROLLED_BACK', updated_at = ? WHERE id = ?",
        (stamp, release_id),
    )
    audit.log(
        conn, actor=actor, actor_kind="owner", action="website.rolled_back",
        detail=json_dump({"release_id": release_id, "restored_from": str(backup)}),
        ref_type="website", ref_id=release_id,
    )
    events.publish(conn, "website.rolled_back", actor, {"release_id": release_id})
    return get_deployment(conn, release_id)
