# Module permettant d’effectuer des actions sur des fichiers

from pathlib import Path

import tomllib


def load_chunk(file: Path, chunk_start: int, chunk_end: int) -> bytes:
    """
    Retourne le contenu du fichier donné en commençant à l’indice
    de début donné et finissant à l’indice de fin donné.
    """
    with open(file, "rb") as f:
        f.seek(chunk_start)
        return f.read(chunk_end - chunk_start)


def load_credentials(file_path: str) -> tuple[str, str]:
    data = tomllib.loads(Path(file_path).expanduser().read_text())
    return data["address"], data["password"]
