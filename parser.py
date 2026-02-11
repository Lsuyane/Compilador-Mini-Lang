#!/usr/bin/env python3
from functools import partial
import sys
from typing import Callable

from istream import InputStream, TuiInputStream
from options import *
from tui import Tui
from utils import EXIT_ERROR, log, log_error
from lexer import Lexer, Num, Token, Tag, Tags, Id, Type
from symbols import Symbol, SymTable
from utils import log_warning
from queue import SimpleQueue as Queue


# Definimos uma exceção personalizada para evitar confusão
# com o "SyntaxError" nativo do Python
class ParseError(Exception):
    pass


class Parser:
    _id_queue: Queue[Id]

    def __init__(
        self,
        lexer: Lexer,
        logger: Callable = log,
        warn_logger: Callable = log_warning,
        optimize: bool = True,
    ):
        # FIXME
        self._lexer = lexer
        self._lookahead: Token = Token("")
        self._optimize = optimize
        self._sym_table = SymTable()
        self._id_queue = Queue()
        self._log = logger
        self._warn = warn_logger

        if self._optimize:
            self.accumulator: int = 0

    def start(self):
        """Inicia o processo de análise lendo o primeiro token."""
        self._lookahead = self._lexer.scan()
        self.program()
        self._lexer.finish()

        # Verifica se o último caractere é o marcador vazio (nil ⇒ EOF)
        if self._lookahead != "":
            raise ParseError()

    def program(self):
        """
        Regra:
            program -> { symTable=null; } stmts
        """
        # SymTable inicia vazia no __init__
        self.stmts()

    def stmts(self):
        """Statements
        Regras:
            stmts -> stmt stmts | ϵ
            stmt -> block | expr;
        """
        while True:
            # stmt -> block
            if self._lookahead.tag == "{":
                self.block()
                continue
            if self.expr():
                if self._lookahead == ";":
                    self.match(Tag(";"))
                else:
                    raise ParseError(
                        f"Erro na linha {self._lexer.line}:"
                        " fim de linha ou ';' esperado."
                    )
                continue
            # Produção vazia
            return

    def expr(self) -> bool:
        """lval_lst declr_or_rval_lst | rval_lst"""
        # stmt -> lval_lst rval_lst
        if self.lval_lst():
            if not self.declr_or_rval_lst():
                self.clear_queue()
                if self._lookahead == ";":
                    self._warn(
                        f"[warning] standalone expression at line :{self._lexer.line}."
                    )
            return True
        # stmt -> rval_lst
        if self.rval_lst():
            if self._lookahead == ";":
                self._warn(
                    f"[warning] standalone expression at line :{self._lexer.line}."
                )
            return True
        return False

    def block(self):
        """
        Regra:
            block -> { saved= symTable;
                       symTable = SymTable(symTable);
                       print('{');
                     } { stmts } { symTable = saved; print('}'); }
        """
        self.match(Tag("{"))

        # TODO -> Check when using captures
        # if not self.match(TAG('{')):
        #     raise ParseError(f"Erro na linha {self._lexer.line}:"
        #                      "era esperado '{' no início do bloco.")

        self._log("{")  # ação semântica: imprime '{'

        # 1. Salva tabela atual
        saved_table = self._sym_table  # ação semântica

        # 2. cria nova tabela aninhada
        self._sym_table = SymTable(previous=saved_table)

        self.stmts()

        if self._lookahead != "}":
            raise ParseError(
                f"Erro na linha {self._lexer.line}:"
                "era esperado '}' no final do bloco."
            )
        self.match(Tag("}"))
        self._log("\n}", end="")  # ação semântica: imprime '}'

        # ação semântica: restaura tabela anterior
        self._sym_table = saved_table
        del saved_table

    def lval_lst(self) -> bool:
        """Left-value list
        Regras:
            lval_lst -> lval [, lval_lst]'
            lval -> ID { push(Id(<lookahead>)) }
        """
        ret = self._lookahead.tag == Tags.ID
        while ret:
            assert isinstance(self._lookahead, Id)
            # lval -> ID { push(ID(<lookahead>)) }
            id = self._lookahead
            self.match(Tags.ID)
            self.queue(id)  # ação semântica: empilha o Id

            # REFACTOR -> Clear
            # raise ParseError(f'Erro na linha {self._lexer.line}:'
            #                  ' era esperado um identificador de variável,'
            #                  f'foi passado {self._lookahead.tag.name} ao invés disso.')

            # if not self.match(TAG.ID):
            #     raise ParseError(f"Erro na linha {self._lexer.line}:"
            #                      " era esperado um identificador de variável.")

            # verifica se a variável foi declarada
            # symbol = self.find(name)
            # if symbol is None:
            #     raise ParseError(f"Erro na linha {self._lexer.line}:"
            #                      f" a variável '{name}' não foi declarada.")
            # self._log(f'{name}', end='', flush=True)  # ação semântica

            # lval_lst -> lval , lval_lst
            if self._lookahead == ",":
                self.match(Tag(","))
            else:
                break
            ret = self._lookahead.tag == Tags.ID
        # Not a left-value
        return ret

    def declr_or_rval_lst(self) -> bool:
        """Expressions
        Regras:
            declr_or_rval_lst -> :
                type {
                    s = symTable.get(id.lexeme);
                    print(id.lexeme); print(':');
                    print(s.type);
                }
                | = rval_lst | ϵ
        """
        if self._lookahead == ":":
            # declr_or_rval_lst -> : type
            self.match(Tag(":"))

            # TODO -> declr_or_rval_lst -> : = exprs (teremos que quebrar a regra ':' em 2 derivações)
            # self.match(TAG('='))

            t = self._lookahead
            if self._lookahead.tag != Tags.TYPE:
                raise ParseError(
                    f"Erro na linha {self._lexer.line}:"
                    " era esperado um identificador de tipo após declaração."
                )
            self.match(Tags.TYPE)
            assert isinstance(t, Type)
            while not self._id_queue.empty():
                id = self.deque()
                assert id is not None
                name = str(id)
                # ação semântica: declara a variável na tabela de símbolos
                if not self._sym_table.insert(name, Symbol(name, str(t))):
                    raise ParseError(
                        f"Erro na linha {self._lexer.line}:"
                        f" a variável '{name}' já foi declarada no escopo atual."
                    )
                # ação semântica: imprime a declaração
                self._log(f"{name} : {t}", flush=True)

            return True
        elif self._lookahead == "=":
            # declr_or_rval_lst -> = rval_lst
            self.match(Tag("="))
            self.rval_lst()
            return True
        # Produção vazia
        return False

    def rval_lst(self) -> bool:
        """R-value list
        Regras:
            rval_lst -> rval [, rval_lst]'
            rval -> expr { id=deque()); print(id+'=') }
        """
        if self.queue_empty():
            # Standalone expression
            while self._lookahead.tag == Tags.NUM or self._lookahead in ("+", "-"):
                self.opers()
                if self._lookahead == ",":
                    self.match(Tag(","))
                else:
                    return True
            return False

        while True:
            id = self.deque()
            if id is None:
                return True

            # rval -> expr
            self._log(f"{id}=", end="", flush=True)  # ação semântica
            self.opers()
            self._log("")

    def queue_empty(self) -> bool:
        """Checks if the id_queue is empty."""
        return self._id_queue.empty()

    def queue(self, id: Id):
        """Puts an Id onto the id_queue."""
        self._id_queue.put(id)

    def deque(self) -> Id | None:
        """Gets an Id from the id_queue."""
        if self.queue_empty():
            return None
        return self._id_queue.get()

    def clear_queue(self):
        """Clears the id_queue."""
        while not self.queue_empty():
            self.deque()

    # def decls(self):
    #     '''
    #     Regras:
    #         decls -> decl decls | ϵ
    #         decl -> ID : tipo
    #     '''
    #     while self._lookahead.tag == TAG.TYPE:
    #         type = str(self._lookahead)
    #         if not self.match(TAG.TYPE):
    #             raise ParseError(f"Erro na linha {self._lexer.line}:"
    #                              " era esperado um tipo de variável.")
    #
    #     name = ''
    #     ...
    #     s = Symbol(type, name)
    #     self._log("Declarado", s)
    #
    #     # insere a variável na tabela de símbolos
    #     if not self._sym_table.insert(name, s):
    #         self._log('Erro: a variável já foi declarada no escopo atual')
    #         raise ParseError()

    def opers(self):
        """Operations
        Regras:
            opers -> digit oper'
            oper -> operator digit oper*
            operator -> + | - | * | /
        """
        self.accumulator = self.digit()

        # operator digit
        if self._optimize:
            while True:
                # Regra: oper -> + digit { print(+) } oper
                if self._lookahead == "+":
                    self.match(Tag("+"))
                    self.accumulator += self.digit()
                # Regra: oper -> - digit { print(-) } oper
                elif self._lookahead == "-":
                    self.match(Tag("-"))
                    self.accumulator -= self.digit()
                # Produção vazia (return)
                else:
                    self._log(self.accumulator, end="", flush=True)
                    return
        else:
            while True:
                self._log(f"{self.accumulator}", end="", flush=True)

                # Regra: oper -> + digit { print(+) } oper
                if self._lookahead == "+":
                    self.match(Tag("+"))
                    self._log("+", end="", flush=True)
                    self.accumulator = self.digit()

                # Regra: oper -> - digit { print(-) } oper
                elif self._lookahead == "-":
                    self.match(Tag("-"))
                    self._log("-", end="", flush=True)
                    self.accumulator = self.digit()

                # Produção vazia (return)
                else:
                    return

    def Fact(self):
        # fact -> id
        ...

    def digit(self) -> int:
        """
        Regra: digit -> digit { print(digit) }
        """
        modifier = 1
        if self._lookahead == "+":
            self.match(Tag("+"))
        elif self._lookahead == "-":
            self.match(Tag("-"))
            modifier = -1
        if self._lookahead.tag == Tags.NUM:
            assert isinstance(self._lookahead, Num)
            num: Num = self._lookahead
            # self._lexer._log(f"{self._lookahead}", end=" ", flush=True)
            self.match(self._lookahead.tag)
            return num.value * modifier
        else:
            log_error(
                f"\nErro na linha {self._lexer.line}:"
                f"\033[35m dígito era esperado, obteve {self._lookahead} ao invés disso."
            )
            raise ParseError()

    def match(self, t: Tag):
        """Verifica se o caractere atual corresponde ao esperado e avança."""
        if t == self._lookahead.tag:
            self._lookahead = self._lexer.scan()
        else:
            # TODO -> Melhorar mensagens de erro
            raise ParseError()


