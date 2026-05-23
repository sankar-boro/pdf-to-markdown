```
python -m venv venv
source venv/bin/activate


python main.py --input ./pdfs/linux-bible-by-christopher-negus.pdf
```

```
python split_pdf.py --input pdfs/linux-bible-by-christopher-negus.pdf --output output/pages

```

# Basic — splits, converts each page, cleans up the split PDFs

python convert_large.py --input pdfs/linux-bible-by-christopher-negus.pdf --output output

# Keep the split page PDFs after conversion

python convert_large.py --input pdfs/linux-bible-by-christopher-negus.pdf --output output --keep-pages

# Custom location for split page PDFs

python convert_large.py --input pdfs/linux-bible-by-christopher-negus.pdf --output output --pages-dir /tmp/pages
