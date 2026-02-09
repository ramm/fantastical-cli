"""Extract binary plist from a signed .shortcut (AEA container).

Usage: uv run python _experiments/_tools/extract_plist.py <shortcut_file> [--json]

Signed .shortcut files are AEA (Apple Encrypted Archive) containers.
This tool extracts the signing cert, decrypts the archive, and parses
the embedded binary plist.

Output: pretty-printed plist dict (Python repr by default, JSON with --json).
"""
import json
import plistlib
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def extract_plist(shortcut_path: str | Path) -> dict:
    """Extract and parse the binary plist from a signed .shortcut file."""
    data = Path(shortcut_path).read_bytes()

    # AEA1 header: 4 bytes magic + 4 bytes padding + 4 bytes LE uint32 (header plist size)
    header_size = struct.unpack("<I", data[8:12])[0]
    header = plistlib.loads(data[12:12 + header_size])
    cert_der = header["SigningCertificateChain"][0]

    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = Path(tmpdir) / "cert.der"
        pubkey_path = Path(tmpdir) / "pubkey.pem"
        decrypted_path = Path(tmpdir) / "decrypted.bin"

        cert_path.write_bytes(cert_der)

        subprocess.run(
            ["openssl", "x509", "-inform", "DER",
             "-in", str(cert_path), "-pubkey", "-noout",
             "-out", str(pubkey_path)],
            check=True, capture_output=True,
        )

        subprocess.run(
            ["aea", "decrypt",
             "-i", str(shortcut_path),
             "-o", str(decrypted_path),
             "-sign-pub", str(pubkey_path)],
            check=True, capture_output=True,
        )

        decrypted = decrypted_path.read_bytes()
        bplist_offset = decrypted.find(b"bplist00")
        if bplist_offset == -1:
            raise ValueError("No bplist00 magic found in decrypted data")
        return plistlib.loads(decrypted[bplist_offset:])


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <shortcut_file> [--json]", file=sys.stderr)
        sys.exit(1)

    shortcut_path = sys.argv[1]
    use_json = "--json" in sys.argv

    plist = extract_plist(shortcut_path)

    if use_json:
        print(json.dumps(plist, indent=2, default=str))
    else:
        from pprint import pprint
        pprint(plist)


if __name__ == "__main__":
    main()
