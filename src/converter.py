from marker.config.parser import ConfigParser
from marker.models import create_model_dict
from pathlib import Path


_models = None


def _get_models():
    global _models
    if _models is None:
        _models = create_model_dict()
    return _models


def convert_single(pdf_path: str, output_dir: str):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config_parser = ConfigParser({"output_format": "markdown"})
    converter_cls = config_parser.get_converter_cls()
    converter = converter_cls(
        config=config_parser.generate_config_dict(),
        artifact_dict=_get_models(),
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
        llm_service=config_parser.get_llm_service(),
    )
    rendered = converter(str(pdf_path))

    output_file = output_dir / (pdf_path.stem + ".md")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(rendered.markdown)

    return output_file


def convert_batch(input_dir: str, output_dir: str):
    input_dir = Path(input_dir)

    for pdf in input_dir.glob("*.pdf"):
        print(f"Converting: {pdf.name}")
        out = convert_single(str(pdf), output_dir)
        print(f"Saved: {out}")
