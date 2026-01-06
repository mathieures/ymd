"""Module contenant toutes les exceptions liées à YMD."""


class YMDException(BaseException):
    """Classe de base pour toutes les exceptions de YMD."""


class YMDChunkAlreadyExists(YMDException):
    def __init__(self, chunk_name: str) -> None:
        super().__init__(f"A chunk named '{chunk_name}' already exists on the server.")


class YMDFileDoesNotExist(YMDException):
    def __init__(self, file_name: str) -> None:
        super().__init__(f"The file '{file_name}' was not found on the server.")


class YMDFetchResultExtractionError(YMDException):
    def __init__(self, fetch_result: tuple) -> None:
        super().__init__(f"Could not extract FETCH result from: {fetch_result}.")


class YMDListResultExtractionError(YMDException):
    def __init__(self, list_result: tuple) -> None:
        super().__init__(f"Could not extract LIST result from: {list_result}.")


class YMDMailsRetrievalError(YMDException):
    def __init__(self, folder_name: str, server_reply: list) -> None:
        super().__init__(
            f"Could not retrieve the mails in folder '{folder_name}', "
            f"the server's reply was invalid: {server_reply}."
        )


class YMDFilesRetrievalError(YMDException):
    def __init__(self, folder_name: str) -> None:
        super().__init__(f"Could not get the files data in '{folder_name}'.")


class YMDAmbiguousNameError(YMDException):
    def __init__(self, ambiguous_name: str, target_folder: str) -> None:
        super().__init__(
            f"The name '{ambiguous_name}' is ambiguous and could target "
            f"both a file in the folder '{target_folder}' or a folder."
        )


class YMDFolderDoesNotExistError(YMDException):
    def __init__(self, folder_name: str) -> None:
        super().__init__(f"Folder '{folder_name}' was not found on the server.")


class YMDFolderIsNotEmptyError(YMDException):
    def __init__(self, folder_name: str) -> None:
        super().__init__(
            f"Folder '{folder_name}' is not empty; enable recursion to force deletion."
        )
