#!./venv/bin/python3

import sys
from typing import Callable, Optional
from utils.utils import EXIT_ERROR, log
from utils.istream import TuiInputStream, InputStream
from functools import partial


class Tag:
    name = property(lambda self: self._name, None, None, "Nome da tag - para debug.")

    def __init__(self, value: int | str, name: str | None = None):
        if isinstance(value, str):
            self.value = ord(value)
            self._name = value
        else:
            assert (
                name is not None
            ), "name deve ser fornecido se o valor for um inteiro."
            self.value = value
            self._name = name

    def __eq__(self, value: "Tag | str") -> bool:  # type: ignore
        return (
            isinstance(value, Tag)
            and self.value == value.value
            or isinstance(value, str)
            and self._name == value
        )

    def __ne__(self, value: "Tag | str") -> bool:  # type: ignore
        return (
            isinstance(value, Tag)
            and self.value != value.value
            or isinstance(value, str)
            and self._name != value
        )

    def __str__(self) -> str:
        return self._name


class Tags:
    ...
    NUM = Tag(256, "NUM")
    ID = Tag(257, "ID")
    TYPE = Tag(258, "TYPE")
    TRUE = Tag(259, "TRUE")  # apenas para ilustrar
    FALSE = Tag(260, "FALSE")  # apenas para ilustrar
    # TODO
    # CHAR = Tag(261, 'CHAR')
    # STR = Tag(262, 'STR')
    # INT = Tag(263, 'INT')
    # FLOAT = Tag(264, 'FLOAT')
    # PTR = Tag(265, 'PTR')


class Token:
    def __init__(self, tag: Tag | str | int):
        if isinstance(tag, int):
            self.tag = Tag(tag, chr(tag) if 32 <= tag <= 126 else f"TAG_{tag}")
        elif isinstance(tag, str):
            if tag == "":
                self.tag = Tag(0, tag)
            else:
                self.tag = Tag(ord(tag), tag)
        else:
            assert isinstance(tag, Tag), f"{tag}"
            self.tag = tag

    def __eq__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, value: Tag | str
    ) -> bool:
        return (
            isinstance(value, Tag)
            and self.tag == value
            or isinstance(value, str)
            and self.tag.name == value
        )

    def __ne__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, value: Tag | str
    ) -> bool:
        return (
            isinstance(value, Tag)
            and self.tag != value
            or isinstance(value, str)
            and self.tag.name != value
        )

    def __str__(self) -> str:
        return str(self.tag)


class Id(Token):
    name: str

    def __init__(self, name: str):
        super().__init__(Tags.ID)
        self.name = name

    def __str__(self) -> str:
        return self.name


class Type(Token):
    def __init__(self, name: str):
        super().__init__(Tags.TYPE)
        self.name = name

    def __str__(self) -> str:
        return self.name


class Num(Token):
    def __init__(self, value: int):
        super().__init__(Tags.NUM)
        self.value = value


