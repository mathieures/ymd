# Module permettant d’interagir avec l’API YahooMail

import base64 as b64
import email
import imaplib
import logging
import time
import typing

from ymd.exceptions import (
    YMDFetchResultExtractionError,
    YMDFolderDoesNotExistError,
    YMDMailsRetrievalError,
)
from ymd.mail_utils import (
    FetchResult,
    Mail,
    decode_folder_name,
    encode_folder_name,
    extract_list_result,
)

if typing.TYPE_CHECKING:
    import email.mime.multipart
    from types import TracebackType

logger = logging.getLogger(__name__)


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
        logger.debug(f"Connecting to IMAP server: {self.IMAP_SERVER_URL}")
        self._imap_connection = imaplib.IMAP4_SSL(host=self.IMAP_SERVER_URL)

        logger.debug(f"Authenticating with address: {address}")
        self._imap_connection.login(address, password)

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(
        self,
        t: type[BaseException] | None,
        v: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        logger.debug(f"Closing connection with IMAP server: {self.IMAP_SERVER_URL}")
        self._imap_connection.__exit__(t, v, tb)

    def _select_folder(self, folder_name: str, *, readonly: bool = True) -> None:
        """
        Wrapper pour sélectionner le dossier dédié
        avec les droits en lecture seule ou non.
        """
        permission = "read-only" if readonly else "write"
        logger.debug(f"Selecting folder '{folder_name}' with {permission} permission")
        self._imap_connection.select(encode_folder_name(folder_name), readonly=readonly)

    def get_all_folders(self) -> list[str]:
        """Retourne la liste de tous les dossiers disponibles."""
        folders = extract_list_result(self._imap_connection.list())
        # Enlève l’échappement sur les guillemets doubles qu’imaplib met en
        # place et décode les caractères encodés en une variante de l’UTF-7
        folders = [decode_folder_name(folder.replace(r"\"", '"')) for folder in folders]

        logger.debug(f"Retrieved folders: {folders}")
        return folders

    def create_folder(self, folder_name: str) -> None:
        """
        Crée le dossier donné s’il n’existe pas, en créant tous
        les dossiers parents si le nom donné contient des slashes.
        """
        logger.debug(f"Trying to create folder '{folder_name}'")
        folders = self.get_all_folders()

        # Si le dossier existe, on s’arrête
        if folder_name in folders:
            logger.debug(f"Folder '{folder_name}' already exists")
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

            logger.debug(f"Creating folder: '{subfolder}'")
            self._imap_connection.create(encode_folder_name(subfolder))

    def delete_folder(self, folder_name: str) -> None:
        """
        Supprime le dossier dont le nom est donné en paramètre.
        """
        logger.debug(f"Trying to delete folder '{folder_name}'")
        folders = self.get_all_folders()

        # Si le dossier n’existe pas, on s’arrête
        if folder_name not in folders:
            raise YMDFolderDoesNotExistError(folder_name)

        logger.debug(f"Deleting folder: '{folder_name}'")
        self._imap_connection.delete(encode_folder_name(folder_name))

    def get_all_mails(self, folder_name: str) -> list[Mail]:
        """
        Retourne la liste de tous les mails dans le dossier donné.
        Peut lever l’exception suivante :
        - YMDMailsRetrievalError si la réponse du serveur IMAP est invalide
        """
        logger.debug(f"Retrieving all mails in folder: '{folder_name}'")
        self._select_folder(folder_name)

        logger.debug("Searching for mail UIDs")
        # Récupère la liste des ID des mails présents dans le dossier
        _status, data = self._imap_connection.uid("SEARCH", "ALL")
        mail_ids: bytes | None = data[0]
        if mail_ids is None:
            raise YMDMailsRetrievalError(folder_name, server_reply=data)

        mail_ids_str = mail_ids.decode().split()
        logger.debug(f"Retrieved mail UIDs: {mail_ids_str}")

        result = []

        # S’il n’y avait aucun mail dans le dossier, on retourne une liste vide
        if not mail_ids_str:
            return result

        # On peut demander des informations sur tous les mails
        # en même temps si on sépare les UID par des virgules
        fetch_result = self._imap_connection.uid(
            "FETCH", ",".join(mail_ids_str), "(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])"
        )

        # Extrait et renverse les données car le serveur répond à l’envers
        try:
            parsed_fetch_result = FetchResult.from_raw(fetch_result)  # pyright: ignore[reportArgumentType]
        except YMDFetchResultExtractionError as err:
            raise YMDMailsRetrievalError(folder_name, server_reply=data) from err

        # Extrait l’objet de chaque mail
        for mail_id, raw_mail_data in zip(
            parsed_fetch_result.uids, parsed_fetch_result.data, strict=True
        ):
            parsed_mail = Mail.from_fetch_result_data(mail_id, raw_mail_data)

            result.append(parsed_mail)

        return result

    def get_attachment_content_of_mail(self, mail: Mail) -> bytes:
        """Retourne le contenu de la pièce jointe du mail donné en paramètre."""
        fetch_result = self._imap_connection.uid(
            "FETCH", mail.mail_id, "(BODY.PEEK[1])"
        )
        parsed_fetch_result = FetchResult.from_raw(fetch_result)  # pyright: ignore[reportArgumentType]
        return b64.b64decode(parsed_fetch_result.data[0])

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
            logger.debug(f"Trashing mail: '{mail.subject}' with UID: {mail.mail_id}")
        else:
            logger.debug(f"Deleting mail: '{mail.subject}' with UID: {mail.mail_id}")

        # Accorde temporairement les droits d’écriture au dossier
        self._select_folder(folder_name, readonly=False)

        if move_to_trash:
            self._imap_connection.uid("COPY", mail.mail_id, "Trash")

        self._imap_connection.uid("STORE", mail.mail_id, "+FLAGS", r"\Deleted")
        # Restreint de nouveau les droits sur le dossier
        self._select_folder(folder_name)

    def delete_mails(
        self, mails: list[Mail], folder_name: str, *, move_to_trash: bool = False
    ) -> None:
        """
        Supprime tous les mails de la liste donnée en paramètre, en
        les mettant optionnellement dans la corbeille si demandé.
        """
        if move_to_trash:
            logger.debug(f"Trashing mails: {mails}")
        else:
            logger.debug(f"Deleting mails: {mails}")

        if not mails:
            return

        # Accorde temporairement les droits d’écriture au dossier
        self._select_folder(folder_name, readonly=False)

        mail_ids_str = ",".join(mail.mail_id for mail in mails)

        if move_to_trash:
            self._imap_connection.uid("COPY", mail_ids_str, "Trash")

        self._imap_connection.uid("STORE", mail_ids_str, "+FLAGS", r"\Deleted")
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
