import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class PageResult:
    page_num: int
    source: str
    output: Optional[Path] = None
    success: bool = False
    skipped: bool = False
    duration: float = 0.0
    output_size: int = 0
    error: Optional[str] = None


@dataclass
class RunReport:
    pdf_name: str
    total_pages: int
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    results: List[PageResult] = field(default_factory=list)

    def finish(self):
        self.end_time = time.time()

    @property
    def elapsed(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def succeeded(self) -> List[PageResult]:
        return [r for r in self.results if r.success]

    @property
    def failed(self) -> List[PageResult]:
        return [r for r in self.results if not r.success and not r.skipped]

    @property
    def skipped(self) -> List[PageResult]:
        return [r for r in self.results if r.skipped]

    @property
    def total_output_size(self) -> int:
        return sum(r.output_size for r in self.results if r.success)

    @property
    def avg_duration(self) -> float:
        done = [r for r in self.results if r.success]
        if not done:
            return 0.0
        return sum(r.duration for r in done) / len(done)

    def format(self) -> str:
        lines = [
            "",
            "=" * 52,
            f"  Conversion Report: {self.pdf_name}",
            "=" * 52,
            f"  Total pages  : {self.total_pages}",
            f"  Succeeded    : {len(self.succeeded)}",
            f"  Skipped      : {len(self.skipped)}",
            f"  Failed       : {len(self.failed)}",
            f"  Total time   : {_fmt_duration(self.elapsed)}",
            f"  Avg per page : {_fmt_duration(self.avg_duration)}",
            f"  Output size  : {_fmt_size(self.total_output_size)}",
        ]

        if self.failed:
            lines.append("")
            lines.append("  Failed pages:")
            for r in self.failed:
                err = r.error or "unknown error"
                lines.append(f"    - page {r.page_num}: {err[:80]}")

        lines.append("=" * 52)
        return "\n".join(lines)

    def save(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.format())
            if self.failed:
                f.write("\n\nFull errors:\n")
                for r in self.failed:
                    f.write(f"\n--- page {r.page_num} ({r.source}) ---\n")
                    f.write(r.error or "no detail")
                    f.write("\n")


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _fmt_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    elif nbytes < 1024 ** 2:
        return f"{nbytes / 1024:.1f} KB"
    else:
        return f"{nbytes / 1024 ** 2:.2f} MB"
