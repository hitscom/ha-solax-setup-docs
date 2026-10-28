"""Pure logic for the EMHASS optimizations and the Solax export limit.

Only the standard library is used here, nothing from Home Assistant, pyscript or
EMHASS, so this file can be imported and unit tested outside of Home Assistant.
The optimizations are returned as an Optimization result, em.py posts it to EMHASS.
The Home Assistant reads and writes live in em_inputs.py, the triggers in em.py.
"""
import logging

from collections import namedtuple
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("spot_eval.pyscript")

# EMHASS actions, the endpoint of http://127.0.0.1:5000/action/<action>
MPC = "naive-mpc-optim"
DAYAHEAD = "dayahead-optim"
PUBLISH = "publish-data"

# Result of building an optimization, em.py posts the payload to the EMHASS action.
# A namedtuple so the repr works inside pyscript, where special methods of own classes don't.
#   action: the EMHASS action to call
#   payload: the json to post, None when skipped
#   skipped: why the optimization is skipped, None when it should run
Optimization = namedtuple("Optimization", ["action", "payload", "skipped"], defaults=[None])

# Timezone of the spot market, the dayahead optimization runs at 23:00 local time
TIMEZONE = ZoneInfo("Europe/Prague")

# Adjustments added to the raw spot price (distribution fees, taxes, trader margin)
BUY_PRICE_ADJUSTMENT = 0.5 + 2.5
SELL_PRICE_ADJUSTMENT = -0.5

# maxim amount of the lines 2
LINES_LIMIT = 24 * 4

# A forecast value older than this means the forecast data is missing
MAX_FORECAST_AGE = timedelta(hours = 2)

# Hour of the day the dayahead optimization runs, the MPC optimizes until the next one
DAYAHEAD_HOUR = 23

# Below this amount of 15 minute lines the MPC is skipped as per the emhass docs
MIN_MPC_LINES = 6

# Tomorrow's production (kWh) below this means the battery should end the day fuller
LOW_PRODUCTION_THRESHOLD = 20
SOC_FINAL_LOW_PRODUCTION = 0.7
SOC_FINAL_NORMAL_PRODUCTION = 0.5


def spot_forecast(attributes):
  """(time, price) of the spot price sensor attributes named by an ISO time.

  The other attributes are skipped: unit_of_measurement, icon, friendly_name and
  whatever else the sensor has, e.g. state_class or device_class.
  """
  forecast = []
  for k, v in attributes.items():
    try:
      date = datetime.fromisoformat(k)
    except ValueError:
      continue
    forecast += [(date, v)]

  # Otherwise a sensor with differently named attributes just gives no prices
  if not forecast:
    logger.warning(f"No spot prices in the attributes {list(attributes)}")
  return forecast


def get_spot_prices_day_ahead(now, attributes, price_adjustment):
  """Get the prices from the forecast."""
  prices = []

  for date, v in spot_forecast(attributes):
    v_a = v

    if date < now:
      continue

    prices += [v_a + price_adjustment]

    if len(prices) == LINES_LIMIT:
      break

  return prices


def get_spot_prices_mpc(attributes, lines_limit, start, tomorrow, price_adjustment):
  """Get the spot prices for the mpc."""
  prices = []

  for date, v in spot_forecast(attributes):
    v_a = v

    if start <= date < tomorrow:
      prices += [v_a + price_adjustment ]

    if len(prices) == lines_limit:
      break

  return prices


def to_quarter_hour(time):
  """Get the start of the quarter hour containing time, in UTC."""
  time = time.astimezone(timezone.utc)
  return time.replace(minute=time.minute - time.minute % 15, second=0, microsecond=0)


def to_nice_minutes(values, now):
  """Get LINES_LIMIT 15 minute values from a {time: value} forecast, starting at the quarter hour of now.

  Each value is held until the next time in the forecast. When the last value is older
  than MAX_FORECAST_AGE, e.g. the next day is missing, the list ends early.
  """
  forecast = sorted([(datetime.fromisoformat(k), v) for k, v in values.items()])

  # Step in UTC, adding minutes to the local time breaks on the DST change
  current = to_quarter_hour(now)

  pv_forecast = []
  index = 0
  # No production before the forecast starts
  value = 0
  value_time = None

  for _ in range(LINES_LIMIT):
    # Take the last forecast value at or before current
    while index < len(forecast) and forecast[index][0] <= current:
      value_time, value = forecast[index]
      index += 1

    # Don't keep the old value when the forecast is missing, let the optimization fail
    if value_time is not None and current - value_time > MAX_FORECAST_AGE:
      logger.warning(f"PV forecast is missing after {value_time}, returning only {len(pv_forecast)} values")
      break

    pv_forecast += [value]
    current = current + timedelta(minutes = 15)

  return pv_forecast


def soc_final(tomorrow_production):
  """Battery level to end the optimization with, fuller when tomorrow's production is low."""
  if float(tomorrow_production) < LOW_PRODUCTION_THRESHOLD:
    return SOC_FINAL_LOW_PRODUCTION
  return SOC_FINAL_NORMAL_PRODUCTION


def mpc_horizon_end(now):
  """The next dayahead optimization at DAYAHEAD_HOUR local time, the MPC optimizes until then."""
  # After the dayahead at 23:00 optimize until the next one
  if now.hour >= DAYAHEAD_HOUR:
    t = now + timedelta(days=1)
  else:
    t = now
  return datetime(year=t.year, month=t.month, day=t.day, hour=DAYAHEAD_HOUR, tzinfo=TIMEZONE)


