// a 2 x 2 assignment: a[i,j] is 1 when worker i takes job j; the cost matrix is flattened (row major)
param n = 2;
param c = [4, 2, 3, 5];

var a[0..n, 0..n] : bool;

minimize cost: sum i in 0..n: sum j in 0..n: c[i*n+j] * a[i,j];

subject to
    forall i in 0..n: row: sum j in 0..n: a[i,j] == 1;
    forall j in 0..n: col: sum i in 0..n: a[i,j] == 1;
