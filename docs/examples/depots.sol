// Two depots supply three shops. cost[i*3+j] is the price per crate from depot i to shop j.
// Depot 0 holds 60 crates, depot 1 holds 50. The shops need 30, 40 and 25. Crates can be split.
param cost = [4, 6, 9,
              5, 3, 7];
param stock = [60, 50];
param need  = [30, 40, 25];

var ship[0..2, 0..3] : real 0..100;

minimize freight: sum i in 0..2: sum j in 0..3: cost[i*3+j] * ship[i,j];

subject to
    forall i in 0..2: stock_limit: sum j in 0..3: ship[i,j] <= stock[i];
    forall j in 0..3: shop_need:   sum i in 0..2: ship[i,j] >= need[j];
