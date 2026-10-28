"""Triggers of the EMHASS optimizations, the publish watchdog and the Solax export limit.

The pyscript decorators and the calls to EMHASS live here. The values are read
in em_inputs.py, the logic is in em_functions.py, both in the modules folder.
"""
import aiohttp
import em_functions
import em_inputs
import logging

logger = logging.getLogger("spot_eval.pyscript")

EMHASS_URL = "http://localhost:5000"


async def call_emhass(action, json):
  """Post to emhass endpoint with json."""

  async with aiohttp.ClientSession() as session:
    async with session.post(
      f"{EMHASS_URL}/action/{action}",
      json=json, headers={"Content-Type": "application/json"}
    ) as response:
      # EMHASS answers with plain text, not json
      text = await response.text()
      if response.status >= 400:
        raise aiohttp.ClientResponseError(
          request_info=response.request_info,
          history=response.history,
          status=response.status,
          message=text
        )
      return text


async def publish():
  """Publish the last optimization to Home Assistant, store the time of an ok publish.

  Ok means EMHASS answered without an error status. Explicit repr(), pyscript
  ignores the !r conversion in f-strings.
  """
  try:
    result = await call_emhass(em_functions.PUBLISH, {})
  except Exception as e:
    logger.error(f"{em_functions.PUBLISH} failed {repr(e)}")
    return

  # debug, this runs every 5 minutes
  logger.debug(f"{em_functions.PUBLISH} result {repr(result)}")
  em_inputs.set_last_publish(em_inputs.now())


async def run_optimization(optimization):
  """Post the optimization to EMHASS and publish the result.

  The EMHASS answer is written to the log as a repr.
  """
  if optimization.skipped:
    logger.info(f"Skipping {optimization.action}: {optimization.skipped}")
    return

  try:
    result = await call_emhass(optimization.action, optimization.payload)
  except Exception as e:
    logger.error(f"{optimization.action} failed {repr(e)}")
    return

  logger.info(f"{optimization.action} result {repr(result)}")
  await publish()

  logger.info(f"Finished the {optimization.action}")


@time_trigger("cron(00 23 * * *)")
async def dayahead():
  """Perform Dayahead optimization."""
  optimization = em_functions.dayahead_optimization(
    em_inputs.now(),
    em_inputs.buy_price_attributes(),
    em_inputs.sell_price_attributes(),
    em_inputs.pv_watts,  # the reader itself, called only when the optimization runs
    em_inputs.battery_soc(),
    em_inputs.tomorrow_production(),
  )
  # The result of the function code, to find issues with it later
  logger.info(f"Optimization {repr(optimization)}")
  await run_optimization(optimization)


@time_trigger("cron(30 * * * *)")
async def mpc():
  """This is the optimization happening mid day"""
  optimization = em_functions.mpc_optimization(
    em_inputs.now(),
    em_inputs.buy_price_attributes(),
    em_inputs.sell_price_attributes(),
    em_inputs.pv_watts,  # the reader itself, called only when the optimization runs
    em_inputs.battery_soc(),
    em_inputs.tomorrow_production(),
  )
  # The result of the function code, to find issues with it later
  logger.info(f"Optimization {repr(optimization)}")
  await run_optimization(optimization)


@time_trigger("startup", "cron(*/5 * * * *)")
async def publish_every_5_minutes():
  """Keep the EMHASS sensors in Home Assistant current, the watchdog checks it."""
  await publish()


# --8<-- [start:watchdog]
# 2 minutes after the publish, so the check sees the publish of the same 5 minutes
@time_trigger("cron(2-59/5 * * * *)")
async def publish_watchdog():
  """Check that the last ok publish is less than 15 minutes old."""
  last_publish = em_inputs.last_publish()
  status, age_minutes = em_functions.publish_status(em_inputs.now(), last_publish)

  previous = em_inputs.publish_watchdog_status()
  em_inputs.set_publish_watchdog(status, age_minutes, last_publish)

  # Log only the change, not every 5 minutes
  if status == previous:
    return
  if status == em_functions.PUBLISH_STALE:
    if age_minutes is None:
      logger.warning("EMHASS publish is stale, there was no ok publish yet")
    else:
      logger.warning(f"EMHASS publish is stale, last ok publish {last_publish}, {age_minutes} minutes ago")
  elif previous == em_functions.PUBLISH_STALE:
    logger.info(f"EMHASS publish is ok again, last ok publish {last_publish}")
# --8<-- [end:watchdog]


# --8<-- [start:export]
@state_trigger("True", watch=[em_inputs.SENSOR_SELL_PRICE])
def enable_disable_solax_grid_export():
  """Enable or disable the export based on your sell price"""

  previous_limit = em_inputs.export_limit()
  spot_price = em_inputs.spot_sell_price()

  logger.debug(f"Previous value {previous_limit} - {float(spot_price)} ")

  out, allowed = em_functions.export_limit(
    spot_price,
    em_inputs.sell_threshold(),
    em_inputs.restore_export_limit(),
  )
  em_inputs.set_export_allowed(allowed)

  # to avoid storing to EEPROM on each evaluation
  if previous_limit != out:
    logger.debug(f"Changing solax export limit from {previous_limit} to {out}")
    em_inputs.set_export_limit(out)
  else:
    logger.debug(f"No change to solax export limit {previous_limit} - {out}")
# --8<-- [end:export]