class Lexer:
    _id_table: dict[str, "Token | Id | Type"] = {}
    line = property(
        lambda self: self._cached_line,
        None,
        None,
        "Cached line number from witch line is being parsed.",
    )

    def __init__(
        self,
        istream: InputStream | TuiInputStream,
        logger: Callable[..., None] = lambda *args, **kwargs: None,
    ):
        self._line = 1
        self._cached_line = 1
        self._peek = " "
        self._istream = istream
        self._log = logger
        self._init_id_table()
        # TODO -> detect empty lines: <https://chatgpt.com/g/g-p-6917e068d6c481918f28825411103d8c-compilers/c/69374318-686c-8330-a4db-d750c2e61e83>
        # self._line_emitted_token = False
        # Logs Line Numbers
        self._log_ln: bool = not isinstance(istream, TuiInputStream)
        self._logged_token: int = Lexer.LoggedToken.NONE

    class LoggedToken:
        NONE = 0
        EXPRESSION = 1
        BLOCK = 2

    def _init_id_table(self):
        self._id_table = {
            "true": Token(Tags.TRUE),
            "false": Token(Tags.FALSE),
            "int": Type("int"),  # 32 bits
            "float": Type("float"),  # 32 bits
            "double": Type("double"),  # 64 bits
            "bool": Type("bool"),
            "char": Type("char"),
            "str": Type("str"),
            "i8": Type("i8"),
            "i16": Type("i16"),
            "u16": Type("u16"),
            "u32": Type("u32"),
            "i64": Type("i64"),
            "u64": Type("u64"),
            "void": Type("void"),  # for pointers and functions
        }

    def _open_source_file(self, filename: str):
        """
        Abre o arquivo de código fonte e carrega seu conteúdo na variável
        _source_code.

        :param filename: nome do arquivo a ser aberto
        """
        with open(filename, "r") as file:
            self._source_code = file.read()

    def _nesting_comment(self, symbols: str) -> bool:
        """Trata comentários aninhados
        symbols: str -> tipo de comentário: '#<>#' ou '/**/'
        returns: True if line break occurs.
        """
        had_nl = False
        nesting = 1
        while nesting > 0:
            while self._peek != symbols[2] or self._istream.peek() != symbols[3]:
                self._peek = self._get_next_char()
                if self._peek == "\n":
                    had_nl = True
                    self._peek = self._get_next_char()
                if self._peek == symbols[0] and self._istream.peek() == symbols[1]:
                    nesting += 1
                    self._peek = self._get_next_char()
                    self._peek = self._get_next_char()
            nesting -= 1
            self._peek = self._get_next_char()
            self._peek = self._get_next_char()
        return had_nl

    def _log_line_interrupt(self) -> Token | None:
        """Deals with line interrupt and returns a semicolon token if an expression was logged."""
        token: Token | None = None
        if self._logged_token & Lexer.LoggedToken.EXPRESSION:
            self._log(f"<;>")
            self._log(f"{self._line:3}: ", end="", flush=True)
            self._peek = self._get_next_char()
            token = Token(";")
        elif self._logged_token & Lexer.LoggedToken.BLOCK:
            self._log(f"\n{self._line:3}: ", end="", flush=True)
            self._cached_line = self._line + 1  # WATCH
        else:
            self._log("\r", end="", flush=True)
            self._log(f"{self._line:3}: ", end="", flush=True)
            self._cached_line = self._line + 1  # WATCH
        self._logged_token = Lexer.LoggedToken.NONE
        return token

    def _get_next_char(self):
        """Simula o cin.get() lendo da string armazenada"""
        # Implementação do método para obter o próximo caractere do código fonte
        while not self._istream.eof_reached:
            char = self._istream.get_char()
            # Se for espaço ou tabulação, ignora
            if char in "\t":
                continue
            if char == "\n" or (char == "\r" and self._istream.peek() == "\n"):
                self._line += 1
                return "\n"
            return char
        return ""  # Fim da entrada

    def scan(self) -> Token | Id | Type | Num:
        """Implementação do método de varredura (scan) do lexer."""
        while True:
            # region 0. Line continuation
            if self._peek == "\\" and self._istream.peek() == "\n":
                self._peek = self._get_next_char()  # consume '\'
                self._peek = self._get_next_char()  # consume '\n'
                continue

            # region 1. Conta o número de linhas, ignorando os espaços em branco
            while self._peek.isspace():
                if self._peek == "\n":
                    token = self._log_line_interrupt()
                    if token is not None:
                        return token
                self._peek = self._get_next_char()
            # endregion

            # region 2. Trata números
            if self._peek.isdigit():
                # region Inteiros
                num_str = ""
                while self._peek.isdigit():
                    num_str += self._peek
                    self._peek = self._get_next_char()

                if self._peek != ".":
                    num = int(num_str)
                    self._log(f"<NUM, {num}> ", end="")
                    self._logged_token = True
                    return Num(num)
                # endregion
                else:
                    # region Ponto Flutuante
                    num_str += self._peek
                    self._peek = self._get_next_char()
                    while self._peek.isdigit():
                        num_str += self._peek
                        self._peek = self._get_next_char()
                    # endregion
            # endregion

            # TODO -> Tratar identificadores genéricos de forma diferente de palavras-reservadas
            # region 3. Trata identificadores e palavras reservadas
            if self._peek.isalpha():
                id_str = ""
                while self._peek.isalpha():
                    id_str += self._peek
                    self._peek = self._get_next_char()

                if id_str in self._id_table:
                    # para debugging
                    token_found: Token | Type | Id = self._id_table[id_str]
                    if isinstance(token_found, Type) or isinstance(token_found, Id):
                        # self._log(f'<{id_str}> ', end='')
                        self._log(
                            f"<{token_found.tag.name}, {token_found.name}> ", end=""
                        )
                    else:
                        self._log(f"<{token_found.tag.name}> ", end="")
                    self._logged_token = True
                    return token_found

                # se o identificador não estiver na tabela, cria um novo
                else:
                    new_id = Id(id_str)
                    self._id_table[id_str] = new_id
                    self._log(f"<{new_id.tag}, {new_id.name}> ", end="")
                    self._logged_token = True
                    return new_id
            # endregion

            # region 4. Ignora comentários
            # #...\n and #<...>#
            if self._peek == "#":
                if self._istream.peek() == "<":
                    if self._nesting_comment("#<>#"):
                        if self._logged_token:
                            token = self._log_line_interrupt()
                            if token is not None:
                                return token
                        self._peek = self._get_next_char()
                    continue
                else:
                    while self._peek != "\n" and self._peek != "":
                        self._peek = self._get_next_char()
                    if self._peek == "\n":
                        token = self._log_line_interrupt()
                        if token is not None:
                            return token
                        else:
                            self._peek = self._get_next_char()
                            continue
            # //...\n and /*...*/ ]
            if self._peek == "/":
                if self._istream.peek() == "/":
                    while self._peek != "\n" and self._peek != "":
                        self._peek = self._get_next_char()
                    if self._peek == "\n":
                        token = self._log_line_interrupt()
                        if token is not None:
                            return token
                        else:
                            self._peek = self._get_next_char()
                            continue
                elif self._istream.peek() == "*":
                    if self._nesting_comment("/**/"):
                        if self._logged_token:
                            token = self._log_line_interrupt()
                            if token is not None:
                                return token
                        self._peek = self._get_next_char()
                    continue
            # endregion

            # region 5. Trata operadores
            t_oper = Token(self._peek)  # pyright: ignore[reportArgumentType]
            if t_oper.tag.name == "":
                return t_oper  # EOF
            if t_oper.tag.name in [" ", "\r", "\t"]:
                # TODO -> better account for line breaker
                self._peek = self._get_next_char()
                continue
            else:
                self._log(f"<'{t_oper.tag}'> ", end="")
                if self._logged_token & Lexer.LoggedToken.EXPRESSION:
                    if t_oper.tag == ";":
                        self._log("\n", end="\t")
                else:
                    self._logged_token |= (
                        Lexer.LoggedToken.BLOCK
                        if t_oper.tag.name in ["{", "}", ",", ";"]
                        else Lexer.LoggedToken.EXPRESSION
                    )
            self._peek = self._get_next_char()
            # endregion

            return t_oper

    def start(self):
        # if self._log_ln:
        self._log("  1: ", end="")
        while self._peek != "":
            self.scan()
        self.finish()

    def finish(self):
        if not self._logged_token:
            self._log("\r    ")


