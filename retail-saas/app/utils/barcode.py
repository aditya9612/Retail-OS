import hashlib


def generate_barcode(sku: str) -> str:
    digest = hashlib.sha256(sku.encode()).hexdigest()
    numeric = "".join(str(int(c, 16) % 10) for c in digest[:12])
    return numeric
