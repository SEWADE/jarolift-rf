// Host stub: one in-memory u16 is enough for the "device_data/devcnt" counter.
#pragma once
#include <cstdint>
typedef int esp_err_t;
typedef uint32_t nvs_handle_t;
#define ESP_OK 0
#define ESP_ERR_NVS_NOT_FOUND 0x1102
#define NVS_READWRITE 1
namespace sim { extern bool nvs_has; extern uint16_t nvs_value; }
inline esp_err_t nvs_open(const char *, int, nvs_handle_t *h) { *h = 1; return ESP_OK; }
inline esp_err_t nvs_get_u16(nvs_handle_t, const char *, uint16_t *v) {
  if (!sim::nvs_has) return ESP_ERR_NVS_NOT_FOUND;
  *v = sim::nvs_value; return ESP_OK;
}
inline esp_err_t nvs_set_u16(nvs_handle_t, const char *, uint16_t v) { sim::nvs_has = true; sim::nvs_value = v; return ESP_OK; }
inline esp_err_t nvs_commit(nvs_handle_t) { return ESP_OK; }
inline void nvs_close(nvs_handle_t) {}
