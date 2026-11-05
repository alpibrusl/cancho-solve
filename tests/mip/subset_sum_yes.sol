//~ EXPECT optimal 3
// Subsets of {3,5,7,11} with sum 15: 3+5+7 = 15 is the only one (11 + anything from {3,5,7} is 14, 16, 18, ...; 11+3 = 14, 11+5 = 16), so the most items is 3.
var x[0..4] : bool;
maximize x[0] + x[1] + x[2] + x[3];
subject to
    target: 3*x[0] + 5*x[1] + 7*x[2] + 11*x[3] == 15;
