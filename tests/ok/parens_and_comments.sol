// parentheses, division by a number, exponent, a comment after a statement
var x : real 0..1e1;   // upper bound 10
var y : real -2.5..2.5;
minimize 2*(x + y) - (x - y)*3 + 4/2;
subject to
    2*(x + 1) <= 5 + y/2;
    -x - y >= -7;
