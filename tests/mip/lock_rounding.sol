//~ EXPECT feasible 3
//~ ARGS --node-limit 1
//~ EXIT 1
//~ NODES 1
//~ LIMIT nodes
// The relaxation is a = 0.4 (5a >= 2) and b = 0.6 (5b <= 3), value 3(0.4) - 0.6 = 0.6. Rounding to the nearest gives a = 0, which breaks `need`; rounding every column up gives b = 1, which breaks
// `room`; rounding every column down gives a = 0 again. Only the lock rounding (docs/design.md 19.8) finds a point: `need` can only be broken by a decrease of a, so a goes up, and `room`
// only by an increase of b, so b goes down: a = 1, b = 0, value 3. With one node the answer is feasible 3 and the bound is the relaxation's 0.6.
var a : bool;
var b : bool;
minimize 3*a - b;
subject to
    need: 5*a >= 2;
    room: 5*b <= 3;
