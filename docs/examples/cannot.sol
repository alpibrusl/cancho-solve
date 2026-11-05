// Two parcels that cannot both be taken and must both be taken.
var a : bool;
var b : bool;
maximize a + b;
subject to
    both:   a + b >= 2;
    either: a + b <= 1;
