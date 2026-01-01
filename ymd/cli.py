import argparse
import logging
from pathlib import Path

from ymd import file_utils
from ymd.display import print_files_list
from ymd.yahoomaildrive import YahooMailDrive

YMD_FOLDER_NAME = "ymd"
YMD_DEFAULT_LOG_LEVEL = logging.ERROR

DEFAULT_CREDENTIALS_FILE_NAME = "credentials.toml"
DEFAULT_CREDENTIALS_LOCATIONS = [
    Path(DEFAULT_CREDENTIALS_FILE_NAME),
    Path("~/.config/ymd", DEFAULT_CREDENTIALS_FILE_NAME),
]


def callback_list_command(args: argparse.Namespace, ymd: YahooMailDrive) -> None:
    """Callback pour la commande "list" de la CLI."""
    print_files_list(ymd.get_files_data(), long=args.long)


def callback_download_command(args: argparse.Namespace, ymd: YahooMailDrive) -> None:
    """Callback pour la commande "download" de la CLI."""
    ymd.download(args.file, args.dest)


def callback_upload_command(args: argparse.Namespace, ymd: YahooMailDrive) -> None:
    """Callback pour la commande "upload" de la CLI."""
    ymd.upload_file_or_folder_recursively(Path(args.file), start_chunk=args.start_chunk)


def callback_remove_command(args: argparse.Namespace, ymd: YahooMailDrive) -> None:
    """Callback pour la commande "remove" de la CLI."""
    ymd.remove(args.file)


def callback_list_folders_command(
    _args: argparse.Namespace, ymd: YahooMailDrive
) -> None:
    """Callback pour la commande "list-folders" de la CLI."""
    print(*ymd.get_folders(), sep="\n")


def _add_global_arguments(parser: argparse.ArgumentParser) -> None:
    """Ajoute les arguments globaux au parser d’argument donné."""
    parser.add_argument(
        "-c",
        "--credentials",
        help="path of the credentials file to use",
        default=DEFAULT_CREDENTIALS_FILE_NAME,
    )
    parser.add_argument(
        "-f",
        "--folder",
        help="name of the destination folder",
        default=YMD_FOLDER_NAME,
    )
    parser.add_argument("--debug", help="enable debug logs", action="store_true")


def main() -> None:
    parser = argparse.ArgumentParser(description="YahooMailDrive CLI")
    subparsers = parser.add_subparsers()

    # Définit les commandes et leurs arguments
    # list
    list_command_parser = subparsers.add_parser("list", aliases=["ls"])
    list_command_parser.add_argument(
        "-l",
        "--long",
        action="store_true",
        help="output more information about the files",
    )
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
    upload_command_parser.add_argument("file", help="path of the file/folder to upload")
    upload_command_parser.add_argument(
        "--start-chunk",
        type=int,
        default=0,
        help="start upload from the given chunk number",
    )
    _add_global_arguments(upload_command_parser)
    upload_command_parser.set_defaults(callback=callback_upload_command)

    # remove
    remove_command_parser = subparsers.add_parser("remove", aliases=["rm"])
    remove_command_parser.add_argument("file", help="name of the remote file")
    _add_global_arguments(remove_command_parser)
    remove_command_parser.set_defaults(callback=callback_remove_command)

    # list-folders
    list_folders_command_parser = subparsers.add_parser("list-folders", aliases=["lsf"])
    _add_global_arguments(list_folders_command_parser)
    list_folders_command_parser.set_defaults(callback=callback_list_folders_command)

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
    address, password = file_utils.load_credentials(
        Path(args.credentials), DEFAULT_CREDENTIALS_LOCATIONS
    )

    # Effectue les actions déterminées par les arguments
    with YahooMailDrive(address, password, target_folder=args.folder) as ymd:
        args.callback(args, ymd)


if __name__ == "__main__":
    main()
