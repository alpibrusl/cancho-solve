//~ EXPECT optimal 20
// Values [10,13,7,8], weights [5,7,4,5], capacity 11. Subsets that fit: {0,2} 17, {0,3} 18, {1,2} 20 (weight 11), {2,3} 15, and the singles (best 13); {0,1} and {1,3} weigh 12.
// So the optimum is 20. The relaxation takes item 0 whole and 6/7 of item 1: 10 + 11.14 = 21.14, which is fractional.
var x[0..4] : bool;
maximize 10*x[0] + 13*x[1] + 7*x[2] + 8*x[3];
subject to
    cap: 5*x[0] + 7*x[1] + 4*x[2] + 5*x[3] <= 11;
