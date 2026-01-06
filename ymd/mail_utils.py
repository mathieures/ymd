# Module permettant d’effectuer des actions sur des mails

import email
import email.header
import logging
import typing
from datetime import datetime

from ymd.exceptions import (
    YMDFetchResultExtractionError,
    YMDListResultExtractionError,
)

logger = logging.getLogger(__name__)


class Mail:
    """Classe représentant très simplement un mail grâce à son ID et son objet."""

    mail_id: str  # C’est un entier, mais les fonctions demandent des chaînes
    subject: str
    date: datetime

    @classmethod
    def from_fetch_result_data(
        cls, mail_id: str, fetch_result_data: bytes
    ) -> typing.Self:
        """Convertit les données brutes récupérées dans un FetchResult en un Mail."""

        def extract_subject(raw_subject: bytes) -> str:
            encoded_subject = raw_subject.removeprefix(b"Subject: ")
            # Si l’objet du mail contient des caractères
            # UTF-8, il commence par une chaîne précise
            if encoded_subject.startswith(b"=?UTF-8?Q?"):
                decoded_header = email.header.decode_header(encoded_subject.decode())
                return decoded_header[0][0].decode()

            return encoded_subject.removesuffix(b"\r\n\r\n").decode()

        def extract_date(raw_date: bytes) -> datetime:
            return datetime.strptime(
                raw_date.removeprefix(b"Date: ").decode(),
                "%a, %d %b %Y %H:%M:%S %z (%Z)",
            )

        split_data = fetch_result_data.splitlines()

        # Initialise le mail avec l’ID donné et des données par défaut
        result = cls(mail_id, "", datetime.now())

        # Vérifie les en-têtes pour en extraire les informations voulues
        for header_data in split_data:
            if header_data.startswith(b"Subject: "):
                result.subject = extract_subject(header_data)
            elif header_data.startswith(b"Date: "):
                result.date = extract_date(header_data)

        return result

    def __init__(self, mail_id: str, subject: str, date: datetime) -> None:
        self.mail_id = mail_id
        self.subject = subject
        self.date = date

    def __repr__(self) -> str:
        return f"<Mail({self.mail_id}, {self.subject})>"


class FetchResult:
    """Classe représentant le résultat « parsé » d’une commande FETCH."""

    uids: list[str]
    data: list[bytes]

    @classmethod
    def from_raw(
        cls, raw_fetch_result: tuple[bytes, list[tuple[bytes, bytes]]]
    ) -> typing.Self:
        """
        Retourne le résultat extrait d’une requête fetch, qui
        contrairement à la documentation est un tuple contenant le
        statut en bytes (et non str) et une liste contenant des données.
        Peut lever l’exception suivante :
        - YMDFetchResultExtractionError si le résultat n’a pas pu être extrait
        """
        _status, raw_data = raw_fetch_result
        if raw_data[0] is None:
            raise YMDFetchResultExtractionError(raw_fetch_result)

        # S’il n’y a pas un nombre pair d’objets, il y a un problème
        if len(raw_data) % 2 != 0:
            raise YMDFetchResultExtractionError(raw_fetch_result)

        uids = []
        data = []
        for metadata, mail_data in raw_data[::2]:
            uids.append(metadata.split()[2].decode())
            data.append(mail_data)

        return cls(uids[::-1], data[::-1])

    def __init__(self, uids: list[str], data: list[bytes]) -> None:
        self.uids = uids
        self.data = data


def extract_list_result(list_result: tuple) -> list[str]:
    """
    Retourne le résultat extrait d’une requête list, qui est un tuple
    contenant le statut en str et une liste contenant des données en bytes.
    Peut lever l’exception suivante :
    - YMDListResultExtractionError si le résultat n’a pas pu être extrait de la réponse
    """
    _status, data = list_result
    data = typing.cast("list[bytes]", data)
    result = []
    for folder_data_bytes in data:
        # Les dossiers suivent la syntaxe suivante : (<flags>) "/" "<chemin_relatif>"
        # où <chemin_relatif> est le chemin du dossier par rapport à la racine.
        partitioned_folder = folder_data_bytes.partition(b' "/" ')
        if partitioned_folder[2] == "":
            raise YMDListResultExtractionError(list_result)
        # Enlève les guillemets au début et à la fin du nom du dossier
        result.append(
            partitioned_folder[2].removeprefix(b'"').removesuffix(b'"').decode()
        )
    return result


def encode_folder_name(folder_name: str) -> str:
    """
    Encode le nom de dossier donné selon la RFC2060
    qui définit une variante de l’UTF-7.
    Inspiré de https://stackoverflow.com/a/45787169/14349477
    """

    def encode_chars(chars_to_encode: list[str]) -> str:
        """
        Encode les caractères donnés selon du base 64
        modifié : "+" devient "&" et "/" devient ",".
        """
        encoded_str = "".join(chars_to_encode).encode("utf-7").decode()
        return encoded_str.replace("+", "&").replace("/", ",")

    result: list[str] = []
    chars_to_encode: list[str] = []
    for char in folder_name:
        # Le caractère "&" (0x26) est encodé en "&-"
        if char == "&":
            # Si on a des caractères à encoder, on le fait
            if chars_to_encode:
                result.append(encode_chars(chars_to_encode))
                chars_to_encode.clear()
            result.append("&-")
            continue

        # Les caractères de 0x20 à 0x25 et de 0x27 à 0x7e ne sont pas encodés
        if ord(char) in range(0x20, 0x7E):
            # Si on a des caractères à encoder, on le fait
            if chars_to_encode:
                result.append(encode_chars(chars_to_encode))
                chars_to_encode.clear()
            result.append(char)
            continue

        # Sinon on est dans une portion de caractères à encoder
        chars_to_encode.append(char)

    # S’il reste des caractères à encoder à la fin, on les ajoute au résultat
    if chars_to_encode:
        result.append(encode_chars(chars_to_encode))

    # Lie tous les caractères et échappe les backslashes et les guillemets doubles
    return f'"{"".join(result).replace("\\", "\\\\").replace('"', r"\"")}"'


def decode_folder_name(encoded_folder_name: str) -> str:
    """
    Décode le nom de dossier donné selon la RFC2060
    qui définit une variante de l’UTF-7.
    Inspiré de https://stackoverflow.com/a/45787169/14349477
    """
    result = []
    folder_name_parts = encoded_folder_name.split("&")
    # Le premier élément est soit vide, soit des caractères normaux
    result.append(folder_name_parts[0])
    for part in folder_name_parts[1:]:
        # On cherche le "-" qui est la fin du ou des caractères encodés
        encoded_chars, normal_chars = part.split("-", maxsplit=1)
        # Si le premier élément est vide, on avait donc "&-"
        if not encoded_chars:
            result.append("&")
        # Sinon on a bien des caractères encodés
        decoded_chars = f"+{encoded_chars.replace(',', '/')}".encode().decode("utf-7")
        # Ajoute les caractères encodés puis les normaux
        result.append(decoded_chars)
        result.append(normal_chars)

    # Lie tous les caractères et déséchappe les backslashes
    return "".join(result).replace("\\\\", "\\")
