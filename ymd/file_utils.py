# Module permettant d’effectuer des actions sur des fichiers

import tomllib
from io import BufferedReader
from pathlib import Path


def load_chunk(buffer: BufferedReader, chunk_start: int, chunk_end: int) -> bytes:
    """
    Retourne le contenu du fichier donné en commençant à l’indice
    de début donné et finissant à l’indice de fin donné.
    """
    buffer.seek(chunk_start)
    return buffer.read(chunk_end - chunk_start)


def load_credentials(
    file_path: Path, default_locations: list[Path] | None = None
) -> tuple[str, str]:
    """
    Charge les informations de connexion depuis le chemin de fichier donné en paramètre,
    ou depuis un des emplacements de la liste donnée si le chemin donné n’existe pas.
    Peut lever l’exception suivante :
    - FileNotFoundError si aucun des fichiers n’a été trouvé
    """
    # Si une liste d’emplacements par défaut est donnée, trouve le premier
    # chemin qui existe parmi celui donné et ceux-là, sinon prend celui donné
    if not default_locations:
        credentials_file = file_path
    else:
        for location in [file_path, *default_locations]:
            credentials_file = location
            if not credentials_file.exists():
                continue
            break

    # Si le fichier choisi n’existe pas, lève une exception
    if not credentials_file.expanduser().exists():
        raise FileNotFoundError(file_path)

    data = tomllib.loads(credentials_file.expanduser().read_text())
    return data["address"], data["password"]
