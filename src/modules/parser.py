from functools import partial
import sys
import json
from typing import Callable
from queue import SimpleQueue as Queue

from .lexer import Integer, Real, Str, Lexer, Token, Tag, Tags, Id, Type
from .symbols import Symbol, SymTable
from ..utils.istream import InputStream, TuiInputStream
from ..utils.options import *
from ..utils.tui import Tui
from ..utils.arg_parser import ArgParser
from ..utils.utils import EXIT_ERROR, log, log_error, log_warning
from ..utils.utils import RICH_COLOR_ORANGE as RTC_ORANGE
from ..modules.ast import (
    Program,
    Block,
    Literal,
    BinOp,
    Assignment,
    VarDecl,
    Identifier,
    ASTNode,
    VarDecl,
    PrintStmt,
    IfStmt,
    WhileStmt,
    ReturnStmt,
    FormalParam,
    FunctionCall,
    FunctionDecl,
    UnaryOp,
)
from typing import List
from pprint import pformat


# Definimos uma exceção personalizada para evitar confusão
# com o "SyntaxError" nativo do Python
class ParseError(Exception):
    pass


class SyntaxError(ParseError):
    pass


class SemanticError(ParseError):
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

        # imprimir arvore
        # self._log(pformat(ast_root, indent=1, width=80))
        self._log(json.dumps(ast_root.to_dict(), indent=2))

        return ast_root

    def program(self) -> Program:
        """
        Regra:
            program = `symTable=null;` stmts
        """
        lista_de_comandos = self.stmts()  # program -> stmts

        # Verifica se o último caractere é o marcador vazio (nil ⇒ EOF)
        if self._lookahead != "":
            raise SyntaxError(
                f"[b][Erro sintático] [{self._lexer.filename}:{self._lexer.line}:{self._lexer.column}]:[/b] "
                f"Token desconhecido [{self._lookahead}]."
            )

        return Program(statements=lista_de_comandos)

    def var_decl(self) -> VarDecl:
        """Regra: var <id> : <type> = <expr> ;"""
        self.match(Tags.VAR)

        var_token = self._lookahead
        name = str(var_token)
        self.match(Tags.ID)
        self.match(Tag(":"))

        var_type = str(self._lookahead)
        self.match(Tags.TYPE)
        self.match(Tag("="))

        expr_node = self.expression()
        self.match(Tag(";"))

        # Verificação de tipos na declaração
        expr_type = self._infer_type(expr_node)
        self._check_type_compatibility(var_type,expr_type, var_token.coords, name)
        if expr_type != "unknown" and var_type != expr_type:
            if not (var_type == "real" and expr_type == "int"):
                raise SemanticError(
                    f"[b][Erro Semântico] [{self._lexer.filename}:{var_token.coords}]:[/b] "
                    f"A variável '[cyan]{name}[/cyan]' foi declarada como "
                    f"'[purple]{var_type}[/purple]', mas recebeu um valor do tipo "
                    f"'[purple]{expr_type}[/purple]'."
                )

        # Salvar tabelas de símbolos
        assert var_token.coords is not None
        if not self._sym_table.insert(name, Symbol(name, var_type, var_token.coords)):
            dupl: Symbol = self._sym_table.find(
                name
            )  # pyright: ignore[reportAssignmentType]
            raise SemanticError(
                f"[b][Erro semântico] [{self._lexer.filename}:{var_token.coords}]:[/b] "
                f"variável '[cyan]{name}[/cyan]' já declarada em [{dupl.coords}]."
            )
        
        #shadowing   
        if self._sym_table.is_shadowing(name):
            shadow: Symbol = self._sym_table.previous.find(name)
            self._warn(
                f"[b][{self._lexer.filename}:{var_token.coords}]:[/b] A variável '[cyan]{name}[/cyan]' "
                "está sombreando um símbolo de mesmo nome declarado em um escopo superior "
                f"[{shadow.coords}]."
            ) 
        return VarDecl(name=name, var_type=var_type, value=expr_node)

    def assignment(self) -> Assignment:
        """Regra: set <id> = <expr> ;"""
        self.match(Tags.SET)

        name = str(self._lookahead)
        self.match(Tags.ID)
        self.match(Tag("="))

        expr_token_coords = self._lookahead.coords
        expr_node = self.expression()
        self.match(Tag(";"))

        sym = self._sym_table.find(name)
        if sym:
            expr_type = self._infer_type(expr_node)
            self._check_type_compatibility(sym.type, expr_type, expr_token_coords, name)
            if expr_type != "unknown" and sym.type != expr_type:
                if not (sym.type == "real" and expr_type == "int"):
                    raise SemanticError(
                        f"[b][Erro semântico] [{self._lexer.filename}:{expr_token_coords}]:[/b] "
                        f"A variável '[cyan]{name}[/cyan]' é do tipo '[purple]{sym.type}[/purple]', "
                        f"mas está a receber um valor do tipo '[purple]{expr_type}[/purple]'."
                    )

        return Assignment(
            name=name, value=expr_node, var_type=sym.type if sym else "undefined"
        )

    def print_stmt(self) -> PrintStmt:
        """Regra: print <expr> ;"""

        self.match(Tags.PRINT)
        expr_node = self.expression()
        self.match(Tag(";"))

        return PrintStmt(expr=expr_node)

    def if_stmt(self) -> IfStmt:
        """REGRA: if( <expression> ) <bloco> [ else <block> ]"""
        self.match(Tags.IF)
        self.match(Tag("("))
        condition = self.expression()
        self.match(Tag(")"))

        true_block = self.block()
        false_block = None

        if self._lookahead.tag == Tags.ELSE:
            self.match(Tags.ELSE)
            false_block = self.block()
        return IfStmt(
            condition=condition, true_block=true_block, false_block=false_block
        )

    def while_stmt(self) -> WhileStmt:
        """While Statement:
        Regra:
            <while-statement> -> while ( <expression> ) <block>
        """
        self.match(Tags.WHILE)
        self.match(Tag("("))
        condition = self.expression()
        self.match(Tag(")"))
        body = self.block()
        return WhileStmt(condition=condition, body=body)

    def return_stmt(self) -> ReturnStmt:
        """Return Statement
        Regra:
            <return-statement> -> return <expression> ;
        """
        self.match(Tags.RETURN)
        expr_node = self.expression()
        self.match(Tag(";"))
        return ReturnStmt(expr=expr_node)

    def function_decl(self) -> FunctionDecl:
        """Function Declaration
        Regras:
            <function-decl> -> "def" <identifier> "(" [ <formal-params> ] ")" ":" <type> <block>
            <formal-params> -> <formal-param> { "," <formal-param> }
            <formal-param> -> <identifier> ":" <type>
        """
        self.match(Tags.DEF)
        name = str(self._lookahead)  # ação semântica
        self.match(Tags.ID)
        self.match(Tag("("))

        # 1. Salva tabela atual
        saved_table = self._sym_table

        # 2. cria nova tabela aninhada
        self._sym_table = SymTable(previous=saved_table)

        # 3. Salva os parâmetros da função
        params = []
        if self._lookahead.tag == Tags.ID:
            # <formal-params> → <formal-param> { "," <formal-param> }
            while True:
                p_token_coords = self._lookahead.coords
                assert p_token_coords is not None
                p_name = str(self._lookahead)  # ação semântica
                self.match(Tags.ID)
                self.match(Tag(":"))
                p_type = str(self._lookahead)  # ação semântica
                self.match(Tags.TYPE)

                # ação semântica: `params.append(<f-p>.node)`
                params.append(FormalParam(name=p_name, param_type=p_type))

                # ação semântica:
                if not self._sym_table.insert(
                    p_name, Symbol(p_name, p_type, p_token_coords)
                ):
                    dupl: Symbol = self._sym_table.find(
                        p_name
                    )  # pyright: ignore[reportAssignmentType]
                    raise SyntaxError(
                        f"[b][Erro de sintaxe] [{self._lexer.filename}:{p_token_coords}]:[/b] "
                        f"o parâmetro '[cyan]{p_name}[/cyan]' já existe em [{dupl.coords}]."
                    )
                if self._sym_table.is_shadowing(p_name):
                    shadow: Symbol = saved_table.find(
                        p_name
                    )  # pyright: ignore[reportAssignmentType]
                    self._warn(
                        f"[b][{self._lexer.filename}:{self._lexer.line}:{self._lexer.column}]:[/b] O parâmetro de nome '[cyan]{p_name}[/cyan]' "
                        "está sombreando (shadowing) um símbolo de mesmo nome neste escopo em "
                        f"[{shadow.coords.line}:{shadow.coords.column}]."
                    )

                if self._lookahead == ",":
                    self.match(Tag(","))
                else:
                    break

        self.match(Tag(")"))
        self.match(Tag(":"))
        ret_type = str(self._lookahead)  # ação semântica
        self.match(Tags.TYPE)

        # 4. Salva a definição da função
        param_symbols = [
            Symbol(p.name, p.param_type, self._lexer.coords) for p in params
        ]
        def_sym = Symbol(name, "function", self._lexer.coords, param_symbols)

        # 5. Insere a função na tabela em seu próprio escopo (permite recursão)
        self._sym_table.insert(name, def_sym)

        # 6. Gera o corpo da função usando o escopo temporário da função
        body = self.block(False)

        # 7. restaura tabela anterior salvando a definição da função no escopo anterior
        self._sym_table = saved_table
        self._sym_table.insert(name, def_sym)

        return FunctionDecl(name=name, params=params, return_type=ret_type, body=body)

    def stmts(self) -> List[ASTNode]:
        """Statements
        Regras:
            <statement> = <variable-decl> ";"
                        | <assignment> ";"
                        | <print-statement> ";"
                        | <if-statement>
                        | <while-statement>
                        | <return-statement> ";"
                        | <function-decl>
                        | <block>
                        | ";" `warn "empty statement"`
        """
        statements_list: List[ASTNode] = []

        while True:
            match self._lookahead.tag:
                # stmts -> var_decl
                case Tags.VAR:
                    statements_list.append(self.var_decl())
                    continue
                # stmts -> assignment
                case Tags.SET:
                    statements_list.append(self.assignment())
                    continue
                # stmts -> print_stmt
                case Tags.PRINT:
                    statements_list.append(self.print_stmt())
                    continue
                # stmts -> if_stmt
                case Tags.IF:
                    statements_list.append(self.if_stmt())
                    continue
                # stmts -> while_stmt
                case Tags.WHILE:
                    statements_list.append(self.while_stmt())
                    continue
                # stmts -> function_decl
                case Tags.DEF:
                    statements_list.append(self.function_decl())
                    continue
                # stmts -> return_stmt
                case Tags.RETURN:
                    statements_list.append(self.return_stmt())
                    continue
                # stmts -> block
                case "{":
                    statements_list.append(self.block())
                    continue
                # stmts -> ;
                case ";":
                    self.match(Tag(";"))
                    self._warn(
                        f"[b][{self._lexer.filename}:{self._lexer.line}:{self._lexer.column}]:[/b] "
                        "Empty statement. Remove single ';'."
                    )
                    continue
                case _:
                    return statements_list

    def block(self, use_new_scope: bool = True) -> Block:
        """
        :param: use_new_scope: Quando `False` pode ser útil no caso em que o
                escopo é especificado na chamada acima.
        Regra:
            block -> { saved= symTable;
                       symTable = SymTable(previous=symTable);
                       print('{');
                     } { stmts } { symTable = saved; print('}'); }
        """
        self.match(Tag("{"))

        if use_new_scope:
            # 1. Salva tabela atual
            saved_table = self._sym_table  # ação semântica

            # 2. cria nova tabela aninhada
            self._sym_table = SymTable(previous=saved_table)  # ação semântica

        block_stmts = self.stmts()

        if self._lookahead != "}":
            raise SyntaxError(
                f"[b][Erro sintático] [{self._lexer.filename}:{self._lookahead.coords}]:[/b] "
                "era esperado '}' no final do bloco."
            )
        self.match(Tag("}"))

        if use_new_scope:
            # 3. restaura tabela anterior
            self._sym_table = (
                saved_table  # pyright: ignore[reportPossiblyUnboundVariable]
            )
            # del # Símbolos no escopo do bloco acessado ja não são mais necessários

        return Block(statements=block_stmts)

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

    def expression(self):
        """Expression
        Regras:
            <expression> -> <simple-expression> { <relational-op> <simple-expression> }
            <simple-expression> -> <term> { <additive-op> <term> }
            <term> -> <factor> { <multiplicative-op> <factor> }
        """
       
        """
        Regras:
            <expression> -> <simple-expression> { <relational-op> <simple-expression> }
            <relational-op> -> "<" | ">" | "==" | "!=" | "<=" | ">="
        """
        # TODO -> <simple-expression> -> <term> { <additive-op> <term> }
        left_node = self.simple_expression()

        while True:
            #  <relational-op>
            if self._lookahead in (">", "<", "==", "!=", "<=", ">="):
                # <simple-expression> -> <term> { <additive-op> <term> }
                op_str = str(self._lookahead)
                self.match(Tag(op_str))
                right_node = self.simple_expression()
                left_node = BinOp(left=left_node, op=op_str, right=right_node)
                self._infer_type(left_node)

            else:
                return left_node

    def simple_expression(self):

        """
        Regras:
            <simple-expression> -> <term> { <additive-op> <term> }
            <additive-op> -> "+" | "-" | "or"
        """
        
        left_node = self.term()

        while True:
            if self._lookahead in ("+", "-", "or"):
                # TODO
                # FIXME -> Deve verificar tipos
                op_str = str(self._lookahead)
                self.match(Tag(op_str))
                right_node = self.term()
                left_node = BinOp(left=left_node, op=op_str, right=right_node)
                self._infer_type(left_node)

            else:
                return left_node

    def term(self):
        """
        Regras:
            <term> -> <factor> { <multiplicative-op> <factor> }
            <multiplicative-op> -> "*" | "/" | "and"
        """
        
        left_node = self.factor()

        while True:
            if self._lookahead in ("*", "/", "and"):
                # TODO
                # FIXME -> Deve verificar tipos
                op_str = str(self._lookahead)
                self.match(Tag(op_str))
                right_node = self.factor()
                left_node = BinOp(left=left_node, op=op_str, right=right_node)
                self._infer_type(left_node)

            else:
                return left_node

    def factor(self) -> ASTNode:
        """Factor
        Regras:
            <factor> -> <literal> | <identifier> | <function-call> | <sub-expression>
            <literal> -> <integer-literal> | <real-literal> | “true” | "false”
            <integer-literal> -> [0-9]+
        """

        if str(self._lookahead) in ("+", "-", "not"):
            unary = str(self._lookahead)
            self.match(Tag(str(self._lookahead)))
            return UnaryOp(op=unary, expr=self.factor())

        match self._lookahead.tag:
            case Tags.INT:
                assert isinstance(self._lookahead, Integer)
                val = self._lookahead.value
                self.match(Tags.INT)
                return Literal(value=val)
            case Tags.REAL:
                assert isinstance(self._lookahead, Real)
                val = self._lookahead.value
                self.match(Tags.REAL)
                return Literal(value=val)
            case Tags.TRUE:
                self.match(Tags.TRUE)
                return Literal(value=True)
            case Tags.FALSE:
                self.match(Tags.FALSE)
                return Literal(value=False)
            case Tags.STR_LIT:
                assert isinstance(self._lookahead, Str)
                val = self._lookahead.value
                self.match(Tags.STR_LIT)
                return Literal(value=val)
            case _:
                if self._lookahead.tag == "(":
                    self.match(Tag("("))
                    expr_node = self.expression()
                    self.match(Tag(")"))
                    return expr_node

        # É uma Variável sendo usada na conta (Identificador)?
        if self._lookahead.tag == Tags.ID:
            id_token_coords = self._lookahead.coords
            name = str(self._lookahead)
            self.match(Tags.ID)

            sym = self._sym_table.find(name)
            if self._sym_table.find(name) is None:
                raise SemanticError(
                    f"[Erro Semântico] [{self._lexer.filename}:{id_token_coords}]: "
                    f"A função '{name}' não foi declarada."
                )
            assert sym is not None
            if self._lookahead == "(":
                self.match(Tag("("))
                args = []
                if self._lookahead != ")":
                    while True:
                        args.append(self.expression())
                        if self._lookahead == ",":
                            self.match(Tag(","))
                        else:
                            break
                closing_token_coords = self._lookahead.coords
                self.match(Tag(")"))

                if sym.type == "function":  # and sym.params_count != -1:
                    if len(args) != len(sym.params):
                        raise SyntaxError(
                            f"[Erro Sintático] [{self._lexer.filename}:{closing_token_coords}]: "
                            f"A função '[cyan]{name}[/cyan]' exige {len(sym.params)} "
                            f"argumento{'s' if len(sym.params) > 1 else ''} "
                            # WARNING -> Verificar se `to_code` é seguro de ser usado aqui!
                            f"[purple]{sym.params}[/purple], mas foi chamada com {len(args)} "
                            f"[purple]{[arg.to_code() for arg in args]}[/purple]."
                        )
                    for i, arg_node in enumerate(args):
                        arg_type = self._infer_type(arg_node)
                        param_symbol = sym.params[i]
                        expected_type = param_symbol.type
                        param_name = param_symbol.var

                        # TODO -> Tipo desconhecido deve ser tratado
                        if arg_type != "unknown" and expected_type != "unknown":
                            allowed = False
                            if expected_type == arg_type: allowed = True
                            elif expected_type == "int" and arg_type == "real": allowed = True
                            elif expected_type == "real" and arg_type == "int": allowed = True
                            elif expected_type == "int" and arg_type == "bool": allowed = True
                            elif expected_type == "bool" and arg_type == "int": allowed = True
                            
                            if not allowed:
                                raise SemanticError(
                                    f"[Erro Semântico] [{self._lexer.filename}:{closing_token_coords}]: "
                                    f"O {i+1}° parâmetro '[orange]{param_name}[/orange]' da função "
                                    f"'[cyan]{name}[/cyan]' em [{param_symbol.coords}] esperava "
                                    f"[purple]{expected_type}[/purple], mas recebeu [purple]{arg_type}[/purple]."
                                )
                return FunctionCall(name=name, args=args)

            return Identifier(name=name)

        else:
            raise SyntaxError(
                f"[b][Erro Sintático] [{self._lexer.filename}:{self._lookahead.coords}][/b]: "
                f"Esperado um fator ([{RTC_ORANGE}]sub-expressão[/{RTC_ORANGE}] entre parênteses, "
                f"[{RTC_ORANGE}]literal[/{RTC_ORANGE}], [{RTC_ORANGE}]identificador[/{RTC_ORANGE}], "
                f"ou [{RTC_ORANGE}]chamada de função[/{RTC_ORANGE}], "
                f"mas recebeu '[purple]{self._lookahead}[/purple]' ao invés disso."
            )

        # def digit(self) -> Literal:
        """
        Regra: digit -> digit { print(digit) }
        """

    def _infer_type(self, node: ASTNode) -> str:
        """Descobre o tipo de uma expressão e bloqueia misturas incompatíveis."""
        if isinstance(node, Literal):
            if isinstance(node.value, bool):
                return "bool"
            if isinstance(node.value, str):
                return "str"
            if isinstance(node.value, float):
                return "real"
            if isinstance(node.value, int):
                return "int"
            return "unknown"

        elif isinstance(node, Identifier):
            sym = self._sym_table.find(node.name)
            return sym.type if sym else "unknown"
        
        elif isinstance(node, UnaryOp):
            expr_type = self._infer_type(node.expr)
            if node.op == "not" and expr_type not in ("bool", "int", "unknown"):
                raise SemanticError(f"[Erro Semântico]: Operador 'not' requer 'bool' ou 'int', recebeu '{expr_type}'. ")
            if node.op in ("+", "-") and expr_type not in ("int", "real", "bool", "unknown"):
                raise (f"[Erro Semântico]: Operador '{node.op}'numérico não suporta o tipo '{expr_type}'.")
            return "bool" if node.op == "not" else expr_type
            
        elif isinstance(node, BinOp):
            left_type = self._infer_type(node.left)
            right_type = self._infer_type(node.right)
            
            if (right_type != "unknown" and left_type != "unknown"):
                #(and,or)
                if node.op in ("and", "or"):
                    if left_type not in ("bool", "int") or right_type not in ("bool", "int"):
                        raise SemanticError(
                            f"[Erro Semântico]: Operador lógico '{node.op}' exige tipos 'bool' ou 'int'."
                            f"Recebeu '{left_type}' e  '{right_type}'."
                        )
                    return "bool"
                #(+, -, *, /)
                if node.op in ("+", "-", "*", "/"):
                    if left_type == "str" or right_type == "str":
                        raise SemanticError(f"[Erro Semântico]: Não é possível usar o operador '{node.op}' com strings.")
                    
                    if (left_type == "bool" and right_type == "real") or (left_type == "real" and right_type == "bool"):
                        raise SemanticError(f"[Erro Semântico]: Tipos incompatíveis (Tentativa de operar 'bool' com 'real').")
                    
                    if left_type == "real" or right_type == "real":
                        return "real"
                    return "int"
                
            if node.op in (">", "<", "==", "!=", ">=", "<="):
                return "bool"

            return left_type

        elif isinstance(node, FunctionCall):
            sym = self._sym_table.find(node.name)
            return sym.type if sym else "unknown"

        # FIXME -> Tratar tipo desconhecido
        return "unknown"

    def match(self, t: Tag):
        """Verifica se o caractere atual corresponde ao esperado e avança."""
        if t == self._lookahead.tag:
            self._lookahead = self._lexer.scan()
        else:
            # WATCH -> Melhorar mensagens de erro
            raise SyntaxError(
                f"[b][Erro Sintático] [{self._lexer.filename}[/b]:{self._lookahead.coords}]:\n"
                f"\tEra esperado '{t.name}', mas o compilador encontrou '{self._lookahead.tag.name}'."
            )

    """Truncamento, Contagem, Veracidade"""
    def _check_type_compatibility(self, target_type:str, expr_type: str, coords, name: str):
        if expr_type == "unknown" or target_type == "unknown":
            return
        if target_type == expr_type:
            return
        
        allowed = False
        if target_type == "int" and expr_type == "real": allowed = True
        elif target_type == "real" and expr_type == "int": allowed = True
        elif target_type == "int" and expr_type == "bool": allowed = True
        elif target_type == "bool" and expr_type == "int": allowed = True
        
        if not allowed:
            raise SemanticError(
                f"[b][Erro Semântico] [{self._lexer.filename}:{coords}]: [/b] "
                f"Tipo incompatível. A variável '[cyan]{name}[/cyan]' é '[purple]{target_type}[/purple]',"
                f"mas recebeu um valor '[purple]{expr_type}[/purple]'."
            )
        
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
            sys.exit(EXIT_ERROR)
        lexer = Lexer(
            istream,
            tui.log_tokens,  # pyright: ignore[reportPossiblyUnboundVariable]
            source_filename=source_filename,
        )
        # Inicia o Parser com o conteúdo do arquivo
        parser = Parser(
            lexer,
            tui.log_ir,
            lambda message="", *args, **kwargs: tui.log_debug(
                f"[yellow][b][Warning][/b]  {message}[/yellow]", *args, **kwargs
            ),
            optimize=not bool(options & Options.NO_OPTIMIZE),
        )
        tui.run(
            parser.start,  # pyright: ignore[reportArgumentType]
            True,
            not bool(options & Options.NO_EXCEPT_TREATMENT),
        )
    else:
        istream: InputStream
        try:
            istream = InputStream(source_filename)
        except FileNotFoundError:
            log_error(f"Error: File '{source_filename}' not found.")
            sys.exit(EXIT_ERROR)
        lexer = Lexer(
            istream,  # pyright: ignore[reportPossiblyUnboundVariable]
            lambda *args, **kwargs: None,
            source_filename=source_filename,
        )
        # Inicia o Parser com o conteúdo do arquivo
        parser = Parser(lexer, optimize=bool(options & Options.NO_OPTIMIZE))
        if options & Options.NO_EXCEPT_TREATMENT:
            parser.start()
        else:
            try:
                parser.start()
            except Exception as e:
                log_error(f"{e}")
        parser._log()  # quebra de linha final


def parse_append(parser: ArgParser) -> None:
    from .lexer import parse_append as append

    append(parser)
    # Option flags
    # TODO -> Verificar se isso está realmente sendo usado
    parser.add_argument(
        "-no", "--no-optimize", action="store_true", help="Disable optimizations"
    )


def fetch_options(args) -> int:
    from . import lexer

    # Build options bitmask
    options = lexer.fetch_options(args)
    if args.no_optimize:
        options |= Options.NO_OPTIMIZE
    return options


if __name__ == "__main__":
    from ..utils.arg_parser import ArgParser

    parser = ArgParser(
        description="Parser layer for your MiniLang source files. Does both the Syntax and Semantic Analysis generating an AST.\n"
        "The generated output is for debugging purposes only. To fully-compile code you need to call the gen layer with the MiniLang source.",
        add_help=False,  # we'll add custom help options to match original
    )
    parse_append(parser)

    # Parse arguments
    args = parser.parse_args()
    options = fetch_options(args)

    # Call main with parsed values
    main(args.source, options)
