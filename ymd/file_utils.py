# Module permettant d’effectuer des actions sur des fichiers

from io import BufferedReader
from pathlib import Path

import tomllib


def load_chunk(buffer: BufferedReader, chunk_start: int, chunk_end: int) -> bytes:
    """
    Retourne le contenu du fichier donné en commençant à l’indice
    de début donné et finissant à l’indice de fin donné.
    """
    buffer.seek(chunk_start)
    return buffer.read(chunk_end - chunk_start)


def load_credentials(file_path: Path) -> tuple[str, str]:
    data = tomllib.loads(file_path.expanduser().read_text())
    return data["address"], data["password"]
