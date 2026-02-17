from dataclasses import dataclass
from typing import List, Optional, Any

class ASTNode:
    pass

@dataclass
class Literal(ASTNode):
    value: Any

@dataclass
class Identifier(ASTNode):
    name: str

@dataclass
class BinOp(ASTNode):
    left: ASTNode
    op: str
    right: ASTNode

@dataclass
class UnaryOp(ASTNode):
    op: str
    expr: ASTNode

@dataclass
class FunctionCall(ASTNode):
    name:str
    args: List[ASTNode]
    
@dataclass
class VarDecl(ASTNode):
    name: str
    var_type: str
    value: ASTNode
    
@dataclass
class Assignment(ASTNode):
    name: str
    value: ASTNode

@dataclass
class PrintStmt(ASTNode):
    expr: ASTNode

@dataclass
class ReturnStmt(ASTNode):
    expr: ASTNode
    
@dataclass
class Block(ASTNode):
    statements: List[ASTNode]
    
@dataclass
class IfStmt(ASTNode):
    condition: ASTNode
    true_block: Block
    false_block: Optional[Block] = None

@dataclass
class WhileStmt(ASTNode):
    condition: ASTNode
    body: Block

# Nós de funçao e programa
@dataclass
class FormalParam(ASTNode):
    name: str
    param_tyoe: str

@dataclass
class FunctionDecl(ASTNode):
    name: str
    params: List[FormalParam]
    return_type: str
    body: Block

@dataclass
class Program(ASTNode):
    statements: List[ASTNode]