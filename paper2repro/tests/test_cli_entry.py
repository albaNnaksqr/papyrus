import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_cli_help():
    """CLI --help exits 0 and shows expected flags."""
    result = subprocess.run(
        [sys.executable, "paper2repro.py", "--help"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--pdf" in result.stdout
    assert "--fast" in result.stdout
    assert "--no-critique" in result.stdout
    assert "--config" in result.stdout


def test_cli_missing_pdf_exits_nonzero():
    """CLI exits non-zero when --pdf is missing."""
    result = subprocess.run(
        [sys.executable, "paper2repro.py"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
