"""Tests for the pure logic in config/pyscript/modules/em_functions.py.

Run with: python3 -m unittest discover -s tests
"""
import importlib.util
import signal
import unittest

from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone

EM_FUNCTIONS_PY = Path(__file__).resolve().parent.parent / "config" / "pyscript" / "modules" / "em_functions.py"

UTC = timezone.utc
PRAGUE = ZoneInfo("Europe/Prague")

# Fail instead of hanging when the function never returns
TIMEOUT_SECONDS = 2


def load_module(path):
  """Import the file as a plain Python module.

  Unlike em.py and em_inputs.py, em_functions.py uses nothing from pyscript or
  Home Assistant, a plain import is the check that it stays that way.
  """
  spec = importlib.util.spec_from_file_location(path.stem, path)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module

em = load_module(EM_FUNCTIONS_PY)

def _timeout(signum, frame):
  raise TimeoutError(f"to_nice_minutes did not return within {TIMEOUT_SECONDS}s (endless loop?)")

def run(values, now):
  """Single place that knows the call signature of to_nice_minutes."""
  # SIGALRM only exists on Unix, without it the test just hangs on an endless loop
  if not hasattr(signal, "SIGALRM"):
    return em.to_nice_minutes(values, now)
  previous = signal.signal(signal.SIGALRM, _timeout)
  signal.alarm(TIMEOUT_SECONDS)
  try:
    return em.to_nice_minutes(values, now)
  finally:
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)


def series(start, count, step):
  """Forecast dict {utc iso string: value}, the value being the index of the entry."""
  return {(start + i * step).isoformat(): i for i in range(count)}


def spot_attributes(start, count, step=timedelta(minutes=15)):
  """Spot price sensor attributes: the price forecast plus the attributes every sensor has."""
  return {"unit_of_measurement": "CZK/kWh", "icon": "mdi:cash", "friendly_name": "Spot"} | series(start, count, step)


class ToNiceMinutesTest(unittest.TestCase):

  def test_returns_next_96_quarter_hours_from_utc_dict(self):
    # 06:00Z .. two days later; 08:00Z is index 8 and equals 10:00 in Prague (CEST)
    values = series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200, timedelta(minutes=15))
    now = datetime(2026, 10, 22, 10, 0, tzinfo=PRAGUE)

    self.assertEqual(run(values, now), list(range(8, 8 + 96)))

  def test_unaligned_now_starts_with_the_quarter_hour_containing_now(self):
    values = series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200, timedelta(minutes=15))
    now = datetime(2026, 10, 22, 10, 7, tzinfo=PRAGUE)

    self.assertEqual(run(values, now), list(range(8, 8 + 96)))

  def test_hourly_values_are_held_for_each_quarter_hour(self):
    """Value at HH:00 applies to HH:00, HH:15, HH:30 and HH:45."""
    values = series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 30, timedelta(hours=1))
    now = datetime(2026, 10, 22, 10, 0, tzinfo=PRAGUE)

    expected = [hour for hour in range(2, 2 + 24) for _ in range(4)]
    self.assertEqual(run(values, now), expected)

  def test_quarter_hours_stay_15_real_minutes_apart_across_dst_change(self):
    # Prague falls back from CEST to CET on 2026-10-25 at 01:00Z
    values = series(datetime(2026, 10, 24, 12, 0, tzinfo=UTC), 200, timedelta(minutes=15))
    now = datetime(2026, 10, 24, 20, 0, tzinfo=PRAGUE)  # 18:00Z, index 24

    self.assertEqual(run(values, now), list(range(24, 24 + 96)))

  def test_stops_when_the_last_value_is_older_than_2_hours(self):
    # 06:00Z .. 10:45Z, e.g. the next day is missing
    values = series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 20, timedelta(minutes=15))
    now = datetime(2026, 10, 22, 10, 0, tzinfo=PRAGUE)  # 08:00Z, index 8

    # 10:45Z is held until 12:45Z, 13:00Z is more than 2 hours old
    self.assertEqual(run(values, now), list(range(8, 20)) + [19] * 8)

  def test_last_hourly_value_is_held_for_2_hours(self):
    # 06:00Z .. 11:00Z
    values = series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 6, timedelta(hours=1))
    now = datetime(2026, 10, 22, 10, 0, tzinfo=PRAGUE)  # 08:00Z, index 2

    # 11:00Z is held until 13:00Z
    expected = [hour for hour in range(2, 5) for _ in range(4)] + [5] * 9
    self.assertEqual(run(values, now), expected)

  def test_gap_of_2_hours_holds_the_last_value(self):
    values = series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200, timedelta(minutes=15))
    # 09:00Z .. 10:45Z missing
    for i in range(12, 20):
      del values[(datetime(2026, 10, 22, 6, 0, tzinfo=UTC) + i * timedelta(minutes=15)).isoformat()]
    now = datetime(2026, 10, 22, 10, 0, tzinfo=PRAGUE)  # 08:00Z, index 8

    expected = [11 if 12 <= i < 20 else i for i in range(8, 8 + 96)]
    self.assertEqual(run(values, now), expected)

  def test_stops_in_a_gap_longer_than_2_hours(self):
    values = series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200, timedelta(minutes=15))
    # 09:00Z .. 11:00Z missing
    for i in range(12, 21):
      del values[(datetime(2026, 10, 22, 6, 0, tzinfo=UTC) + i * timedelta(minutes=15)).isoformat()]
    now = datetime(2026, 10, 22, 10, 0, tzinfo=PRAGUE)  # 08:00Z, index 8

    self.assertEqual(run(values, now), list(range(8, 12)) + [11] * 8)

  def test_before_the_forecast_starts_is_0(self):
    values = series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200, timedelta(minutes=15))
    now = datetime(2026, 10, 22, 6, 0, tzinfo=PRAGUE)  # 04:00Z, 8 quarter hours early

    self.assertEqual(run(values, now), [0] * 8 + list(range(0, 88)))


