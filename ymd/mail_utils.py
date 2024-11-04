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

    def __init__(self, address: str, password: str, target_folder: str) -> None:
        logging.debug(f"Connecting to IMAP server: {self.IMAP_SERVER_URL}")
        self._imap_connection = imaplib.IMAP4_SSL(host=self.IMAP_SERVER_URL)

        logging.debug(f"Authenticating with address: {address}")
        self._imap_connection.login(address, password)

        # Crée le dossier de destination dès le début
        # pour ne pas rencontrer de problème plus tard
        self.init_folder(target_folder)

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

    def _select_folder(self, folder_name: str, readonly: bool = True) -> None:
        """
        Wrapper pour sélectionner le dossier dédié
        avec les droits en lecture seule ou non.
        """
        permission = "read-only" if readonly else "write"
        logging.debug(f"Selecting folder {folder_name} with {permission} permission")
        self._imap_connection.select(folder_name, readonly=readonly)

    def get_all_folders(self) -> list[str]:
        """Retourne la liste de tous les dossiers disponibles."""
        folders = extract_list_result(self._imap_connection.list())
        logging.debug(f"Retrieved folders: {folders}")
        return folders

    def init_folder(self, folder_name: str) -> None:
        """Crée le dossier dédié s’il n’existe pas."""

        logging.debug(f"Checking the existence of the dedicated folder: {folder_name}")
        folders = self.get_all_folders()

        # Si le dossier n’existe pas, on le crée
        if folder_name not in folders:
            logging.debug(f"Initializing dedicated folder: {folder_name}")
            self._imap_connection.create(folder_name)

    def get_all_mails(self, folder_name: str) -> list[Mail]:
        """
        Retourne la liste de tous les mails dans le dossier donné.
        Peut lever l’exception suivante :
        - ValueError s’il y a une erreur dans l’analyse d’un objet
        """

        logging.debug(f"Retrieving all mails in folder: {folder_name}")
        result = []

        self._select_folder(folder_name, readonly=True)

        # Récupère la liste des ID des mails présents dans le dossier
        _status, data = self._imap_connection.uid("SEARCH", "ALL")
        mail_ids: bytes = data[0]
        # Pour chaque ID de mail, récupère l’objet du mail
        for mail_id_bytes in mail_ids.split():
            mail_id = mail_id_bytes.decode()  # Entier sous forme de bytes (ex : b"1")

            try:
                subject_data = extract_fetch_result(
                    self._imap_connection.uid(
                        "FETCH", mail_id, "(BODY[HEADER.FIELDS (SUBJECT)])"
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
        """Retourne le contenu de la pièce jointe du mail donné en paramètre."""
        return b64.b64decode(
            extract_fetch_result(
                self._imap_connection.uid("FETCH", mail.mail_id, "(BODY.PEEK[1])")
            )
        )

    def save_mail(
        self, msg: email.mime.multipart.MIMEMultipart, folder_name: str
    ) -> None:
        """Sauvegarde le mail dans le dossier sélectionné au préalable."""
        self._imap_connection.append(
            folder_name,
            "",
            imaplib.Time2Internaldate(time.time()),
            msg.as_bytes(),
        )

    def delete_mail(self, mail: Mail, folder_name: str) -> None:
        """
        Supprime le mail donné en paramètre, en essayant un
        nombre de fois défini : supprimer plusieurs mails
        rapidement peut obliger le serveur a renvoyer une erreur.
        """
        logging.debug(f"Deleting mail: '{mail.subject}' with UID: {mail.mail_id}")

        # Accorde temporairement les droits d’écriture au dossier
        self._select_folder(folder_name, readonly=False)
        self._imap_connection.uid("STORE", mail.mail_id, "+FLAGS", r"\Deleted")
        # Restreint de nouveau les droits sur le dossier
        self._select_folder(folder_name)


def extract_fetch_result(fetch_result: tuple) -> bytes:
    """
    Retourne le résultat extrait d’une requête fetch, qui
    contrairement à la documentation est un tuple contenant le
    statut en bytes (et non str) et une liste contenant des données.
    Peut lever l’exception suivante :
    - ValueError si le résultat n’a pas pu être extrait de la réponse
    """
    _status, data = fetch_result
    data = typing.cast(tuple[bytes], data)
    if data[0] is None or isinstance(data[0][1], int):
        raise ValueError(f"Could not extract fetch result from: {data}")
    return data[0][1]


def extract_list_result(list_result: tuple) -> list[str]:
    """
    Retourne le résultat extrait d’une requête list, qui est un tuple
    contenant le statut en str et une liste contenant des données en bytes.
    Peut lever l’exception suivante :
    - ValueError si le résultat n’a pas pu être extrait de la réponse
    """
    _status, data = list_result
    data = typing.cast(list[bytes], data)
    result = []
    for folder_data_bytes in data:
        # Les dossiers suivent la syntaxe suivante : (<flags>) "/" "<chemin_relatif>"
        # où <chemin_relatif> est le chemin du dossier par rapport à la racine.
        partitioned_folder = folder_data_bytes.partition(b' "/" ')
        if partitioned_folder[2] == "":
            raise ValueError(f"Could not extract list result from: {data}")
        # Enlève les guillemets au début et à la fin du nom du dossier
        result.append(
            partitioned_folder[2].removeprefix(b'"').removesuffix(b'"').decode()
        )
    return result
