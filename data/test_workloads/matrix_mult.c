1
#include <stdio.h>
2
#define N 512
3
4
// Naive O(N³) — cache thrashing, high power draw
5
int A[N][N], B[N][N], C[N][N];
6
7
int main() {
8
for (int i = 0; i < N; i++)
9
for (int j = 0; j < N; j++)
10
for (int k = 0; k < N; k++)
11
C[i][j] += A[i][k] * B[k][j];
12
printf("Naive execution complete.\n");
13
return 0;
14
}