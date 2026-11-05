//~ RULE solve.nonlinear
var x[0..2] : real 0..1;
minimize sum i in 0..2: x[i]*x[i];
