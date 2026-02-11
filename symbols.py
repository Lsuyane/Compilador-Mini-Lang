#!/usr/bin/env python3
"""Defines the symbol table."""
from utils import log, log_info, log_success, log_warning


class Symbol:
    """Estrutura para salvar o nome de uma variável e o tipo."""

    var: str
    type: str

    def __init__(self, var: str, type: str) -> None:
        self.var = var
        self.type = type

    def __repr__(self) -> str:
        return f"Symbol(var='{self.var}', type='{self.type})"


class SymTable:
    """Tabela de símbolos.
    As referências de escopo são montadas como uma lista encadeada reversa.
    Se mantida as referências para as folhas, pode compor uma 'árvore'
    cujo cadeias apontam para raiz.
    """

    previous: "SymTable | None"
    table: dict[str, Symbol]  # Tabela inicia vazia

    def __init__(self, previous: "SymTable | None" = None) -> None:
        """Construtor da tabela de símbolos.
        Se `prev` for `None`, essa será uma tabela global (escopo mais externo).
        Se `prev` for passado, é uma nova tabela aninhada a ser criada dentro
        do escopo de `prev`.
        """
        self.table = {}  # Each SymTable has its own dict
        self.previous = previous

    def insert(self, id: str, symbol: Symbol) -> bool:
        """
        Função para inserir um símbolo na tabela atual.

        :param id: Identificador do símbolo a inserir.
        :param symbol: Símbolo a ser inserido.
        :return: Retorna `True` se o símbolo foi inserido com sucesso,
                ou `False` se a entrada já existia na tabela.
        """
        if id in self.table:
            return False

        self.table[id] = symbol
        return True

    def find(self, id) -> Symbol | None:
        """
        Busca por um símbolo na tabela.

        :param id: Identificador do símbolo a ser buscado.
        :return: Retorna o símbolo encontrado, ou `None`.
        """
        # Começa a busca na tabela atual.
        current_scope = self

        # Percorre as referências para `previous`
        while current_scope is not None:
            if id in current_scope.table:
                return current_scope.table[id]

            # Sobe para o escopo anterior
            current_scope = current_scope.previous

        return None


if __name__ == "__main__":
    # region [test] SymTable
    log_info("Testando a classe SymTable...")

    # region 1. Criando escopo global
    global_scope = SymTable()
    log_success("Escopo Global Criado!")

    # inserir uma variável global 'x' (int)
    sym1 = Symbol("x", "int")
    global_scope.insert("x", sym1)
    log_success(f"Inserido no escopo Global: x -> {global_scope.find('x')}")
    # endregion

    # region 2. Criar escopo local (ex: dentro de uma função)
    # Passamos o global_scope como `previous`
    local_scope = SymTable(previous=global_scope)
    log_success("Escopo local criado dentro do escopo global!")

    # inserir uma variável local 'y' (float)
    sym2 = Symbol("y", "float")
    local_scope.insert("y", sym2)
    # endregion

    # region 3. Testes de Busca (Lookup)
    log_warning(
        f"Buscando 'y' no local: \033[m{local_scope.find('y')}"
    )  # Deve achar no local
    log_warning(
        f"Buscando 'x' no local: \033[m{local_scope.find('x')}"
    )  # Deve achar no global (via `previous`)

    log()
    # endregion

    # region 4. Sombreamento (Shadowing)
    log_info("Inserindo 'x' no escopo local (Shadowing)...")
    sym3 = Symbol("x", "char")  # Novo x, agora char
    local_scope.insert("x", sym3)

    log_warning(
        f"Buscando 'x' no local:  \033[m{local_scope.find('x')}"
    )  # Deve ser char (local)
    log_warning(
        f"Buscando 'x' no global: \033[m{global_scope.find('x')}"
    )  # Deve ser int (original)
    # endregion
    # endregion [test]
