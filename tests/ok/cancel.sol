// terms that cancel are dropped; a feasibility problem has "objective": null
var x : int 0..5;
var y : int 0..5;
subject to c: x + y - x <= 3;
