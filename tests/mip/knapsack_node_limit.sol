//~ EXPECT unknown
//~ ARGS --node-limit 1
//~ EXIT 1
// The same knapsack with one node: the root relaxation is fractional (21.14) and rounding it (items 0 and 1 weigh 12 > 11) gives no incumbent, so the answer is unknown.
var x[0..4] : bool;
maximize 10*x[0] + 13*x[1] + 7*x[2] + 8*x[3];
subject to
    cap: 5*x[0] + 7*x[1] + 4*x[2] + 5*x[3] <= 11;
