"""Versión única de la implementación de referencia MTI."""

from pathlib import Path

SOFTWARE_NAME = "motif-mti"
SOFTWARE_VERSION = "0.2.0"


def _git_commit() -> str:
    """Resuelve el commit sin invocar Git; funciona también en el servidor local."""
    git_dir = Path(__file__).resolve().parents[1] / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            reference = head[5:]
            loose_ref = git_dir / reference
            if loose_ref.is_file():
                return loose_ref.read_text(encoding="utf-8").strip()[:12]
            for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
                if line.endswith(f" {reference}"):
                    return line.split(" ", 1)[0][:12]
        return head[:12]
    except (OSError, IndexError):
        return "unavailable"


GIT_COMMIT = _git_commit()
