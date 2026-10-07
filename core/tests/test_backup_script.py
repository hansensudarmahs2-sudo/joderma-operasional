"""Uji nyata scripts/backup.sh dan scripts/encrypt_plain_backups.sh.

Script dijalankan dengan bash di direktori sementara (bukan data produksi).
Dilewati bila bash/openssl tidak tersedia.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKUP_SH = REPO / "scripts" / "backup.sh"
ENCRYPT_SH = REPO / "scripts" / "encrypt_plain_backups.sh"
RESTORE_SH = REPO / "scripts" / "restore.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("openssl") is None,
    reason="butuh bash dan openssl",
)

PASS = "rahasia-uji"


@pytest.fixture
def env(tmp_path):
    app = tmp_path / "app"
    (app / "data").mkdir(parents=True)
    conn = sqlite3.connect(app / "data" / "db.sqlite3")
    conn.execute("CREATE TABLE pasien_uji (id INTEGER PRIMARY KEY, nama TEXT)")
    conn.execute("INSERT INTO pasien_uji (nama) VALUES ('x')")
    conn.commit()
    conn.close()
    (app / "private_media").mkdir()
    (app / "private_media" / "a.txt").write_text("lampiran")
    backups = tmp_path / "backups"
    base = {k: v for k, v in os.environ.items() if k not in {"BACKUP_PASSPHRASE", "BACKUP_KIND"}}
    base.update(
        APP_DIR=str(app),
        BACKUP_DIR=str(backups),
        PYBIN=sys.executable,
    )
    return {"app": app, "backups": backups, "env": base, "tmp": tmp_path}


def run(script, env, *args, passphrase=PASS, extra=None):
    e = dict(env["env"])
    if passphrase is not None:
        e["BACKUP_PASSPHRASE"] = passphrase
    e.update(extra or {})
    return subprocess.run(
        ["bash", str(script), *args], env=e, capture_output=True, text=True, timeout=120
    )


def decrypt(path: Path, passphrase=PASS) -> bytes:
    return subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
         "-in", str(path), "-pass", "env:BACKUP_PASSPHRASE"],
        env={**os.environ, "BACKUP_PASSPHRASE": passphrase},
        capture_output=True, check=True,
    ).stdout


def manifest_of(path: Path) -> str:
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(decrypt(path)), mode="r:gz") as tar:
        return tar.extractfile("MANIFEST.txt").read().decode()


def test_daily_run_is_encrypted_and_manifest_kind_daily(env):
    r = run(BACKUP_SH, env)
    assert r.returncode == 0, r.stderr
    files = list((env["backups"] / "daily").iterdir())
    assert len(files) == 1 and files[0].name.endswith(".tar.gz.enc")
    assert "kind=daily" in manifest_of(files[0])
    assert not (env["backups"] / "predeploy").exists()


def test_predeploy_does_not_disturb_daily(env):
    daily = env["backups"] / "daily"
    daily.mkdir(parents=True)
    old = time.time() - 86400
    names = []
    for i in range(7):
        f = daily / f"joderma-ops-2026010{i}-020000.tar.gz.enc"
        f.write_text("dummy")
        os.utime(f, (old + i, old + i))
        names.append(f.name)
    for _ in range(3):
        r = run(BACKUP_SH, env, "--predeploy")
        assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in daily.iterdir()) == sorted(names)
    pre = list((env["backups"] / "predeploy").iterdir())
    assert len(pre) == 3 and all(p.name.endswith(".enc") for p in pre)
    assert "kind=predeploy" in manifest_of(pre[0])
    assert not (env["backups"] / "weekly").exists()
    assert not (env["backups"] / "monthly").exists()


def test_predeploy_keep_limit(env):
    for _ in range(3):
        r = run(BACKUP_SH, env, "--predeploy", extra={"BACKUP_KEEP_PREDEPLOY": "2"})
        assert r.returncode == 0, r.stderr
    assert len(list((env["backups"] / "predeploy").iterdir())) == 2


def test_predeploy_reads_passphrase_from_dotenv_and_restores(env):
    (env["app"] / ".env").write_text('OTHER=1\nBACKUP_PASSPHRASE="secret"\r\n')
    r = run(BACKUP_SH, env, "--predeploy", passphrase=None)
    assert r.returncode == 0, r.stderr
    assert "secret" not in r.stdout + r.stderr
    (archive,) = (env["backups"] / "predeploy").iterdir()
    assert archive.name.endswith(".enc")
    target = env["tmp"] / "restore"
    rr = subprocess.run(
        ["bash", str(RESTORE_SH), str(archive), str(target)],
        env={**env["env"], "BACKUP_PASSPHRASE": "secret"},
        capture_output=True, text=True, timeout=120,
    )
    assert rr.returncode == 0, rr.stderr
    conn = sqlite3.connect(target / "data" / "db.sqlite3")
    assert conn.execute("SELECT count(*) FROM pasien_uji").fetchone()[0] == 1
    conn.close()


def test_predeploy_without_passphrase_fails_and_leaves_no_plain_archive(env):
    r = run(BACKUP_SH, env, "--predeploy", passphrase=None)
    assert r.returncode != 0
    assert "wajib terenkripsi" in r.stderr
    for sub in ("predeploy", "daily"):
        d = env["backups"] / sub
        assert not d.exists() or not list(d.iterdir())
    tmp = env["backups"] / "tmp"
    assert not tmp.exists() or not list(tmp.iterdir())


def test_encrypt_plain_backups_helper(env):
    import tarfile

    daily = env["backups"] / "daily"
    daily.mkdir(parents=True)
    for n in ("a", "b"):
        payload = env["tmp"] / f"{n}.txt"
        payload.write_text(n)
        with tarfile.open(daily / f"joderma-ops-{n}.tar.gz", "w:gz") as tar:
            tar.add(payload, arcname=f"{n}.txt")
    enc_existing = daily / "joderma-ops-keep.tar.gz.enc"
    enc_existing.write_text("sudah terenkripsi")

    r = run(ENCRYPT_SH, env, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert len(list(daily.glob("*.tar.gz"))) == 2
    assert not (env["backups"] / "predeploy").exists()

    r = run(ENCRYPT_SH, env)
    assert r.returncode == 0, r.stderr
    assert not list(daily.glob("*.tar.gz"))
    assert enc_existing.exists()
    out = sorted((env["backups"] / "predeploy").iterdir())
    assert [p.name for p in out] == [
        "joderma-ops-a.tar.gz.enc", "joderma-ops-b.tar.gz.enc",
    ]
    for p in out:
        assert decrypt(p)[:2] == b"\x1f\x8b"


def test_encrypt_plain_backups_requires_passphrase(env):
    daily = env["backups"] / "daily"
    daily.mkdir(parents=True)
    (daily / "joderma-ops-z.tar.gz").write_text("polos")
    r = run(ENCRYPT_SH, env, passphrase=None)
    assert r.returncode != 0
    assert (daily / "joderma-ops-z.tar.gz").exists()


def test_dotenv_inline_comment_is_refused(env):
    (env["app"] / ".env").write_text("BACKUP_PASSPHRASE=secret #komentar\n")
    r = run(BACKUP_SH, env, "--predeploy", passphrase=None)
    assert r.returncode == 1
    assert "ambigu" in r.stderr
    assert "secret" not in r.stdout + r.stderr
    assert not (env["backups"] / "predeploy").exists() or not list(
        (env["backups"] / "predeploy").iterdir()
    )


def test_dotenv_dollar_is_refused(env):
    (env["app"] / ".env").write_text("BACKUP_PASSPHRASE=ab$cd\n")
    r = run(BACKUP_SH, env, "--predeploy", passphrase=None)
    assert r.returncode == 1
    assert "ambigu" in r.stderr


def test_dotenv_edge_whitespace_is_refused_in_helper(env):
    (env["app"] / ".env").write_text("BACKUP_PASSPHRASE= spasi\n")
    daily = env["backups"] / "daily"
    daily.mkdir(parents=True)
    (daily / "joderma-ops-z.tar.gz").write_text("polos")
    r = run(ENCRYPT_SH, env, passphrase=None)
    assert r.returncode == 1
    assert "ambigu" in r.stderr
    assert (daily / "joderma-ops-z.tar.gz").exists()


def test_environment_passphrase_is_used_as_is(env):
    r = run(BACKUP_SH, env, "--predeploy", passphrase="a$b #c")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_keep_predeploy_must_be_positive_integer(env, value):
    r = run(BACKUP_SH, env, "--predeploy", extra={"BACKUP_KEEP_PREDEPLOY": value})
    assert r.returncode == 2
    assert "BACKUP_KEEP_PREDEPLOY" in r.stderr


def test_failing_openssl_leaves_no_plaintext_and_empty_tmp(env):
    fake = env["tmp"] / "fakebin"
    fake.mkdir()
    (fake / "openssl").write_text("#!/bin/sh\nexit 1\n")
    (fake / "openssl").chmod(0o755)
    r = run(
        BACKUP_SH, env, "--predeploy",
        extra={"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"},
    )
    assert r.returncode != 0
    leftovers = [
        p for p in env["backups"].rglob("*") if p.is_file() and p.name != ".gitkeep"
    ]
    assert leftovers == []
    assert list((env["backups"] / "tmp").iterdir()) == []


def test_helper_skips_existing_enc_without_overwriting(env):
    daily = env["backups"] / "daily"
    pre = env["backups"] / "predeploy"
    daily.mkdir(parents=True)
    pre.mkdir(parents=True)
    (daily / "joderma-ops-q.tar.gz").write_text("polos")
    (pre / "joderma-ops-q.tar.gz.enc").write_text("jangan-ditimpa")
    r = run(ENCRYPT_SH, env)
    assert r.returncode == 0, r.stderr
    assert (pre / "joderma-ops-q.tar.gz.enc").read_text() == "jangan-ditimpa"
    assert (daily / "joderma-ops-q.tar.gz").exists()


def test_dockerignore_excludes_secrets_and_data():
    lines = {
        ln.strip() for ln in (REPO / ".dockerignore").read_text().splitlines()
    }
    for entry in (".env", "data/", "private_media/", "backups/", "logs/"):
        assert entry in lines, f".dockerignore tidak memuat {entry}"
    assert "!.env.example" in lines
    for needed in ("scripts", "static", "templates", "requirements.txt", "gunicorn.conf.py"):
        assert needed not in lines and f"{needed}/" not in lines
