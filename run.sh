#!/bin/bash

python -m venv venv
source venv/bin/activate

python convert_large.py --input pdfs/linux-bible-by-christopher-negus.pdf --output output