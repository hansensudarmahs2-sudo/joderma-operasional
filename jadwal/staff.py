"""Staf dua cabang dan PIC-nya, per arahan product owner 29 September 2026.

Sumber: memo penunjukan 002–005 (KP-178), KP-169 (Regitta, Citraland), KP-212
(PIC apotek per cabang), `memory/08-KASIR.md` §20 (cadangan kasir Arsi, Luki,
Elvira), jadwal jaga Oktober 2026.

Catatan peran:
- Semua yang ikut giliran tindakan berkomisi memegang peran PERAWAT, termasuk
  Desy (bidan) dan Heni serta Regitta (perawat merangkap Koordinator Shift).
- FRONT_DESK dipakai sebagai "boleh menjadi kasir hari itu". Di Jemur: Desy (PIC
  Kasir) dan cadangannya. Di Citraland belum ada penetapan kasir; sementara
  diberikan kepada Ayu dan Nanda (tenaga apotek), dapat diubah lewat Admin.
- Yani dan Luki bertugas di dua cabang, jadi memegang peran di keduanya.
"""
from __future__ import annotations

import datetime as dt

from accounts.models import PicFunction, Role

JMR = "jemur-andayani"
CTL = "citraland"

S = Role.STAF

STAFF = [
    # username, nama tampilan, jabatan, {cabang: [peran]}, [(cabang, fungsi PIC, mulai)]
    ("heni", "Heni", "Perawat · Koordinator Shift Jemur",
     {JMR: [Role.PERAWAT, Role.SUPERVISOR, Role.PIC, S]},
     [(JMR, PicFunction.SHIFT_COORDINATOR, dt.date(2026, 9, 2))]),
    ("desy", "Desy", "Bidan · PIC Kasir dan Koordinator Layanan Daring Jemur",
     {JMR: [Role.PERAWAT, Role.FRONT_DESK, Role.ONLINE, Role.PIC, S]},
     [(JMR, PicFunction.CASHIER, dt.date(2026, 9, 2)), (JMR, PicFunction.ONLINE, dt.date(2026, 9, 2))]),
    ("elvira", "Elvira, Apt.", "Apoteker · PIC Apotek dan PJ Kebersihan dan Sterilitas Jemur",
     {JMR: [Role.APOTEKER, Role.FRONT_DESK, Role.PIC, S]},
     [(JMR, PicFunction.PHARMACY, dt.date(2026, 9, 27)), (JMR, PicFunction.CLEANLINESS, dt.date(2026, 9, 2))]),
    ("alya", "Alya", "Perawat", {JMR: [Role.PERAWAT, S]}, []),
    ("lia", "Lia", "Perawat", {JMR: [Role.PERAWAT, S]}, []),
    ("yani", "Yani", "Perawat (Jemur; Minggu tertentu di Citraland)",
     {JMR: [Role.PERAWAT, S], CTL: [Role.PERAWAT, S]}, []),
    ("arsi", "Arsi", "Asisten Apoteker · cadangan kasir",
     {JMR: [Role.ASISTEN_APOTEKER, Role.FRONT_DESK, S]}, []),
    ("luki", "Luki", "Purchasing · Asisten Apoteker · cadangan kasir",
     {JMR: [Role.ASISTEN_APOTEKER, Role.FRONT_DESK, S], CTL: [Role.ASISTEN_APOTEKER, Role.FRONT_DESK, S]}, []),
    ("regitta", "Regitta", "Perawat · Koordinator Shift dan Layanan Daring Citraland",
     {CTL: [Role.PERAWAT, Role.SUPERVISOR, Role.ONLINE, Role.PIC, S]},
     [(CTL, PicFunction.SHIFT_COORDINATOR, dt.date(2026, 9, 21)), (CTL, PicFunction.ONLINE, dt.date(2026, 9, 21))]),
    ("ayu", "Ayu (Rahayu)", "Apoteker · PIC Apotek Citraland",
     {CTL: [Role.APOTEKER, Role.FRONT_DESK, Role.PIC, S]},
     [(CTL, PicFunction.PHARMACY, dt.date(2026, 9, 27))]),
    ("nanda", "Nanda", "Asisten Apoteker", {CTL: [Role.ASISTEN_APOTEKER, Role.FRONT_DESK, S]}, []),
    ("naya", "Naya", "Perawat (pindah dari Jemur)", {CTL: [Role.PERAWAT, S]}, []),
    ("silvi", "Silvi", "Perawat", {CTL: [Role.PERAWAT, S]}, []),
]

# Ejaan lain yang mungkin sudah dipakai sebagai username (lama -> baru). Dijalankan
# sesudah `rapikan_akun` membuang akhiran _pic, jadi `heny_pic` -> `heny` -> `heni`.
RENAMES = {"heny": "heni", "regita": "regitta", "rahayu": "ayu", "aliya": "alya", "aliyah": "alya"}
