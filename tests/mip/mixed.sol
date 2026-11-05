//~ EXPECT optimal 5.5
// maximise x + y, x integer in 0..10, y real in 0..10, 2x + y <= 7.5, x + 2y <= 9.5. For x = 0, 1, 2, 3 the best y is 4.75, 4.25, 3.5, 1.5, so the values are
// 4.75, 5.25, 5.5, 4.5; x = 4 is infeasible. The optimum is 5.5 at (2, 3.5). The relaxation's vertex (11/6, 23/6) gives 5.67.
var x : int 0..10;
var y : real 0..10;
maximize x + y;
subject to
    a: 2*x + y <= 7.5;
    b: x + 2*y <= 9.5;
