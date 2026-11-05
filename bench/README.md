# bench/

`pivot.cho` and `pivot.c` are the simplex's pivot row update on its own (`row_i -= f * row_r` for every row but the pivot row, 100 sweeps over a 400 x 1200 matrix), `pivot.cho` in three
spellings of the inner loop (`a`: flat slice with `ib + j`, as `lib/lp/simplex.cho` writes it; `b`: two row slices and a loop condition that proves both bounds; `c`: `wrapping_add` on the indices).
They check that the program's checksum agrees across variants and compilers. `docs/design.md` section 16 has the numbers.

    cancho build bench/pivot.cho --std --backend llvm -o /tmp/pivot-llvm && /tmp/pivot-llvm a
    clang -O2 -ffp-contract=off -o /tmp/pivot-c bench/pivot.c && /tmp/pivot-c

To change the size or the number of sweeps edit `m`, `big` and the last argument of the `sweep_*` call (and the same in `pivot.c`).
