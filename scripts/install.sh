#!/bin/bash
cd $(dirname "$0")/..

python -m venv .venv

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

pip install -r requirements.txt
