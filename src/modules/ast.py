from dataclasses import dataclass
from typing import Callable, List, Optional, Any

from ..utils.utils import log


class ASTNode:
    def gen(self, logger: Callable, indent: int = 0) -> None:
        raise NotImplementedError

    def to_dict(self):
        raise NotImplementedError


@dataclass
class Literal(ASTNode):
    value: Any

    def to_code(self) -> str:
        return repr(self.value)

    def to_dict(self):
        return {"type": "Literal", "value": self.value}


@dataclass
class Identifier(ASTNode):
    name: str

    def to_code(self) -> str:
        return self.name

    def to_dict(self):
        return {"type": "Identifier", "name": self.name}


@dataclass
class BinOp(ASTNode):
    left: ASTNode
    op: str
    right: ASTNode

    def to_code(self) -> str:
        left = _to_code(self.left)
        right = _to_code(self.right)
        return f"({left} {self.op} {right})"

    def to_dict(self):
        return {
            "type": "BinOp",
            "left": self.left.to_dict(),
            "op": self.op,
            "right": self.right.to_dict(),
        }


@dataclass
class UnaryOp(ASTNode):
    op: str
    expr: ASTNode

    def to_code(self) -> str:
        return f"({self.op}({_to_code(self.expr)}))"

    def to_dict(self):
        return {
            "type": "UnaryOp",
            "op": self.op,
            "expr": self.expr.to_dict(),
        }


@dataclass
class FunctionCall(ASTNode):
    name: str
    args: List[ASTNode]

    def to_code(self) -> str:
        args = ", ".join(_to_code(a) for a in self.args)
        return f"{self.name}({args})"

    def to_dict(self):
        return {
            "type": "FunctionCall",
            "name": self.name,
            "args": [arg.to_dict() for arg in self.args],
        }


@dataclass
class VarDecl(ASTNode):
    name: str
    var_type: str
    value: ASTNode

    def gen(self, logger: Callable, indent: int = 0) -> None:
        py_type = "float" if self.var_type == "real" else self.var_type
        val_str = _to_code(self.value)

        if self.var_type == "int":
            val_str = f"int({val_str})"
        logger(f"{_indent(indent)}{self.name}: {py_type} = {val_str}")

    def to_dict(self):
        return {
            "type": "VarDecl",
            "name": self.name,
            "var_type": self.var_type,
            "value": self.value.to_dict(),
        }


@dataclass
class Assignment(ASTNode):
    name: str
    value: ASTNode
    var_type: str = "unknown"

    def gen(self, logger: Callable, indent: int = 0) -> None:
        val_str = _to_code(self.value)

        if self.var_type == "int":
            val_str = f"int({val_str})"

        logger(f"{_indent(indent)}{self.name} = {val_str}")

    def to_dict(self):
        return {
            "type": "Assignment",
            "name": self.name,
            "var_type": self.var_type,
            "value": self.value.to_dict(),
        }


@dataclass
class PrintStmt(ASTNode):
    expr: ASTNode

    def gen(self, logger: Callable, indent: int = 0) -> None:
        logger(f"{_indent(indent)}print({_to_code(self.expr)})")

    def to_dict(self):
        return {
            "type": "PrintStmt",
            "expr": self.expr.to_dict(),
        }


@dataclass
class ReturnStmt(ASTNode):
    expr: ASTNode

    def gen(self, logger: Callable, indent: int = 0) -> None:
        logger(f"{_indent(indent)}return {_to_code(self.expr)}")

    def to_dict(self):
        return {
            "type": "ReturnStmt",
            "expr": self.expr.to_dict(),
        }


@dataclass
class Block(ASTNode):
    statements: List[ASTNode]

    def gen(self, logger: Callable, indent: int = 0) -> None:
        for stmt in self.statements:
            try:
                stmt.gen(logger, indent)
            except TypeError:
                stmt.gen(logger)

    def to_dict(self):
        return {
            "type": "Block",
            "statements": [stmt.to_dict() for stmt in self.statements],
        }


@dataclass
class IfStmt(ASTNode):
    condition: ASTNode
    true_block: "Block"
    false_block: Optional["Block"] = None

    def gen(self, logger: Callable, indent: int = 0) -> None:
        logger(f"{_indent(indent)}if {_to_code(self.condition)}:")
        if self.true_block is not None:
            self.true_block.gen(logger, indent + 1)
        else:
            logger(f"{_indent(indent+1)}pass")
        if self.false_block is not None:
            logger(f"{_indent(indent)}else:")
            self.false_block.gen(logger, indent + 1)

    def to_dict(self):
        dict = {
            "type": "IfStmt",
            "condition": self.condition.to_dict(),
            "true_block": self.true_block.to_dict(),
        }
        if self.false_block is not None:
            dict["false_block"] = self.false_block.to_dict()
        return dict


@dataclass
class WhileStmt(ASTNode):
    condition: ASTNode
    body: "Block"

    def gen(self, logger: Callable, indent: int = 0) -> None:
        logger(f"{_indent(indent)}while {_to_code(self.condition)}:")
        if self.body is not None:
            self.body.gen(logger, indent + 1)
        else:
            logger(f"{_indent(indent+1)}pass")

    def to_dict(self):
        return {
            "type": "WhileStmt",
            "condition": self.condition.to_dict(),
            "body": self.body.to_dict(),
        }


# Nós de funçao e programa
@dataclass
class FormalParam(ASTNode):
    name: str
    param_type: str

    def to_dict(self):
        return {"type": "FormalParam", "name": self.name, "param_type": self.param_type}


@dataclass
class FunctionDecl(ASTNode):
    name: str
    params: List[FormalParam]
    return_type: str
    body: Block

    def gen(self, logger: Callable, indent: int = 0) -> None:
        def to_py_type(t: str) -> str:
            return "float" if t == "real" else t

        params = ", ".join(f"{p.name}: {to_py_type(p.param_type)}" for p in self.params)
        ret = f" -> {to_py_type(self.return_type)}" if getattr(self, "return_type", None) else ""
        logger(f"{_indent(indent)}def {self.name}({params}){ret}:")
        if self.body and getattr(self.body, "statements", None):
            self.body.gen(logger, indent + 1)
        else:
            logger(f"{_indent(indent+1)}pass")

    def to_dict(self):
        return {
            "type": "FunctionDecl",
            "name": self.name,
            "params": [p.to_dict() for p in self.params],
            "return_type": self.return_type,
            "body": self.body.to_dict(),
        }


@dataclass
class Program(ASTNode):
    statements: List[ASTNode]

    def gen(self, logger: Callable = log) -> None:
        for stmt in self.statements:
            # statements receive (logger, indent)
            stmt.gen(logger)

    def to_dict(self):
        return {
            "type": "Program",
            "statements": [stmt.to_dict() for stmt in self.statements],
        }


# --- Code generation helpers attached to AST nodes ---


def _indent(level: int) -> str:
    return "    " * (level or 0)


def _to_code(node: Optional[ASTNode]) -> str:
    if node is None:
        return "None"
    # expressions implement `to_code` where appropriate
    if hasattr(node, "to_code"):
        return node.to_code()  # pyright: ignore[reportAttributeAccessIssue]
    # fallback: try to stringify
    return str(node)
