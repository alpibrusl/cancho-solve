//~ EXPECT optimal 8
// maximise 3x + 2y with 2x + 3y <= 7, x - y <= 2, x in -3..4, y in -2..5. By cases on x: x = 2 gives y in 0..1, best (2,1) = 8; x = 3 needs y <= 0 and y >= 1, none;
// x = 1 gives y <= 1: 5; x = 0: y <= 2: 4; x = 4 needs y <= -1 and y >= 2, none; x <= -1 gives at most 3x + 2*4 < 8 (and y <= 5 caps it). So 8.
// The relaxation's vertex (2.6, 0.6) gives 9.
var x : int -3..4;
var y : int -2..5;
maximize 3*x + 2*y;
subject to
    a: 2*x + 3*y <= 7;
    b: x - y <= 2;
