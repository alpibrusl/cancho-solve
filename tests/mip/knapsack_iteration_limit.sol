//~ EXPECT unknown
//~ ARGS --iteration-limit 0
//~ EXIT 1
//~ NODES 0
//~ LIMIT iterations
// With no iteration allowed the root relaxation cannot be solved: unknown, no node solved, no bound.
var x[0..4] : bool;
maximize 10*x[0] + 13*x[1] + 7*x[2] + 8*x[3];
subject to
    cap: 5*x[0] + 7*x[1] + 4*x[2] + 5*x[3] <= 11;
