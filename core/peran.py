"""Tampilan per peran: menu, halaman pertama sesudah login, dan halaman yang boleh dibuka.

Lihat `docs/KEBUTUHAN_REDEFINISI_PERAN.md`. Setiap pengguna punya satu *tampilan*
(persona) yang ditentukan dari perannya:

- ``DIREKTUR``: memegang peran Direktur Operasional (AOM). Melihat semuanya.
- ``OWNER``: Owner / Direktur Utama. Hanya baca: dashboard, keputusan, jadwal.
- ``PIC``: memegang fungsi PIC atau Koordinator Shift. Melihat dan mengatur timnya.
- ``STAF``: staf biasa. Hanya yang ia kerjakan.
- ``ADMIN``: akun sistem (Admin tanpa peran kerja lain). Pengguna, konfigurasi, jadwal.

Menu hanya kemudahan. Pembatasan sebenarnya ada di `route_allowed`, yang dipanggil
`PersonaAccessMiddleware` untuk setiap permintaan, ditambah pemeriksaan izin di masing-masing
view seperti sebelumnya. Keduanya harus lolos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.urls import reverse

from accounts.models import Role

DIREKTUR = "DIREKTUR"
OWNER = "OWNER"
PIC = "PIC"
STAF = "STAF"
ADMIN = "ADMIN"

LABELS = {
    DIREKTUR: "Direktur Operasional",
    OWNER: "Owner / Direktur Utama",
    PIC: "PIC / Koordinator",
    STAF: "Staf",
    ADMIN: "Admin sistem",
}

# Halaman pertama sesudah login.
HOME = {
    DIREKTUR: "direktur:overview",
    OWNER: "owner:dashboard",
    PIC: "core:dashboard",
    STAF: "core:today",
    ADMIN: "accounts:user_list",
}

# Selalu boleh untuk siapa pun yang login.
COMMON = {
    ":home",
    ":health",
    "accounts:login",
    "accounts:logout",
    "accounts:change_password",
    "notifications:*",
}

# Owner / Direktur Utama: daftar yang BOLEH (selain itu 403). Tim, Prioritas, Kanban, dan
# Jadwal Task dibuka dari dalam dashboard, bukan menu utama; Jadwal Jaga dari "Lihat jadwal penuh".
OWNER_ALLOWED = COMMON | {
    "owner:*",
    "direktur:team",
    "direktur:tasks",  # Daftar Task, baca saja (unduh CSV lewat GET)
    "direktur:meeting",  # Bahan rapat Kamis, baca saja
    "direktur:kpi",  # KPI per staf, baca saja (unduh CSV lewat GET)
    "direktur:kpi_staff",
    "jejak:index",  # Jejak kehadiran, baca saja
    "absensi:index",  # Absensi jam kerja, baca saja; unggah ditolak `can_edit_absensi`
    "absensi:staf",
    "absensi:saya",
    "jejak:devices",  # perangkat dikenal, baca saja (POST ditolak di view)
    "direktur:kanban",
    "direktur:matrix",
    "direktur:gantt",
    "direktur:task_detail",  # baca saja; tombol ubah hanya untuk pemberi tugas/Direktur
    "direktur:decisions",
    "direktur:decision_detail",
    "reports:policies",  # Kebijakan berlaku (5 Okt 2026), baca saja
    "jadwal:roster",
    "stok:index",  # Stok Apotek, baca saja; unggah dan parameter tetap ditolak
    "core:attachment",  # foto permintaan/temuan; izin per lampiran diperiksa di view
    # Laporan Masuk lintas cabang (3 Okt 2026) dan detailnya, baca saja (lihat OWNER_READ_ONLY).
    "reports:inbox",
    "issues:detail",
    "reports:laporan_page_detail",
    "reports:masukan_page_detail",
}

# Halaman yang boleh dibuka Owner tetapi tidak boleh dikirimi perubahan (POST ditolak 403).
OWNER_READ_ONLY = {"issues:detail", "reports:laporan_page_detail", "reports:masukan_page_detail"}

# Admin sistem: daftar yang BOLEH. Tidak mengisi checklist, kas, atau data operasional.
ADMIN_ALLOWED = COMMON | {
    "accounts:*",
    "admin:*",  # Django admin (superuser)
    "core:config",
    "core:clinic_profile",
    "checklists:templates",
    "absensi:saya",
    "jadwal:*",
}

# Staf: daftar yang DILARANG (selain itu mengikuti izin masing-masing view).
STAF_BLOCKED = {
    "reports:index",  # Laporan Operasional: rekap seluruh tim
    "reports:export",
    "jadwal:plan",  # Pembagian Tugas seluruh tim; porsinya sendiri ada di Checklist Saya
    "jadwal:day",
    "direktur:*",
    "owner:*",
    "audit:*",
    "jejak:*",
    # Jam kerja seluruh tim tertutup untuk staf; jam kerjanya sendiri terbuka
    # lewat "Absensi saya" (keputusan D5), jadi dilarang per rute, bukan per namespace.
    "absensi:index",
    "absensi:staf",
    "absensi:unggah",
    # Fase 7 (staf sederhana): grid tim diganti halaman "saya". Hari Ini dan Checklist Saya tetap
    # bisa dibuka (aksi hari dan pengisian checklist), hanya tidak ada di menu staf.
    "jadwal:roster",
    "breaks:list",
    "breaks:create",
    "breaks:update",
    "breaks:cancel",
    "nurses:board",
    "nurses:roster",
    "nurses:assign",
    "nurses:cancel",
    "nurses:skip",
    "nurses:ledger",
    "nurses:hand_over",
    "nurses:move",
    "nurses:sync",
    "nurses:tally_day",
    "nurses:tally_correct",
}

# Staf membuka Kas hanya pada hari ia ditugaskan sebagai kasir (porsi kelompok Kas di Pembagian Tugas).
STAF_CASHIER_ONLY = {"cash:*"}


def persona(user) -> str:
    """Satu tampilan per pengguna. Urutan: Direktur, Owner, PIC, Staf, Admin."""
    from core.permissions import roles

    codes = roles(user)
    if Role.AOM in codes:
        return DIREKTUR
    if Role.OWNER in codes:
        return OWNER
    if codes & {Role.PIC, Role.SUPERVISOR}:
        return PIC
    if codes - {Role.ADMIN}:
        return STAF
    if Role.ADMIN in codes or getattr(user, "is_superuser", False):
        return ADMIN
    return STAF


def home_url(user) -> str:
    return reverse(HOME[persona(user)])


def _matches(route: str, patterns: set[str]) -> bool:
    namespace = route.split(":", 1)[0]
    return route in patterns or f"{namespace}:*" in patterns


def route_allowed(user, route: str, method: str = "GET") -> bool:
    """Apakah tampilan pengguna ini boleh membuka rute `namespace:nama` dengan metode itu."""
    who = persona(user)
    if who == OWNER:
        if route in OWNER_READ_ONLY and method not in ("GET", "HEAD"):
            return False
        return _matches(route, OWNER_ALLOWED)
    if who == ADMIN:
        from core.permissions import has_admin_full_access

        # Admin yang diberi akses penuh data bisnis (OWNER_DECISION_REVIEW D8) tidak dibatasi.
        return has_admin_full_access(user) or _matches(route, ADMIN_ALLOWED)
    if who == STAF:
        if _matches(route, STAF_CASHIER_ONLY):
            from jadwal.services import is_cashier_today

            return is_cashier_today(user)
        return not _matches(route, STAF_BLOCKED)
    return True


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------


@dataclass
class NavSection:
    title: str = ""
    # (label, url, path lain yang ikut menyorot menu ini, dipisah spasi)
    items: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, label: str, route: str, query: str = "", also: tuple[str, ...] = ()) -> None:
        # `also`: nama rute, atau awalan path literal (diawali "/") untuk halaman detail ber-id.
        self.items.append((label, reverse(route) + query, " ".join(r if r.startswith("/") else reverse(r) for r in also)))

    def add_group(self, user, key: str) -> None:
        """Satu menu untuk satu kelompok halaman (SUBNAV_GROUPS); halaman lainnya lewat tab di atas halaman."""
        label, tabs, extra = SUBNAV_GROUPS[key]
        allowed = [_tab(t) for t in tabs if route_allowed(user, _tab(t)[1])]
        if allowed:
            first = allowed[0]
            others = tuple(dict.fromkeys(r for _, r, _ in allowed[1:] if r != first[1]))
            self.add(label, first[1], first[2], also=others + tuple(extra))


def _tab(entry) -> tuple[str, str, str]:
    """Tab kelompok: (label, rute) atau (label, rute, query) — mis. Komplain/Masukan/Kerusakan berbagi rute."""
    return entry if len(entry) == 3 else (*entry, "")


# 5 Okt 2026 (product owner): menu Direktur/Owner terlalu panjang. Halaman sejenis digabung jadi satu
# menu; di dalam halaman ada baris tab di atas untuk pindah antarhalaman kelompok itu.
# key: (label menu, [(label tab, rute[, query])], rute/awalan path yang ikut kelompok tanpa tab sendiri)
SUBNAV_GROUPS = {
    # 5 Okt 2026: semua yang datang dari staf satu menu untuk Direktur (daftar lintas cabang).
    "dari_staf": ("Dari staf", [("Komplain", "issues:list", "?tipe=KOMPLAIN"),
                                ("Masukan", "issues:list", "?tipe=MASUKAN"),
                                ("Kerusakan", "issues:list", "?tipe=KERUSAKAN"),
                                ("Laporan staf", "reports:laporan_page"),
                                ("Masukan privat staf", "reports:masukan_page")],
                  ("issues:list",)),  # detail catatan /catatan/<id>/ juga menyorot menu ini
    "task": ("Task", [("Daftar Task", "direktur:tasks"), ("Kanban", "direktur:kanban"),
                      ("Prioritas", "direktur:matrix"), ("Jadwal Task", "direktur:gantt")],
             ("/direktur/task/",)),  # Task baru dan detail task
    "evaluasi": ("Evaluasi staf", [("KPI", "direktur:kpi"), ("Jejak", "jejak:index"),
                                   ("Absensi", "absensi:index")], ()),
    "kebijakan": ("Kebijakan", [("Kebijakan", "reports:policies"), ("Keputusan", "direktur:decisions"),
                                ("Bahan Rapat", "direktur:meeting")], ()),
}
# Halaman detail yang menampilkan tab kelompoknya (tanpa tab aktif).
SUBNAV_DETAIL = {
    "direktur:task_new": "task", "direktur:task_detail": "task", "direktur:kpi_staff": "evaluasi",
    "jejak:devices": "evaluasi", "absensi:staf": "evaluasi", "direktur:decision_detail": "kebijakan",
    "issues:detail": "dari_staf", "reports:laporan_page_detail": "dari_staf",
    "reports:masukan_page_detail": "dari_staf",
}


def subnav(user, view_name: str, params=None) -> dict | None:
    """Baris tab di atas halaman untuk Direktur dan Owner, bila halaman termasuk satu kelompok.

    `params`: request.GET; tab ber-query (mis. ?tipe=MASUKAN) aktif bila query-nya cocok."""
    if persona(user) not in (DIREKTUR, OWNER) or not view_name:
        return None
    key = next((k for k, (_, tabs, _) in SUBNAV_GROUPS.items()
                if any(_tab(t)[1] == view_name for t in tabs)), None)
    key = key or SUBNAV_DETAIL.get(view_name)
    if key is None:
        return None
    label, tabs, _ = SUBNAV_GROUPS[key]
    params = params or {}

    def current(route, query):
        if route != view_name:
            return False
        from urllib.parse import parse_qsl

        return all(params.get(k) == v for k, v in parse_qsl(query.lstrip("?")))

    items = [(name, reverse(r) + q, current(r, q)) for name, r, q in map(_tab, tabs) if route_allowed(user, r)]
    return {"label": label, "items": items} if len(items) > 1 else None


def _report_section(user, flags) -> NavSection:
    lapor = NavSection("Lapor")
    if flags["issues"]:
        lapor.add("Komplain", "issues:list", "?tipe=KOMPLAIN")
        lapor.add("Masukan", "issues:list", "?tipe=MASUKAN")
        lapor.add("Kerusakan", "issues:list", "?tipe=KERUSAKAN")
    lapor.add("Laporan Saya", "reports:laporan_page")
    lapor.add("Masukan Saya", "reports:masukan_page")
    return lapor


def _flags(user) -> dict:
    from core.permissions import (
        can_manage_config,
        can_manage_templates,
        can_manage_users,
        can_view_audit,
        can_view_cash_amounts,
        can_edit_stok,
        can_view_clinic_profile,
        has_role,
        is_nurse,
        is_supervisor,
    )

    return {
        "cash": can_view_cash_amounts(user),
        "orders": has_role(user, Role.ONLINE, Role.APOTEKER, Role.ASISTEN_APOTEKER, Role.SUPERVISOR, Role.PIC),
        "nurses": is_nurse(user) or is_supervisor(user),
        "issues": True,
        "audit": can_view_audit(user),
        "clinic": can_view_clinic_profile(user),
        "users": can_manage_users(user),
        "config": can_manage_config(user),
        "templates": can_manage_templates(user),
        "stok": can_edit_stok(user),
    }


def nav_sections(user) -> list[NavSection]:
    who = persona(user)
    flags = _flags(user)

    if who == OWNER:
        main = NavSection()
        main.add("Dashboard", "owner:dashboard")
        main.add("Inbox", "reports:inbox")
        main.add_group(user, "task")
        main.add_group(user, "evaluasi")
        main.add_group(user, "kebijakan")
        main.add("Summary Harian", "owner:summary")
        main.add("Jadwal", "owner:jadwal")
        main.add("Stok Apotek", "stok:index")
        return [main]

    if who == ADMIN:
        admin = NavSection()
        admin.add("Pengguna", "accounts:user_list")
        admin.add("Reset peran", "accounts:role_reset")
        if flags["config"]:
            admin.add("Konfigurasi", "core:config")
        admin.add("Template Checklist", "checklists:templates")
        admin.add("Pengaturan Klinik", "core:clinic_profile")
        if flags["audit"]:
            admin.add("Audit", "audit:log")
        jadwal = NavSection("Jadwal")
        jadwal.add("Jadwal Jaga", "jadwal:roster")
        jadwal.add("Pembagian Tugas", "jadwal:plan")
        return [admin, jadwal]

    if who == DIREKTUR:
        overview = NavSection()
        overview.add("Ringkasan", "direktur:overview")
        overview.add("Inbox", "reports:inbox")
        overview.add_group(user, "dari_staf")
        overview.add("Tim", "direktur:team")
        overview.add_group(user, "task")
        overview.add_group(user, "evaluasi")
        overview.add_group(user, "kebijakan")
        mine = NavSection("Direktur")
        mine.add("Checklist Direktur", "direktur:checklist")
        mine.add("Summary Harian", "owner:summary")
        mine.add("Catatan", "direktur:notes")
        ops = NavSection("Operasional")
        ops.add("Hari Ini", "core:dashboard")
        ops.add("Checklist Saya", "checklists:index")
        ops.add("Jadwal Jaga", "jadwal:roster")
        ops.add("Pembagian Tugas", "jadwal:plan")
        if flags["nurses"]:
            ops.add("Giliran Perawat", "nurses:board")
        if flags["cash"]:
            ops.add("Kas", "cash:index")
        if flags["orders"]:
            ops.add("Order Produk Online", "orders:index")
        ops.add("Stok Apotek", "stok:index")
        reports = NavSection("Laporan")
        reports.add("Laporan Operasional", "reports:index")
        if flags["audit"]:
            reports.add("Audit", "audit:log")
        settings = NavSection("Pengaturan")
        if flags["clinic"]:
            settings.add("Pengaturan Klinik", "core:clinic_profile")
        if flags["users"] or flags["config"]:
            settings.add("Admin", "accounts:user_list")
        return [s for s in (overview, mine, ops, reports, settings) if s.items]

    if who == STAF:
        return _staff_sections(user, flags)

    # PIC
    work = NavSection()
    work.add("Hari Ini", "core:dashboard")
    work.add("Checklist Saya", "checklists:index")
    team = NavSection("Jadwal")
    team.add("Jadwal Jaga", "jadwal:roster")
    if who == PIC:
        team.add("Pembagian Tugas", "jadwal:plan")
    team.add("Jadwal Istirahat", "breaks:list")
    if flags["nurses"]:
        team.add("Giliran Perawat", "nurses:board")
    if flags["cash"]:
        work.add("Kas", "cash:index")
    if flags["orders"]:
        work.add("Order Produk Online", "orders:index")
    if flags["stok"]:
        work.add("Stok Apotek", "stok:index")
    work.add("Kebijakan", "reports:policies")
    sections = [work, team, _report_section(user, flags)]
    if who == PIC:
        manage = NavSection("Koordinasi")
        manage.add("Laporan Operasional", "reports:index")
        if flags["audit"]:
            manage.add("Audit", "audit:log")
        if flags["templates"]:
            manage.add("Template Checklist", "checklists:templates")
        sections.append(manage)
    if flags["users"] or flags["config"]:
        settings = NavSection("Pengaturan")
        settings.add("Admin", "accounts:user_list")
        sections.append(settings)
    return sections


def _staff_sections(user, flags) -> list[NavSection]:
    """Menu staf (fase 7): hanya yang ia kerjakan hari itu dan jadwalnya sendiri."""
    from jadwal.services import is_cashier_today

    work = NavSection()
    work.add("Tugas hari ini", "core:today")
    work.add("Jadwal saya", "jadwal:mine")
    work.add("Absensi saya", "absensi:saya")
    work.add("Istirahat saya", "breaks:mine")
    if flags["nurses"]:
        work.add("Tindakan saya", "nurses:mine")
    if flags["cash"] and is_cashier_today(user):
        work.add("Kas", "cash:index")
    if flags["orders"]:
        work.add("Order Produk Online", "orders:index")
    if flags["stok"]:
        work.add("Stok Apotek", "stok:index")
    work.add("Kebijakan", "reports:policies")
    return [work, _report_section(user, flags)]
