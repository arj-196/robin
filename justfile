set shell := ["zsh", "-cu"]
set positional-arguments := true

default:
    @just --list

list:
    @find abilities -name ability.yaml | sort

notion *args='--help':
    ./bin/notion "$@"

auto-coder *args='--help':
    ./bin/auto-coder "$@"

dashboard *args='help':
    ./bin/dashboard "$@"
