#!/usr/bin/env python3
from functools import partial
import sys
from typing import Callable

from utils.istream import InputStream, TuiInputStream
from utils.options import *
from utils.tui import Tui
from utils.utils import EXIT_ERROR, log, log_error
from modules.lexer import Lexer, Num, Token, Tag, Tags, Id, Type
from modules.symbols import Symbol, SymTable
from utils.utils import log_warning
from queue import SimpleQueue as Queue

from modules.ast import Program, Block, Literal, BinOp, Assignment, VarDecl, Identifier, ASTNode, VarDecl, PrintStmt
from typing import List
from pprint import pformat

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

    def start(self) -> Program:
        """Inicia o processo de análise e retorna a AST completa."""
        self._lookahead = self._lexer.scan()
        ast_root = self.program()
        self._lexer.finish()

        # Verifica se o último caractere é o marcador vazio (nil ⇒ EOF)
        if self._lookahead != "":
            raise ParseError("Erro: Código extra encontrado após o fim do escopo principal.")
        
        #imprimir arvore
        self._log("\n" + "="*40)
        self._log("AST GERADA COM SUCESSO:")
        self._log("="*40)
        self._log(pformat(ast_root,indent=2,width=80))
        self._log("\n")
        
        return ast_root

    def program(self):
        """
        Regra:
            program -> { symTable=null; } stmts
        """
        lista_de_comandos = self.stmts()
        return Program(statements=lista_de_comandos)

    def var_decl(self) -> VarDecl:
        """Regra: var <id> : <type> = <expr> ;"""
        self.match(Tags.VAR)
        
        name = str(self._lookahead)
        self.match(Tags.ID)
        self.match(Tag(":"))
        
        var_type = str(self._lookahead)
        self.match(Tags.TYPE)
        self.match(Tag("="))
        
        expr_node = self.opers()
        self.match(Tag(";"))

        #Salvar tabelas de simbolos
        if not self._sym_table.insert(name, Symbol(name, var_type)):
            raise ParseError(f"Erro: variável '{name}' já declarada.")
        return VarDecl(name=name, var_type=var_type, value=expr_node)
    
    def assignment(self) -> Assignment:
        """Regra: set <id> = <expr> ;"""      
        self.match(Tags.SET)
        
        name = str(self._lookahead)
        self.match(Tags.ID)
        self.match(Tag("="))
        
        expr_node = self.opers()
        self.match(Tag(";"))
        
        return Assignment(name=name, value=expr_node)
    
    def print_stmt(self) -> PrintStmt:
        """Regra: print <expr> ;"""
        
        self.match(Tags.PRINT)
        expr_node = self.opers()
        self.match(Tag(";"))
        
        return PrintStmt(expr=expr_node)
            
    def stmts(self) -> List[ASTNode]:
        """Statements
        Regras:
            stmts -> stmt stmts | ϵ
            stmt -> block | expr;
        """
        statements_list = []
        
        while True:
            # stmt -> block
            if self._lookahead == ";":
                self.match(Tag(";"))
                continue
            
            if self._lookahead.tag == "{":
                statements_list.append(self.block())
                continue
            
            if self._lookahead.tag == Tags.VAR:
                statements_list.append(self.var_decl())
                continue
            
            if self._lookahead.tag == Tags.SET:
                statements_list.append(self.assignment())
                continue
            
            if self._lookahead.tag == Tags.PRINT:
                statements_list.append(self.print_stmt())
                continue
            
            
            # Produção vazia
            return statements_list

    def expr(self) -> List[ASTNode] | None:
        """lval_lst declr_or_rval_lst | rval_lst"""
        # stmt -> lval_lst rval_lst
        if self.lval_lst():
            nodes = self.declr_or_rval_lst()
            if nodes is None:
                self.clear_queue()
                if self._lookahead == ";":
                    self._warn(
                        f"[warning] standalone expression at line :{self._lexer.line}."
                    )
                return []
            return nodes
        
        nodes = self.rval_lst()
        # stmt -> rval_lst
        if nodes is not None:
            if self._lookahead == ";":
                self._warn(
                    f"[warning] standalone expression at line :{self._lexer.line}."
                )
            return nodes
        return None

    def block(self) -> Block:
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

        # 1. Salva tabela atual
        saved_table = self._sym_table  # ação semântica

        # 2. cria nova tabela aninhada
        self._sym_table = SymTable(previous=saved_table)

        comando_dos_blocos = self.stmts()

        if self._lookahead != "}":
            raise ParseError(
                f"Erro na linha {self._lexer.line}:"
                "era esperado '}' no final do bloco."
            )
        self.match(Tag("}"))
       
        # ação semântica: restaura tabela anterior
        self._sym_table = saved_table
       # del saved_table
        return Block(statements=comando_dos_blocos)

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

    def declr_or_rval_lst(self) -> List[ASTNode] | None:
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
            
            declarations = []
            while not self.queue_empty():
                id_token = self.deque()
                #assert id is not None
                name = str(id_token)
                # ação semântica: declara a variável na tabela de símbolos
                if not self._sym_table.insert(name, Symbol(name, str(t))):
                    raise ParseError(
                        f"Erro na linha {self._lexer.line}:"
                        f" a variável '{name}' já foi declarada no escopo atual."
                    )
                # cria o nó de declaraçao na ast
                declarations.append(VarDecl(name=name, var_type=str(t), value=Literal(None)))
            return declarations
        
        elif self._lookahead == "=":
            # declr_or_rval_lst -> = rval_lst
            self.match(Tag("="))
            valores = self.rval_lst() or []
            
            assignments = []
        
            while not self.queue_empty():
                id_token = self.deque()
                name = str(id_token)
                
                val_node = valores.pop(0) if valores else Literal(None)
                assignments.append(Assignment(name=name, value=val_node))
            return assignments
        return None
    
    def rval_lst(self) -> List[ASTNode] | None:
        """R-value list
        Regras:
            rval_lst -> rval [, rval_lst]'
            rval -> expr { id=deque()); print(id+'=') }
        """
        exprs = []
        if self.queue_empty():
            # Standalone expression
            while self._lookahead.tag == Tags.NUM or self._lookahead in ("+", "-"):
                exprs.append(self.opers())
                if self._lookahead == ",":
                    self.match(Tag(","))
                else:
                    return exprs
            return None if not exprs else exprs

        while True:
            exprs.append(self.opers())
            if self._lookahead == ",":
                self.match(Tag(","))
            else:
                break
        return exprs
        

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
        left_node = self.factor()
      
        while True:
            
            if self._lookahead == "+":
                op_str = self._lookahead.tag.name
                self.match(Tag("+"))
                right_node = self.factor()
                
                left_node = BinOp(left=left_node, op=op_str,right=right_node)
           
            elif self._lookahead == "-":
                op_str = self._lookahead.tag.name
                self.match(Tag("-"))
                right_node = self.factor()
                
                left_node = BinOp(left=left_node, op=op_str, right=right_node)
            # Produção vazia (return)
            else:
                return left_node
    
    def factor(self) -> ASTNode:
        
        modifier = 1
        if self._lookahead == "+":
            self.match(Tag("+"))
        elif self._lookahead == "-":
            self.match(Tag("-"))
            modifier = -1
        
        if self._lookahead.tag == Tags.NUM:
            val = self._lookahead.value * modifier
            self.match(Tags.NUM)
            return Literal(value=val)
            
        # É uma String (texto entre aspas)?
        elif self._lookahead.tag == Tags.STR_LIT:
            val = self._lookahead.value
            self.match(Tags.STR_LIT)
            return Literal(value=val)
            
        # É uma Variável sendo usada na conta (Identificador)?
        elif self._lookahead.tag == Tags.ID:
            name = str(self._lookahead)
            self.match(Tags.ID)
            return Identifier(name=name)
        
        else:
            raise ParseError(f"Erro na linha {self._lexer.line}: Esperado um valor, variável ou string.")
        
    #def digit(self) -> Literal:
        """
        Regra: digit -> digit { print(digit) }
        """
     #   modifier = 1
     #   if self._lookahead == "+":
     #       self.match(Tag("+"))
     #   elif self._lookahead == "-":
     #       self.match(Tag("-"))
     #       modifier = -1
            
     #   if self._lookahead.tag == Tags.NUM:
     #       assert isinstance(self._lookahead, Num)
     #       num_value = self._lookahead.value * modifier
     #       # self._lexer._log(f"{self._lookahead}", end=" ", flush=True)
     #       self.match(self._lookahead.tag)
     #       return Literal(value=num_value)
     #   else:
     #       log_error(
     #           f"\nErro na linha {self._lexer.line}:"
     #           f"\033[35m dígito era esperado, obteve {self._lookahead} ao invés disso."
    #        )
    #        raise ParseError()

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
    from src.utils.utils import log_warning

    # Verifica se o usuário passou o nome do arquivo
    if len(sys.argv) < 2:
        log_warning(
            "Uso: \033[32m" "python" f"\033[m {sys.argv[0]} \033[34m<arquivo_fonte>"
        )
        sys.exit(EXIT_ERROR)

    main(source_filename=sys.argv[1], options=Options.NO_OPTIMIZE | Options.LOG)
