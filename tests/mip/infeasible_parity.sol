//~ EXPECT infeasible
// 2x + 2y is even and 3 is odd, so no integer point satisfies the row; the relaxation does (x = 1.5, y = 0), so the search must branch to find out.
var x : int 0..5;
var y : int 0..5;
minimize x + y;
subject to
    odd: 2*x + 2*y == 3;
