"""Workstation and network configuration for Bangkah office.

Usage:
    python setup_workstation.py
    
This will:
1. Create workstation network configuration
2. Set up shared folders
3. Configure printer network
4. Initialize print job database
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.office_store import OfficeStore, ROSTER, _now


BASE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = BASE_DIR / "workspace"
PRINTERS_DIR = BASE_DIR / "prints"


def ensure_dirs() -> None:
    """Create workspace directories for each employee."""
    WORKSPACE_DIR.mkdir(exist_ok=True)
    PRINTERS_DIR.mkdir(exist_ok=True)
    
    # Owner workspace
    owner_dir = WORKSPACE_DIR / "owner"
    owner_dir.mkdir(exist_ok=True)
    (owner_dir / "Documents").mkdir(exist_ok=True)
    (owner_dir / "Projects").mkdir(exist_ok=True)
    (owner_dir / "Desktop").mkdir(exist_ok=True)
    
    # Employee workspaces
    for emp_id in ROSTER:
        if emp_id == "owner":
            continue
        emp_dir = WORKSPACE_DIR / emp_id
        emp_dir.mkdir(exist_ok=True)
        (emp_dir / "Documents").mkdir(exist_ok=True)
        (emp_dir / "Projects").mkdir(exist_ok=True)
        (emp_dir / "Desktop").mkdir(exist_ok=True)


def setup_workstation_config(store: OfficeStore) -> None:
    """Initialize workstation configuration in database."""
    with store._db() as db:
        # Recreate workstations table
        db.execute("DROP TABLE IF EXISTS workstations")
        db.execute("""
            CREATE TABLE workstations (
                id TEXT PRIMARY KEY,
                assigned_to TEXT NOT NULL,
                ip_address TEXT NOT NULL DEFAULT '192.168.1.',
                mac_address TEXT,
                status TEXT NOT NULL DEFAULT 'online',
                last_active TEXT NOT NULL
            )
        """)
        
        # Create print_jobs table
        db.execute("""
            CREATE TABLE IF NOT EXISTS print_jobs (
                id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                document_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                pages INTEGER DEFAULT 1,
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            )
        """)
        
        # Create shared_folders table
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_folders (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                permission_level TEXT NOT NULL DEFAULT 'read',
                created_at TEXT NOT NULL
            )
        """)
        
        # Insert workstation records
        workstations = [
            ("OWNER-PC-001", "owner", "192.168.1.10", "online"),
            ("PC-MGR-001", "lead", "192.168.1.20", "online"),
            ("PC-PM-001", "coo", "192.168.1.21", "online"),
            ("PC-ARCH-001", "architect", "192.168.1.30", "online"),
            ("PC-BE-001", "backend", "192.168.1.40", "online"),
            ("PC-BE-002", "backend", "192.168.1.41", "online"),
            ("PC-API-001", "api", "192.168.1.50", "online"),
            ("PC-FE-001", "frontend", "192.168.1.60", "online"),
            ("PC-QA-001", "qa", "192.168.1.70", "online"),
            ("PRINTER-001", "shared", "192.168.1.200", "online"),
        ]
        
        for ws_id, assigned, ip, status in workstations:
            db.execute("""
                INSERT OR IGNORE INTO workstations (id, assigned_to, ip_address, status, last_active)
                VALUES (?, ?, ?, ?, ?)
            """, (ws_id, assigned, ip, status, _now()))
        
        # Insert shared folders
        shared_folders = [
            ("sf-001", "Company Documents", "\\\\server\\documents", "read"),
            ("sf-002", "Project Files", "\\\\server\\projects", "read_write"),
            ("sf-003", "HR Documents", "\\\\server\\hr", "read"),
            ("sf-004", "Finance", "\\\\server\\finance", "read"),
        ]
        
        for sf_id, name, path, perm in shared_folders:
            db.execute("""
                INSERT OR IGNORE INTO shared_folders (id, name, path, permission_level, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (sf_id, name, path, perm, _now()))


def main() -> None:
    print("Setting up workstations and network...")
    
    store = OfficeStore()
    ensure_dirs()
    setup_workstation_config(store)
    
    print("Workstation setup complete!")
    print("\nWorkstation assigned:")
    for emp_id, (name, role, room) in ROSTER.items():
        print(f"  {name} ({emp_id}): {emp_id}")
    print(f"\nShared folders created in: {WORKSPACE_DIR}")
    print(f"Print queue directory: {PRINTERS_DIR}")


if __name__ == "__main__":
    main()
