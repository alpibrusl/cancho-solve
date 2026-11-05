// A two-variable LP.
var x : real 0..10;
var y : real 0..10;
maximize 3*x + 2*y;
subject to
    c1: x + y <= 4;
    c2: x + 3*y <= 6;
