#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
static void sweep(double *w, long m, long big, long r, long q, long rounds) {
    for (long n = 0; n < rounds; n++) {
        const double *src = w + r * big;
        for (long i = 0; i < m; i++) {
            if (i == r) continue;
            double f = w[i * big + q];
            if (f != 0.0) {
                double *dst = w + i * big;
                for (long j = 0; j < big; j++) dst[j] = dst[j] - f * src[j];
            }
        }
    }
}
int main(void) {
    long m = 400, big = 1200, cells = m * big;
    double *w = malloc(cells * sizeof(double));
    for (long k = 0; k < cells; k++) w[k] = 1.0 + (double)(k % 7) * 0.25;
    for (long i = 0; i < m; i++) w[i * big + 5] = 1e-9;
    sweep(w, m, big, 3, 5, 100);
    double sum = 0; for (long k = 0; k < cells; k++) sum += w[k];
    printf("%ld\n", (long)sum);
    return 0;
}
