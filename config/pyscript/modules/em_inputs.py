"""Reads from and writes to Home Assistant.

Everything that touches Home Assistant lives here: the entity names, the state
reads and the service calls writing to Solax.
The logic that works with the values is in em_functions.py, the triggers and
the calls to EMHASS in em.py.

Adapt the entity names below to match your entities.
"""
from datetime import datetime

from em_functions import PUBLISH_OK, PUBLISH_STALE, TIMEZONE

# This is the OTE integation sensor, if you use something else, please adapt the spot price functions
SENSOR_TODAY_SPOT = "sensor.current_spot_electricity_price_15min"
SENSOR_TODAY_SPOT_BUY = "sensor.current_spot_electricity_price_15min"
SENSOR_TODAY_SPOT_SELL = "sensor.current_spot_electricity_price_15min"

# Weather integration
SENSOR_TODAY_WEATHER = "sensor.energy_production_today_2"
SENSOR_TOMORROW_WEATHER = "sensor.energy_production_tomorrow_2"

# Solax
SENSOR_BATTERY_CAPACITY = "sensor.solax_battery_capacity"

# Sensor containing the current spot *sell* price
# Used for the disable enable
SENSOR_SELL_PRICE = "sensor.current_spot_electricity_price"

# Solax field for changing the user limit
SENSOR_EXPORT_LIMIT = "number.solax_export_control_user_limit"

# Input sensor for saving the status
INPUT_SENSOR_EXPORT_ALLOWED = "input_boolean.export_allowed"

# Input sensor for modifying the minimum sell price
INPUT_SENSOR_SELL_THRESHOLD = "input_number.export_price_threshold"

# Input sensor that defines the maximum limit restoration
INPUT_SENSOR_RESTORE_EXPORT_ALLOWED = "input_number.maximum_export_allowed"

# Entities written by em.py. Neither is kept across Home Assistant restarts, on purpose:
# the EMHASS sensors are gone after a restart until the first ok publish, so a publish
# from before the restart must not count.
# Time of the last ok publish to EMHASS, as an ISO timestamp
PYSCRIPT_LAST_PUBLISH = "pyscript.emhass_last_publish"
# Result of the publish watchdog as a problem binary sensor: on when the publish is stale,
# off when it is ok, with the age as an attribute. The Solax automations act only when off.
BINARY_SENSOR_PUBLISH_STALE = "binary_sensor.emhass_publish_stale"


def now():
  """Current time in the spot market timezone."""
  return datetime.now(TIMEZONE)


def buy_price_attributes():
  """{iso time: price} forecast of the buy spot price."""
  return hass.states.get(SENSOR_TODAY_SPOT_BUY).attributes


def sell_price_attributes():
  """{iso time: price} forecast of the sell spot price."""
  return hass.states.get(SENSOR_TODAY_SPOT_SELL).attributes


def pv_watts():
  """{iso time: watts} production forecast of today and tomorrow."""
  today_attributes = hass.states.get(SENSOR_TODAY_WEATHER).attributes
  tomorrow_attributes = hass.states.get(SENSOR_TOMORROW_WEATHER).attributes
  return today_attributes["watts"] | tomorrow_attributes["watts"]


def battery_soc():
  """Battery level in percent, as the raw state."""
  return hass.states.get(SENSOR_BATTERY_CAPACITY).state


def tomorrow_production():
  """Forecasted production tomorrow in kWh, as the raw state."""
  return hass.states.get(SENSOR_TOMORROW_WEATHER).state


def spot_sell_price():
  """Current spot sell price, as the raw state."""
  return hass.states.get(SENSOR_SELL_PRICE).state


def sell_threshold():
  """User defined minimum sell price, as the raw state."""
  return hass.states.get(INPUT_SENSOR_SELL_THRESHOLD).state


def restore_export_limit():
  """User defined export limit to restore when exporting is allowed, as the raw state."""
  return hass.states.get(INPUT_SENSOR_RESTORE_EXPORT_ALLOWED).state


def export_limit():
  """Export limit currently set in Solax, as a number."""
  return float(hass.states.get(SENSOR_EXPORT_LIMIT).state)


def set_export_allowed(allowed):
  """Store whether exporting is allowed in the input boolean."""
  if allowed:
    service.call("input_boolean", "turn_on", entity_id=INPUT_SENSOR_EXPORT_ALLOWED)
  else:
    service.call("input_boolean", "turn_off", entity_id=INPUT_SENSOR_EXPORT_ALLOWED)


def set_export_limit(value):
  """Write the export limit to Solax."""
  service.call("number", "set_value", entity_id=SENSOR_EXPORT_LIMIT, value=value)


def last_publish():
  """Time of the last ok publish, as the raw state (an ISO timestamp or unknown)."""
  # Doesn't exist until the first ok publish after a restart
  if not state.exist(PYSCRIPT_LAST_PUBLISH):
    return "unknown"
  return state.get(PYSCRIPT_LAST_PUBLISH)


def set_last_publish(time):
  """Store the time of an ok publish."""
  state.set(PYSCRIPT_LAST_PUBLISH, time.isoformat())


def publish_watchdog_status():
  """Last result of the publish watchdog: PUBLISH_OK, PUBLISH_STALE, or None before its first run."""
  # Doesn't exist until the first run after a restart
  if not state.exist(BINARY_SENSOR_PUBLISH_STALE):
    return None
  value = state.get(BINARY_SENSOR_PUBLISH_STALE)
  if value == "on":
    return PUBLISH_STALE
  if value == "off":
    return PUBLISH_OK
  return None


def set_publish_watchdog(status, age_minutes, last_publish):
  """Store the result of the publish watchdog, usable in automations and dashboards.

  device_class problem makes Home Assistant show on as Problem and off as OK.
  """
  state.set(
    BINARY_SENSOR_PUBLISH_STALE,
    "on" if status == PUBLISH_STALE else "off",
    device_class="problem",
    friendly_name="EMHASS publish",
    age_minutes=age_minutes,
    last_publish=str(last_publish),
  )
