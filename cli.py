import argparse
import logging

from ymd import file_utils
from ymd.yahoomaildrive import YahooMailDrive

YMD_FOLDER_NAME = "ymd"
YMD_DEFAULT_LOG_LEVEL = logging.ERROR


def callback_list_command(_args: argparse.Namespace, ymd: YahooMailDrive) -> None:
    """Callback pour la commande "list" de la CLI."""
    print(*ymd.get_files_data().keys(), sep="\n")


def callback_download_command(args: argparse.Namespace, ymd: YahooMailDrive) -> None:
    """Callback pour la commande "download" de la CLI."""
    ymd.download(args.file, args.dest)


def callback_upload_command(args: argparse.Namespace, ymd: YahooMailDrive) -> None:
    """Callback pour la commande "upload" de la CLI."""
    ymd.upload(args.file)


def callback_remove_command(args: argparse.Namespace, ymd: YahooMailDrive) -> None:
    """Callback pour la commande "remove" de la CLI."""
    ymd.remove(args.file)


def _add_global_arguments(parser: argparse.ArgumentParser) -> None:
    """Ajoute les arguments globaux au parser d’argument donné."""
    parser.add_argument(
        "-c",
        "--credentials",
        help="path of the credentials file to use",
        default="credentials.toml",
    )
    parser.add_argument(
        "-f",
        "--folder",
        help="name of the destination folder",
        default=YMD_FOLDER_NAME,
    )
    parser.add_argument("--debug", help="enable debug logs", action="store_true")


def main():
    parser = argparse.ArgumentParser(description="YahooMailDrive CLI")
    subparsers = parser.add_subparsers()

    # Définit les commandes et leurs arguments
    # list
    list_command_parser = subparsers.add_parser("list", aliases=["ls"])
    _add_global_arguments(list_command_parser)
    list_command_parser.set_defaults(callback=callback_list_command)

    # download
    download_command_parser = subparsers.add_parser("download", aliases=["d"])
    download_command_parser.add_argument("file", help="name of the remote file")
    download_command_parser.add_argument("dest", help="destination path")
    _add_global_arguments(download_command_parser)
    download_command_parser.set_defaults(callback=callback_download_command)

    # upload
    upload_command_parser = subparsers.add_parser("upload", aliases=["u"])
    upload_command_parser.add_argument("file", help="path of the file to upload")
    _add_global_arguments(upload_command_parser)
    upload_command_parser.set_defaults(callback=callback_upload_command)

    # remove
    remove_command_parser = subparsers.add_parser("remove", aliases=["rm"])
    remove_command_parser.add_argument("file", help="name of the remote file")
    _add_global_arguments(remove_command_parser)
    remove_command_parser.set_defaults(callback=callback_remove_command)

    # Parse les arguments
    args = parser.parse_args()

    # Si aucun argument n’est donné, args est vide et essayer d’accéder à un attribut
    # lèvera une exception, donc si c’est le cas on affiche l’aide et on s’arrête
    if not vars(args):
        parser.print_help()
        parser.exit(1)

    # Effectue les actions globales avant l’exécution des commandes
    # Si --debug est donné, active le debug
    log_level = logging.DEBUG if args.debug else YMD_DEFAULT_LOG_LEVEL
    logging.basicConfig(format="%(levelname)s: %(message)s", level=log_level)
    # Charge les informations de connexion
    address, password = file_utils.load_credentials(args.credentials)

    # Effectue les actions déterminées par les arguments
    with YahooMailDrive(address, password, target_folder=args.folder) as ymd:
        args.callback(args, ymd)


if __name__ == "__main__":
    main()
