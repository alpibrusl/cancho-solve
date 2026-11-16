#!/bin/zsh
# The sweep of docs/design.md 22.19: the 33 tight models of 22.15 to 22.17 and the 16 held-out models (24 x 16 tight seeds 101 to 116), each under six settings, one line per cell:
#   model  setting  root_bound  root_seconds  status  objective  nodes  seconds  final_bound
# The root run is `--node-limit 1` with `eager-rounds`, the full run `--node-limit 30000` (the limit of 22.15 to 22.17; `solve run` has no time limit). Time is wall time, `$EPOCHREALTIME`; cells run 6 at a time, so a
# difference under 10% is not read. Usage: scripts/sweep_gomory.sh OUT.tsv   (SOLVE, LAB as in the gates; JOBS=6)
zmodload zsh/datetime
SOLVE=${SOLVE:-build/solve}; LAB=${LAB:-build/lab}

cell() {   # model "V T seed", setting
    local m=(${=1}) spec=$2 a=() t0 t1 r f
    [[ $spec != none ]] && a=(--exp $spec)
    local text; text=$($LAB gen ev $m[1] $m[2] tight $m[3])
    local ra=(--exp eager-rounds); [[ $spec != none ]] && ra=(--exp $spec,eager-rounds)   # the root run needs the rounds before the search (22.18), or its bound is the LP's
    t0=$EPOCHREALTIME; r=$(print -r -- $text | $SOLVE run --node-limit 1 $ra); t1=$EPOCHREALTIME
    local rb=$(print -r -- $r | jq -r '.bound // .objective // "-"') rs=$(printf %.2f $((t1 - t0)))
    t0=$EPOCHREALTIME; f=$(print -r -- $text | $SOLVE run --node-limit 30000 $a); t1=$EPOCHREALTIME
    local tail; tail=$(print -r -- $f | jq -r '[.status, (.objective // "-"), .stats.nodes, "'$(printf %.2f $((t1 - t0)))'", (.bound // .objective // "-")] | map(tostring) | join("\t")')
    printf '%s\t%s\t%s\t%s\t%s\n' "$m[1]x$m[2]s$m[3]" "$spec" "$rb" "$rs" "$tail"   # one write per cell: parallel cells must not interleave
}

if [[ $1 == cell ]]; then cell "$2" "$3"; exit; fi

out=${1:?usage: sweep_gomory.sh OUT.tsv}
models=()
for V in 10 12 16; do for s in 1 2 3 4 5 6 7 8; do models+=("$V 12 $s"); done; done
for s in 1 2 3 4 5 6 7 8 9; do models+=("24 16 $s"); done
for s in {101..116}; do models+=("24 16 $s"); done
settings=(none gomory "gomory,gomory-nnz=1" "gomory,gomory-nnz=2" "gomory,gomory-nnz=4" "gomory,gomory-nnz=7")
for m in $models; do for sp in $settings; do print -r -- "$m|$sp"; done; done | \
    xargs -P ${JOBS:-6} -I{} zsh -c 'j="{}"; '"SOLVE=$SOLVE LAB=$LAB"' scripts/sweep_gomory.sh cell "${j%%|*}" "${j##*|}"' > $out
sort -o $out $out; print "$(wc -l < $out) cells in $out"
