//~ EXPECT optimal 12
//~ NODES 1
// A 3 x 3 assignment (the constraint matrix is totally unimodular, so the relaxation has an integral optimal vertex and one node proves it).
// Costs [[4,2,8],[4,3,7],[3,1,6]]; the six permutations cost 13 (0,1,2), 12 (0,2,1), 12 (1,0,2), 12 (1,2,0), 13 (2,0,1), 14 (2,1,0): the least is 12.
param n = 3;
param c = [4, 2, 8, 4, 3, 7, 3, 1, 6];
var a[0..n, 0..n] : bool;
minimize cost: sum i in 0..n: sum j in 0..n: c[i*n+j] * a[i,j];
subject to
    forall i in 0..n: row: sum j in 0..n: a[i,j] == 1;
    forall j in 0..n: col: sum i in 0..n: a[i,j] == 1;
