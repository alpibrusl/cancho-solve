//~ EXPECT unknown
//~ ARGS --node-limit 50
//~ EXIT 1
// 2x - 2y == 1 has no integer point (parity), but the relaxation has, and each branch moves the fractional vertex by one unit along ranges of a million: the search cannot finish
// in 50 nodes, and no incumbent exists, so the answer is unknown with a bound (the node limit is what stops it, not a proof).
var x : int 0..1000000;
var y : int 0..1000000;
minimize x;
subject to
    parity: 2*x - 2*y == 1;
