var x : real 0..10;
minimize (1+2)*(x) + 2*(3 - 1);   // 3x + 4
subject to (4/2)*x >= sum i in 0..3: i;   // 2x - 3 >= 0, so 2x >= 3
