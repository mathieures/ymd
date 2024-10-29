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


class Mail:
    """Classe représentant très simplement un mail grâce à son ID et son objet."""

    mail_id: str  # C’est un entier, mais les fonctions demandent des chaînes
    subject: str

    def __init__(self, mail_id: str, subject: str) -> None:
        self.mail_id = mail_id
        self.subject = subject

    def __repr__(self) -> str:
        return f"<Mail({self.mail_id}, {self.subject})>"


class YahooMailAPI:
    """Classe permettant d’interagir avec des mails dans YahooMail."""

    # URL du serveur IMAP de YahooMail
    IMAP_SERVER_URL: str = "imap.mail.yahoo.com"
    # Taille maximale d’une pièce jointe sur YahooMail
    # Note : les 100Ko de moins que la vraie taille maximale (environ 29,1Ko)
    # devraient permettre d’avoir des noms de fichier relativement longs
    MAX_ATTACHMENT_SIZE: int = 29 * 2**20  # 29Mo

    _imap_connection: imaplib.IMAP4_SSL  # Connexion au serveur IMAP
    _target_folder: str  # Chemin du dossier où les mails seront stockés

    def __init__(self, address: str, password: str, target_folder: str) -> None:
        self._target_folder = target_folder

        logging.debug(f"Connecting to IMAP server: {self.IMAP_SERVER_URL}")
        self._imap_connection = imaplib.IMAP4_SSL(host=self.IMAP_SERVER_URL)

        logging.debug(f"Authenticating with address: {address}")
        self._imap_connection.login(address, password)

        self.init_folder()

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

    def init_folder(self) -> None:
        """Crée le dossier dédié s’il n’existe pas."""

        logging.debug(
            f"Checking the existence of the dedicated folder: {self._target_folder}"
        )
        folders = extract_list_result(self._imap_connection.list())
        logging.debug(f"Existing folders: {folders}")

        # Si le dossier n’existe pas, on le crée
        if self._target_folder not in folders:
            logging.debug(f"Initializing dedicated folder: {self._target_folder}")
            self._imap_connection.create(self._target_folder)

    def get_all_mails(self) -> list[Mail]:
        logging.debug(f"Retrieving all mails in folder: {self._target_folder}")
        result = []

        self._imap_connection.select(self._target_folder, readonly=True)

        # Récupère la liste des ID des mails présents dans le dossier
        _status, data = self._imap_connection.search(None, "ALL")
        mail_ids: bytes = data[0]
        # Pour chaque ID de mail, récupère l’objet du mail
        for mail_id_bytes in mail_ids.split():
            mail_id = mail_id_bytes.decode()  # Entier sous forme de bytes (ex : b"1")

            try:
                subject_data = extract_fetch_result(
                    self._imap_connection.fetch(
                        mail_id, "(BODY[HEADER.FIELDS (SUBJECT)])"
                    )
                )
            except ValueError as err:
                raise ValueError(
                    f"Could not parse the subject in data: {data}"
                ) from err

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
        return b64.b64decode(
            extract_fetch_result(
                self._imap_connection.fetch(mail.mail_id, "(BODY.PEEK[1])")
            )
        )

    def save_mail(self, msg: email.mime.multipart.MIMEMultipart) -> None:
        self._imap_connection.append(
            self._target_folder,
            "",
            imaplib.Time2Internaldate(time.time()),
            msg.as_bytes(),
        )


def extract_fetch_result(fetch_result: tuple) -> bytes:
    """
    Retourne le résultat extrait d’une requête fetch, qui
    contrairement à la documentation est un tuple contenant le
    statut en bytes (et non str) et une liste contenant des données.
    """
    _status, data = fetch_result
    data = typing.cast(tuple[bytes], data)
    if data[0] is None or isinstance(data[0][1], int):
        raise ValueError(f"Could not extract fetch result from: {data}")
    return data[0][1]


def extract_list_result(list_result: tuple) -> set[str]:
    """
    Retourne le résultat extrait d’une requête list, qui est un tuple
    contenant le statut en str et une liste contenant des données en bytes.
    """
    _status, data = list_result
    data = typing.cast(list[bytes], data)
    result = set()
    for folder_data_bytes in data:
        # Les dossiers suivent la syntaxe suivante : (<flags>) "/" "<chemin_relatif>"
        # où <chemin_relatif> est le chemin du dossier par rapport à la racine.
        partitioned_folder = folder_data_bytes.partition(b' "/" ')
        if partitioned_folder[2] == "":
            raise ValueError(f"Could not extract list result from: {data}")
        # Enlève les guillemets au début et à la fin du nom du dossier
        result.add(partitioned_folder[2].removeprefix(b'"').removesuffix(b'"').decode())
    return result
