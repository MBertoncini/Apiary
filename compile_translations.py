"""
Compila i file .po -> .mo per tutte le lingue in locale/.

Pensato per Windows (dove gettext/msgfmt non e' installato di default).
Implementa il formato GNU MO (https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html).

Uso:
    python compile_translations.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path


def parse_po(path: Path) -> dict[str, str]:
    """Parser .po minimale (sufficiente per i nostri file)."""
    entries: dict[str, str] = {}
    msgid: list[str] = []
    msgstr: list[str] = []
    msgid_plural: list[str] = []
    msgstr_plurals: dict[int, list[str]] = {}
    state: str | None = None
    plural_index: int | None = None

    def flush() -> None:
        nonlocal msgid, msgstr, msgid_plural, msgstr_plurals
        if msgid or msgstr:
            key = "".join(msgid)
            if msgid_plural:
                # Salva singolare e plurale separati da \0 (formato GNU MO)
                singular = "".join(msgstr_plurals.get(0, []))
                plural = "".join(msgstr_plurals.get(1, []))
                entries[key + "\x00" + "".join(msgid_plural)] = singular + "\x00" + plural
            else:
                entries[key] = "".join(msgstr)
        msgid = []
        msgstr = []
        msgid_plural = []
        msgstr_plurals = {}

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            if not line:
                flush()
                state = None
            continue
        if line.startswith("msgid_plural"):
            state = "msgid_plural"
            msgid_plural = [_unquote(line[len("msgid_plural"):].strip())]
            continue
        if line.startswith("msgid"):
            flush()
            state = "msgid"
            msgid = [_unquote(line[len("msgid"):].strip())]
            continue
        if line.startswith("msgstr["):
            # msgstr[N]
            close = line.index("]")
            plural_index = int(line[7:close])
            state = "msgstr_plural"
            msgstr_plurals[plural_index] = [_unquote(line[close + 1:].strip())]
            continue
        if line.startswith("msgstr"):
            state = "msgstr"
            msgstr = [_unquote(line[len("msgstr"):].strip())]
            continue
        # Continuazione di una stringa
        if line.startswith('"'):
            chunk = _unquote(line)
            if state == "msgid":
                msgid.append(chunk)
            elif state == "msgstr":
                msgstr.append(chunk)
            elif state == "msgid_plural":
                msgid_plural.append(chunk)
            elif state == "msgstr_plural" and plural_index is not None:
                msgstr_plurals[plural_index].append(chunk)
    flush()
    return entries


def _unquote(value: str) -> str:
    if not value.startswith('"') or not value.endswith('"'):
        return value
    inner = value[1:-1]
    return inner.encode("utf-8").decode("unicode_escape")


def write_mo(entries: dict[str, str], out_path: Path) -> None:
    """Scrive entries nel formato GNU MO."""
    keys = sorted(entries.keys())
    offsets: list[tuple[int, int, int, int]] = []
    ids = b""
    strs = b""
    for key in keys:
        value = entries[key]
        kb = key.encode("utf-8")
        vb = value.encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\x00"
        strs += vb + b"\x00"

    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets: list[int] = []
    voffsets: list[int] = []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]

    output = struct.pack(
        "Iiiiiii",
        0x950412DE,  # magic
        0,           # version
        len(keys),
        7 * 4,
        7 * 4 + len(keys) * 8,
        0, 0,
    )
    output += struct.pack("i" * len(koffsets), *koffsets)
    output += struct.pack("i" * len(voffsets), *voffsets)
    output += ids
    output += strs

    out_path.write_bytes(output)


def main() -> int:
    base = Path(__file__).resolve().parent / "locale"
    if not base.exists():
        print(f"locale/ non trovata in {base}", file=sys.stderr)
        return 1

    count = 0
    for po in base.glob("*/LC_MESSAGES/*.po"):
        mo = po.with_suffix(".mo")
        try:
            entries = parse_po(po)
            write_mo(entries, mo)
            print(f"  {po.relative_to(base.parent)} -> {mo.name} ({len(entries)} stringhe)")
            count += 1
        except Exception as exc:
            print(f"ERRORE su {po}: {exc}", file=sys.stderr)
            return 2
    print(f"\nCompilati {count} file .po")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
