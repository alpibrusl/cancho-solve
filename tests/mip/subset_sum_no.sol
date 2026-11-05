//~ EXPECT infeasible
// Every weight is even, so no subset sums to 15; the relaxation reaches 15 with fractions.
var x[0..4] : bool;
maximize x[0] + x[1] + x[2] + x[3];
subject to
    target: 4*x[0] + 6*x[1] + 10*x[2] + 12*x[3] == 15;
