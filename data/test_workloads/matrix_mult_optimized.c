#include <stdio.h>
#define N 512

// Standard, naive O(N^3) matrix multiplication.
// This keeps the processor awake, moving data constantly, drawing high power.
int A[N][N], B[N][N], C[N][N];

int main() {
    int blockSize = 64; // Petal Injected Block Size
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
    printf("Naive execution complete.\n");
    return 0;
}