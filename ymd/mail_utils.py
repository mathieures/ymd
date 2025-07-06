# Module permettant d’effectuer des actions sur des mails

import base64 as b64
import email
import email.header
import email.mime.application
import email.mime.multipart
import email.mime.text
import imaplib
import logging
import time
import typing
from types import TracebackType

from ymd.exceptions import (
    YMDFetchResultExtractionError,
    YMDListResultExtractionError,
    YMDMailsRetrievalError,
)


class Mail:
    """Classe représentant très simplement un mail grâce à son ID et son objet."""

    mail_id: str  # C’est un entier, mais les fonctions demandent des chaînes
    subject: str

    @classmethod
    def from_dict(cls, mail_dict: dict[str, str]) -> typing.Self:
        """
        Transforme un dictionnaire contenant les données d’un mail en un objet Mail.
        """
        return cls(mail_id=mail_dict["mail_id"], subject=mail_dict["subject"])

    def __init__(self, mail_id: str, subject: str) -> None:
        self.mail_id = mail_id
        self.subject = subject

    def __repr__(self) -> str:
        return f"<Mail({self.mail_id}, {self.subject})>"

    def to_dict(self) -> dict[str, str]:
        """
        Retourne un dictionnaire contenant les données du mail, sérialisable en JSON.
        """
        return {"mail_id": self.mail_id, "subject": self.subject}


