import logging

logger = logging.getLogger("spot_eval.pyscript")

## Do not change unless you know what you are doing
SELL_TO_GRID = "Sell to grid"
CHARGE = "Charge"
DISCHARGE = "Discharge"
NO_ACTION = "No action"


# Change to the forecast sensors from emhass.
SENSOR_PV_FORECAST = "sensor.p_pv_forecast"
SENSOR_P_LOAD_FORECAST = "sensor.p_load_forecast"
SENSOR_P_BATT_FORECAST = "sensor.p_batt_forecast"
SENSOR_P_GRID_FORECAST = "sensor.p_grid_forecast"


# Change to the solax battery
SENSOR_BATTERY_CAPACITY = "sensor.solax_battery_capacity"

# INPUT_SELECTOR used to save the strategy
INPUT_INVERTOR_STRATEGY = "input_select.invertor_strategy"


@state_trigger("1 == 1",
               watch=[SENSOR_PV_FORECAST, SENSOR_P_LOAD_FORECAST, SENSOR_P_BATT_FORECAST, SENSOR_P_GRID_FORECAST])
def select_strategy():
    p_pv = float(hass.states.get(SENSOR_PV_FORECAST).state)
    p_load = float(hass.states.get(SENSOR_P_LOAD_FORECAST).state)
    p_grid = float(hass.states.get(SENSOR_P_GRID_FORECAST).state)
    p_batt = float(hass.states.get(SENSOR_P_BATT_FORECAST).state)

    soc = float(hass.states.get(SENSOR_BATTERY_CAPACITY).state)

    strategy = select(p_pv, p_load, p_grid, p_batt, soc)

    service.call("input_select", "select_option", entity_id=INPUT_INVERTOR_STRATEGY, option=strategy)

    logger.debug("Strategy chosen")


# b_batt -> negative is charging, positive is discharge
# feel free to modify the strategy selection
def select(p_pv: int, p_load: int, p_grid: int, p_batt: int, soc: float) -> str:
    # check for charging

    if (p_batt < 0 and p_grid > 0) and (- p_batt > (0.5 * p_grid)):
        return CHARGE

    if (p_batt > 0 and p_grid < 0) and (p_batt > (0.5 * - p_grid)):
        return DISCHARGE

    if p_batt < 500 and p_grid < 0 and soc < 85:
        return SELL_TO_GRID

    return NO_ACTION
