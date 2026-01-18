# Module permettant d’effectuer des actions de stockage de fichiers sur YahooMail

import concurrent.futures
import email
import email.mime.application
import email.mime.multipart
import logging
import typing
from pathlib import Path

from ymd import file_utils, mail_utils
from ymd.display import print_progress
from ymd.exceptions import (
    YMDAmbiguousNameError,
    YMDChunkAlreadyExists,
    YMDFileDoesNotExist,
    YMDFilesRetrievalError,
    YMDFolderDoesNotExistError,
    YMDFolderIsNotEmptyError,
    YMDMailsRetrievalError,
)
from ymd.yahoomail import YahooMailAPI

if typing.TYPE_CHECKING:
    from io import BufferedReader, BufferedWriter
    from types import TracebackType


logger = logging.getLogger(__name__)


class YahooMailDrive:
    """
    Classe permettant d’interagir avec YahooMail pour
    lister, télécharger et téléverser des fichiers.
    Il est possible de créer plusieurs connexions simultanées
    pour pouvoir effectuer plusieurs actions en même temps.
    """

    _ym: list[YahooMailAPI]  # Liste de connexions (le plus souvent 1) à YahooMail
    _target_folder: str  # Chemin du dossier où les mails seront stockés

    @property
    def target_folder(self) -> str:
        return self._target_folder

    @target_folder.setter
    def target_folder(self, folder_name: str) -> None:
        # Crée le dossier donné s’il n’existe pas
        self._ym[0].create_folder(folder_name)
        self._target_folder = folder_name

    def __init__(
        self, address: str, password: str, target_folder: str, *, connections: int = 1
    ) -> None:
        # Sauvegarde la valeur brute du nom du dossier voulu par l’utilisateur
        self._target_folder = target_folder

        if connections <= 0:
            msg = "Cannot create less than one connection to YahooMail"
            raise ValueError(msg)

        self._ym = [YahooMailAPI(address, password) for _ in range(connections)]

        # Crée le dossier de destination dès le début
        # pour ne pas rencontrer de problème plus tard
        self._ym[0].create_folder(self._target_folder)

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(
        self,
        t: type[BaseException] | None,
        v: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        for connection in self._ym:
            connection.__exit__(t, v, tb)

    def get_chunk_count_for_size(self, size: int) -> int:
        """
        Retourne le nombre de morceaux nécessaires au téléversement
        d’un fichier dont la taille est donnée en paramètre.
        """
        return (size // YahooMailAPI.MAX_ATTACHMENT_SIZE) + 1

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
        return self.get_chunk_count_for_size(length)

    def _get_subject_for_file_chunk(self, file_name: str, chunk_index: int) -> str:
        """
        Retourne l’objet qu’un mail doit avoir pour le fichier
        au chemin donné et pour l’indice du morceau donné.
        """
        # Note : arbitrairement, on commence à compter les morceaux à partir de 1.
        return f"{file_name}.part{chunk_index + 1}"

    def _get_file_name_from_subject(self, subject: str) -> str | None:
        """
        Retourne le nom du fichier extrait de l’objet de mail
        donné, ou None si un nom n’a pas pu être extrait.
        """
        logger.debug(f"Parsing subject: '{subject}'")
        partitioned_subject = subject.partition(".part")

        # Si l’objet du mail n’est pas comme prévu, ne retourne rien
        if partitioned_subject[1] != ".part":
            return None

        return partitioned_subject[0]

    def get_folders(self) -> list[str]:
        """Retourne la liste de tous les dossiers disponibles."""
        return self._ym[0].get_all_folders()

    def _get_files_data_in_folder(
        self,
        folder_name: str,
        dict_key_prefix: str | None = None,
    ) -> dict[str, list[mail_utils.Mail]]:
        """
        Retourne un dictionnaire de fichiers téléversés associant
        leur nom à une liste contenant les mails de leurs morceaux.
        Optionnellement, préfixe le nom des fichiers par ce qui est donné.
        Peut lever l’exception suivante :
        - YMDFilesRetrievalError si les fichiers n’ont pas pu être récupérés
        """
        # Récupère la liste de tous les morceaux
        try:
            mails = self._ym[0].get_all_mails(folder_name)
        except YMDMailsRetrievalError as err:
            raise YMDFilesRetrievalError(folder_name) from err

        result: dict[str, list[mail_utils.Mail]] = {}

        # Pour chaque mail, extrait le nom de fichier situé dans son objet
        for mail in mails:
            file_name = self._get_file_name_from_subject(mail.subject)
            # Si le nom n’a pas pu être extrait, on passe ce fichier
            if file_name is None:
                logger.warning(
                    f"Could not determine file name of chunk: '{mail.subject}'"
                )
                continue

            # Sinon, ajoute le mail à la liste associée au nom du fichier
            dict_key = (
                file_name
                if dict_key_prefix is None
                else f"{dict_key_prefix}{file_name}"
            )
            if dict_key not in result:
                result[dict_key] = [mail]
            else:
                result[dict_key].append(mail)

        return result

    def _get_subfolders(self, folder_name: str, *, reverse: bool = False) -> list[str]:
        """
        Retourne les sous-dossiers du dossier dont le
        nom est donné, triés par profondeur ascendante.
        Peut lever l’exception suivante :
        - YMDFolderDoesNotExist si le dossier n’existe pas
        """

        def depth_key(folder_name: str) -> int:
            return folder_name.count("/")

        logger.debug(f"Getting subfolders of '{folder_name}'")

        folders = self.get_folders()
        if folder_name not in folders:
            raise YMDFolderDoesNotExistError(folder_name)

        subfolders = [
            folder
            for folder in folders
            if folder.startswith(folder_name) and folder != folder_name
        ]

        subfolders.sort(key=depth_key, reverse=reverse)
        return subfolders

    def get_files_data(
        self,
        *,
        max_recursion_depth: int | None = None,
    ) -> dict[str, list[mail_utils.Mail]]:
        """
        Retourne un dictionnaire de fichiers téléversés dans le dossier cible
        associant leur nom à une liste contenant les mails de leurs morceaux.
        Si une profondeur de récursion est donnée, affiche les fichiers et
        sous-dossiers ayant une profondeur inférieure ou égale ; sinon,
        affiche tous les fichiers et sous-dossiers de l’arborescence.
        Peut lever l’exception suivante :
        - YMDFilesRetrievalError si les fichiers n’ont pas pu être récupérés
        """
        result = self._get_files_data_in_folder(self.target_folder)

        if max_recursion_depth is not None and max_recursion_depth <= 0:
            return result

        # Parcourt les sous-dossiers soit pour récupérer leurs fichiers, soit
        # pour les ajouter à la liste en fonction de la profondeur de récursion
        subfolders = self._get_subfolders(self.target_folder)
        for subfolder in subfolders:
            # Détermine le préfixe des clés du dictionnaire (le
            # dossier parent des fichiers, relatif au dossier cible)
            relative_folder = f"{subfolder.removeprefix(f'{self.target_folder}/')}/"

            # Note: sujet aux faux-positifs si un dossier contient des "/"
            depth = relative_folder.count("/")

            # Si le sous-dossier est à la profondeur
            # maximale, on l’affiche mais pas son contenu
            if max_recursion_depth is not None and depth == max_recursion_depth:
                # Ajoute un élément avec 0 morceau
                result.update({relative_folder: []})
                continue

            # Si sa profondeur est supérieure à la
            # profondeur maximale, on ne l’affiche pas
            if max_recursion_depth is not None and depth > max_recursion_depth:
                continue

            result.update(
                self._get_files_data_in_folder(
                    subfolder,
                    dict_key_prefix=relative_folder,
                )
            )

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
            progress_text = "Downloaded chunk(s):"
            total_chunks = len(files[file_name])
            for chunk_index, file_chunk_mail in enumerate(files[file_name]):
                logger.debug(f"Downloading chunk: '{file_chunk_mail.subject}'")
                print_progress(progress_text, chunk_index, total_chunks)

                # Télécharge la pièce jointe et écrit son contenu à la fin du fichier
                written_bytes_count = dst_buffer.write(
                    self._ym[0].get_attachment_content_of_mail(file_chunk_mail)
                )
                logger.debug(f"Wrote {written_bytes_count} bytes")

            print_progress(
                progress_text, total_chunks, total_chunks, final_newline=True
            )

        # Récupère le nom des fichiers téléversés et
        # les infos sur les mails de leurs morceaux
        logger.debug(f"Checking the existence of {file_name} on the server")
        files = self.get_files_data(max_recursion_depth=0)

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
                raise FileExistsError(dst_file.resolve())

            # Sinon, on télécharge le fichier grâce à ses morceaux
            with dst_file.open("wb") as file:
                _download_file_into(file_name, file)
            return

        # Sinon un buffer de destination est donné, alors on écrit dedans
        if dst_path_or_buffer is not None:
            _download_file_into(file_name, dst_path_or_buffer)

    def _upload_file_or_buffer(
        self,
        file_path: Path,
        buffer: BufferedReader | None,
        start_chunk: int,
        workers: int,
        progress_text_override: str | None = None,
    ) -> None:
        """
        Téléverse le fichier dont le chemin est donné en paramètre ou le
        contenu du buffer donné en le découpant en plusieurs morceaux s’il
        est plus gros que la taille maximale autorisée pour les pièces jointes.
        Le chemin donné est également utilisé pour déterminer
        le nom du fichier sur le serveur une fois téléversé.
        Si un numéro de morceau est donné, commence le
        téléversement à partir de celui-ci au lieu du début.
        Peut lever l’exception suivante :
        - YMDChunkAlreadyExists si le fichier existe déjà sur le serveur
        """

        def create_attachment_with_buffer(
            buffer: BufferedReader, chunk_index: int
        ) -> email.mime.application.MIMEApplication:
            """
            Retourne une pièce jointe créée avec le morceau du contenu
            du buffer correspondant à l’indice donné en paramètre.
            """
            return email.mime.application.MIMEApplication(
                file_utils.load_chunk(
                    buffer,
                    chunk_start=chunk_index * YahooMailAPI.MAX_ATTACHMENT_SIZE,
                    chunk_end=(chunk_index + 1) * YahooMailAPI.MAX_ATTACHMENT_SIZE,
                ),
                _subtype=file_path.name.split(".")[-1],
            )

        def upload_batch(batch: tuple[int, ...], connection: YahooMailAPI) -> None:
            """
            Téléverse les morceaux avec les indices
            donnés avec la connexion donnée.
            """
            nonlocal uploaded_chunks_count  # Utilise la variable déclarée hors-fonction

            for chunk_index in batch:
                attachment_name = self._get_subject_for_file_chunk(
                    file_path.name, chunk_index
                )

                # Crée un nouveau mail
                msg = email.mime.multipart.MIMEMultipart()

                # Définit l’objet comme le nom du morceau pour les identifier
                # Note : l’expéditeur et le destinataire ne sont pas nécessaires
                msg["Subject"] = attachment_name

                # Ajoute la pièce jointe
                if buffer is None:
                    with file_path.open("rb") as file:
                        attachment = create_attachment_with_buffer(file, chunk_index)
                else:
                    attachment = create_attachment_with_buffer(buffer, chunk_index)

                attachment.add_header(
                    "Content-Disposition", "attachment", filename=attachment_name
                )
                msg.attach(attachment)

                # Ajoute le mail au dossier
                logger.debug(f"Uploading email {attachment_name}")
                print_progress(
                    progress_text, uploaded_chunks_count, needed_chunks_count
                )
                connection.save_mail(msg, self._target_folder)
                uploaded_chunks_count += 1

        # Vérifie si un morceau de fichier existe déjà sur le serveur
        # possédant le même nom que le morceau qui va être téléversé
        logger.debug(f"Checking the existence of {file_path.name} on the server")
        files_data = self.get_files_data(max_recursion_depth=0)
        first_subject = self._get_subject_for_file_chunk(file_path.name, start_chunk)
        already_present_subjects = [
            mail.subject for mail in files_data.get(file_path.name, [])
        ]

        # S’il existe déjà, on s’arrête
        if first_subject in already_present_subjects:
            raise YMDChunkAlreadyExists(first_subject)

        # Pour chaque indice de début de morceau de fichier
        needed_chunks_count = self._get_chunk_count_for_file(file_path, buffer=buffer)
        logger.debug(f"{needed_chunks_count} chunk(s) will be needed")

        progress_text = (
            progress_text_override if progress_text_override else "Uploaded chunk(s):"
        )

        chunks_indices = tuple(range(start_chunk, needed_chunks_count))

        # Distribue les morceaux équitablement entre toutes les connexions
        # Note : les nombres impairs causent des déséquilibres ; la ou
        # les premières connexions prennent le surplus grâce au modulo.
        batches_size = len(chunks_indices) // workers + len(chunks_indices) % workers

        batches = [
            chunks_indices[batches_size * i_batch : batches_size * (i_batch + 1)]
            for i_batch in range(workers)
        ]

        # Téléverse un batch par connexion
        with concurrent.futures.ThreadPoolExecutor(workers) as executor:
            futures: list[concurrent.futures.Future] = []
            uploaded_chunks_count = 0
            for ym, batch in zip(self._ym, batches, strict=True):
                futures.append(
                    executor.submit(
                        upload_batch,
                        batch=batch,
                        connection=ym,
                    )
                )

            concurrent.futures.wait(futures)

        print_progress(
            progress_text, needed_chunks_count, needed_chunks_count, final_newline=True
        )

    def upload_file_or_folder_recursively(
        self,
        file_or_folder_path: Path,
        source_buffer: BufferedReader | None = None,
        start_chunk: int = 0,
        local_base_folder: str | None = None,
        workers: int = 1,
    ) -> None:
        """
        Téléverse le fichier ou le dossier dont le chemin est
        donné en paramètre, ou le contenu du buffer donné.
        Le chemin donné est utilisé pour lire le contenu, mais aussi pour
        définir le nom du fichier/dossier une fois le contenu téléversé.
        Si un numéro de morceau est donné, le téléversement commencera à partir de
        celui-ci au lieu du début (0 signifie « commencer au premier morceau »).
        Peut lever les exceptions suivantes :
        - FileNotFoundError si le fichier ou dossier donné n’est pas trouvé localement
        - YMDChunkAlreadyExists si le fichier existe déjà sur le serveur
        """

        if source_buffer is None and not file_or_folder_path.exists():
            raise FileNotFoundError(file_or_folder_path)

        # Si le chemin donné pointe vers un fichier, on peut le téléverser directement
        if not file_or_folder_path.is_dir():
            self._upload_file_or_buffer(
                file_or_folder_path,
                buffer=source_buffer,
                start_chunk=start_chunk,
                workers=workers,
            )
            return

        # Sinon c’est un dossier donc on le téléverse récursivement
        logger.debug(f"Uploading folder {file_or_folder_path} recursively")

        # Sauvegarde le nom du dossier local duquel on part, pour pouvoir
        # le supprimer du chemin de chacun de ses fichiers et sous-dossiers
        if local_base_folder is None:
            local_base_folder = str(file_or_folder_path)

        folder_content = tuple(file_or_folder_path.iterdir())
        for inner_file_or_folder in folder_content:
            if inner_file_or_folder.is_dir():
                logger.debug(f"Detected subfolder to upload: '{inner_file_or_folder}'")
                previous_target_folder = self.target_folder

                # Crée le sous-dossier nécessaire
                self.target_folder = f"{self.target_folder}/{inner_file_or_folder.name}"

                self.upload_file_or_folder_recursively(
                    inner_file_or_folder,
                    source_buffer=source_buffer,
                    start_chunk=start_chunk,
                    local_base_folder=local_base_folder,
                    workers=workers,
                )

                self.target_folder = previous_target_folder
            else:
                try:
                    self._upload_file_or_buffer(
                        inner_file_or_folder,
                        buffer=source_buffer,
                        start_chunk=start_chunk,
                        progress_text_override=f"{inner_file_or_folder}:",
                        workers=workers,
                    )
                except YMDChunkAlreadyExists:
                    logger.exception(
                        f"Error while trying to upload file {inner_file_or_folder}"
                    )
                    break

    def remove_file_or_folder_recursively(
        self,
        file_or_folder_name: str,
        *,
        recurse: bool = False,
    ) -> None:
        """
        Supprime le fichier ou dossier dont le chemin est donné en
        paramètre en supprimant tous les mails contenant ses morceaux.
        Si la récursion est activée, le dossier donné est supprimé
        même s’il contient encore des fichiers ou sous-dossiers.
        Peut lever l’exception suivante :
        - YMDFileDoesNotExist si le fichier n’existe pas sur le serveur
        - YMDFolderDoesNotExist si le dossier n’existe pas sur le serveur
        """
        # Récupère le nom des fichiers téléversés et
        # les infos sur les mails de leurs morceaux
        logger.debug(
            f"Trying to delete file {file_or_folder_name} "
            f"from folder {self.target_folder}"
        )
        files_data = self.get_files_data(max_recursion_depth=0)

        if file_or_folder_name in files_data:
            # Vérifie si un dossier avec le même nom existe, et lève une exception
            # si c’est le cas (cela devrait éviter des erreurs de suppression)
            if file_or_folder_name in self.get_folders():
                raise YMDAmbiguousNameError(file_or_folder_name, self.target_folder)

            self._ym[0].delete_mails(
                files_data[file_or_folder_name], self.target_folder, move_to_trash=True
            )
            return

        logger.debug(
            f"File '{file_or_folder_name}' not found in folder"
            f"'{self.target_folder}', trying to delete a folder instead"
        )

        # Si aucun dossier avec ce nom n’existe
        if file_or_folder_name not in self.get_folders():
            if recurse:
                raise YMDFolderDoesNotExistError(file_or_folder_name)
            raise YMDFileDoesNotExist(file_or_folder_name)

        logger.debug(f"Found folder '{file_or_folder_name}'")

        # Sinon, on a trouvé un dossier, donc on vérifie qu’il est vide
        files_data = self._get_files_data_in_folder(file_or_folder_name)
        if files_data and not recurse:
            raise YMDFolderIsNotEmptyError(file_or_folder_name)

        # Supprime tous les fichiers et sous-dossiers du dossier, puis lui-même
        files_data_to_delete: list[mail_utils.Mail] = []
        for file_data in files_data.values():
            files_data_to_delete.extend(file_data)
        self._ym[0].delete_mails(
            files_data_to_delete, self.target_folder, move_to_trash=True
        )
        for subfolder in self._get_subfolders(file_or_folder_name, reverse=True):
            self._ym[0].delete_folder(subfolder)

        self._ym[0].delete_folder(file_or_folder_name)

    def noop(self) -> None:
        """
        Envoie un NOOP (NO OPeration) au serveur IMAP.
        N’a aucun effet, mais peut être utilisé pour ne pas subir de timeout.
        """
        for connection in self._ym:
            connection.noop()

    def logout(self) -> None:
        """
        Clôt la connexion au serveur IMAP. Toutes  les commandes
        suivantes lèveront une erreur imaplib.IMAP4.error.
        """
        for connection in self._ym:
            connection.logout()
