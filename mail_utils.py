import email.header
import imaplib
import typing


class Mail:
    """Classe représentant très simplement un mail grâce à son ID et son objet."""

    mail_id: str  # C’est un entier, mais les fonctions demandent des chaînes
    subject: str

    def __init__(self, mail_id: str, subject: str) -> None:
        self.mail_id = mail_id
        self.subject = subject

    def __repr__(self) -> str:
        return f"<Mail({self.mail_id}, {self.subject})>"


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


def get_all_mails(imap_server: imaplib.IMAP4_SSL, folder_name: str) -> list[Mail]:
    result = []

    imap_server.select(folder_name, readonly=True)

    # Récupère la liste des ID des mails présents dans le dossier
    _status, data = imap_server.search(None, "ALL")
    mail_ids: bytes = data[0]
    # Pour chaque ID de mail, récupère l’objet du mail
    for mail_id_bytes in mail_ids.split():
        mail_id = mail_id_bytes.decode()  # Entier sous forme de bytes (ex : b"1")

        try:
            subject_data = extract_fetch_result(
                imap_server.fetch(mail_id, "(BODY[HEADER.FIELDS (SUBJECT)])")
            )
        except ValueError as err:
            raise ValueError(f"Could not parse the subject in data: {data}") from err

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
