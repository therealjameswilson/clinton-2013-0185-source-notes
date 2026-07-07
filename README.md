# Clinton 2013-0185-M Source Notes

Static browser and download package for FRUS-style Clinton Library source-note metadata entries derived from the attached 2013-0185-M finding-aid PDFs.

## Contents

- `index.html`, `styles.css`, `app.js`: GitHub Pages browser with search, part, office/series, review-status filters, infinite 1,000-row loading, and copy buttons.
- `data/entries.min.json`: compact browser payload.
- `data/summary.json`: generation summary.
- `downloads/`: full Markdown, text, CSV, and JSON exports.
- `tools/build-clinton-2013-0185-source-notes.py`: repeatable extraction script used to build the source-note entries. It expects the four source PDFs in `source-pdfs/` using their original filenames.

## Source-Note Form

```text
Source: Clinton Library, Clinton Presidential Records, National Security Council, [office or series], OA/ID [number], [folder title].
```

These are folder-level source-path leads in FRUS Source Note order. The 2013-0185-M Part/PDF-page locator, printed restriction markers, and verification cautions stay in metadata fields rather than in the copyable Source note. Before final publication, compilers should append only verified item-level document title/date, exact folder contents, classification/handling, attachments, annotations, excisions, and declassification markings from the original folder or document image.

## Generated Counts

- Entries: 42,413.
- Unique source-note strings: 42,127.
- Duplicate folder-level source-note strings retained as separate finding-aid rows: 286.
- Finding-aid pages processed: 1,290.
- Entries with printed restriction markers: 274.
- Entries with review flags: 6,258.
- Entries where office/series remained not legible after OCR/layout recovery: 220.
- Source-note validation counts for bad prefix, URLs, double spaces, structural punctuation errors, and restriction-marker leaks: 0.

## Local Preview

Run a static server from this directory:

```bash
python3 -m http.server 8765
```

Then open `http://127.0.0.1:8765/`.

To rebuild the downloadable exports, place the four 2013-0185-M PDFs in `source-pdfs/` and run:

```bash
python3 tools/build-clinton-2013-0185-source-notes.py
```
