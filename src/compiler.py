#!/usr/bin/env python3
"""
Usage: python ./compyler.py <source_file> [-l|--lexer]
    @option [-?|--help] show help
    @option [-!|--log] log intermediary output using tui
    @option [-l|--lexer] options on lexer. Enable log
    @option [-no|--no-optimize] don't use accumulator
"""

import sys
from utils.options import *
from utils.utils import log_error, EXIT_SUCCESS, EXIT_ERROR


def show_help():
    # TODO -> Requires the output file for the --out option
    print(
        "\033[34m"
        # f'Usage: python {sys.argv[0]} <source_file> [<output_file>] [-!|--log] [-no|--no-optimize] [-l|--lexer]\n'
        f"Usage: python {sys.argv[0]} <source_file> [-!|--log] [-no|--no-optimize] [-l|--lexer]\n"
        "\t[-?|--help] show this help\n"
        "\t[-!|--log] log intermediary output using tui\n"
        "\t[-l|--lexer] options on lexer. Enable log\n"
        "\t[-no|--no-optimize] don't use accumulator\n"
        "\033[m"
    )


if __name__ == "__main__":
    # region Options
    options: int = Options.NONE  # type: ignore
    # endregion

    # region 1. Verifica se o usuário passou o nome do arquivo
    if len(sys.argv) < 2:
        log_error("Error: No file name provided")
        show_help()
        sys.exit(EXIT_ERROR)
    # endregion
    # region 2. Verifica se foram passadas opções
    elif len(sys.argv) > 2:
        for i in range(2, len(sys.argv)):
            # TODO -> Grouped options parsing
            if sys.argv[i] in ["-?", "--help"]:
                show_help()
                sys.exit()
            if sys.argv[i] in ["-l", "--lexer"]:
                options |= Options.LEXER
                options |= Options.LOG
            if sys.argv[i] in ["-!", "--log"]:
                options |= Options.LOG
            if sys.argv[i] in ["-no", "--no-optimize"]:
                # Allows the parser to use an accumulator to process results directly
                options |= Options.NO_OPTIMIZE
    # endregion

    source_filename = sys.argv[1]

    # region Lexer only
    if options & Options.LEXER:
        import modules.lexer as lexer

        lexer.main(source_filename, bool(options & Options.LOG))
        exit(EXIT_SUCCESS)
    # endregion

    # region Full compiler
    import modules.parser as parser

    parser.main(source_filename, options)
    # endregion
