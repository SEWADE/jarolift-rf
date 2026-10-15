// Host stub of the Arduino API: virtual clock + GDO0 level recorder.
#pragma once
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <vector>

typedef uint8_t byte;
#define IRAM_ATTR
#define LOW 0
#define HIGH 1
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define CHANGE 3
#define bitRead(value, bit) (((value) >> (bit)) & 0x01)
#define ESP_LOGD(tag, ...) ((void)0)
#define ESP_LOGI(tag, ...) ((void)0)
#define ESP_LOGE(tag, ...) ((void)0)

namespace sim {
enum Kind { WRITE, TX, RX, DELAY };
struct Event { Kind kind; uint64_t t; long value; };
extern uint64_t now_us;
extern int tx_pin;
extern std::vector<Event> events;
}  // namespace sim

inline unsigned long micros() { return (unsigned long)sim::now_us; }
inline void delayMicroseconds(unsigned int us) { sim::now_us += us; }
inline void delay(unsigned long ms) {
  sim::events.push_back({sim::DELAY, sim::now_us, (long)ms});
  sim::now_us += ms * 1000ULL;
}
inline void digitalWrite(int pin, int level) {
  if (pin == sim::tx_pin) sim::events.push_back({sim::WRITE, sim::now_us, level});
}
inline int digitalRead(int) { return 0; }
inline void pinMode(int, int) {}
inline void attachInterrupt(int, void (*)(), int) {}