class SpotPricesTest(unittest.TestCase):

  def test_day_ahead_skips_the_past_and_adds_the_adjustment(self):
    attributes = spot_attributes(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200)
    start = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)  # index 8

    self.assertEqual(em.get_spot_prices_day_ahead(start, attributes, 3), [i + 3 for i in range(8, 8 + 96)])

  def test_day_ahead_returns_what_is_there_when_the_forecast_is_short(self):
    attributes = spot_attributes(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 20)
    start = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)

    self.assertEqual(em.get_spot_prices_day_ahead(start, attributes, 0), list(range(8, 20)))

  def test_mpc_takes_the_prices_between_start_and_end(self):
    attributes = spot_attributes(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200)
    start = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)  # index 8
    end = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)  # index 16, excluded

    self.assertEqual(em.get_spot_prices_mpc(attributes, 96, start, end, -0.5), [i - 0.5 for i in range(8, 16)])

  def test_mpc_stops_at_lines_limit(self):
    attributes = spot_attributes(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200)
    start = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)
    end = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)

    self.assertEqual(em.get_spot_prices_mpc(attributes, 4, start, end, 0), [8, 9, 10, 11])

  def test_attributes_that_are_not_a_time_are_skipped(self):
    extra = {"state_class": "measurement", "device_class": "monetary", "attribution": "OTE"}
    attributes = extra | spot_attributes(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200)
    start = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)
    end = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)

    self.assertEqual(em.get_spot_prices_mpc(attributes, 96, start, end, 0), list(range(8, 16)))
    self.assertEqual(em.get_spot_prices_day_ahead(start, attributes, 0), list(range(8, 8 + 96)))


class SocFinalTest(unittest.TestCase):

  def test_low_production_tomorrow_keeps_the_battery_fuller(self):
    self.assertEqual(em.soc_final("19.9"), 0.7)

  def test_normal_production_tomorrow(self):
    self.assertEqual(em.soc_final("20"), 0.5)
    self.assertEqual(em.soc_final(35.2), 0.5)


