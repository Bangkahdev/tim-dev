"""Cloudflare Email Routing setup for Bangkah.

This enables free email forwarding from @bangkah.web.id to any personal email.
Usage:
    python setup_email_routing.py
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

import requests

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def get_zone_id(token: str, domain: str) -> str | None:
    resp = requests.get(
        f"{CLOUDFLARE_API}/zones",
        headers=_headers(token),
        params={"name": domain},
    )
    data = resp.json()
    if data.get("success") and data.get("result"):
        return data["result"][0]["id"]
    return None


def get_email_routing_settings(token: str, zone_id: str) -> dict[str, Any]:
    resp = requests.get(
        f"{CLOUDFLARE_API}/zones/{zone_id}/email/routing",
        headers=_headers(token),
    )
    return resp.json()


def enable_email_routing(token: str, zone_id: str, domain: str) -> None:
    print(f"Enabling Email Routing for {domain}...")
    
    # Get current settings
    settings = get_email_routing_settings(token, zone_id)
    
    if settings.get("success"):
        result = settings.get("result", {})
        if result.get("enabled"):
            print("Email Routing already enabled")
            return
    
    # Enable email routing
    resp = requests.post(
        f"{CLOUDFLARE_API}/zones/{zone_id}/email/routing",
        headers=_headers(token),
        json={"enabled": True},
    )
    data = resp.json()
    print(f"Enabled: {data.get('success', False)}")


def create_email_rule(token: str, zone_id: str, domain: str, prefix: str, destination: str) -> None:
    """Create email routing rule: prefix@domain -> destination"""
    print(f"Creating rule: {prefix}@{domain} -> {destination}")
    
    resp = requests.post(
        f"{CLOUDFLARE_API}/zones/{zone_id}/email/routing/rules",
        headers=_headers(token),
        json={
            "actions": [{"type": "forward", "value": [destination]}],
            "enabled": True,
            "matchers": [
                {"type": "literal", "field": "to", "value": f"{prefix}@{domain}"}
            ],
            "name": f"{prefix}@{domain}",
        },
    )
    data = resp.json()
    print(f"  Created: {data.get('success', False)}")
    if not data.get("success"):
        print(f"  Error: {data.get('errors', data.get('messages', 'unknown'))}")


def main() -> None:
    load_dotenv()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not token:
        print("ERROR: CLOUDFLARE_API_TOKEN not set")
        sys.exit(1)
    
    domain = os.getenv("BANGKAH_DOMAIN", "bangkah.web.id")
    forwarding_destination = os.getenv("BANGKAH_EMAIL_FORWARDING", "")
    
    if not forwarding_destination:
        print("ERROR: Set BANGKAH_EMAIL_FORWARDING in .env to your personal email")
        print("Example: BANGKAH_EMAIL_FORWARDING=yourname@gmail.com")
        sys.exit(1)
    
    zone_id = get_zone_id(token, domain)
    if not zone_id:
        print(f"ERROR: Zone not found for {domain}")
        sys.exit(1)
    
    print(f"Zone: {domain} ({zone_id})")
    
    # Enable email routing
    enable_email_routing(token, zone_id, domain)
    
    # Create forwarding rules for each employee
    employees = [
        ("owner", "Owner"),
        ("arman", "Arman"),
        ("sinta", "Sinta"),
        ("raka", "Raka"),
        ("bima", "Bima"),
        ("naya", "Naya"),
        ("dira", "Dira"),
        ("tika", "Tika"),
    ]
    
    print("\nCreating email forwarding rules...")
    for prefix, name in employees:
        create_email_rule(token, zone_id, domain, prefix, forwarding_destination)
    
    print("\nEmail Routing setup complete!")
    print(f"All emails to @{domain} will be forwarded to {forwarding_destination}")
    print("\nTo send emails FROM @bangkah.web.id, you need to:")
    print("1. Set up SMTP (SendGrid/Mailgun/Gmail)")
    print("2. Add SPF/DKIM/DMARC records")


if __name__ == "__main__":
    main()
