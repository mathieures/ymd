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
from pathlib import Path
from types import TracebackType

import file_utils
import mail_utils


class YahooMailAPI:
    """
    Classe permettant d’interagir avec YahooMail afin
    de lister, téléverser et télécharger des fichiers.
    """

    # URL du serveur IMAP de YahooMail
    YM_IMAP_SERVER_URL: str = "imap.mail.yahoo.com"
    # Taille maximale d’une pièce jointe sur YahooMail
    # Note : les 100Ko de moins que la vraie taille maximale (environ 29,1Ko)
    # devraient permettre d’avoir des noms de fichier relativement longs
    YM_MAX_ATTACHMENT_SIZE: int = 29 * 2**20  # 29Mo

    _imap_connection: imaplib.IMAP4_SSL  # Connexion au serveur IMAP
    _ym_folder_name: str  # Nom du dossier dédié aux mails

    def __init__(self, address: str, password: str, folder_name: str) -> None:
        self._ym_folder_name = folder_name

        logging.debug(f"Connecting to IMAP server: {self.YM_IMAP_SERVER_URL}")
        self._imap_connection = imaplib.IMAP4_SSL(host=self.YM_IMAP_SERVER_URL)

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
        logging.debug(f"Closing connection with IMAP server: {self.YM_IMAP_SERVER_URL}")
        self._imap_connection.__exit__(t, v, tb)

    def _get_chunk_count_for_file(self, file: Path) -> int:
        """
        Retourne les indices auxquels il faut découper le fichier dont le chemin est
        donné en paramètre pour que chaque morceau soit acceptable comme pièce jointe
        de mail. La liste contient toujours 0 en tant que premier élément. Si un
        fichier pèse exactement la taille maximale, il n’y aura qu’un seul indice.
        """
        length = file.stat().st_size
        return (length // self.YM_MAX_ATTACHMENT_SIZE) + 1

    def _get_subject_for_file_chunk(self, file_name: str, chunk_index: int) -> str:
        """
        Retourne l’objet qu’un mail doit avoir pour le fichier
        au chemin donné et pour l’indice du morceau donné.
        """
        return f"{file_name}.part{chunk_index + 1}"

    def init_folder(self) -> None:
        """Crée le dossier dédié s’il n’existe pas."""

        logging.debug(
            f"Checking the existence of the dedicated folder: {self._ym_folder_name}"
        )
        folders = mail_utils.extract_list_result(self._imap_connection.list())
        logging.debug(f"Existing folders: {folders}")

        # Si le dossier n’existe pas, on le crée
        if self._ym_folder_name not in folders:
            logging.debug(f"Initializing dedicated folder: {self._ym_folder_name}")
            self._imap_connection.create(self._ym_folder_name)

    def get_files_data(self) -> dict[str, list[mail_utils.Mail]]:
        """
        Retourne un dictionnaire de fichiers téléversés associant
        leur nom à une liste contenant les mails de leurs morceaux.
        """
        # Récupère la liste de tous les morceaux
        logging.debug(f"Retrieving all mails in folder: {self._ym_folder_name}")
        mails = mail_utils.get_all_mails(self._imap_connection, self._ym_folder_name)

        result = {}
        # Pour chaque mail, extrait le nom de fichier situé dans son objet
        for mail in mails:
            logging.debug(f"Parsing subject: {mail.subject}")
            partitioned_subject = mail.subject.partition(".part")

            # Si l’objet du mail n’est pas comme prévu, on le passe
            if partitioned_subject[1] != ".part":
                logging.warning(
                    f"Could not determine file name of chunk: {mail.subject}"
                )
                continue
            file_name = partitioned_subject[0]
            if file_name not in result:
                result[file_name] = [mail]
            else:
                result[file_name].append(mail)

        return result

    def download(self, file_name: str, dst_path: str) -> None:
        """
        Télécharge le fichier dont le nom est donné
        en paramètre vers le chemin donné en paramètre.
        """
        # Récupère le nom des fichiers téléversés et
        # les infos sur les mails de leurs morceaux
        logging.debug(f"Checking the existence of {file_name} on the server")
        files = self.get_files_data()

        # Si le fichier dont le nom est donné en paramètre n’est pas trouvé, on s’arrête
        if file_name not in files:
            raise FileNotFoundError(
                f"The file '{file_name}' was not found on the server."
            )

        # Si le fichier de destination existe déjà, on s’arrête
        dst_file = Path(dst_path)
        if dst_file.exists():
            raise FileExistsError(f"The file '{dst_file}' already exists.")

        # Sinon, on télécharge le fichier grâce à ses morceaux
        with open(dst_file, "wb") as f:
            for file_chunk_mail in files[file_name]:
                logging.debug(f"Downloading chunk: {file_chunk_mail.subject}")
                encoded_attachment_content = mail_utils.extract_fetch_result(
                    self._imap_connection.fetch(
                        file_chunk_mail.mail_id, "(BODY.PEEK[1])"
                    )
                )
                written_bytes_count = f.write(b64.b64decode(encoded_attachment_content))
                logging.debug(
                    f"Wrote {written_bytes_count} bytes to {dst_file.resolve()}"
                )

    def upload(self, file_path: str) -> None:
        """
        Téléverse le fichier dont le chemin est donné en paramètre
        en le découpant en plusieurs morceaux s’il est plus gros
        que la taille maximale autorisée pour les pièces jointes.
        """
        file = Path(file_path)

        # Si un fichier possédant ce nom a déjà été téléversé, on s’arrête
        logging.debug(f"Checking the existence of {file.name} on the server")
        if file.name in self.get_files_data():
            raise ValueError(f"A file named '{file.name}' already exists.")

        # Pour chaque indice de début de morceau de fichier
        needed_chunks_count = self._get_chunk_count_for_file(file)
        logging.debug(f"{needed_chunks_count} chunk(s) will be needed")
        for chunk_index in range(needed_chunks_count):
            attachment_name = self._get_subject_for_file_chunk(file.name, chunk_index)

            # Crée un nouveau mail
            msg = email.mime.multipart.MIMEMultipart()

            # Définit l’objet comme le nom du morceau pour tous les retrouver facilement
            msg["Subject"] = attachment_name
            # L’expéditeur et le destinataire ne sont pas nécessaires
            # msg["From"] = ""
            # msg["To"] = ""

            # Ajoute la pièce jointe
            attachment = email.mime.application.MIMEApplication(
                file_utils.load_chunk(
                    file,
                    chunk_start=chunk_index * self.YM_MAX_ATTACHMENT_SIZE,
                    chunk_end=(chunk_index + 1) * self.YM_MAX_ATTACHMENT_SIZE,
                ),
                _subtype=file.name.split(".")[-1],
            )
            attachment.add_header(
                "Content-Disposition", "attachment", filename=attachment_name
            )
            msg.attach(attachment)

            # Ajoute le mail au dossier
            logging.debug(f"Sending email {attachment_name}")
            self._imap_connection.append(
                self._ym_folder_name,
                "",
                imaplib.Time2Internaldate(time.time()),
                msg.as_bytes(),
            )

            logging.debug(f"Sent email {attachment_name}")
