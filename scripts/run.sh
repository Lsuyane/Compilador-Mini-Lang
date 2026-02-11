#!/bin/bash
cd $(dirname "$0")/..

if [[ ! $VIRTUAL_ENV ]]; then
    case $SHELL in
        */fish)
            source .venv/bin/activate.fish
            ;;
        */bash | */zsh)
            source .venv/bin/activate
            ;;
        *)
            source .venv/bin/activate
            if [[ $? -ne 0 ]]; then
                printf "\033[31mUnknown shell.\033[0m\n"
                exit 1
            fi
            ;;
    esac
fi

if [[ ! "$@" ]]; then
    python ./src/compiler.py ./code.ml --lexer --log "$@"
else
    python ./src/compiler.py $@
fi
