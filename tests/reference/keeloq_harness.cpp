// Reference KeeLoq vectors from the unmodified KeeloqLib (32-bit results).
// stdin: key_high key_low data  (decimal) -> stdout: encrypt decrypt
#include <cstdio>
#include "KeeloqLib.h"
int main() {
  unsigned long hi, lo, data;
  while (std::scanf("%lu %lu %lu", &hi, &lo, &data) == 3) {
    Keeloq k(hi, lo);
    std::printf("%lu %lu\n", k.encrypt(data) & 0xFFFFFFFFUL, k.decrypt(data) & 0xFFFFFFFFUL);
  }
  return 0;
}
