#!/usr/bin/env python3
"""PDF text extractor — outputs plain text to stdout."""
import sys
import pdfplumber

MAX_CHARS = 28000


def parse_pdf(filepath: str) -> str:
    parts = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
            for table in page.extract_tables():
                if table:
                    for row in table:
                        cells = [str(c or "").strip() for c in row]
                        if any(cells):
                            parts.append(" | ".join(cells))
    full = "\n".join(parts)
    if len(full) > MAX_CHARS:
        sys.stderr.write(f"[警告] 文本长度 {len(full)}，截断至 {MAX_CHARS}\n")
        return full[:MAX_CHARS] + "\n...[文档已截断]"
    return full


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("用法: python parse_pdf.py <pdf路径>\n")
        sys.exit(1)
    print(parse_pdf(sys.argv[1]))
