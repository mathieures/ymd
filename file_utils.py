# Module permettant d’effectuer des actions sur des fichiers
# (qui seront ensuite utilisés comme pièces jointes par exemple)

from pathlib import Path


def load_chunk(file: Path, chunk_start: int, chunk_end: int) -> bytes:
    """
    Retourne le contenu du fichier donné en commençant à l’indice
    de début donné et finissant à l’indice de fin donné.
    """
    with open(file, "rb") as f:
        f.seek(chunk_start)
        return f.read(chunk_end - chunk_start)
