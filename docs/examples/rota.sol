// Four nurses, four night shifts, one nurse per shift and one shift per nurse.
// dislike[i*n+j] is how much nurse i dislikes shift j (0 = happy, 9 = would rather not).
param n = 4;
param dislike = [3, 7, 2, 9,
                 6, 1, 8, 4,
                 5, 5, 3, 2,
                 9, 4, 6, 1];

var give[0..n, 0..n] : bool;

minimize unhappiness: sum i in 0..n: sum j in 0..n: dislike[i*n+j] * give[i,j];

subject to
    forall i in 0..n: one_shift_each: sum j in 0..n: give[i,j] == 1;
    forall j in 0..n: one_nurse_each: sum i in 0..n: give[i,j] == 1;
