#include <stdio.h>
#define N 512

// Naive O(N³) — cache thrashing, high power draw
int A[N][N], B[N][N], C[N][N];

int main() {
 for (int i = 0; i < N; i++)
 for (int j = 0; j < N; j++)
 for (int k = 0; k < N; k++)
 C[i][j] += A[i][k] * B[k][j];
 printf("Naive execution complete.\n");
 return 0;
}
