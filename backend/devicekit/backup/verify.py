"""Backup verify ladder: none → listed → hashed (plan 25 part 6).

The non-obvious correctness lesson: hash the tar's members and compare each to the hash in
the **stored** ``manifest.json`` (written beside the tarball, so a corrupt tar can't have
rewritten it). Never trust a hash recomputed from the same file you're trying to prove good.
"""
import json
import hashlib
import tarfile

from devicekit.models.backup import VERIFY_NONE, VERIFY_LISTED, VERIFY_HASHED


def _load_stored_manifest(manifest_path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_backup(tar_path, manifest_path):
    """Run the ladder against a tarball + its stored manifest.

    Returns ``{level, detail}`` where level is the *highest* rung reached
    (``none`` < ``listed`` < ``hashed``). A tar that lists but whose members' hashes don't
    match the stored manifest stops at ``listed`` with a mismatch detail.
    """
    detail = {"listed": False, "hashed": False}

    # --- listed: the tar is readable and holds the expected members ---
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            members = {m.name: m for m in tar.getmembers()}
    except Exception as e:
        return {"level": VERIFY_NONE, "detail": {"error": f"tar not listable: {e}"}}
    detail["listed"] = True
    detail["members"] = sorted(members)

    # --- hashed: each artifact's tar bytes match the STORED manifest hash ---
    try:
        manifest = _load_stored_manifest(manifest_path)
    except Exception as e:
        return {"level": VERIFY_LISTED, "detail": {**detail,
                "error": f"manifest unreadable: {e}"}}

    mismatches = []
    with tarfile.open(tar_path, "r:gz") as tar:
        for art in manifest.get("artifacts", []):
            name = art["name"]
            member = members.get(name)
            if member is None:
                mismatches.append({"name": name, "error": "missing from tar"})
                continue
            f = tar.extractfile(member)
            if f is None:
                mismatches.append({"name": name, "error": "not a file"})
                continue
            h = hashlib.sha256()
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
            actual = h.hexdigest()
            if actual != art["sha256"]:
                mismatches.append({"name": name, "expected": art["sha256"],
                                   "actual": actual})

    if mismatches:
        detail["mismatches"] = mismatches
        return {"level": VERIFY_LISTED, "detail": detail}
    detail["hashed"] = True
    return {"level": VERIFY_HASHED, "detail": detail}
