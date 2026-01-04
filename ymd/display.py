"""Module contenant des fonctions pratiques pour afficher du texte dans la console."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ymd.mail_utils import Mail


def print_files_list(
    files_data: dict[str, list[Mail]], *, long: bool, column_separator: str = " "
) -> None:
    """Affiche la liste de fichiers donnée avec un en-tête."""

    if not files_data:
        return

    # Liste des lignes qui seront affichées
    lines: list[tuple[str, ...]] = []

    # Initialise la liste de lignes avec l’en-tête si activé
    if long:
        header = ("chunks", "date", "file")
        # Stocke la longueur que chaque colonne de
        # l’en-tête devra avoir pour les aligner
        header_lengths = [len(field) for field in header]

    # Pour chaque fichier, affiche le nombre de morceaux
    # téléversés aligné à droite et le nom du fichier
    for file_name, file_data in files_data.items():
        if long:
            chunks = f"{len(file_data):>{len(header[0])}}"
            date = (
                file_data[-1].date.strftime("%Y-%m-%d %H:%M") if file_data else " " * 16
            )
            line = (chunks, date, file_name)
            for i_col in range(len(header)):
                header_lengths[i_col] = max(header_lengths[i_col], len(line[i_col]))
        else:
            line = (file_name,)
        lines.append(line)

    # Construit la chaîne résultante en commençant par l’en-tête
    # aligné en fonction des longueurs maximales pour chaque colonne
    if long:
        header_str_parts = (
            f"{field:<{length}}"
            for field, length in zip(header, header_lengths, strict=True)
        )
        header_str = f"{column_separator.join(header_str_parts)}\n"
    else:
        header_str = ""
    print(header_str + "\n".join(column_separator.join(line) for line in lines))


def print_progress(
    text: str, current: int, target: int, *, final_newline: bool = False
) -> None:
    """
    Affiche le progrès en fonction du progrès actuel et de la cible
    donnés, préfixés par le texte donné en effaçant le texte précédent.
    """
    percentage = current / target * 100
    print(
        f"\r{text} {current}/{target} ({percentage:.1f}%)",
        end="\n" if final_newline else "",
    )
