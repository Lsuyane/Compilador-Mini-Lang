from typing import Callable


# TODO -> Input Stream-based
# class InputStream:
#     position = property(lambda self: self._position, None, None, "Current position in the input stream.")
#     eof_reached = property(lambda self: self._eof_reached, None, None, "Indicates if the end of the stream has been reached.")
#
#     def __init__(self, file_path: str):
#         """Initializes the InputStream with the file path."""
#         self.file = open(file_path, 'r', encoding='utf-8')  # Open the file in read mode
#         self._position = 0  # Track the current position in the file
#         self._eof_reached = False
#
#     def get_char(self) -> str:
#         """Reads the next character from the file."""
#         char = self.file.read(1)
#         if char:
#             self._position += 1
#             return char
#         self._eof_reached = True
#         return ''  # Return empty string if EOF is reached
#
#     def __del__(self):
#         """Ensures the file is closed when the InputStream is deleted."""
#         self.file.close()
#
#
# class TuiInputStream:
#     position = property(lambda self: self._position, None, None, "Current position in the input stream.")
#     eof_reached = property(lambda self: self._eof_reached, None, None, "Indicates if the end of the stream has been reached.")
#
#     def __init__(self, file_path: str, echo_func: Callable[[str], None]):
#         """Initializes the InputStream with the file path."""
#         self.file = open(file_path, 'r', encoding='utf-8')  # Open the file in read mode
#         self._position = 0  # Track the current position in the file
#         self.echo_func = echo_func  # Function to echo characters to TUI
#         self._eof_reached = False
#
#     def get_char(self) -> str:
#         """Reads the next character from the file."""
#         char = self.file.read(1)
#         if char:
#             self._position += 1
#             self.echo_func(char)
#             return char
#         self._eof_reached = True
#         return ''  # Return empty string if EOF is reached
#
#     def __del__(self):
#         """Ensures the file is closed when the InputStream is deleted."""
#         self.file.close()


# String based InputStream
class InputStream:
    position = property(
        lambda self: self._position, None, None, "Current position in the input stream."
    )
    eof_reached = property(
        lambda self: self._eof_reached,
        None,
        None,
        "Indicates if the end of the stream has been reached.",
    )

    def __init__(self, file_path: str):
        """Initializes the InputStream with the file path."""
        with open(file_path, "r", encoding="utf-8") as file:
            self._source_code = file.read()
        self._position = 0  # Track the current position in the source code
        self._eof_reached = False

    def get_char(self) -> str:
        """Reads the next character from the source code."""
        if self._position < len(self._source_code):
            char = self._source_code[self._position]
            self._position += 1
            return char
        self._eof_reached = True
        return ""  # Return empty string if EOF is reached

    def peek(self, offset: int = 0) -> str:
        """Peeks at the character at the current position plus offset without advancing."""
        pos = self._position + offset
        if pos < len(self._source_code):
            return self._source_code[pos]
        return ""  # Return empty string if EOF is reached


class TuiInputStream:
    position = property(
        lambda self: self._position, None, None, "Current position in the input stream."
    )
    eof_reached = property(
        lambda self: self._eof_reached,
        None,
        None,
        "Indicates if the end of the stream has been reached.",
    )

    def __init__(self, file_path: str, echo_func: Callable[[str], None]):
        """Initializes the InputStream with the file path."""
        with open(file_path, "r", encoding="utf-8") as file:
            self._source_code = file.read()
        self._position = 0  # Track the current position in the source code
        self.echo_func = echo_func  # Function to echo characters to TUI
        self._eof_reached = False

    def get_char(self) -> str:
        """Reads the next character from the source code."""
        if self._position < len(self._source_code):
            char = self._source_code[self._position]
            self._position += 1
            self.echo_func(char)
            return char
        self._eof_reached = True
        return ""  # Return empty string if EOF is reached

    def peek(self, offset: int = 0) -> str:
        """Peeks at the character at the current position plus offset without advancing."""
        pos = self._position + offset
        if pos < len(self._source_code):
            return self._source_code[pos]
        return ""  # Return empty string if EOF is reached
