"""Import katalog produk dari workbook LIST PRODUK JODERMA.xlsx tanpa dependency Excel."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from orders.models import Product

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _col(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    value = 0
    for char in letters:
        value = value * 26 + ord(char) - 64
    return value - 1


def _read_workbook(path):
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iterfind(".//m:t", NS)))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            name = sheet.attrib["name"]
            target = relmap[sheet.attrib[f"{{{NS['r']}}}id"]]
            target = target if target.startswith("xl/") else f"xl/{target}"
            root = ET.fromstring(archive.read(target))
            rows = []
            for row in root.findall("m:sheetData/m:row", NS):
                values = {}
                for cell in row.findall("m:c", NS):
                    value = cell.find("m:v", NS)
                    if value is None:
                        continue
                    text = value.text or ""
                    if cell.attrib.get("t") == "s":
                        text = shared[int(text)]
                    values[_col(cell.attrib["r"])] = text
                rows.append(values)
            yield name, rows


class Command(BaseCommand):
    help = "Import produk topikal dan obat minum dari workbook katalog JoDerma."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)

    def handle(self, *args, **options):
        path = options["path"]
        if not path.exists():
            raise CommandError(f"File tidak ditemukan: {path}")
        if "orders_product" not in connection.introspection.table_names():
            raise CommandError(
                "Tabel katalog belum ada. Jalankan 'python manage.py migrate' "
                "pada database yang sama, lalu ulangi import."
            )
        imported = 0
        for sheet, rows in _read_workbook(path):
            if not rows:
                continue
            header_index = next((i for i, row in enumerate(rows[:4]) if "sediaan topikal" in " ".join(str(v).lower() for v in row.values())), None)
            if header_index is not None:
                kind, name_col, ingredient_col = "Topikal", 2, 3
            else:
                header_index = next((i for i, row in enumerate(rows[:4]) if "nama obat" in " ".join(str(v).lower() for v in row.values())), None)
                if header_index is None:
                    continue
                kind, name_col, ingredient_col = "Obat minum", 2, 3
            category = "Tidak diklasifikasikan"
            for row in rows[header_index + 1:]:
                name = str(row.get(name_col, "")).strip()
                if not name or name.lower() == "none":
                    continue
                if row.get(1):
                    category = str(row[1]).strip()
                # Kolom harga di katalog sengaja tidak dibaca (keputusan 6 Okt 2026).
                Product.objects.update_or_create(
                    category=f"{kind} · {category}",
                    name=name,
                    defaults={"ingredient": str(row.get(ingredient_col, "") or "").strip(), "source": path.name, "active": "RACIKAN" not in category.upper()},
                )
                imported += 1
        self.stdout.write(self.style.SUCCESS(f"Produk diimpor/diperbarui: {imported}"))
