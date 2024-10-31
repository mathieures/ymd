"""Module contenant toutes les exceptions liées à YMD."""


class YMDException(BaseException):
    """Classe de base pour toutes les exceptions de YMD."""


class YMDFileAlreadyExists(YMDException):
    def __init__(self, file_name: str) -> None:
        super().__init__(f"A file named '{file_name}' already exists on the server.")


class YMDFileDoesNotExist(YMDException):
    def __init__(self, file_name: str) -> None:
        super().__init__(f"The file '{file_name}' was not found on the server.")
