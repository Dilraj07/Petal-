#include <stdio.h>
#define N 512

// Blocked (Tiled) matrix multiplication.
// Highly cache-friendly. Executes faster and lets the CPU drop power states.
int A[N][N], B[N][N], C[N][N];

int main() {
    int blockSize = 64; 
    for(int i=0; i<N; i+=blockSize){
        for(int j=0; j<N; j+=blockSize){
            for(int k=0; k<N; k+=blockSize){
                for(int ii=i; ii<i+blockSize; ii++){
                    for(int jj=j; jj<j+blockSize; jj++){
                        for(int kk=k; kk<k+blockSize; kk++){
                            C[ii][jj] += A[ii][kk] * B[kk][jj];
                        }
                    }
                }
            }
        }
    }
    printf("Petal optimized execution complete.\n");
    return 0;
}