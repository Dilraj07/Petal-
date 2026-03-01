def apply_loop_tiling(source_code):
    print("[\033[92mPetal Optimizer\033[0m] Applying 'Loop Tiling' transformation pass...")
    
    # We locate the bad loops and inject the optimized tiled version dynamically
    # (This is a simplified source-to-source compiler technique)
    
    optimized_code = source_code.replace(
        "int main() {", 
        "int main() {\n    int blockSize = 64; // Petal Injected Block Size"
    )
    
    # Replace naive loops with blocked loops
    naive_loops = """for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            for (int k = 0; k < N; k++) {"""
            
    tiled_loops = """for(int i=0; i<N; i+=blockSize){
        for(int j=0; j<N; j+=blockSize){
            for(int k=0; k<N; k+=blockSize){
                for(int ii=i; ii<i+blockSize; ii++){
                    for(int jj=j; jj<j+blockSize; jj++){
                        for(int kk=k; kk<k+blockSize; kk++){"""
                        
    optimized_code = optimized_code.replace(naive_loops, tiled_loops)
    
    # Add the closing brackets for the 3 new loops
    optimized_code = optimized_code.replace(
        "C[i][j] += A[i][k] * B[k][j];\n            }\n        }\n    }",
        "C[ii][jj] += A[ii][kk] * B[kk][jj];\n                        }\n                    }\n                }\n            }\n        }\n    }"
    )
    
    return optimized_code
