// A variable with no bounds: the checker refuses it before any solver sees it.
var x : real;
maximize x;
subject to c: x <= 4;