def main(source_filename: str, options: int, *args, **kwargs):
    if options & Options.LOG:
        tui = Tui(Tui.Mode.PARSER)
        istream: TuiInputStream  # pyright: ignore[reportRedeclaration]
        try:
            istream = TuiInputStream(
                source_filename, partial(tui.log_source, end="")
            )  # pyright: ignore[reportAssignmentType]
        except FileNotFoundError:
            log_error(f"Error: The file '{source_filename}' was not found.")
        lexer = Lexer(
            istream, tui.log_tokens  # pyright: ignore[reportPossiblyUnboundVariable]
        )
        # Inicia o Parser com o conteúdo do arquivo
        parser = Parser(
            lexer,
            tui.log_ir,
            lambda message, *args, **kwargs: tui.log_debug(
                f"\033[33m{message}", *args, **kwargs
            ),
            optimize=not bool(options & Options.NO_OPTIMIZE),
        )
        tui.run(parser.start, True)
    else:
        istream: InputStream
        try:
            istream = InputStream(source_filename)
        except FileNotFoundError:
            log_error(f"Error: The file '{source_filename}' was not found.")
        lexer = Lexer(
            istream,  # pyright: ignore[reportPossiblyUnboundVariable]
            lambda *args, **kwargs: None,
        )
        # Inicia o Parser com o conteúdo do arquivo
        parser = Parser(lexer, optimize=bool(options & Options.NO_OPTIMIZE))
        parser.start()
        parser._log()  # quebra de linha final


# except ParseError:
#     log_error("\nErro de Sintaxe")


if __name__ == "__main__":
    from utils import log_warning

    # Verifica se o usuário passou o nome do arquivo
    if len(sys.argv) < 2:
        log_warning(
            "Uso: \033[32m" "python" f"\033[m {sys.argv[0]} \033[34m<arquivo_fonte>"
        )
        sys.exit(EXIT_ERROR)

    main(source_filename=sys.argv[1], options=Options.NO_OPTIMIZE | Options.LOG)
