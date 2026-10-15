// Host stub of the CC1101 driver: records TX/RX state changes only.
#pragma once
#include <Arduino.h>
#define CC1101_MARCSTATE 0x35
#define CC1101_RSSI 0x34
#define CC1101_STATUS_REGISTER 0xC0
#define CC1101_SCAL 0x33
#define PA_LongDistance 0xC0
enum CFREQ { CFREQ_868 = 0, CFREQ_915, CFREQ_433, CFREQ_918, CFREQ_LAST };
class CC1101 {
 public:
  void setGPIO(int, int, int, int, int) {}
  bool init() { return true; }
  bool connected() { return true; }
  void setSyncWord(uint8_t, bool) {}
  void setCarrierFreq(int) {}
  void disableAddressCheck() {}
  void setTxPowerAmp(uint8_t) {}
  void cmdStrobe(uint8_t) {}
  uint8_t readReg(uint8_t, uint8_t) { return 0; }
  uint8_t readStatusReg(uint8_t) { return state_; }
  void setTxState() { state_ = 0x13; sim::events.push_back({sim::TX, sim::now_us, 0}); }
  void setRxState() { state_ = 0x0D; sim::events.push_back({sim::RX, sim::now_us, 0}); }
 private:
  uint8_t state_ = 0x0D;
};
