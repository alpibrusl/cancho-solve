// an empty sum and an empty forall are skipped whole: x[3] would be out of range if its body were read
var x[0..3] : bool;
var y : real 0..1;
minimize sum i in 0..0: x[i] + 2*y;
subject to
    forall i in 3..3: bad: x[i] <= 1;
    after: y <= 1;
