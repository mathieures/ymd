# Module permettant d’effectuer des actions sur des fichiers
# (qui seront ensuite utilisés comme pièces jointes par exemple)

from pathlib import Path


def concatenate(content1: bytes, content2: bytes) -> bytes:
    """Concatène les deux contenus donnés en un seul et renvoie le résultat."""
    return content1 + content2


def split_at(content: bytes, index: int) -> tuple[bytes, bytes]:
    """Renvoie un tuple contenant les deux parties du contenu coupé à l’indice donné."""
    return content[:index], content[index:]


def load(file_path: str) -> bytes:
    """Retourne le contenu du fichier dont le chemin est donné."""
    return Path(file_path).read_bytes()


def load_chunk(file: Path, chunk_start: int, chunk_end: int) -> bytes:
    """
    Retourne le contenu du fichier donné en commençant à l’indice
    de début donné et finissant à l’indice de fin donné.
    """
    with open(file, "rb") as f:
        f.seek(chunk_start)
        return f.read(chunk_end - chunk_start)