class MpcHorizonTest(unittest.TestCase):

  def test_before_23_ends_today_at_23(self):
    now = datetime(2026, 10, 22, 10, 30, tzinfo=PRAGUE)

    self.assertEqual(em.mpc_horizon_end(now), datetime(2026, 10, 22, 23, 0, tzinfo=PRAGUE))

  def test_at_or_after_23_ends_tomorrow_at_23(self):
    now = datetime(2026, 10, 22, 23, 30, tzinfo=PRAGUE)

    self.assertEqual(em.mpc_horizon_end(now), datetime(2026, 10, 23, 23, 0, tzinfo=PRAGUE))

  def test_lines_limit_counts_15_minute_steps(self):
    now = datetime(2026, 10, 22, 10, 30, tzinfo=PRAGUE)
    start = em.to_quarter_hour(now)

    self.assertEqual(em.mpc_lines_limit(start, em.mpc_horizon_end(now)), 50)

  def test_lines_limit_counts_the_extra_hour_of_the_dst_change(self):
    # Prague falls back on 2026-10-25, the local day has 25 hours
    now = datetime(2026, 10, 24, 23, 30, tzinfo=PRAGUE)
    start = em.to_quarter_hour(now)

    self.assertEqual(em.mpc_lines_limit(start, em.mpc_horizon_end(now)), 24 * 4 + 4 - 2)


class PayloadTest(unittest.TestCase):

  def setUp(self):
    self.now = datetime(2026, 10, 22, 10, 7, tzinfo=PRAGUE)  # 08:07Z
    self.buy = spot_attributes(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200)
    self.sell = {k: (v * 10 if not isinstance(v, str) else v) for k, v in self.buy.items()}
    # the pv forecast is passed as a reader, like em_inputs.pv_watts
    self.watts = lambda: series(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 200, timedelta(minutes=15))

  def test_dayahead_optimization(self):
    optimization = em.dayahead_optimization(self.now, self.buy, self.sell, self.watts, "55", "19")

    self.assertEqual(optimization.action, em.DAYAHEAD)
    self.assertIsNone(optimization.skipped)
    self.assertEqual(optimization.payload, {
      "pv_power_forecast": list(range(8, 8 + 96)),
      "load_cost_forecast": [i + 3 for i in range(8, 8 + 96)],
      "prod_price_forecast": [i * 10 - 0.5 for i in range(8, 8 + 96)],
      "soc_init": 0.55,
      "soc_final": 0.7,
    })

  def test_dayahead_is_skipped_before_the_prices_of_tomorrow_are_published(self):
    """EMHASS ignores prediction_horizon in the dayahead, a shorter forecast fails there."""
    def unavailable():
      raise KeyError("watts")
    # The prices end at 22:00Z (midnight in Prague), 08:00Z .. 22:00Z is 56 lines
    buy = spot_attributes(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 64)

    optimization = em.dayahead_optimization(self.now, buy, self.sell, unavailable, "55", "25")

    self.assertEqual(optimization.action, em.DAYAHEAD)
    self.assertIsNone(optimization.payload)
    self.assertIn("only 56 lines", optimization.skipped)

  def test_dayahead_is_skipped_when_the_prices_are_missing(self):
    def unavailable():
      raise KeyError("watts")

    optimization = em.dayahead_optimization(self.now, spot_attributes(self.now, 0), self.sell, unavailable, "55", "25")

    self.assertEqual(optimization.action, em.DAYAHEAD)
    self.assertIsNone(optimization.payload)
    self.assertIn("only 0 lines", optimization.skipped)

  def test_mpc_optimization_cuts_every_forecast_to_the_horizon(self):
    # 08:00Z .. 21:00Z (23:00 Prague) is 52 lines
    optimization = em.mpc_optimization(self.now, self.buy, self.sell, self.watts, "55", "25")

    self.assertEqual(optimization.action, em.MPC)
    self.assertIsNone(optimization.skipped)
    self.assertEqual(optimization.payload, {
      "pv_power_forecast": list(range(8, 8 + 52)),
      "load_cost_forecast": [i + 3 for i in range(8, 8 + 52)],
      "prod_price_forecast": [i * 10 - 0.5 for i in range(8, 8 + 52)],
      "soc_init": 0.55,
      "soc_final": 0.5,
      "prediction_horizon": 52,
    })

  def test_mpc_optimization_shrinks_the_horizon_when_the_prices_end_sooner(self):
    buy = spot_attributes(datetime(2026, 10, 22, 6, 0, tzinfo=UTC), 20)  # until 10:45Z, 12 lines
    payload = em.mpc_optimization(self.now, buy, self.sell, self.watts, "55", "25").payload

    self.assertEqual(payload["prediction_horizon"], 12)
    for key in ("pv_power_forecast", "load_cost_forecast", "prod_price_forecast"):
      self.assertEqual(len(payload[key]), 12, key)

  def test_mpc_optimization_is_skipped_close_to_the_dayahead(self):
    now = datetime(2026, 10, 22, 22, 0, tzinfo=PRAGUE)  # 4 lines until 23:00

    optimization = em.mpc_optimization(now, self.buy, self.sell, self.watts, "55", "25")

    self.assertEqual(optimization.action, em.MPC)
    self.assertIsNone(optimization.payload)
    self.assertIn("only 4 lines", optimization.skipped)

  def test_mpc_optimization_does_not_read_the_pv_forecast_when_skipped(self):
    """Late in the day the forecast sensors may be unavailable, the skip must not touch them."""
    def unavailable():
      raise KeyError("watts")
    now = datetime(2026, 10, 22, 22, 30, tzinfo=PRAGUE)

    self.assertIn("only 2 lines", em.mpc_optimization(now, self.buy, self.sell, unavailable, "55", "25").skipped)

  def test_mpc_optimization_is_skipped_when_the_prices_are_missing(self):
    optimization = em.mpc_optimization(self.now, spot_attributes(self.now, 0), self.sell, self.watts, "55", "25")

    self.assertIsNone(optimization.payload)
    self.assertIn("only 0 lines", optimization.skipped)

  def test_optimization_repr_shows_action_payload_and_reason(self):
    """em.py logs the repr, it has to be readable (special methods don't work in pyscript classes)."""
    optimization = em.Optimization(em.MPC, {"soc_init": 0.5})

    self.assertEqual(repr(optimization), "Optimization(action='naive-mpc-optim', payload={'soc_init': 0.5}, skipped=None)")


