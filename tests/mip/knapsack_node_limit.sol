//~ EXPECT feasible 10
//~ ARGS --node-limit 1
//~ EXIT 1
//~ NODES 1
//~ LIMIT nodes
// The same knapsack with one node: the root relaxation is fractional (21.14). Rounding it to the nearest (items 0 and 1, weight 12 > 11) gives no point, but rounding down (item 0 alone,
// weight 5) is feasible with value 10, so the answer is feasible 10 with the bound 21.14 (docs/design.md 19.8; with only the nearest rounding it was unknown).
var x[0..4] : bool;
maximize 10*x[0] + 13*x[1] + 7*x[2] + 8*x[3];
subject to
    cap: 5*x[0] + 7*x[1] + 4*x[2] + 5*x[3] <= 11;