class YahooMailAPI:
    """Classe permettant d’interagir avec des mails dans YahooMail."""

    # URL du serveur IMAP de YahooMail
    IMAP_SERVER_URL: str = "imap.mail.yahoo.com"
    # Taille maximale d’une pièce jointe sur YahooMail
    # Note : les 100Ko de moins que la vraie taille maximale (environ 29,1Ko)
    # devraient permettre d’avoir des noms de fichier relativement longs
    MAX_ATTACHMENT_SIZE: int = 29 * 2**20  # 29Mo

    _imap_connection: imaplib.IMAP4_SSL  # Connexion au serveur IMAP

    def __init__(self, address: str, password: str) -> None:
        logging.debug(f"Connecting to IMAP server: {self.IMAP_SERVER_URL}")
        self._imap_connection = imaplib.IMAP4_SSL(host=self.IMAP_SERVER_URL)

        logging.debug(f"Authenticating with address: {address}")
        self._imap_connection.login(address, password)

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(
        self,
        t: type[BaseException] | None,
        v: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        logging.debug(f"Closing connection with IMAP server: {self.IMAP_SERVER_URL}")
        self._imap_connection.__exit__(t, v, tb)

    def _select_folder(self, folder_name: str, *, readonly: bool = True) -> None:
        """
        Wrapper pour sélectionner le dossier dédié
        avec les droits en lecture seule ou non.
        """
        permission = "read-only" if readonly else "write"
        logging.debug(f"Selecting folder {folder_name} with {permission} permission")
        self._imap_connection.select(encode_folder_name(folder_name), readonly=readonly)

    def get_all_folders(self) -> list[str]:
        """Retourne la liste de tous les dossiers disponibles."""
        folders = extract_list_result(self._imap_connection.list())
        # Enlève l’échappement sur les guillemets doubles qu’imaplib met en
        # place et décode les caractères encodés en une variante de l’UTF-7
        folders = [decode_folder_name(folder.replace(r"\"", '"')) for folder in folders]

        logging.debug(f"Retrieved folders: {folders}")
        return folders

    def create_folder(self, folder_name: str) -> None:
        """
        Crée le dossier donné s’il n’existe pas, en créant tous
        les dossiers parents si le nom donné contient des slashes.
        """
        logging.debug(f"Checking the existence of the folder: {folder_name}")
        folders = self.get_all_folders()

        # Si le dossier existe, on s’arrête
        if folder_name in folders:
            logging.debug(f"Folder {folder_name} already exists")
            return

        # Si le nom contient des slashes, il est composé de sous-dossiers, donc
        # on crée chaque sous-dossier pour éviter des problèmes : YahooMail ne
        # fonctionne pas correctement si on crée un sous-dossier sans ses parents
        path_separator = "/"
        subfolders = folder_name.split(path_separator)
        for subfolder_index in range(len(subfolders)):
            # Crée le sous-dossier arrivant jusqu’au sous-dossier actuel
            subfolder = path_separator.join(subfolders[: subfolder_index + 1])
            if subfolder in folders:
                continue
            logging.debug(f"Creating folder: {subfolder}")
            self._imap_connection.create(encode_folder_name(subfolder))

    def get_all_mails(self, folder_name: str) -> list[Mail]:
        """
        Retourne la liste de tous les mails dans le dossier donné.
        Peut lever l’exception suivante :
        - YMDMailsRetrievalError si la réponse du serveur IMAP est invalide
        """
        logging.debug(f"Retrieving all mails in folder: {folder_name}")
        self._select_folder(folder_name)

        # Récupère la liste des ID des mails présents dans le dossier
        _status, data = self._imap_connection.uid("SEARCH", "ALL")
        mail_ids: bytes | None = data[0]
        if mail_ids is None:
            raise YMDMailsRetrievalError(folder_name, server_reply=data)

        mail_ids_str = mail_ids.decode().split()
        logging.debug(f"Retrieved mail IDs: {mail_ids_str}")

        result = []

        # S’il n’y avait aucun mail dans le dossier, on retourne une liste vide
        if not mail_ids_str:
            return result

        # On peut demander des informations sur tous les mails
        # en même temps si on sépare les UID par des virgules
        fetch_result = self._imap_connection.uid(
            "FETCH", ",".join(mail_ids_str), "(BODY[HEADER.FIELDS (SUBJECT)])"
        )

        # Extrait et renverse les données car le serveur répond à l’envers
        try:
            mails_data = extract_fetch_result(fetch_result)[::-1]
        except YMDFetchResultExtractionError as err:
            raise YMDMailsRetrievalError(folder_name, server_reply=data) from err

        for mail_id, subject_data in zip(mail_ids_str, mails_data, strict=True):
            encoded_subject = subject_data.removeprefix(b"Subject: ")

            # Si l’objet du mail contient des caractères
            # UTF-8, il commence par une chaîne précise
            if encoded_subject.startswith(b"=?UTF-8?Q?"):
                decoded_header = email.header.decode_header(encoded_subject.decode())
                subject = decoded_header[0][0].decode()
            else:
                subject = encoded_subject.removesuffix(b"\r\n\r\n").decode()

            result.append(Mail(mail_id, subject))

        return result

    def get_attachment_content_of_mail(self, mail: Mail) -> bytes:
        """Retourne le contenu de la pièce jointe du mail donné en paramètre."""
        fetch_result = self._imap_connection.uid(
            "FETCH", mail.mail_id, "(BODY.PEEK[1])"
        )
        return b64.b64decode(extract_fetch_result(fetch_result)[0])

    def save_mail(
        self, msg: email.mime.multipart.MIMEMultipart, folder_name: str
    ) -> None:
        """
        Sauvegarde le mail dans le dossier donné en le rendant
        « lu » pour ne pas être confondu avec un vrai mail.
        """
        self._imap_connection.append(
            encode_folder_name(folder_name),
            r"\Seen",
            imaplib.Time2Internaldate(time.time()),
            msg.as_bytes(),
        )

    def delete_mail(
        self, mail: Mail, folder_name: str, *, move_to_trash: bool = False
    ) -> None:
        """
        Supprime le mail donné en paramètre, en le mettant
        optionnellement dans la corbeille si demandé.
        """
        if move_to_trash:
            logging.debug(f"Trashing mail: '{mail.subject}' with UID: {mail.mail_id}")
        else:
            logging.debug(f"Deleting mail: '{mail.subject}' with UID: {mail.mail_id}")

        # Accorde temporairement les droits d’écriture au dossier
        self._select_folder(folder_name, readonly=False)

        if move_to_trash:
            self._imap_connection.uid("COPY", mail.mail_id, "Trash")

        self._imap_connection.uid("STORE", mail.mail_id, "+FLAGS", r"\Deleted")
        # Restreint de nouveau les droits sur le dossier
        self._select_folder(folder_name)

    def noop(self) -> None:
        """
        Envoie un NOOP (NO OPeration) au serveur IMAP.
        N’a aucun effet, mais peut être utilisé pour ne pas subir de timeout.
        """
        self._imap_connection.noop()

    def logout(self) -> None:
        """
        Clôt la connexion au serveur IMAP. Toutes  les commandes
        suivantes lèveront une erreur imaplib.IMAP4.error.
        """
        self._imap_connection.logout()


def extract_fetch_result(fetch_result: tuple) -> list[bytes]:
    """
    Retourne le résultat extrait d’une requête fetch, qui
    contrairement à la documentation est un tuple contenant le
    statut en bytes (et non str) et une liste contenant des données.
    Peut lever l’exception suivante :
    - YMDFetchResultExtractionError si le résultat n’a pas pu être extrait de la réponse
    """
    _status, data = fetch_result
    # Les données sont un ou des tuples suivi(s) d’un objet bytes constant : b")".
    # Les tuples contiennent deux objets bytes : les métadonnées et les données,
    # donc on extrait à chaque fois le second élément de chaque tuple.
    if data[0] is None:
        raise YMDFetchResultExtractionError(fetch_result)
    return [t[1] for t in data[::2]]


def extract_list_result(list_result: tuple) -> list[str]:
    """
    Retourne le résultat extrait d’une requête list, qui est un tuple
    contenant le statut en str et une liste contenant des données en bytes.
    Peut lever l’exception suivante :
    - YMDListResultExtractionError si le résultat n’a pas pu être extrait de la réponse
    """
    _status, data = list_result
    data = typing.cast(list[bytes], data)
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