class ExportLimitTest(unittest.TestCase):

  def test_price_above_the_threshold_allows_export_with_the_restore_limit(self):
    self.assertEqual(em.export_limit("2.5", "2.0", "6000.0"), (6000.0, True))

  def test_limit_is_a_number_so_it_compares_equal_to_the_current_limit(self):
    """Otherwise the limit is written to the Solax EEPROM on every price change."""
    limit, _ = em.export_limit("2.5", "2.0", "6000.0")

    self.assertEqual(limit, 6000)

  def test_price_at_or_below_the_threshold_disables_export(self):
    self.assertEqual(em.export_limit("2.0", "2.0", "6000.0"), (0, False))
    self.assertEqual(em.export_limit("-1", "2.0", "6000.0"), (0, False))



class PublishStatusTest(unittest.TestCase):

  def setUp(self):
    self.now = datetime(2026, 10, 28, 10, 2, tzinfo=PRAGUE)

  def status(self, last_publish):
    return em.publish_status(self.now, last_publish)

  def test_recent_publish_is_ok(self):
    self.assertEqual(self.status((self.now - timedelta(minutes=2)).isoformat()), (em.PUBLISH_OK, 2.0))

  def test_just_under_15_minutes_is_ok(self):
    self.assertEqual(self.status((self.now - timedelta(minutes=14, seconds=59)).isoformat())[0], em.PUBLISH_OK)

  def test_15_minutes_is_stale(self):
    self.assertEqual(self.status((self.now - timedelta(minutes=15)).isoformat()), (em.PUBLISH_STALE, 15.0))

  def test_older_is_stale(self):
    self.assertEqual(self.status((self.now - timedelta(hours=3)).isoformat()), (em.PUBLISH_STALE, 180.0))

  def test_utc_timestamp_compares_with_prague_now(self):
    published = (self.now - timedelta(minutes=5)).astimezone(UTC).isoformat()

    self.assertEqual(self.status(published), (em.PUBLISH_OK, 5.0))

  def test_never_published_is_stale(self):
    for value in ("unknown", "unavailable", "", None, "not a time"):
      self.assertEqual(self.status(value), (em.PUBLISH_STALE, None), value)

  def test_timestamp_without_timezone_is_stale(self):
    self.assertEqual(self.status("2026-10-28T10:00:00"), (em.PUBLISH_STALE, None))


if __name__ == "__main__":
  unittest.main()
