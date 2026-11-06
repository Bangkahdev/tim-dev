import os, re, ipaddress

def safe_username(u):
    u = str(u or "").strip()
    if not u or len(u) > 64:
        raise ValueError("Username tidak valid.")
    if not re.match(r"^[A-Za-z0-9._-]+$", u):
        raise ValueError("Username mengandung karakter tidak diizinkan.")
    if ".." in u or "/" in u or "\\" in u:
        raise ValueError("Username tidak valid.")
    return u

def safe_path(root, relative):
    root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root, relative or ""))
    if not (target == root or target.startswith(root + os.sep)):
        raise ValueError("Path traversal terdeteksi.")
    return target

def validate_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False

def validate_cidr(value):
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False
