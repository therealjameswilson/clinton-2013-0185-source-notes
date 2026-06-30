#!/usr/bin/env python3
"""Build FRUS-style Clinton Library source-note entries from 2013-0185-M PDFs."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "downloads"
DATA_DIR = ROOT / "data"
SOURCE_PDF_DIR = ROOT / "source-pdfs"

PDFS = [
    {"part": 1, "file": "2013-0185-M_Part1.pdf", "path": SOURCE_PDF_DIR / "2013-0185-M_Part1.pdf"},
    {"part": 2, "file": "2013-0185-M_Part2.pdf", "path": SOURCE_PDF_DIR / "2013-0185-M_Part2.pdf"},
    {"part": 3, "file": "2013-0185-M_Part3.pdf", "path": SOURCE_PDF_DIR / "2013-0185-M_Part3.pdf"},
    {"part": 4, "file": "2013-0185-M_Part4.pdf", "path": SOURCE_PDF_DIR / "2013-0185-M_Part4.pdf"},
]

COLLECTION = "Clinton Presidential Records"
REPOSITORY = "Clinton Library"
FORMAL_REPOSITORY = "William J. Clinton Presidential Library"
SERIES = "National Security Council"
REQUEST_ID = "2013-0185-M"

OUTPUT_BASE = "clinton-2013-0185-m-source-note-entries"
JSON_PATH = REPORTS / f"{OUTPUT_BASE}.json"
CSV_PATH = REPORTS / f"{OUTPUT_BASE}.csv"
MD_PATH = REPORTS / f"{OUTPUT_BASE}.md"
TXT_PATH = REPORTS / f"{OUTPUT_BASE}.txt"
MIN_JSON_PATH = DATA_DIR / "entries.min.json"
SUMMARY_PATH = DATA_DIR / "summary.json"

ROW_RE = re.compile(r"^\s*(?P<oa>\d{2,5}[A-Z]?)\s{2,}(?P<body>.+?)\s*$")
HEADER_RE = re.compile(r"\bOA/ID(?:\s+Number)?\b.*\bFolder\b.*\bNotes\b", re.I)

SKIP_LINE_PATTERNS = [
    r"^OA/ID\s*$",
    r"^Number\s+Folder\s+Notes\s*$",
    r"^OA/ID\s+Number\s+Folder\s+Notes\s*$",
    r"^Folder\s+Notes\s*$",
    r"^Withdrawal/Redaction",
    r"^Clinton Library\s*$",
    r"^DOCUMENT NO\.",
    r"^SUBJECT/TITLE\b",
    r"^AND TYPE\s*$",
    r"^COLLECTION:\s*$",
    r"^FOLDER TITLE:\s*$",
    r"^RESTRICTION CODES\s*$",
    r"^Presidential Records Act\b",
    r"^Freedom of Information Act\b",
    r"^\[5 U\.S\.C\. 552",
    r"^(P[1-6]|b\([1-9]\)|C\.|PRM\.|RR\.)\b",
    r"^of gift\.$",
    r"^2201\(3\)\.$",
    r"^personal privacy",
    r"^purposes \[\(b\)\(7\)",
    r"^financial institutions",
    r"^concerning wells",
    r"^2013-0185-M\s*$",
    r"^kh2069\s*$",
    r"^-+$",
]
SKIP_LINE_RES = [re.compile(pattern, re.I) for pattern in SKIP_LINE_PATTERNS]

NOTEISH_RE = re.compile(
    r"(Access Managemen\w*|NSC Admin(?:/Security)?|Records Management|Speechwriting|"
    r"Executive Secretary|White House Situation Room|Press|Communications|Counsel|"
    r"Legal Advisor|Staff Director|Democracy/Human Rights|"
    r"Transnational Threats|Environmental Affairs|Legislative Affairs|Protocol|"
    r"Domestic Policy|Public Affairs|Personnel|Administration|Defense Policy|"
    r"Intelligence Programs|Inter-American Affairs|International Economic Affairs|"
    r"International Health Affairs|European Affairs|African Affairs|Asian Affairs|"
    r"Southeast European Affairs|Multilateral & Humanitarian Affairs|"
    r"Russia/Ukraine/Eurasian Affairs|Near East and South Asian Affairs|"
    r"Office of the National Security Advisor|Campaign/Transition|"
    r"Nonproliferation and Export Controls|ISCAP|Transition|"
    r"[A-Z][A-Za-z/& ]+-[A-Z][A-Za-z!.]+,\s*[A-Z])",
    re.I,
)

RESTRICTION_RES = [
    re.compile(r"\bE\.?\s*O\.?\s*13526\s*3\.5\s*\(c\)\b", re.I),
    re.compile(r"\bE\.?\s*O\.?\s*12958\s*3\.6\s*\(b\)\b", re.I),
    re.compile(r"(?<![A-Za-z0-9])\(b\)\s*\([1-9]\)(?![A-Za-z0-9])", re.I),
    re.compile(r"(?<![A-Za-z0-9])b\([1-9]\)(?![A-Za-z0-9])", re.I),
    re.compile(r"\bP[1-6]\s*/\s*b\([1-9]\)\b", re.I),
]

NOTE_FIXES = [
    (r"\bAccess Managemen[ilt1!]+\b", "Access Management"),
    (r"\bMuitilateral\b", "Multilateral"),
    (r"\bMuttilateral\b", "Multilateral"),
    (r"\bMultitateral\b", "Multilateral"),
    (r"\bMultilateral!\b", "Multilateral"),
    (r"\bSoutheastem\b", "Southeastern"),
    (r"\bNoriand\b", "Norland"),
    (r"\bHuriey\b", "Hurley"),
    (r"\bDanie!\b", "Daniel"),
    (r"\bWippman,\s+David\s+et\s+al\.\b", "Wippman, David et al."),
    (r"\bMcE!ldowney\b", "McEldowney"),
    (r"\bMcEidowney\b", "McEldowney"),
    (r"\bippman,\s+David\b", "Wippman, David"),
    (r"\bDefense PolicyBel+\s*Robert\b", "Defense Policy-Bell, Robert"),
    (r"\bDefense PolicyBel+,\s*Robert\b", "Defense Policy-Bell, Robert"),
]

TITLE_FIXES = [
    (r"\blreland\b", "Ireland"),
    (r"\bireland\b", "Ireland"),
    (r"\blraq\b", "Iraq"),
    (r"\blran\b", "Iran"),
    (r"\bPo!-Mil\b", "Pol-Mil"),
    (r"\bFall 200C\b", "Fall 2000"),
    (r"\bExlm\b", "ExIm"),
]

SUSPECT_RE = re.compile(r"[!{}]|(?:\b[A-Za-z]+1\b)|(?:\[[^\]]*$)|(?:\([^\)]*$)")
FINDING_AID_ARTIFACT_FIXES = [
    (r"\b2013-0185-M\b", " "),
    (r"\bKBH\s+\d{1,2}/\d{1,2}/\d{4}\b", " "),
    (r"\bDECLASSIFIED\s+IN\s+PART\b", " "),
    (r"\bPER\s*E\.?\s*[O0]\.?\s*13526\b", " "),
    (r"\bPERE\.?\s*[O0]\.?\s*13526\b", " "),
    (r"\bB?E\.?\s*[O0]\.?\s*13526(?:\s*3\.5\s*\(c\))?\b", " "),
]


def ascii_clean(value: str) -> str:
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = unicodedata.normalize("NFKC", value)
    return value.encode("ascii", "ignore").decode("ascii")


def clean_spaces(value: str) -> str:
    value = ascii_clean(value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:])", r"\1", value)
    return value.strip()


def strip_finding_aid_artifacts(value: str) -> str:
    value = clean_spaces(value)
    for pattern, replacement in FINDING_AID_ARTIFACT_FIXES:
        value = re.sub(pattern, replacement, value, flags=re.I)
    return clean_spaces(value)


def clean_note(value: str) -> str:
    value = strip_finding_aid_artifacts(value)
    value = re.sub(
        r"(Nonproliferation and Export Controls-Samore, Gary/Poneman,)\s+\1",
        r"\1",
        value,
    )
    for pattern, replacement in NOTE_FIXES:
        value = re.sub(pattern, replacement, value)
    value = re.sub(r"\s*-\s*", "-", value)
    value = re.sub(r",\s*,", ",", value)
    return clean_spaces(value).rstrip(",")


def clean_title(value: str) -> str:
    value = strip_finding_aid_artifacts(value)
    for pattern, replacement in TITLE_FIXES:
        value = re.sub(pattern, replacement, value)
    value = re.sub(r"\s+-\s+", "-", value)
    value = re.sub(r"\s*/\s*", "/", value)
    return clean_spaces(value)


def is_skip_line(line: str) -> bool:
    stripped = clean_spaces(line)
    if not stripped:
        return True
    if stripped in {"-", "_", "--"}:
        return True
    return any(pattern.search(stripped) for pattern in SKIP_LINE_RES)


def extract_layout_text(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def extract_pdf_pages(pdf_path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.M)
    return int(match.group(1)) if match else 0


def line_start(line: str) -> int:
    match = re.search(r"\S", line)
    return match.start() if match else 0


def estimate_note_col(lines: list[str]) -> int:
    for line in lines[:8]:
        if HEADER_RE.search(clean_spaces(line)):
            idx = line.lower().find("notes")
            if idx >= 0:
                return idx

    candidates: list[int] = []
    for line in lines:
        if not ROW_RE.match(line):
            continue
        for match in re.finditer(r"\s{2,}\S", line):
            start = match.end() - 1
            if start < 20:
                continue
            tail = line[start:].strip()
            if NOTEISH_RE.search(tail):
                candidates.append(start)

    if candidates:
        return int(median(candidates))
    return 78


def split_restrictions(value: str) -> tuple[str, list[str]]:
    markers: list[str] = []

    def collect(match: re.Match[str]) -> str:
        marker = clean_spaces(match.group(0))
        marker = re.sub(r"\bE\.?\s*O\.?", "E.O.", marker, flags=re.I)
        marker = re.sub(r"\s+", " ", marker)
        if marker not in markers:
            markers.append(marker)
        return " "

    for pattern in RESTRICTION_RES:
        value = pattern.sub(collect, value)
    return clean_spaces(value), markers


def split_row_body(line: str, oa_id: str, note_col: int) -> tuple[str, str]:
    id_end = line.find(oa_id) + len(oa_id)
    folder_part = line[id_end:note_col].strip() if len(line) > note_col else line[id_end:].strip()
    note_part = line[note_col:].strip() if len(line) > note_col else ""

    if note_part and not NOTEISH_RE.search(note_part):
        fallback = re.split(r"\s{2,}", line[id_end:].strip())
        if len(fallback) > 1 and NOTEISH_RE.search(fallback[-1]):
            return " ".join(fallback[:-1]), fallback[-1]
        return line[id_end:].strip(), ""

    if not note_part:
        fallback = re.split(r"\s{2,}", line[id_end:].strip())
        if len(fallback) > 1 and NOTEISH_RE.search(fallback[-1]):
            return " ".join(fallback[:-1]), fallback[-1]

    return folder_part, note_part


def split_continuation_body(line: str, note_col: int) -> tuple[str, str]:
    folder_part = line[:note_col].strip() if len(line) > note_col else line.strip()
    note_part = line[note_col:].strip() if len(line) > note_col else ""

    if note_part and NOTEISH_RE.search(note_part):
        return folder_part, note_part

    fallback = re.split(r"\s{2,}", line.strip())
    if len(fallback) > 1 and NOTEISH_RE.search(fallback[-1]):
        return " ".join(fallback[:-1]), fallback[-1]
    return folder_part, note_part


def title_for_source_note(title: str) -> str:
    if title == "[folder title withheld in finding aid]":
        return "folder title withheld in finding aid"
    return title


def build_source_note(entry: dict) -> str:
    parts = [
        REPOSITORY,
        COLLECTION,
        SERIES,
        entry["office_or_series"],
        f"OA/ID {entry['oa_id']}",
        title_for_source_note(entry["folder_title"]),
    ]
    source = f"Source: {', '.join(part for part in parts if part)}"
    return source if source.endswith((".", "?", "!")) else f"{source}."


def compiler_note(entry: dict) -> str:
    page = entry["pdf_page"]
    part = entry["part"]
    return (
        f"Folder-level lead from {REQUEST_ID} finding aid Part {part}, PDF p. {page}; "
        "verify item-level document title/date, exact folder contents, classification/handling, "
        "attachments, annotations, excisions, and declassification markings against the original "
        "folder/document image before final publication."
    )


def review_flags(raw_title: str, title: str, raw_note: str, note: str) -> list[str]:
    flags: list[str] = []
    if title == "[folder title withheld in finding aid]":
        flags.append("folder-title-withheld")
    if note == "[office or series not legible in finding aid]":
        flags.append("office-series-not-legible")
    if SUSPECT_RE.search(raw_title):
        flags.append("raw-folder-title-has-ocr-suspect")
    if SUSPECT_RE.search(raw_note):
        flags.append("raw-office-series-has-ocr-suspect")
    if raw_title != title:
        flags.append("folder-title-normalized")
    if raw_note != note:
        flags.append("office-series-normalized")
    return flags


def refresh_entry(entry: dict) -> None:
    title_without_markers, title_markers = split_restrictions(entry["raw_folder_title"])
    note_without_markers, note_markers = split_restrictions(entry["raw_office_or_series"])
    for marker in title_markers + note_markers:
        if marker not in entry["restriction_markers"]:
            entry["restriction_markers"].append(marker)

    title = clean_title(title_without_markers)
    note = clean_note(note_without_markers)
    entry["folder_title"] = title or "[folder title withheld in finding aid]"
    entry["office_or_series"] = note or "[office or series not legible in finding aid]"
    entry["source_note"] = build_source_note(entry)
    entry["compiler_note"] = compiler_note(entry)
    entry["review_flags"] = review_flags(
        entry["raw_folder_title"],
        entry["folder_title"],
        entry["raw_office_or_series"],
        entry["office_or_series"],
    )


def make_entry(
    *,
    part: int,
    pdf_page: int,
    sequence_on_page: int,
    oa_id: str,
    raw_title: str,
    raw_note: str,
    restriction_markers: list[str],
) -> dict:
    raw_title = clean_spaces(raw_title)
    raw_note = clean_spaces(raw_note)

    title_without_markers, title_markers = split_restrictions(raw_title)
    note_without_markers, note_markers = split_restrictions(raw_note)
    markers = []
    for marker in restriction_markers + title_markers + note_markers:
        if marker and marker not in markers:
            markers.append(marker)

    title = clean_title(title_without_markers)
    note = clean_note(note_without_markers)
    if not title:
        title = "[folder title withheld in finding aid]"
    if not note:
        note = "[office or series not legible in finding aid]"

    entry = {
        "entry_id": f"{REQUEST_ID}-P{part}-p{pdf_page:04d}-{sequence_on_page:03d}",
        "part": part,
        "pdf_page": pdf_page,
        "sequence_on_page": sequence_on_page,
        "oa_id": oa_id,
        "folder_title": title,
        "office_or_series": note,
        "repository": REPOSITORY,
        "formal_repository": FORMAL_REPOSITORY,
        "record_collection": COLLECTION,
        "record_group_or_series": SERIES,
        "request_id": REQUEST_ID,
        "restriction_markers": markers,
        "finding_aid_locator": f"{REQUEST_ID}, Part {part}, PDF p. {pdf_page}",
        "raw_folder_title": raw_title,
        "raw_office_or_series": raw_note,
    }
    entry["source_note"] = build_source_note(entry)
    entry["compiler_note"] = compiler_note(entry)
    entry["review_flags"] = review_flags(raw_title, title, raw_note, note)
    return entry


def parse_page(part: int, pdf_page: int, page_text: str) -> list[dict]:
    lines = page_text.splitlines()
    if not any(ROW_RE.match(line) for line in lines):
        return []

    note_col = estimate_note_col(lines)
    entries: list[dict] = []
    pending_folder_lines: list[str] = []
    pending_note_lines: list[str] = []
    pending_restrictions: list[str] = []
    previous_entry: dict | None = None
    sequence_on_page = 0

    for line in lines:
        if is_skip_line(line) or HEADER_RE.search(clean_spaces(line)):
            continue

        row = ROW_RE.match(line)
        if row:
            oa_id = row.group("oa")
            folder_text, note_text = split_row_body(line, oa_id, note_col)
            if pending_note_lines:
                id_end = line.find(oa_id) + len(oa_id)
                fixed_folder = line[id_end:note_col].strip() if len(line) > note_col else folder_text
                fixed_note = line[note_col:].strip() if len(line) > note_col else note_text
                if fixed_note:
                    folder_text = fixed_folder
                    note_text = fixed_note
            restriction_source = " ".join([folder_text, note_text])
            restriction_source, row_markers = split_restrictions(restriction_source)
            if row_markers:
                # Re-split the row body after stripping markers so the source fields stay clean.
                clean_line = line
                for marker in row_markers:
                    clean_line = clean_line.replace(marker, " ")
                folder_text, note_text = split_row_body(clean_line, oa_id, note_col)

            full_folder = " ".join(pending_folder_lines + [folder_text])
            sequence_on_page += 1
            entry = make_entry(
                part=part,
                pdf_page=pdf_page,
                sequence_on_page=sequence_on_page,
                oa_id=oa_id,
                raw_title=full_folder,
                raw_note=" ".join(pending_note_lines + [note_text]),
                restriction_markers=pending_restrictions + row_markers,
            )
            entries.append(entry)
            previous_entry = entry
            pending_folder_lines = []
            pending_note_lines = []
            pending_restrictions = []
            continue

        stripped, markers = split_restrictions(line)
        if not stripped and markers:
            pending_restrictions.extend(marker for marker in markers if marker not in pending_restrictions)
            continue
        if not stripped or is_skip_line(stripped):
            continue

        start = line_start(line)
        previous_needs_continuation = (
            previous_entry is not None
            and (
                previous_entry["office_or_series"] == "[office or series not legible in finding aid]"
                or previous_entry["raw_folder_title"].rstrip().endswith("-")
            )
        )
        if previous_needs_continuation:
            folder_text, note_text = split_continuation_body(line, note_col)
            if note_text:
                previous_entry["raw_folder_title"] = clean_spaces(
                    f"{previous_entry['raw_folder_title']} {folder_text}"
                )
                previous_entry["raw_office_or_series"] = clean_spaces(
                    f"{previous_entry['raw_office_or_series']} {note_text}"
                )
                for marker in markers:
                    if marker not in previous_entry["restriction_markers"]:
                        previous_entry["restriction_markers"].append(marker)
                refresh_entry(previous_entry)
                continue

        if start >= note_col - 4 and NOTEISH_RE.search(stripped):
            pending_note_lines.append(stripped)
            for marker in markers:
                if marker not in pending_restrictions:
                    pending_restrictions.append(marker)
            continue

        if start >= note_col - 4 and previous_entry is not None:
            raw_note = clean_spaces(f"{previous_entry['raw_office_or_series']} {stripped}")
            clean_raw_note, note_markers = split_restrictions(raw_note)
            previous_entry["raw_office_or_series"] = clean_raw_note
            previous_entry["office_or_series"] = clean_note(clean_raw_note)
            for marker in markers + note_markers:
                if marker not in previous_entry["restriction_markers"]:
                    previous_entry["restriction_markers"].append(marker)
            previous_entry["source_note"] = build_source_note(previous_entry)
            previous_entry["compiler_note"] = compiler_note(previous_entry)
            previous_entry["review_flags"] = review_flags(
                previous_entry["raw_folder_title"],
                previous_entry["folder_title"],
                previous_entry["raw_office_or_series"],
                previous_entry["office_or_series"],
            )
        elif NOTEISH_RE.search(stripped) and previous_entry is not None and start > note_col - 18:
            raw_note = clean_spaces(f"{previous_entry['raw_office_or_series']} {stripped}")
            clean_raw_note, note_markers = split_restrictions(raw_note)
            previous_entry["raw_office_or_series"] = clean_raw_note
            previous_entry["office_or_series"] = clean_note(clean_raw_note)
            for marker in markers + note_markers:
                if marker not in previous_entry["restriction_markers"]:
                    previous_entry["restriction_markers"].append(marker)
            previous_entry["source_note"] = build_source_note(previous_entry)
            previous_entry["compiler_note"] = compiler_note(previous_entry)
        else:
            pending_folder_lines.append(stripped)
            for marker in markers:
                if marker not in pending_restrictions:
                    pending_restrictions.append(marker)

    return entries


def parse_pdf(part: int, pdf_path: Path) -> tuple[list[dict], int]:
    page_count = extract_pdf_pages(pdf_path)
    text = extract_layout_text(pdf_path)
    pages = text.split("\f")
    entries: list[dict] = []
    for page_index, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue
        entries.extend(parse_page(part, page_index, page_text))
    return entries, page_count


def write_csv(entries: list[dict]) -> None:
    fields = [
        "entry_id",
        "part",
        "pdf_page",
        "sequence_on_page",
        "oa_id",
        "office_or_series",
        "folder_title",
        "source_note",
        "finding_aid_locator",
        "restriction_markers",
        "compiler_note",
        "review_flags",
        "raw_office_or_series",
        "raw_folder_title",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for entry in entries:
            row = dict(entry)
            row["restriction_markers"] = "; ".join(entry["restriction_markers"])
            row["review_flags"] = "; ".join(entry["review_flags"])
            writer.writerow({field: row.get(field, "") for field in fields})


def write_txt(entries: list[dict]) -> None:
    TXT_PATH.write_text("\n".join(entry["source_note"] for entry in entries) + "\n", encoding="utf-8")


def write_markdown(entries: list[dict], summary: dict) -> None:
    lines: list[str] = []
    lines.append("# Clinton 2013-0185-M Source Note Metadata Entries")
    lines.append("")
    lines.append(f"Generated: {summary['generated_at']}")
    lines.append("")
    lines.append("Source basis: attached finding-aid PDFs for 2013-0185-M.")
    lines.append("")
    lines.append("Copy-paste FRUS source-note form:")
    lines.append("")
    lines.append(
        "Source: Clinton Library, Clinton Presidential Records, National Security Council, "
        "[office or series], OA/ID [number], [folder title]."
    )
    lines.append("")
    lines.append(
        "Compiler caution: these are folder-level source-path entries. The CSV/JSON keep "
        "the 2013-0185-M Part/PDF-page locator, restriction markers, and verification note "
        "outside the copy-paste Source note so compilers can append item-level title/date, "
        "classification/handling, attachments, annotations, excisions, and declassification "
        "facts only after checking the original folder or document image."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Entries: {summary['entry_count']}")
    lines.append(f"- Finding-aid pages processed: {summary['pages_processed']}")
    lines.append(f"- Entries with printed restriction markers: {summary['entries_with_restriction_markers']}")
    lines.append(f"- Entries with review flags: {summary['entries_with_review_flags']}")
    lines.append("")
    lines.append("## Counts By Part")
    lines.append("")
    for part, count in summary["counts_by_part"].items():
        lines.append(f"- Part {part}: {count}")
    lines.append("")
    lines.append("## Copy-Paste Source Notes")
    lines.append("")

    last_part_page = None
    for entry in entries:
        part_page = (entry["part"], entry["pdf_page"])
        if part_page != last_part_page:
            lines.append("")
            lines.append(f"### Part {entry['part']}, PDF p. {entry['pdf_page']}")
            lines.append("")
            last_part_page = part_page
        lines.append(entry["source_note"])
        lines.append("")

    MD_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def build_summary(entries: list[dict], page_counts: dict[int, int]) -> dict:
    counts_by_part = Counter(str(entry["part"]) for entry in entries)
    counts_by_office = Counter(entry["office_or_series"] for entry in entries)
    flags = Counter(flag for entry in entries for flag in entry["review_flags"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_files": [
            {"part": item["part"], "file": item["file"], "pages": page_counts.get(item["part"], 0)}
            for item in PDFS
        ],
        "entry_count": len(entries),
        "pages_processed": sum(page_counts.values()),
        "counts_by_part": dict(sorted(counts_by_part.items(), key=lambda item: int(item[0]))),
        "top_office_or_series": counts_by_office.most_common(50),
        "entries_with_restriction_markers": sum(1 for entry in entries if entry["restriction_markers"]),
        "entries_with_review_flags": sum(1 for entry in entries if entry["review_flags"]),
        "review_flag_counts": dict(flags),
        "style_basis": {
            "repository_first": True,
            "repository_form": REPOSITORY,
            "formal_repository_name": FORMAL_REPOSITORY,
            "locator_policy": "The 2013-0185-M request ID, Part/PDF-page evidence, and finding-aid restriction markers are kept in metadata fields, not in the copy-paste source_note line.",
            "source_note_order": [
                "repository",
                "record collection",
                "record group or series",
                "office or series",
                "OA/ID",
                "folder title",
            ],
        },
    }


def write_json(entries: list[dict], summary: dict) -> None:
    payload = {"summary": summary, "entries": entries}
    JSON_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_browser_payload(entries: list[dict], summary: dict) -> None:
    compact_entries = [
        {
            "id": entry["entry_id"],
            "p": entry["part"],
            "pg": entry["pdf_page"],
            "seq": entry["sequence_on_page"],
            "oa": entry["oa_id"],
            "office": entry["office_or_series"],
            "folder": entry["folder_title"],
            "rest": entry["restriction_markers"],
            "flags": entry["review_flags"],
            "loc": entry["finding_aid_locator"],
        }
        for entry in entries
    ]
    payload = {"summary": summary, "entries": compact_entries}
    MIN_JSON_PATH.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_entries: list[dict] = []
    page_counts: dict[int, int] = {}

    for item in PDFS:
        part = item["part"]
        pdf_path = item["path"]
        entries, page_count = parse_pdf(part, pdf_path)
        all_entries.extend(entries)
        page_counts[part] = page_count

    summary = build_summary(all_entries, page_counts)
    write_json(all_entries, summary)
    write_csv(all_entries)
    write_txt(all_entries)
    write_markdown(all_entries, summary)
    write_browser_payload(all_entries, summary)

    print(json.dumps({
        "entry_count": summary["entry_count"],
        "pages_processed": summary["pages_processed"],
        "counts_by_part": summary["counts_by_part"],
        "entries_with_restriction_markers": summary["entries_with_restriction_markers"],
        "entries_with_review_flags": summary["entries_with_review_flags"],
        "outputs": {
            "markdown": str(MD_PATH),
            "text": str(TXT_PATH),
            "csv": str(CSV_PATH),
            "json": str(JSON_PATH),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
