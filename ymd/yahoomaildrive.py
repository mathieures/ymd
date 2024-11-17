import email
import email.header
import email.mime.application
import email.mime.multipart
import email.mime.text
import logging
import typing
from io import BufferedReader, BufferedWriter
from pathlib import Path
from types import TracebackType

from ymd import file_utils, mail_utils
from ymd.exceptions import YMDFileAlreadyExists, YMDFileDoesNotExist
from ymd.mail_utils import YahooMailAPI


class YahooMailDrive:
    """
    Classe permettant d’interagir avec YahooMail pour
    lister, télécharger et téléverser des fichiers.
    """

    _ym_api: YahooMailAPI
    _target_folder: str  # Chemin du dossier où les mails seront stockés

    @property
    def target_folder(self) -> str:
        return self._target_folder

    @target_folder.setter
    def target_folder(self, folder_name: str) -> None:
        # Crée le dossier donné s’il n’existe pas
        self._ym_api.create_folder(folder_name)
        self._target_folder = folder_name

    def __init__(self, address: str, password: str, target_folder: str) -> None:
        self._target_folder = target_folder
        self._ym_api = YahooMailAPI(address, password)
        # Crée le dossier de destination dès le début
        # pour ne pas rencontrer de problème plus tard
        self._ym_api.create_folder(self._target_folder)

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(
        self,
        t: type[BaseException] | None,
        v: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._ym_api.__exit__(t, v, tb)

    def _get_chunk_count_for_file(
        self, file_path: Path, buffer: BufferedReader | None = None
    ) -> int:
        """
        Retourne le nombre de pièces jointes nécessaires au téléversement
        du fichier passé en paramètre. Si un fichier pèse exactement
        la taille maximale, il n’y aura qu’un seul morceau.
        """
        # Les buffers n’ont pas de méthode stat(), on
        # récupère donc la dernière position disponible
        if buffer is not None:
            # Sauvegarde la position du curseur de lecture dans le buffer
            old_cursor_pos = buffer.tell()
            # 2 signifie la fin du fichier (voir https://docs.python.org/3/library/io.html#io.IOBase.seek)
            buffer.seek(0, 2)
            length = buffer.tell()
            # Replace le curseur de lecture à l’ancienne position
            buffer.seek(old_cursor_pos)
        else:
            length = file_path.stat().st_size
        return (length // self._ym_api.MAX_ATTACHMENT_SIZE) + 1

    def _get_subject_for_file_chunk(self, file_name: str, chunk_index: int) -> str:
        """
        Retourne l’objet qu’un mail doit avoir pour le fichier
        au chemin donné et pour l’indice du morceau donné.
        """
        return f"{file_name}.part{chunk_index + 1}"

    def get_folders(self) -> list[str]:
        """Retourne la liste de tous les dossiers disponibles."""
        return self._ym_api.get_all_folders()

    def get_files_data(self) -> dict[str, list[mail_utils.Mail]]:
        """
        Retourne un dictionnaire de fichiers téléversés associant
        leur nom à une liste contenant les mails de leurs morceaux.
        """
        # Récupère la liste de tous les morceaux
        try:
            mails = self._ym_api.get_all_mails(self._target_folder)
        except ValueError as err:
            raise ValueError(
                f"Could not get the files data in {self._target_folder}"
            ) from err

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

    def download(
        self, file_name: str, dst_path_or_buffer: str | BufferedWriter
    ) -> None:
        """
        Télécharge le fichier dont le nom est donné en paramètre
        vers le chemin ou le buffer donné en paramètre.
        Peut lever les exceptions suivantes :
        - YMDFileDoesNotExist si le fichier n’existe pas sur le serveur
        - FileExistsError si le chemin de destination est occupé par un fichier
        """

        def _download_file_into(file_name: str, dst_buffer: BufferedWriter) -> None:
            """Télécharge le fichier dont le nom est donné vers le buffer donné."""
            for file_chunk_mail in files[file_name]:
                logging.debug(f"Downloading chunk: {file_chunk_mail.subject}")
                # Télécharge la pièce jointe et écrit son contenu à la fin du fichier
                written_bytes_count = dst_buffer.write(
                    self._ym_api.get_attachment_content_of_mail(file_chunk_mail)
                )
                logging.debug(f"Wrote {written_bytes_count} bytes")

        # Récupère le nom des fichiers téléversés et
        # les infos sur les mails de leurs morceaux
        logging.debug(f"Checking the existence of {file_name} on the server")
        files = self.get_files_data()

        # Si le fichier dont le nom est donné en paramètre n’est pas trouvé, on s’arrête
        if file_name not in files:
            raise YMDFileDoesNotExist(file_name)

        # Si le paramètre donné est une chaîne de caractère,
        # on sait que c’est un chemin de fichier
        if isinstance(dst_path_or_buffer, str):
            # Sinon on a le chemin du fichier de destination, donc on
            # vérifie s’il existe déjà et on s’arrête si c’est le cas
            dst_file = Path(dst_path_or_buffer)
            if dst_file.exists():
                raise FileExistsError(
                    f"The file '{dst_file.resolve()}' already exists."
                )

            # Sinon, on télécharge le fichier grâce à ses morceaux
            with open(dst_file, "wb") as file:
                _download_file_into(file_name, file)
            return

        # Sinon un buffer de destination est donné, alors on écrit dedans
        if dst_path_or_buffer is not None:
            _download_file_into(file_name, dst_path_or_buffer)

    def upload(self, file_path: Path, buffer: BufferedReader | None = None) -> None:
        """
        Téléverse le fichier dont le chemin est donné en paramètre ou le
        contenu du buffer donné en le découpant en plusieurs morceaux s’il
        est plus gros que la taille maximale autorisée pour les pièces jointes.
        Le chemin donné est également utilisé pour déterminer
        le nom du fichier sur le serveur une fois téléversé.
        Peut lever l’exception suivante :
        - YMDFileAlreadyExists si le fichier existe déjà sur le serveur
        """

        def _create_attachment_with_buffer(buffer: BufferedReader, chunk_index: int):
            """
            Retourne une pièce jointe créée avec le morceau du contenu
            du buffer correspondant à l’indice donné en paramètre.
            """
            return email.mime.application.MIMEApplication(
                file_utils.load_chunk(
                    buffer,
                    chunk_start=chunk_index * self._ym_api.MAX_ATTACHMENT_SIZE,
                    chunk_end=(chunk_index + 1) * self._ym_api.MAX_ATTACHMENT_SIZE,
                ),
                _subtype=file_path.name.split(".")[-1],
            )

        # Si un fichier possédant ce nom a déjà été téléversé, on s’arrête
        logging.debug(f"Checking the existence of {file_path.name} on the server")
        if file_path.name in self.get_files_data():
            raise YMDFileAlreadyExists(file_path.name)

        # Pour chaque indice de début de morceau de fichier
        needed_chunks_count = self._get_chunk_count_for_file(file_path, buffer=buffer)
        logging.debug(f"{needed_chunks_count} chunk(s) will be needed")
        for chunk_index in range(needed_chunks_count):
            attachment_name = self._get_subject_for_file_chunk(
                file_path.name, chunk_index
            )

            # Crée un nouveau mail
            msg = email.mime.multipart.MIMEMultipart()

            # Définit l’objet comme le nom du morceau pour tous les retrouver facilement
            msg["Subject"] = attachment_name
            # L’expéditeur et le destinataire ne sont pas nécessaires
            # msg["From"] = ""
            # msg["To"] = ""

            # Ajoute la pièce jointe
            if buffer is None:
                with open(file_path, "rb") as file:
                    attachment = _create_attachment_with_buffer(file, chunk_index)
            else:
                attachment = _create_attachment_with_buffer(buffer, chunk_index)

            attachment.add_header(
                "Content-Disposition", "attachment", filename=attachment_name
            )
            msg.attach(attachment)

            # Ajoute le mail au dossier
            logging.debug(f"Uploading email {attachment_name}")
            self._ym_api.save_mail(msg, self._target_folder)
            logging.debug(f"Uploaded email {attachment_name}")

    def remove(self, file_name: str) -> None:
        """
        Supprime le fichier dont le chemin est donné en paramètre
        en supprimant tous les mails contenant ses morceaux.
        Peut lever l’exception suivante :
        - YMDFileDoesNotExist si le fichier n’existe pas sur le serveur
        """
        # Récupère le nom des fichiers téléversés et
        # les infos sur les mails de leurs morceaux
        logging.debug(f"Checking the existence of {file_name} on the server")
        files = self.get_files_data()

        # Si le fichier dont le nom est donné en paramètre n’est pas trouvé, on s’arrête
        if file_name not in files:
            raise YMDFileDoesNotExist(file_name)

        for file_chunk_mail in files[file_name]:
            self._ym_api.delete_mail(file_chunk_mail, self._target_folder)