def mpc_lines_limit(start, end):
  """Number of 15 minute steps between start and end.

  Start is in UTC so the DST change is counted in.
  """
  return int((end - start).total_seconds() // (15 * 60))


def dayahead_optimization(now, buy_attributes, sell_attributes, pv_watts, soc_init, tomorrow_production):
  """Build the dayahead optimization, skipped when the prices don't cover the whole day.

  buy_attributes, sell_attributes: {iso time: price} attributes of the spot price sensors
  pv_watts: function returning the {iso time: watts} forecast of today and tomorrow,
            only called when the optimization runs
  soc_init: battery level in percent
  tomorrow_production: forecasted production tomorrow in kWh

  EMHASS plans the dayahead always for the next LINES_LIMIT steps, it ignores
  prediction_horizon and rejects a shorter forecast. Run during the day, e.g. for
  testing, it works only after the prices of tomorrow are published in the afternoon.
  The pv forecast is read after the skip decision, like in mpc_optimization.
  """
  # Same first slot as the pv forecast
  start = to_quarter_hour(now)

  load_cost_forecast = get_spot_prices_day_ahead(start, buy_attributes, BUY_PRICE_ADJUSTMENT)
  prod_price_forecast = get_spot_prices_day_ahead(start, sell_attributes, SELL_PRICE_ADJUSTMENT)

  lines = min(len(load_cost_forecast), len(prod_price_forecast))
  if lines < LINES_LIMIT:
    return Optimization(DAYAHEAD, None, f"only {lines} lines of prices from {start.isoformat()}, "
                        f"the dayahead needs {LINES_LIMIT}, the prices of tomorrow are published in the afternoon")

  return Optimization(DAYAHEAD, {
    "pv_power_forecast" : to_nice_minutes(pv_watts(), now),
    "load_cost_forecast" : load_cost_forecast,
    "prod_price_forecast" : prod_price_forecast,
    "soc_init": float(soc_init) / 100,
    "soc_final": soc_final(tomorrow_production),
  })


def mpc_optimization(now, buy_attributes, sell_attributes, pv_watts, soc_init, tomorrow_production):
  """Build the MPC optimization, skipped when the horizon is too short.

  Takes the same inputs as dayahead_optimization. Every forecast is cut to the same
  prediction_horizon, EMHASS needs them exactly that long. The pv forecast is read
  after the skip decision, the forecast sensors may be unavailable late in the day.
  """
  start = to_quarter_hour(now)
  end = mpc_horizon_end(now)

  lines_limit = mpc_lines_limit(start, end)

  load_cost_forecast = get_spot_prices_mpc(buy_attributes, lines_limit, start, end, BUY_PRICE_ADJUSTMENT)
  prod_price_forecast = get_spot_prices_mpc(sell_attributes, lines_limit, start, end, SELL_PRICE_ADJUSTMENT)

  # EMHASS needs every forecast exactly prediction_horizon long, the prices may end sooner
  lines_limit = min(lines_limit, len(load_cost_forecast), len(prod_price_forecast))

  # Early return we do not perform optimizations as per the emhass docs if the ending of the day is close.
  if lines_limit < MIN_MPC_LINES:
    return Optimization(MPC, None, f"only {lines_limit} lines until {end.isoformat()}, less than {MIN_MPC_LINES}")

  return Optimization(MPC, {
    "pv_power_forecast" : to_nice_minutes(pv_watts(), now)[:lines_limit],
    "load_cost_forecast" : load_cost_forecast[:lines_limit],
    "prod_price_forecast" : prod_price_forecast[:lines_limit],
    "soc_init": float(soc_init) / 100,
    "soc_final": soc_final(tomorrow_production),
    "prediction_horizon": lines_limit
  })


# --8<-- [start:export]
def export_limit(spot_price, sell_threshold, restore_limit):
  """Decide the Solax export limit from the sell price.

  Returns (limit, allowed): the limit to set as a number and whether exporting is allowed.
  The export is allowed when the spot price is above the user threshold.
  """
  if float(spot_price) > float(sell_threshold):
    return float(restore_limit), True
  return 0, False
# --8<-- [end:export]


# An ok publish older than this means EMHASS stopped publishing, em.py publishes every 5 minutes
MAX_PUBLISH_AGE = timedelta(minutes = 15)
PUBLISH_OK = "ok"
PUBLISH_STALE = "stale"


def publish_status(now, last_publish):
  """Decide whether the last ok publish is recent enough.

  last_publish: the stored ISO timestamp of the last ok publish, as the raw state
  Returns (status, age_minutes): PUBLISH_OK when the publish is less than MAX_PUBLISH_AGE
  old, PUBLISH_STALE otherwise. age_minutes is None when there is no usable timestamp,
  e.g. never published yet, which counts as stale.
  """
  try:
    published = datetime.fromisoformat(str(last_publish))
  except ValueError:
    return PUBLISH_STALE, None

  # A timestamp without timezone can't be compared to now
  if published.tzinfo is None:
    return PUBLISH_STALE, None

  age = now - published
  age_minutes = round(age.total_seconds() / 60, 1)

  if age < MAX_PUBLISH_AGE:
    return PUBLISH_OK, age_minutes
  return PUBLISH_STALE, age_minutes
