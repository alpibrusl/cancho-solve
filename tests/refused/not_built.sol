//~ RULE solve.not-built
var x[0..3] : int 0..3;
subject to all_different(x[0], x[1], x[2]);
