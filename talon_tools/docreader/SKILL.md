---
description: Extract text from PDFs, Word docs, Excel spreadsheets, and PowerPoint presentations
dependencies:
  - talon-tools[docreader]
---

# Document Reader

Extract text content from office documents and PDFs. Supports PDF, Word (.docx), Excel (.xlsx/.xls), and PowerPoint (.pptx).

## When to Use

- "Read this PDF for me"
- "What does this spreadsheet contain?"
- "Summarise this Word document"
- "Extract text from the presentation"
- "What's in the attached file?"

## Installation & Invocation

```bash
pip install 'talon-tools[docreader]'
```

Load and call:

```python
import asyncio
from talon_tools.docreader.tools import build_tools

tools = {t.name: t for t in build_tools()}
result = asyncio.run(tools["doc_read"].handler({"path": "/path/to/document.pdf"}))
print(result.content)
```

No credentials required.

## Available Tools

| Tool | Purpose |
|------|---------|
| `doc_read` | Read and extract text from a document file |

## Supported Formats

| Format | Extension | Output Style |
|--------|-----------|--------------|
| PDF | `.pdf` | Text per page with `--- Page N ---` markers |
| Word | `.docx` | Full document text |
| Excel | `.xlsx`, `.xls` | Pipe-delimited tables per sheet |
| PowerPoint | `.pptx` | Text extracted per slide |

## Notes

- Maximum output: 50,000 characters (truncates large documents with warning)
- Accepts both absolute and relative file paths
- For Excel files, each sheet is rendered as a separate table with headers
