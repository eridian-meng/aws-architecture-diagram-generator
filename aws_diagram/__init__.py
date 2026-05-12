from pathlib import Path


_src_pkg = Path(__file__).resolve().parent.parent / "src" / "aws_diagram"
if _src_pkg.exists():
    __path__.append(str(_src_pkg))
