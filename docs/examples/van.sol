// A courier van carries at most 15 kg. Six parcels, each taken whole or left behind:
// weight in kg, and the fee the courier earns for delivering it.
param n   = 6;
param w   = [12, 2, 1, 4, 7, 5];
param fee = [4, 2, 1, 10, 8, 6];
param cap = 15;

var take[0..n] : bool;

maximize income: sum i in 0..n: fee[i] * take[i];

subject to
    weight: sum i in 0..n: w[i] * take[i] <= cap;
