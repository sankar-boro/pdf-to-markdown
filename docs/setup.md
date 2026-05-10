Here’s a clean way to set this up as a **local, reusable project** instead of just a one-off script.

---

# 📦 Project Structure

```
pdf-to-md/
│
├── src/
│   └── converter.py
│
├── input/
├── output/
│
├── requirements.txt
├── README.md
└── main.py
```

---

# ⚙️ Step 1: Create Virtual Environment

```bash
python -m venv venv
```

Activate it:

- Linux/macOS:

```bash
source venv/bin/activate
```

---

# 📥 Step 2: Install Dependencies

Create `requirements.txt`:

```txt
marker-pdf[full]
```

Then install:

```bash
pip install -r requirements.txt
```

---

# 🧠 Step 3: Core Converter Module

### `src/converter.py`

```python
from marker.convert import convert_pdf_to_markdown
from pathlib import Path


def convert_single(pdf_path: str, output_dir: str):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / (pdf_path.stem + ".md")

    markdown = convert_pdf_to_markdown(str(pdf_path))

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown)

    return output_file


def convert_batch(input_dir: str, output_dir: str):
    input_dir = Path(input_dir)

    for pdf in input_dir.glob("*.pdf"):
        print(f"📄 Converting: {pdf.name}")
        out = convert_single(pdf, output_dir)
        print(f"✅ Saved: {out}")
```

---

# 🚀 Step 4: Entry Point

### `main.py`

```python
import argparse
from src.converter import convert_single, convert_batch


def main():
    parser = argparse.ArgumentParser(description="PDF to Markdown converter using Marker")

    parser.add_argument("--input", required=True, help="Input PDF file or folder")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--batch", action="store_true", help="Batch convert folder")

    args = parser.parse_args()

    if args.batch:
        convert_batch(args.input, args.output)
    else:
        result = convert_single(args.input, args.output)
        print(f"✅ Converted: {result}")


if __name__ == "__main__":
    main()
```

---

# ▶️ Step 5: Run the Project

### Convert single file:

```bash
python main.py --input input/sample.pdf
```

### Batch convert folder:

```bash
python main.py --input input/ --batch
```

---

# 🧪 Optional Enhancements

You can easily extend this:

### ✅ Add logging

Use `logging` instead of print

### ✅ Preserve images

Marker supports image extraction—can add flags

### ✅ Clean Markdown

Post-process using regex or Markdown formatters

### ✅ API wrapper

Wrap this in FastAPI for a local service

---

# 📘 README.md (minimal)

```md
# PDF to Markdown Converter

Uses Marker to convert PDFs into Markdown.

## Usage

Single:
python main.py --input file.pdf

Batch:
python main.py --input folder/ --batch
```

---

If you want, I can turn this into:

- a **FastAPI microservice**
- a **Dockerized tool**
- or a **GUI app (Tkinter / Electron)**

Just tell me 👍
