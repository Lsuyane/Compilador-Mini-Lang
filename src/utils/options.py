class Options:
    NONE = 0
    LEXER = 1  # Stop on Lexer
    LOG = 2  # Log to stderr
    NO_OPTIMIZE = 4  # Optimize parser: use accumulator

    def __or__(self, other) -> int:
        return self.value | other.value

    def __and__(self, other) -> int:
        return self.value & other.value

    def __bool__(self) -> bool:
        return self.value != 0

    def __xor__(self, other) -> int:
        return self.value ^ other.value

    def __invert__(self) -> int:
        return ~self.value

    def __init__(self, value: int) -> None:
        super().__init__()
        self.value = value
