#!/bin/bash

python -m venv venv
source venv/bin/activate

python convert_large.py --input /home/sankar/Desktop/Books/ai_book.pdf --output output/ai_book/