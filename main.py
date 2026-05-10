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