def show_help():
    print(
        "\033[34m"
        # f'Usage: python {sys.argv[0]} <source_file> [<output_file>] [-!|--log] [-no|--no-optimize] [-l|--lexer]\n'
        f"Usage: python {sys.argv[0]} <source_file> [-!|--log]\n"
        "\t[-?|--help] show this help\n"
        "\t[-!|--log] log output using tui\n"
        "\033[m"
    )


def main(filename: str, log_enabled: bool, *args, **kwargs) -> None:
    if log_enabled:
        from utils.tui import Tui

        ui = Tui(mode=Tui.Mode.LEXER)
        istream = TuiInputStream(filename, partial(ui.log_source, end=""))
        lexer = Lexer(istream, ui.log_tokens)
        ui.run(lexer.start, hold=True)
    else:
        istream = InputStream(filename)
        lexer = Lexer(istream, log)
        lexer.start()


if __name__ == "__main__":
    from utils.utils import log_warning, log_error, EXIT_ERROR

    # Verifica se o usuário passou o nome do arquivo
    if len(sys.argv) < 2:
        log_error("Error: No file name provided")
        log_warning(
            "Usage: \033[32m" "python" f"\033[m {sys.argv[0]} \033[34m<arquivo_fonte>"
        )
        sys.exit(EXIT_ERROR)

    main(filename=sys.argv[1], log_enabled=True)
