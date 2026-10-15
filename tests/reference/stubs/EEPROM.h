#pragma once
#include <cstdint>
struct EEPROMClass {
  void begin(int) {}
  template <typename T> void get(int, T &v) { v = 0; }
};
inline EEPROMClass EEPROM;
