#!/bin/sh
# Compila duas vezes, verifica a entrega e mantem auxiliares fora do repositorio.
set -eu
bd2_paper_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
bd2_build_dir=$(mktemp -d /tmp/bd2-paper.XXXXXX)
trap 'rm -rf "$bd2_build_dir"' EXIT HUP INT TERM
cd "$bd2_paper_dir"
for bd2_pass in 1 2; do
    if ! pdflatex -interaction=nonstopmode -halt-on-error \
        -output-directory="$bd2_build_dir" main.tex > "$bd2_build_dir/run-$bd2_pass.txt" 2>&1; then
        cat "$bd2_build_dir/run-$bd2_pass.txt" >&2
        exit 1
    fi
done
bd2_pages=$(pdfinfo "$bd2_build_dir/main.pdf" | awk '/^Pages:/ {print $2}')
if [ "$bd2_pages" -lt 3 ] || [ "$bd2_pages" -gt 5 ]; then
    printf 'PDF com %s paginas; esperado: 3 a 5.\n' "$bd2_pages" >&2
    exit 1
fi
if rg -n 'Overfull|undefined|Missing character' "$bd2_build_dir/main.log"; then
    printf 'Corrija as referencias ou a diagramacao antes de entregar.\n' >&2
    exit 1
fi
cp "$bd2_build_dir/main.pdf" main.pdf
printf 'Gerado: %s/main.pdf (%s paginas).\n' "$bd2_paper_dir" "$bd2_pages"
