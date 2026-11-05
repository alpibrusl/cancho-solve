//~ EXPECT optimal 1
//~ NODES 1
// The relaxation is a = 0.4 (5a >= 2), d = 0: value 0.4. Rounding to the nearest or down gives a = 0 and breaks `need`. The lock rounding leaves a at the nearest, because a has a lock in
// each direction (`need` against a decrease, `share` against an increase). Rounding every column up gives a = 1, d = 0: feasible, value 1. The objective is whole, so the root's 0.4 cannot
// beat an incumbent of 1 and the search stops at the root: optimal 1 in one node. Without the up rounding the root has no incumbent and the search branches (3 nodes).
var a : bool;
var d : bool;
minimize a + d;
subject to
    need: 5*a >= 2;
    share: a + d <= 1;
