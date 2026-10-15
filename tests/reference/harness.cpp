// Runs the unmodified reference JaroliftController on the host and dumps
// every GDO0 level change, TX/RX switch and delay as JSON (one line per case).
// Input (stdin), one case per line:
//   id kind cmd arg legacy base_serial counter master_msb master_lsb
//   kind: ch | grp | srv ; numbers in decimal
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>

#include "JaroliftController.h"

namespace sim {
uint64_t now_us = 0;
int tx_pin = 4;
std::vector<Event> events;
bool nvs_has = false;
uint16_t nvs_value = 0;
}  // namespace sim

static const char *kKind[] = {"w", "tx", "rx", "d"};

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.empty()) continue;
    std::istringstream in(line);
    std::string id, kind, cmd;
    long arg, legacy, base, counter;
    unsigned long msb, lsb;
    in >> id >> kind >> cmd >> arg >> legacy >> base >> counter >> msb >> lsb;

    sim::now_us = 0;
    sim::events.clear();
    sim::nvs_has = false;
    JaroliftController jc;
    jc.setGPIO(12, 13, 11, 10, sim::tx_pin, 5);
    jc.setKeys(msb, lsb);
    jc.setBaseSerial((uint32_t)base);
    jc.setLegacyLearnMode(legacy != 0);
    jc.begin();
    jc.setDeviceCounter((uint16_t)counter);
    sim::events.clear();
    sim::now_us = 0;

    using C = JaroliftController;
    uint8_t ch = (uint8_t)arg;
    if (kind == "ch") {
      C::commands c = cmd == "up" ? C::CMD_UP : cmd == "down" ? C::CMD_DOWN : cmd == "stop" ? C::CMD_STOP
                    : cmd == "shade" ? C::CMD_SHADE : C::CMD_SET_SHADE;
      jc.cmdChannel(c, ch);
    } else if (kind == "grp") {
      C::commands c = cmd == "up" ? C::CMD_UP : cmd == "down" ? C::CMD_DOWN : cmd == "stop" ? C::CMD_STOP : C::CMD_SHADE;
      jc.cmdGroup(c, (uint16_t)arg);
    } else if (cmd == "learn") jc.cmdLearn(ch);
    else if (cmd == "unlearn") jc.cmdUnlearn(ch);
    else if (cmd == "set_endpoint_up") jc.cmdSetEndPointUp(ch);
    else if (cmd == "delete_endpoint_up") jc.cmdDeleteEndPointUp(ch);
    else if (cmd == "set_endpoint_down") jc.cmdSetEndPointDown(ch);
    else if (cmd == "delete_endpoint_down") jc.cmdDeleteEndPointDown(ch);
    else { std::cerr << "unknown " << cmd << "\n"; return 2; }

    std::printf("{\"id\":\"%s\",\"counter_after\":%u,\"events\":[", id.c_str(), (unsigned)sim::nvs_value);
    for (size_t i = 0; i < sim::events.size(); ++i) {
      const auto &e = sim::events[i];
      std::printf("%s[\"%s\",%llu,%ld]", i ? "," : "", kKind[e.kind], (unsigned long long)e.t, e.value);
    }
    std::printf("]}\n");
  }
  return 0;
}
