set shell := ["bash", "-cu"]
set positional-arguments := true

default:
    @just --list

list:
    @find abilities -name ability.yaml | sort

notion *args='--help':
    ./bin/notion "$@"

auto-coder *args='--help':
    ./bin/auto-coder "$@"

chores *args='--help':
    ./bin/chores "$@"

history-dashboard *args='help':
    ./bin/history-dashboard "$@"
